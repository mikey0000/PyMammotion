"""DeviceHandle — per-device facade unifying transport, broker, queue, and state."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import dataclasses
import logging
import time
from typing import TYPE_CHECKING, Any, TypeVar, cast

from mashumaro.exceptions import InvalidFieldValue, MissingField

from pymammotion.aliyun.exceptions import DeviceOfflineException, DeviceUnboundException, TooManyRequestsException
from pymammotion.data.model.device import MowerDevice
from pymammotion.data.mqtt.event import DeviceProtobufMsgEventParams
from pymammotion.data.mqtt.status import StatusType
from pymammotion.device.ble_loop import ble_activity_loop, ble_polling_loop
from pymammotion.device.dynamics_line_loop import dynamics_line_loop
from pymammotion.device.modes import _DeviceMode
from pymammotion.device.mqtt_loop import mqtt_activity_loop, poll_interval
from pymammotion.device.state_reducer import StateReducer, get_state_reducer
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_queue import DeviceCommandQueue, Priority
from pymammotion.proto import LubaMsg, MsgDevice, RptAct, RptInfoType
from pymammotion.state.device_state import (
    DeviceAvailability,
    DeviceConnectionState,
    DeviceShutdownEvent,
    DeviceSnapshot,
    DeviceStateMachine,
)
from pymammotion.transport.base import (
    BLEUnavailableError,
    CommandTimeoutError,
    ConcurrentRequestError,
    EventBus,
    NoTransportAvailableError,
    Subscription,
    Transport,
    TransportAvailability,
    TransportError,
    TransportRateLimitedError,
    TransportType,
)
from pymammotion.transport.ble import BLETransport
from pymammotion.utility.constant import MOWING_ACTIVE_MODES, NO_REQUEST_MODES
from pymammotion.utility.device_type import DeviceType

_T = TypeVar("_T")

#: How long an MQTT-side ``todev_ble_sync(3)`` keeps the device "synced".  The device
#: drops out of its synced state (and stops responding to commands / serving report+map
#: frames) roughly ``~10 s`` after the *last sync* — the same window the BLE heartbeat
#: stays under (see ``ble_loop._KEEP_ALIVE_BLE_INTERVAL``).  Crucially the device's timer
#: is reset only by a sync, NOT by ordinary command traffic, so we re-sync whenever it's
#: been longer than this since the last sync we sent — not since the last command.  7 s
#: leaves ~3 s of margin for cloud round-trip jitter while keeping sync volume low
#: (heartbeats are quota-free; see ``Transport.send_heartbeat``).
_MQTT_SYNC_INTERVAL: float = 7.0

#: Channels sent in one-shot (count=1) polls AND in the BLE continuous stream.
_REPORT_CHANNELS: list[RptInfoType] = [
    RptInfoType.RIT_DEV_STA,
    RptInfoType.RIT_DEV_LOCAL,
    RptInfoType.RIT_WORK,
    RptInfoType.RIT_MAINTAIN,
    RptInfoType.RIT_BASESTATION_INFO,
    RptInfoType.RIT_VIO,
    RptInfoType.RIT_CONNECT,
]

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.data.model.device import Device, MowingDevice
    from pymammotion.data.mqtt.event import ThingEventMessage
    from pymammotion.data.mqtt.properties import MammotionPropertiesMessage, ThingPropertiesMessage
    from pymammotion.data.mqtt.status import ThingStatusMessage
    from pymammotion.device.readiness import ReadinessChecker, ReadinessStatus
    from pymammotion.messaging.saga import Saga

_logger = logging.getLogger(__name__)


class _DebouncedBus:
    """Wraps EventBus[DeviceSnapshot] with optional debounce.

    When debounce_interval > 0, rapid consecutive events are coalesced:
    only the most recent snapshot is emitted after debounce_interval seconds
    of silence, OR after max_debounce_wait seconds from the first suppressed
    event (whichever comes first).

    When debounce_interval == 0 (default), events are emitted immediately.
    """

    def __init__(
        self,
        debounce_interval: float = 0.0,
        max_debounce_wait: float = 2.0,
    ) -> None:
        """Initialise the debounced bus with optional debounce parameters."""
        self._bus: EventBus[DeviceSnapshot] = EventBus()
        self._debounce_interval = debounce_interval
        self._max_debounce_wait = max_debounce_wait
        self._pending_snapshot: DeviceSnapshot | None = None
        self._debounce_task: asyncio.Task[None] | None = None
        self._first_suppressed_at: float = 0.0

    def subscribe(self, handler: Callable[[DeviceSnapshot], Awaitable[None]]) -> Subscription:
        """Register a handler and return a Subscription for later cancellation."""
        return self._bus.subscribe(handler)

    async def emit(self, snapshot: DeviceSnapshot) -> None:
        """Emit a snapshot, coalescing if debounce_interval > 0."""
        if self._debounce_interval <= 0.0:
            await self._bus.emit(snapshot)
            return

        now = time.monotonic()

        # If this is the start of a new burst, record the time
        if self._pending_snapshot is None:
            self._first_suppressed_at = now

        self._pending_snapshot = snapshot

        # Cancel any existing debounce task
        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()

        # Calculate effective sleep duration
        elapsed = now - self._first_suppressed_at
        remaining_max = self._max_debounce_wait - elapsed
        if remaining_max <= 0:
            # max_debounce_wait exceeded — emit immediately
            to_emit = self._pending_snapshot
            self._pending_snapshot = None
            self._debounce_task = None
            await self._bus.emit(to_emit)
            return

        sleep_duration = min(self._debounce_interval, remaining_max)
        self._debounce_task = asyncio.create_task(self._debounce_emit(sleep_duration))

    async def _debounce_emit(self, delay: float) -> None:
        """Wait for delay seconds then emit the latest pending snapshot."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        snapshot = self._pending_snapshot
        self._pending_snapshot = None
        self._debounce_task = None
        if snapshot is not None:
            await self._bus.emit(snapshot)

    async def stop(self) -> None:
        """Cancel any pending debounce task without emitting."""
        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._debounce_task
        self._debounce_task = None
        self._pending_snapshot = None


class DeviceHandle:
    """Per-device facade unifying transport, broker, queue, and state.

    Use send_command() for normal operations.
    Use enqueue_saga() for map/plan fetches.
    Subscribe to state_changed to receive DeviceSnapshot updates.
    """

    #: Seconds since the last inbound protobuf after which an online thing/status
    #: event triggers an immediate get_report_cfg to refresh device state.
    _REPORT_STALE_THRESHOLD: float = 60.0

    def __init__(
        self,
        device_id: str,
        device_name: str,
        initial_device: Device,
        *,
        iot_id: str = "",
        user_account: int = 0,
        mqtt_transport: Transport | None = None,
        ble_transport: Transport | None = None,
        prefer_ble: bool = False,
        debounce_interval: float = 0.0,
        max_debounce_wait: float = 2.0,
        readiness_checker: ReadinessChecker | None = None,
    ) -> None:
        """Initialise the device handle with optional initial transports."""
        self.device_id = device_id
        self.device_name = device_name
        self.iot_id = iot_id
        self.user_account = user_account
        self.broker = DeviceMessageBroker()
        self.queue = DeviceCommandQueue(device_name)
        self.state_machine = DeviceStateMachine(device_id, initial_device)
        self._availability = DeviceAvailability()
        self._transports: dict[TransportType, Transport] = {}
        self._state_changed_bus: _DebouncedBus = _DebouncedBus(debounce_interval, max_debounce_wait)
        self._status_bus: EventBus[ThingStatusMessage] = EventBus()
        self._properties_bus: EventBus[ThingPropertiesMessage] = EventBus()
        self._event_bus: EventBus[ThingEventMessage] = EventBus()
        #: Emits the raw command bytes of every outbound payload (excludes heartbeats).
        #: Subscribers can decode to LubaMsg for tracing/debug purposes.
        self._sent_bus: EventBus[bytes] = EventBus()
        self._prefer_ble: bool = prefer_ble
        self._mow_path_fetch_enabled: bool = True
        # Pick a reducer matching the device kind. PoolCleanerDevice instances
        # get a PoolStateReducer (currently a stub); everything else gets the
        # full mower reducer. Decided once at construction so the per-message
        # hot path doesn't pay an isinstance check.  The saga-active callable
        # lets the reducer skip eager geojson regen during map fetches.
        self._reducer: StateReducer = get_state_reducer(device_name, is_saga_active=lambda: self.queue.is_saga_active)
        self._error_bus: EventBus[Exception] = EventBus()
        self._map_updated_bus: EventBus[None] = EventBus()
        self._shutdown_bus: EventBus[DeviceShutdownEvent] = EventBus()
        self._readiness_checker: ReadinessChecker | None = readiness_checker
        self._stopping: bool = False
        self._keep_alive_task: asyncio.Task[None] | None = None
        #: monotonic timestamp of the last user-initiated command (updated via
        #: ``record_user_command``; heartbeats and internal sends do NOT update
        #: this).  Used to wake the poll loop early via ``_rearm_event``.
        self._last_user_command_monotonic: float = time.monotonic()
        #: Monotonic timestamp of the last ``todev_ble_sync(3)`` we sent per MQTT
        #: transport.  Read by ``_send_marked`` to keep the device synced on a fixed
        #: cadence (``_MQTT_SYNC_INTERVAL``) independent of command traffic — see the
        #: constant's docstring for why the gate is against the last *sync*, not send.
        self._last_mqtt_sync_monotonic: dict[TransportType, float] = {}
        #: Set by ``record_user_command`` to interrupt a long sleep and re-arm
        #: the activity loop immediately with the short window.
        self._rearm_event: asyncio.Event = asyncio.Event()
        #: True when the device name identifies an RTK base station.
        self._is_rtk: bool = DeviceType.is_rtk(device_name)
        #: True for Spino pool cleaners (PoolCleanerDevice).
        self._is_swimming_pool: bool = DeviceType.is_swimming_pool(device_name)
        #: RTK base stations and Spino pool cleaners don't run the mower-style
        #: MQTT activity loop or the BLE keep-alive/polling loops — they neither
        #: speak the report-cfg/``send_todev_ble_sync`` protocol nor derive a
        #: mower work-mode for cadence.  Their state is driven by their own
        #: coordinators and unsolicited pushes instead.
        self._skips_activity_loops: bool = self._is_rtk or self._is_swimming_pool
        #: Consecutive BLE heartbeat failures in _ble_activity_loop.  Reset on
        #: successful BLE connection.  Once it reaches _BLE_HEARTBEAT_FAIL_LIMIT
        #: the BLE loop exits and BLE is marked disconnected.
        self._ble_heartbeat_failures: int = 0
        #: Task running the BLE-specific 20 s heartbeat loop (separate from MQTT loop).
        self._ble_keep_alive_task: asyncio.Task[None] | None = None
        #: Task running the BLE polling/streaming loop (renews continuous stream while
        #: mowing, falls back to count=1 polls when docked).
        self._ble_polling_task: asyncio.Task[None] | None = None
        #: Task running the dynamics-line poll loop — sends NavGetCommData(action=8,
        #: type=18) every 10 s while the device is in ACTIVE mode, for device types
        #: where DeviceType.is_support_dynamics_line() is true.  Mirrors APK
        #: HashDataManager.handlerType_getDynamicsLine.
        self._dynamics_line_task: asyncio.Task[None] | None = None
        #: Background BLE-connect task and its single-flight lock.  ``send_raw`` / ``_do_send``
        #: kick a background reconnect when BLE is preferred-but-disconnected; the lock keeps
        #: only one connect running at a time (bursts of sends must not spawn concurrent
        #: ``ble.connect()`` calls that churn proxy slots) and the stored task lets ``stop()``
        #: cancel it and prevents the detached task from being garbage-collected mid-connect.
        self._ble_connect_task: asyncio.Task[None] | None = None
        self._ble_connect_lock: asyncio.Lock = asyncio.Lock()
        #: True while the BLE continuous (count=0) report stream is active.  The MQTT
        #: activity loop checks this and skips its own poll while the stream is feeding.
        self._ble_stream_active: bool = False
        #: Monotonic timestamp of the last successfully-parsed inbound LubaMsg.
        #: Used by ensure_fresh_state to decide whether a snapshot poll is needed.
        self._last_report_at: float = 0.0
        #: Snapshot of the previous active_transport selection / availability so
        #: the DEBUG log can suppress repeats — only the transitions matter.
        #: Tuple of (selection_path, prefer_ble, ble_usable, mqtt_usable).
        self._last_active_transport_log: tuple[str, bool, bool, bool] | None = None
        #: Timer handle for the transient continuous-stream auto-stop.
        self._report_stream_timer: asyncio.TimerHandle | None = None
        #: Client-wired hook invoked once when the cloud reports this device unbound
        #: (Aliyun 29004).  The client re-discovers the device and either migrates it
        #: to Mammotion MQTT or removes it entirely.  Guarded by ``_unbound_migrating``
        #: so repeated 29004s don't launch concurrent migrations.
        self.on_device_unbound: Callable[[DeviceHandle], Awaitable[None]] | None = None
        self._unbound_migrating: bool = False
        # Wire up critical error propagation from queue
        self.queue.on_critical_error = self._on_critical_error

        # Saga hooks: poll items use skip_if_saga_active=True; no explicit stop needed.
        async def _on_saga_start() -> None:
            pass  # poll items use skip_if_saga_active=True; no explicit stop needed

        async def _on_saga_end() -> None:
            self._rearm_event.set()  # wake poll loop to re-evaluate after saga

        self.queue.on_saga_start = _on_saga_start
        self.queue.on_saga_end = _on_saga_end

        if mqtt_transport is not None:
            self._wire_transport(mqtt_transport)

        if ble_transport is not None:
            self._wire_transport(ble_transport)

    @property
    def commands(self) -> MammotionCommand:
        """Return a MammotionCommand builder for this device."""
        return MammotionCommand(self.device_name, self.user_account)

    def _wire_transport(self, transport: Transport) -> None:
        """Wire callbacks on a transport and register it."""
        transport.on_message = self._make_message_handler(transport.transport_type)
        transport.add_availability_listener(self._make_availability_handler(transport.transport_type))
        self._transports[transport.transport_type] = transport

    def _make_message_handler(self, transport_type: TransportType) -> Callable[[bytes], Awaitable[None]]:
        """Create a per-transport message callback that carries the transport type."""

        async def _handler(payload: bytes) -> None:
            await self.on_raw_message(payload, transport_type)

        return _handler

    def _make_availability_handler(
        self, transport_type: TransportType
    ) -> Callable[[TransportAvailability], Awaitable[None]]:
        """Create a per-transport availability callback."""

        async def _handler(state: TransportAvailability) -> None:
            # Don't pass mqtt_reported_offline — the default (None) preserves the existing
            # flag.  Listener fires on every transport flap; we must not infer the offline
            # state from the flap itself, only from cloud "offline" reports / inbound frames.
            self.update_availability(transport_type, state)
            if transport_type == TransportType.BLE:
                if state == TransportAvailability.CONNECTED:
                    # BLE arriving while MQTT is reconnecting provides a fallback send path —
                    # open the queue gate so commands can flow immediately over BLE.
                    self.queue.resume_after_reconnect()
                    asyncio.get_running_loop().create_task(self._on_ble_connected())
                else:
                    # Wake the MQTT loop immediately so it resumes heartbeating
                    # rather than sleeping out the rest of its 180 s idle period.
                    self._rearm_event.set()
                    if state == TransportAvailability.DISCONNECTED:
                        # Cancel the BLE heartbeat loop so it stops retrying
                        # against a dead connection instead of exhausting all
                        # 30 attempts.  task.cancel() schedules CancelledError
                        # at the next await inside the task (asyncio.sleep) —
                        # safe to call from within the task itself.
                        ka_task = self._ble_keep_alive_task
                        if ka_task is not None and not ka_task.done():
                            ka_task.cancel()
                        # Cancel the BLE polling loop so the MQTT loop can resume
                        # without waiting up to _BLE_MODE_RECHECK_INTERVAL for
                        # the loop to detect the disconnect on its own.
                        task = self._ble_polling_task
                        if task is not None and not task.done():
                            task.cancel()
                        # Dynamics-line polling is BLE-only — cancel here so it
                        # restarts cleanly on the next _on_ble_connected.
                        dl_task = self._dynamics_line_task
                        if dl_task is not None and not dl_task.done():
                            dl_task.cancel()
                        self._ble_stream_active = False
            elif state == TransportAvailability.CONNECTING:
                # MQTT subscription is not yet active — commands sent now would time
                # out waiting for a response.  Gate the queue unless BLE is connected
                # and can serve as the send path instead.
                ble = self._transports.get(TransportType.BLE)
                if ble is None or not ble.is_connected:
                    _logger.debug(
                        "DeviceHandle[%s]: MQTT transport reconnecting — pausing command dispatch",
                        self.device_name,
                    )
                    self.queue.pause_for_reconnect()
            else:
                # CONNECTED or DISCONNECTED — open the gate.
                # CONNECTED: subscription is live, commands can be dispatched normally.
                # DISCONNECTED: don't hold commands indefinitely; let NoTransportAvailableError
                # handle them if no other transport is available.
                _logger.debug(
                    "DeviceHandle[%s]: MQTT transport connected — resuming command dispatch",
                    self.device_name,
                )
                self.queue.resume_after_reconnect()

        return _handler

    async def _on_ble_connected(self) -> None:
        """Called when the BLE transport transitions to CONNECTED.

        Resets BLE failure counters, fires a one-shot ``get_report_cfg(count=1)``
        for an immediate state refresh, and starts both the BLE keep-alive
        heartbeat loop and the BLE polling/streaming loop.  The MQTT loop is
        nudged via ``_rearm_event`` so it can re-evaluate the new transport
        topology immediately.

        No-op for RTK base stations and Spino pool cleaners — they run no BLE
        loops and don't speak the report-cfg protocol.
        """
        if self._skips_activity_loops:
            return
        _logger.debug("_on_ble_connected [%s]: starting BLE loops and requesting report", self.device_name)
        self._ble_heartbeat_failures = 0
        self._rearm_event.set()  # wake MQTT loop early so it sees BLE is now connected
        self._start_ble_loop()
        self._start_ble_polling_loop()
        self._start_dynamics_line_loop()
        cmd = self.commands.get_report_cfg()

        async def _send_report_cfg() -> None:
            try:
                await self.send_raw(cmd, prefer_ble=True)
            except Exception:
                _logger.debug("_on_ble_connected [%s]: report_cfg request failed", self.device_name, exc_info=True)

        await self.queue.enqueue(_send_report_cfg, priority=Priority.BACKGROUND, skip_if_saga_active=True)

    async def _send_marked(self, transport: Transport, payload: bytes) -> None:
        """Send *payload* on *transport* and record the send time.

        Call this instead of ``transport.send()`` from any path that a
        keep-alive heartbeat should debounce against.  The recorded timestamp
        is read by :meth:`_keep_alive_loop` to skip heartbeat sends when the
        transport has seen activity within the keep-alive window.

        Raises TransportRateLimitedError immediately if the transport is currently
        rate-limited — without touching the network — so all callers (commands,
        sagas, heartbeats) are blocked uniformly while the 12-hour ban is active.
        BLE transports are never rate-limited and are always allowed through.
        """
        if transport.transport_type != TransportType.BLE and transport.is_rate_limited:
            raise TransportRateLimitedError(
                f"Transport {transport.transport_type.value} is rate-limited — send blocked"
            )

        if transport.transport_type != TransportType.BLE:
            # The device drops out of its "synced" state ~10 s after the last sync and
            # then ignores commands / stops serving report+map frames.  That timer is
            # reset only by a sync — NOT by ordinary command traffic — so we debounce
            # against the last *sync* we sent (not the last command, which is why a busy
            # burst used to desync mid-stream).  Re-sync whenever the window is about to
            # lapse, awaited so it lands before the payload (a concurrent send lets the
            # payload race ahead and be ignored).
            since_sync = time.monotonic() - self._last_mqtt_sync_monotonic.get(transport.transport_type, 0.0)
            if since_sync > _MQTT_SYNC_INTERVAL:
                await self._send_mqtt_sync(transport, since_sync=since_sync)

        version = self.snapshot.raw.update_check.current_version

        # TODO do this by device type
        if version == "1.0.0.0" and hasattr(cast(MowerDevice, self.snapshot.raw), "mower_state"):
            version = cast(MowerDevice, self.snapshot.raw).mower_state.swversion

        await transport.send(payload, iot_id=self.iot_id, firmware_version=version)
        if not self._stopping:
            await self._sent_bus.emit(payload)

    async def _send_mqtt_sync(self, transport: Transport, *, since_sync: float) -> None:
        """Send a ``todev_ble_sync(3)`` keep-alive on *transport* and stamp the sync timer.

        This is the **single source of truth** for ``_last_mqtt_sync_monotonic``: the
        timestamp is advanced *only here*, and only after the sync is actually handed to
        the transport.  Because nothing else writes it, the timer can never be *falsely*
        advanced — a stale entry only ever causes one extra (quota-free) sync, never a
        missed one, so no caller can induce a desync.

        Other paths that emit a sync as an ordinary payload (the sagas' ``_send_ble_sync``,
        the RPT_START retry prefix) go through ``send_raw`` → ``_send_marked`` like any
        command, so this gate re-syncs ahead of their send when the window has lapsed —
        the device stays synced regardless of which path initiated it.  ``send_heartbeat``
        keeps the sync off the 24-hour command quota.
        """
        _logger.debug(
            "_send_marked [%s]: %.1fs since last %s sync — sending todev_ble_sync(3)",
            self.device_name,
            since_sync,
            transport.transport_type.value,
        )
        sync = self.commands.send_todev_ble_sync(sync_type=3)
        await transport.send_heartbeat(sync, iot_id=self.iot_id)
        self._last_mqtt_sync_monotonic[transport.transport_type] = time.monotonic()

    async def _on_critical_error(self, error: Exception) -> None:
        """Propagate critical errors to the error bus."""
        await self._error_bus.emit(error)

    async def notify_critical_error(self, error: Exception) -> None:
        """Publicly emit a critical error to subscribers of this device's error bus.

        Used by :class:`MammotionClient` to tell exactly the mowers on a permanently
        failed transport (e.g. Mammotion MQTT auth gave up) that they need re-auth,
        so the host can mark just those devices unavailable.
        """
        await self._on_critical_error(error)

    async def add_transport(self, transport: Transport) -> None:
        """Register a transport (MQTT or BLE).  Replaces any existing transport of the same type.

        Wires the per-transport message and availability handlers — that's it.
        BLE keepalive and polling loops are started exclusively from
        :meth:`_on_ble_connected`, which fires when the BLE availability
        listener observes a transition to CONNECTED after :meth:`connect`
        succeeds.  Registration and lifecycle are kept as separate concerns.
        """
        existing = self._transports.get(transport.transport_type)
        if existing is not None:
            _logger.debug("add_transport '%s': replacing existing %s", self.device_name, transport.transport_type.value)
            await existing.disconnect()
        _logger.debug("add_transport '%s': registered %s", self.device_name, transport.transport_type.value)
        self._wire_transport(transport)

    async def remove_transport(self, transport_type: TransportType) -> None:
        """Disconnect and remove a transport by type."""
        transport = self._transports.pop(transport_type, None)
        if transport is not None:
            await transport.disconnect()

    def detach_transport(self, transport_type: TransportType) -> Transport | None:
        """Remove a transport from this handle WITHOUT disconnecting it.

        Use for account-shared transports (e.g. the Aliyun MQTT transport, which is
        the same object across every device handle on an account): disconnecting it
        would tear down cloud for all the account's devices.  ``remove_transport``
        disconnects and so must NOT be used for shared transports.  Returns the
        removed transport, or ``None`` if it was not registered (idempotent).
        """
        return self._transports.pop(transport_type, None)

    async def on_raw_message(self, payload: bytes, transport_type: TransportType = TransportType.CLOUD_ALIYUN) -> None:
        """Receive raw bytes from transport, decode, update state, route to broker.

        Called via the per-transport closure created in _make_message_handler so
        that transport_type is always known.

        Steps:
          1. Decode bytes → LubaMsg (log and return on error)
          2. Clear mqtt_reported_offline if this message arrived over a cloud transport
          3. Route LubaMsg to broker for request/response correlation
             (done BEFORE the state pipeline so saga acks aren't blocked by
             slow state-changed subscribers — e.g. HA coordinator entity
             rebuilds, geojson generation — which can add hundreds of ms per
             frame to map-fetch latency).
          4. Apply LubaMsg to state via StateReducer
          5. Update DeviceStateMachine and emit the new snapshot
        """
        # 1. Parse bytes → LubaMsg
        try:
            luba_msg = LubaMsg().parse(payload)
        except UnicodeDecodeError:
            return
        except Exception:
            _logger.info("Failed to parse incoming bytes as LubaMsg (%d bytes)", len(payload))
            return

        # Sanity-check the envelope fields. If sender/rcver parsed as a list
        # (packed repeated bytes misidentified as field 2/3) the payload is not
        # a LubaMsg — protobuf silently accepts alien wire formats, so we must
        # guard here rather than letting garbage propagate to the state machine.
        # NOTE: msgtype is intentionally NOT checked here — MsgCmdType.START == 0
        # is the protobuf default, so legitimate cloud messages that omit msgtype
        # would be incorrectly dropped.
        if not isinstance(luba_msg.sender, MsgDevice) or not isinstance(luba_msg.rcver, MsgDevice):
            _logger.debug("← %s  ignored non-LubaMsg BLE notification (%d bytes)", self.device_name, len(payload))
            return

        try:
            _logger.debug("← %s  %s", self.device_name, luba_msg.to_dict(include_default_values=False))
        except (ValueError, KeyError):
            _logger.debug("← %s  <unparseable protobuf — unknown enum value>", self.device_name)
        self._last_report_at = time.monotonic()

        if self._availability.mqtt_reported_offline and transport_type != TransportType.BLE:
            self.update_availability(transport_type, self._availability.mqtt, mqtt_reported_offline=False)

        # 3. Route to broker for request/response correlation FIRST.
        # Saga handlers only enqueue the message into their internal asyncio
        # queue, so this is microseconds — but it must not be gated behind
        # the slow state pipeline (deep-copy of the map, plus all
        # state_changed subscribers) or saga ack latency stretches into
        # seconds per frame and map fetches take minutes.
        await self.broker.on_message(luba_msg)

        # 4. Apply to state via reducer (returns a new MowingDevice copy).
        # A corrupt frame can parse as a LubaMsg yet carry a field of the wrong
        # shape (e.g. a BLE notification garbled on the wire so WorkData.bp_pos_y
        # arrives as a list instead of an int).  betterproto2 accepts the alien
        # wire format and the failure only surfaces here when mashumaro coerces
        # the model — raising InvalidFieldValue (a ValueError) / TypeError.  Drop
        # the bad frame and keep the handler alive rather than letting it kill the
        # transport's receive task; natural traffic supplies a clean frame next.
        try:
            updated_device = self._reducer.apply(self.state_machine.current.raw, luba_msg)
        except (InvalidFieldValue, MissingField, TypeError) as exc:
            # mashumaro raises InvalidFieldValue (a ValueError) when a field coerces to the
            # wrong type and MissingField (a LookupError) when a required one is absent; an
            # unwrapped TypeError can also surface from the underlying coercion.  Catch those
            # by name (note: MissingField is NOT a KeyError, so a bare LookupError catch would
            # be the only structural alternative) and drop the frame.  Log the exception
            # message and the raw bytes (hex) so the offending field/value can be investigated.
            _logger.error(
                "← %s  dropping frame: malformed report data failed deserialization (%d bytes): %s | raw=%s",
                self.device_name,
                len(payload),
                exc,
                payload.hex(),
                exc_info=True,
            )
            return

        # 5. Update state machine and emit if anything in the model changed.
        # _diff now walks `raw`, so deep-field mutations (e.g.
        # report_data.dev.sys_status) correctly produce a non-empty `changed`.
        snapshot, changed = self.state_machine.apply(updated_device, self._availability)
        if changed and not self._stopping:
            await self._state_changed_bus.emit(snapshot)

        # 6. Emit map_updated when the area set HA renders changes:
        #   - toapp_all_hash_name: wholesale area-name list (post-2025 / non-Luba1).
        #   - toapp_map_name_msg: single-area rename ack (hash != 0; hash == 0 is
        #     the get-list request shape, not a rename).
        # Area geometry (toapp_get_commondata_ack) is deliberately NOT a trigger: it
        # arrives per-frame in bulk during a MapFetchSaga, and the saga's on_complete
        # already emits map_updated once at the end — so firing per frame would just
        # churn map-derived UI mid-fetch.
        nav = luba_msg.nav
        if nav is not None and (
            nav.toapp_all_hash_name is not None or (nav.toapp_map_name_msg is not None and nav.toapp_map_name_msg.hash)
        ):
            await self._map_updated_bus.emit(None)

        # 7. Emit shutdown when the device notifies it is about to power off.
        if luba_msg.sys is not None and luba_msg.sys.mow_to_app_info is not None:
            info = luba_msg.sys.mow_to_app_info
            if info.type == 0 and info.cmd == 0 and info.mow_data:
                _logger.debug("Device %s is powering off (power_type=%d)", self.device_name, info.mow_data[0])
                self.update_availability(transport_type, self._availability.mqtt, mqtt_reported_offline=True)
                await self._shutdown_bus.emit(
                    DeviceShutdownEvent(device_id=self.device_id, power_type=info.mow_data[0])
                )

    async def on_status_message(self, msg: ThingStatusMessage) -> None:
        """Store status_properties on the device model from a thing/status message.

        If the device is reported online and no protobuf has been received within
        :attr:`_REPORT_STALE_THRESHOLD` seconds, a ``get_report_cfg`` is enqueued
        immediately so state is refreshed without waiting for the next MQTT poll cycle.
        """
        updated = dataclasses.replace(self.state_machine.current.raw, status_properties=msg)
        snapshot, _ = self.state_machine.apply(updated, self._availability)
        if not self._stopping:
            await self._state_changed_bus.emit(snapshot)
            await self._status_bus.emit(msg)

        online = msg.params.status.value is StatusType.CONNECTED

        if self._availability.mqtt_reported_offline:
            if online and not self._stopping and time.monotonic() - self._last_report_at > self._REPORT_STALE_THRESHOLD:
                await self.request_report_cfg(dedup_key="report_cfg_on_status")

            if cloud_transport := self.cloud_transport():
                self.update_availability(cloud_transport, self._availability.mqtt, mqtt_reported_offline=not online)

    async def request_report_cfg(self, *, dedup_key: str = "report_cfg") -> None:
        """Enqueue a get_report_cfg command in the background."""
        if self._stopping:
            return
        cmd = self.commands.get_report_cfg()

        async def _send() -> None:
            try:
                await self.send_raw(cmd)
            except Exception:
                _logger.debug("request_report_cfg [%s]: failed", self.device_name, exc_info=True)

        await self.queue.enqueue(_send, priority=Priority.BACKGROUND, skip_if_saga_active=True, dedup_key=dedup_key)

    async def on_mammotion_properties(self, properties: MammotionPropertiesMessage) -> None:
        """Update device state from a Mammotion MQTT flat property push."""

        if self._availability.mqtt_reported_offline:
            if cloud_transport := self.cloud_transport():
                self.update_availability(cloud_transport, self._availability.mqtt, mqtt_reported_offline=False)

        updated = self._reducer.apply_mammotion_properties(self.state_machine.current.raw, properties)
        snapshot, _ = self.state_machine.apply(updated, self._availability)

        if not self._stopping:
            await self._state_changed_bus.emit(snapshot)

    async def on_device_event(self, event: ThingEventMessage) -> None:
        """Update device state with a thing.events message.

        If the event carries a ``device_protobuf_msg_event`` payload the
        base64-encoded protobuf is decoded and forwarded to ``on_raw_message``
        so that the state reducer and broker can process it (same path as a
        ``thing/model/down_raw`` delivery).  All other event types are stored
        as ``device_event`` on the device model.

        Staleness filtering (dropping buffered messages older than the wall
        clock) is handled upstream in ``AliyunMQTTTransport._dispatch_aliyun_event``
        where the raw envelope timestamp is available before deserialization.
        """
        if isinstance(event.params, DeviceProtobufMsgEventParams):
            try:
                raw_bytes = base64.b64decode(event.params.value.content)
                await self.on_raw_message(raw_bytes)
            except Exception:
                _logger.debug("on_device_event: failed to decode protobuf content", exc_info=True)
        else:
            if self._availability.mqtt_reported_offline:
                if cloud_transport := self.cloud_transport():
                    self.update_availability(cloud_transport, self._availability.mqtt, mqtt_reported_offline=False)

            updated = dataclasses.replace(self.state_machine.current.raw, device_event=event)
            snapshot, _ = self.state_machine.apply(updated, self._availability)
            if not self._stopping:
                await self._state_changed_bus.emit(snapshot)
                await self._event_bus.emit(event)

    async def on_device_properties(self, properties: ThingPropertiesMessage) -> None:
        """Update device state with a thing.properties message.

        For mower devices the properties are stored as ``mqtt_properties`` on the
        device (unchanged behaviour).  For device types whose reducer overrides
        :meth:`StateReducer.apply_properties` (currently :class:`RTKStateReducer`),
        the JSON payloads are also unpacked into typed model fields so the state
        machine remains the single source of truth.
        """
        # Let the reducer extract any typed fields it knows about (no-op for mowers).
        device_with_props = self._reducer.apply_properties(self.state_machine.current.raw, properties)

        if self._availability.mqtt_reported_offline:
            if cloud_transport := self.cloud_transport():
                self.update_availability(cloud_transport, self._availability.mqtt, mqtt_reported_offline=False)

        # Always persist the raw envelope so subscribers can inspect it.
        updated = dataclasses.replace(device_with_props, mqtt_properties=properties)
        snapshot, _ = self.state_machine.apply(updated, self._availability)
        if not self._stopping:
            await self._state_changed_bus.emit(snapshot)
            await self._properties_bus.emit(properties)

    async def send_command(
        self,
        command: bytes,
        expected_field: str,
        *,
        priority: Priority = Priority.NORMAL,
        skip_if_saga_active: bool = False,
    ) -> None:
        """Enqueue a command for execution via broker.send_and_wait.

        Does NOT return the response — responses update device state via on_message.
        The queue handles priority and saga blocking.
        """
        if skip_if_saga_active and self.queue.is_saga_active:
            _logger.debug("send_command '%s': saga active — skipping field=%s", self.device_name, expected_field)
            return

        async def _do_send(cmd: bytes, field: str) -> None:
            self._last_user_command_monotonic = time.monotonic()
            _logger.debug(
                "_do_send '%s': field=%s transports=%s",
                self.device_name,
                field,
                {k.value: v.is_connected for k, v in self._transports.items()},
            )
            if self._prefer_ble:
                ble = self._transports.get(TransportType.BLE)
                if ble is not None and not ble.is_connected and ble.is_usable:
                    _logger.debug("BLE preferred but disconnected for '%s' — reconnecting", self.device_name)
                    self.schedule_ble_connection(cast(BLETransport, ble))
            try:
                transport = self.active_transport()
            except NoTransportAvailableError:
                # Restart any dead MQTT task so future commands have a transport.
                # The fixed connect() is a no-op if the task is still running (retry-sleep).
                for t_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
                    mqtt_t = self._transports.get(t_type)
                    if mqtt_t is not None:
                        if not mqtt_t.is_connected:
                            _logger.warning(
                                "DeviceHandle[%s]: %s not connected on send — restarting loop",
                                self.device_name,
                                t_type.value,
                            )
                            await mqtt_t.connect()
                ble = self._transports.get(TransportType.BLE)
                if ble is not None and not ble.is_connected and ble.is_usable:
                    _logger.debug("BLE disconnected for '%s' — reconnecting before send", self.device_name)
                    await ble.connect()
                    transport = self.active_transport()
                else:
                    raise
            _logger.debug(
                "_do_send '%s': sending field=%s via %s", self.device_name, field, transport.transport_type.value
            )
            try:
                await self.broker.send_and_wait(
                    send_fn=lambda: self._send_marked(transport, cmd),
                    expected_field=field,
                )
            except DeviceOfflineException:
                ble = self._on_device_offline(transport)
                if ble is None:
                    raise
                await self.broker.send_and_wait(
                    send_fn=lambda: self._send_marked(ble, cmd),
                    expected_field=field,
                )
            except DeviceUnboundException:
                unbound_ble = await self._on_device_unbound(transport)
                if unbound_ble is None:
                    raise
                await self.broker.send_and_wait(
                    send_fn=lambda t=unbound_ble: self._send_marked(t, cmd),
                    expected_field=field,
                )

        await self.queue.enqueue(
            lambda: _do_send(command, expected_field),
            priority=priority,
            skip_if_saga_active=False,
        )

    def _on_device_offline(self, transport: Transport) -> Transport | None:
        """Mark the device offline on *transport* and pick a BLE fallback.

        Centralises the "cloud says device is offline" policy shared by
        ``send_command`` / ``_do_send`` and ``send_raw``: flag MQTT as
        offline, then return a connected BLE transport if one exists so
        the caller can retry on it.  Returns ``None`` when no fallback is
        available — caller is expected to re-raise ``DeviceOfflineException``.
        """
        self.update_availability(
            transport.transport_type,
            self._availability.mqtt,
            mqtt_reported_offline=True,
        )
        ble = self._transports.get(TransportType.BLE)
        if ble is not None and ble.is_connected:
            _logger.warning("Device '%s' offline via MQTT, retrying over BLE", self.device_name)
            return ble
        _logger.warning(
            "Device '%s' reported offline by cloud — marking %s unavailable",
            self.device_name,
            transport.transport_type,
        )
        return None

    async def _on_device_unbound(self, transport: Transport) -> Transport | None:
        """Handle a cloud "device is unbound" (Aliyun 29004) during a send.

        Detaches *transport* from this handle WITHOUT disconnecting it (it is the
        account-shared Aliyun connection serving other devices), then triggers the
        client's re-discovery hook once — which migrates the device to Mammotion MQTT
        or removes it entirely.  Returns a connected BLE transport so the in-flight
        command can still complete locally, or ``None`` if there is no BLE fallback.

        Unlike ``_on_device_offline`` this does NOT set ``mqtt_reported_offline``:
        that flag marks a recoverable offline cleared by inbound frames, whereas an
        unbind is a permanent detach with no Aliyun transport left to clear it.
        """
        removed = self.detach_transport(transport.transport_type)
        if removed is None:
            # Already detached by an earlier 29004 — don't re-trigger migration.
            ble = self._transports.get(TransportType.BLE)
            return ble if ble is not None and ble.is_connected else None

        self.update_availability(transport.transport_type, TransportAvailability.DISCONNECTED)
        _logger.warning(
            "Device '%s' unbound from cloud (%s) — detaching transport and re-discovering",
            self.device_name,
            transport.transport_type.value,
        )
        if self.on_device_unbound is not None and not self._unbound_migrating:
            self._unbound_migrating = True
            # Fire-and-forget so the send path isn't blocked by network re-discovery.
            asyncio.ensure_future(self.on_device_unbound(self))  # noqa: RUF006

        ble = self._transports.get(TransportType.BLE)
        if ble is not None and ble.is_connected:
            _logger.warning("Device '%s' unbound via cloud, retrying over BLE", self.device_name)
            return ble
        return None

    def reset_unbound_migration(self) -> None:
        """Re-arm the unbound hook so a future 29004 can trigger migration again.

        Called by the client once it finishes handling an unbound event.
        """
        self._unbound_migrating = False

    async def enqueue_saga(
        self,
        saga: Saga,
        on_complete: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Enqueue a saga for exclusive execution."""
        await self.queue.enqueue_saga(saga, self.broker, on_complete=on_complete)

    def has_queued_commands(self) -> bool:
        """Return True if the queue has pending work or a saga is active."""
        return self.queue._queue.qsize() > 0 or self.queue.is_saga_active  # noqa: SLF001

    def update_availability(
        self,
        transport_type: TransportType,
        availability: TransportAvailability,
        *,
        mqtt_reported_offline: bool | None = None,
    ) -> None:
        """Update transport availability and emit state_changed if connection state changed.

        ``mqtt_reported_offline`` semantics:
          * ``None`` (default) — preserve the existing flag.  Used by callers
            that only want to update transport state and don't know whether
            the device is currently flagged offline (e.g. the per-transport
            availability listener).
          * ``True`` — the cloud has reported the device offline.  ``send_raw``
            and ``_do_send`` set this on ``DeviceOfflineException``.
          * ``False`` — explicit clear.  ``on_raw_message`` sets this when an
            inbound MQTT frame arrives, since fresh traffic is the device
            telling us it's online again.
        """
        old_state = self._availability.connection_state
        state_avail = availability
        # Preserve the existing flag when caller didn't specify; explicit True/False overrides.
        new_offline = (
            self._availability.mqtt_reported_offline if mqtt_reported_offline is None else mqtt_reported_offline
        )

        if transport_type == TransportType.BLE:
            self._availability = DeviceAvailability(
                mqtt=self._availability.mqtt,
                ble=state_avail,
                mqtt_reported_offline=new_offline,
            )
        else:
            self._availability = DeviceAvailability(
                mqtt=state_avail,
                ble=self._availability.ble,
                mqtt_reported_offline=new_offline,
            )

        new_state = self._availability.connection_state
        if old_state != new_state and not self._stopping:
            snapshot, _ = self.state_machine.apply(self.state_machine.current.raw, self._availability)
            asyncio.get_running_loop().create_task(self._state_changed_bus.emit(snapshot))
            if old_state != DeviceConnectionState.CONNECTED and new_state == DeviceConnectionState.CONNECTED:
                asyncio.get_running_loop().create_task(self.restart_keep_alive())

    @property
    def availability(self) -> DeviceAvailability:
        """Current transport availability state."""
        return self._availability

    @property
    def snapshot(self) -> DeviceSnapshot:
        """The latest immutable device state snapshot."""
        return self.state_machine.current

    def restore_device(self, device: Device) -> None:
        """Restore previously saved device state (e.g. from HA storage)."""
        self.state_machine.restore(device)

    def subscribe_state_changed(
        self,
        handler: Callable[[DeviceSnapshot], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to state changes. Returns RAII Subscription handle."""
        return self._state_changed_bus.subscribe(handler)

    _UNSET: object = object()

    def watch_field(
        self,
        getter: Callable[[DeviceSnapshot], _T],
        handler: Callable[[_T], Awaitable[None]],
    ) -> Subscription:
        """Fire handler only when the value returned by getter changes.

        The handler is not called on the first snapshot — only on subsequent
        snapshots where the extracted value differs from the previous one.
        """
        last: list[object] = [self._UNSET]

        async def _on_state(snapshot: DeviceSnapshot) -> None:
            new_val = getter(snapshot)
            if last[0] is self._UNSET:
                last[0] = new_val
                return
            if new_val != last[0]:
                last[0] = new_val
                await handler(new_val)

        return self._state_changed_bus.subscribe(_on_state)

    def subscribe_device_status(
        self,
        handler: Callable[[ThingStatusMessage], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to thing/status messages. Returns RAII Subscription handle."""
        return self._status_bus.subscribe(handler)

    def subscribe_device_properties(
        self,
        handler: Callable[[ThingPropertiesMessage], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to thing/properties messages. Returns RAII Subscription handle."""
        return self._properties_bus.subscribe(handler)

    def subscribe_device_event(
        self,
        handler: Callable[[ThingEventMessage], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to non-protobuf thing/events messages. Returns RAII Subscription handle."""
        return self._event_bus.subscribe(handler)

    def subscribe_sent(
        self,
        handler: Callable[[bytes], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to outbound command bytes for tracing/debug purposes.

        Fires for every payload sent via :meth:`_send_marked` (excludes raw
        heartbeats). Subscribers can decode to ``LubaMsg`` to extract the
        ``which_one_of`` field name. Returns RAII Subscription handle.
        """
        return self._sent_bus.subscribe(handler)

    def subscribe_map_updated(
        self,
        handler: Callable[[], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to map-updated events.

        Fires when ``toapp_all_hash_name`` is received from the device or when
        a ``MapFetchSaga`` completes successfully.  Use this to rebuild map-derived
        UI (e.g. area switches) without reacting to every telemetry tick.
        """

        async def _wrap(_: None) -> None:
            await handler()

        return self._map_updated_bus.subscribe(_wrap)

    async def emit_map_updated(self) -> None:
        """Fire the map-updated event to all subscribers.

        Called by the client after a MapFetchSaga completes and any post-fetch
        state restoration finishes, so subscribers (HA-Luba's coordinators)
        see the final state — not the partial mid-fetch view.  Pairs with
        :meth:`subscribe_map_updated` for the listener side.
        """
        await self._map_updated_bus.emit(None)

    def subscribe_shutdown(
        self,
        handler: Callable[[DeviceShutdownEvent], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to device shutdown events.

        Fires when the device broadcasts a ``mow_to_app_info`` power-off
        notification (``type=0, cmd=0``), giving the earliest possible signal
        that the device is about to go offline.
        """
        return self._shutdown_bus.subscribe(handler)

    async def start(self) -> None:
        """Start the command queue processor and the MQTT activity loop.

        RTK base stations and Spino pool cleaners skip the activity task entirely.
        The BLE keepalive and polling loops are started exclusively by
        ``_on_ble_connected`` when the BLE availability listener observes a
        CONNECTED transition.
        """
        self._stopping = False
        self.queue.start()
        if not self._skips_activity_loops and (self._keep_alive_task is None or self._keep_alive_task.done()):
            self._keep_alive_task = asyncio.get_running_loop().create_task(mqtt_activity_loop(self))
        # _dynamics_line_task is BLE-gated and starts/stops from _on_ble_connected
        # / the BLE availability handler — not from start().  Dynamics-line polling
        # only makes sense over BLE (10 s cadence would be MQTT-quota-expensive).

    def _start_ble_loop(self) -> None:
        """Start (or restart) the BLE heartbeat task if not already running."""
        if self._skips_activity_loops or self._stopping:
            return
        if self._ble_keep_alive_task is None or self._ble_keep_alive_task.done():
            _logger.debug("start_ble_loop [%s]: starting BLE activity loop", self.device_name)
            self._ble_keep_alive_task = asyncio.get_running_loop().create_task(ble_activity_loop(self))

    def _start_ble_polling_loop(self) -> None:
        """Start (or restart) the BLE polling/streaming loop if not already running."""
        if self._skips_activity_loops or self._stopping:
            return
        if self._ble_polling_task is None or self._ble_polling_task.done():
            _logger.debug("start_ble_polling_loop [%s]: starting BLE polling loop", self.device_name)
            self._ble_polling_task = asyncio.get_running_loop().create_task(ble_polling_loop(self))

    def _start_dynamics_line_loop(self) -> None:
        """Start (or restart) the dynamics-line poll loop if the device type supports it.

        BLE-gated — only called from ``_on_ble_connected``.  Skipped entirely for
        device types that can never support dynamics line; LUBA_VA is included
        because its eligibility flips on firmware >= 1.15.3.4422, which the loop
        re-checks on every tick using the live ``main_controller`` version.
        """
        if self._skips_activity_loops or self._stopping:
            return
        if self._dynamics_line_task is not None and not self._dynamics_line_task.done():
            return
        dt = DeviceType.value_of_str(self.device_name)
        if not (dt.is_support_dynamics_line() or dt is DeviceType.LUBA_VA):
            return
        _logger.debug("start_dynamics_line_loop [%s]: starting dynamics-line poll loop", self.device_name)
        self._dynamics_line_task = asyncio.get_running_loop().create_task(dynamics_line_loop(self))

    async def restart_keep_alive(self) -> None:
        """Restart the MQTT activity loop if it has exited or was never started."""
        if self._skips_activity_loops or self._stopping:
            return
        if self._keep_alive_task is None or self._keep_alive_task.done():
            _logger.debug("restart_keep_alive [%s]: restarting MQTT activity loop", self.device_name)
            self._keep_alive_task = asyncio.get_running_loop().create_task(mqtt_activity_loop(self))

    async def stop_polling(self) -> None:
        """Cancel the MQTT poll loop, leaving the queue and transports running.

        The handle stays fully operational for receiving messages — state updates,
        saga results, and user-initiated sends all continue to work.  No outbound
        polls are sent until ``start()`` is called again.
        """
        if self._keep_alive_task is not None and not self._keep_alive_task.done():
            self._keep_alive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._keep_alive_task
        self._keep_alive_task = None

    async def stop(self) -> None:
        """Stop the command queue, broker, debounce task, and disconnect all transports."""
        self._stopping = True
        if self._report_stream_timer is not None:
            self._report_stream_timer.cancel()
            self._report_stream_timer = None
        for task in (
            self._keep_alive_task,
            self._ble_keep_alive_task,
            self._ble_polling_task,
            self._dynamics_line_task,
            self._ble_connect_task,
        ):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._keep_alive_task = None
        self._ble_keep_alive_task = None
        self._ble_polling_task = None
        self._dynamics_line_task = None
        self._ble_connect_task = None
        self._ble_stream_active = False
        await self.queue.stop()
        await self.broker.close()
        await self._state_changed_bus.stop()
        for transport in list(self._transports.values()):
            await transport.disconnect()
        self._transports.clear()

    def record_user_command(self) -> None:
        """Stamp the user-command timestamp and wake the poll loop for early re-evaluation.

        Call this whenever a user-initiated command is dispatched so that
        ``_rearm_event`` interrupts any in-progress sleep and the loop
        can re-evaluate immediately.
        """
        self._last_user_command_monotonic = time.monotonic()
        self._rearm_event.set()

    def device_mode(self) -> _DeviceMode:
        """Return the coarse device-mode bucket used for cadence selection.

        ACTIVE        — sys_status in ``MOWING_ACTIVE_MODES`` (mowing/returning).
        DOCKED_FULL   — on dock and battery at 100%.
        DOCKED_CHARGING — on dock but battery below 100%.
        IDLE          — anything else (paused, locked, lost, …).

        Public because the BLE / MQTT / dynamics-line loops all consult it
        to pick their tick cadence.
        """
        try:
            dev = self.state_machine.current.raw.report_data.dev  # type: ignore
            sys_status = dev.sys_status
            if sys_status in MOWING_ACTIVE_MODES:
                return _DeviceMode.ACTIVE
            charge_state = int(dev.charge_state)
            if charge_state != 0:
                if int(dev.battery_val) >= 100:
                    return _DeviceMode.DOCKED_FULL
                return _DeviceMode.DOCKED_CHARGING
            return _DeviceMode.IDLE
        except (AttributeError, TypeError, ValueError):
            return _DeviceMode.IDLE

    def in_no_request_mode(self) -> bool:
        """True when the device is in a mode where polling sends are unwelcome.

        Public — the BLE polling loop consults this to skip count=1 polls in
        modes that don't want to receive them.
        """
        try:
            return self.state_machine.current.raw.report_data.dev.sys_status in NO_REQUEST_MODES  # type: ignore
        except (AttributeError, TypeError):
            return False

    async def sleep_or_rearm(self, seconds: float) -> bool:
        """Sleep for *seconds*, returning ``True`` early if ``_rearm_event`` fires.

        The event is *consumed* (cleared) only after the wait observes it.  This
        preserves a ``set()`` delivered between iterations — the next call sees
        the event already set and returns ``True`` immediately, instead of
        clearing the signal and sleeping the full interval.

        Public — used by all three background loops on the handle.
        """
        try:
            await asyncio.wait_for(self._rearm_event.wait(), timeout=seconds)
        except TimeoutError:
            return False
        self._rearm_event.clear()
        return True

    def _poll_interval(self) -> float:
        """Return the MQTT one-shot poll interval based on current device mode.

        Thin wrapper kept on the handle for tests; actual cadence table lives
        in :mod:`pymammotion.device.mqtt_loop`.
        """
        return poll_interval(self)

    # ------------------------------------------------------------------
    # Public report-cfg API (used by MammotionClient / HA via client.py)
    # ------------------------------------------------------------------

    @property
    def last_report_at(self) -> float:
        """Monotonic timestamp of the last received LubaMsg (0.0 if none yet)."""
        return self._last_report_at

    async def request_report_snapshot(self) -> None:
        """Fire a one-shot count=1 report — no-op while BLE continuous stream is active.

        Used by HA after state-changing commands and in the sys_status watcher.
        Safe to call at any time; skips silently if BLE is already streaming fresher data.
        """
        if self._ble_stream_active:
            return
        await self._send_one_shot_report()

    async def start_report_stream(self, duration_ms: int = 300_000) -> None:
        """Start a transient report window lasting ``duration_ms`` ms.

        If the device is actively mowing or returning (ACTIVE mode), starts a
        continuous (count=0) stream and arms a stop timer.  In any other mode
        (docked, idle) a single one-shot count=1 poll is issued instead — there
        is no point holding a continuous stream for a stationary device.

        For the continuous path:
        * Repeated calls within the window reset the timer without re-sending
          RPT_START (prevents cloud quota spam on frequent callers like a dashboard).
        * If the BLE polling loop already holds a continuous stream the RPT_START
          is skipped (data already flowing) but the timer is still armed.
        * The stop callback skips RPT_STOP if BLE is still streaming so the BLE
          polling loop is never interrupted mid-run.
        """
        if self.device_mode() != _DeviceMode.ACTIVE:
            await self.request_report_snapshot()
            return

        already_streaming = self._report_stream_timer is not None

        if self._report_stream_timer is not None:
            self._report_stream_timer.cancel()
            self._report_stream_timer = None

        if not self._ble_stream_active:
            if already_streaming:
                await self._send_report_stream_keep()
            else:
                await self._send_report_stream_start(duration_ms)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._report_stream_timer = loop.call_later(duration_ms / 1000, self._fire_report_stream_stop)

    def _fire_report_stream_stop(self) -> None:
        """Sync timer callback — creates the async stop task."""
        self._report_stream_timer = None
        if self._ble_stream_active:
            # BLE loop is still streaming (mowing/idle); let it manage its own teardown.
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._send_report_stream_stop())
        except RuntimeError:
            pass

    async def _send_rpt_start_verified(
        self,
        cmd_bytes: bytes,
        transport_send: Callable[[bytes], Awaitable[None]],
    ) -> bool:
        """Send an ``RPT_START`` and wait for the first ``toapp_report_data`` ack.

        Uses ``broker.send_and_wait`` with its default budget (1 s × 2
        attempts).  On the broker's retry attempt, prefixes a
        ``send_todev_ble_sync(sync_type=2)`` to nudge the link before
        re-issuing the RPT_START.

        Returns ``True`` if the device responded with a ``toapp_report_data``
        frame, ``False`` on final timeout.  ``ConcurrentRequestError`` is
        treated as "another verified RPT_START is in flight on this broker"
        — its future will resolve via the same field, so we fall back to a
        plain send and return False without raising.

        Scope: this only covers the *initial* RPT_START.  The post-start
        case (RPT_KEEPs land but reports stop arriving) is handled by the
        stale watchdog in ``ble_polling_loop``.
        """
        sync_bytes = self.commands.send_todev_ble_sync(sync_type=3)
        attempts = [0]

        async def _send() -> None:
            attempts[0] += 1
            if attempts[0] > 1:
                try:
                    _logger.debug("RPT_START [%s]: retry-prefix sending todev_ble_sync(3)", self.device_name)
                    await transport_send(sync_bytes)
                except Exception:  # noqa: BLE001
                    _logger.debug(
                        "RPT_START [%s]: retry-prefix ble_sync send failed",
                        self.device_name,
                        exc_info=True,
                    )
            await transport_send(cmd_bytes)

        try:
            await self.broker.send_and_wait(_send, expected_field="toapp_report_data")
            return True
        except CommandTimeoutError:
            _logger.debug(
                "RPT_START [%s]: no toapp_report_data ack — next poll tick will retry",
                self.device_name,
            )
            return False
        except ConcurrentRequestError:
            try:
                await transport_send(cmd_bytes)
            except Exception:  # noqa: BLE001
                _logger.debug(
                    "RPT_START [%s]: concurrent-fallback send failed",
                    self.device_name,
                    exc_info=True,
                )
            return False

    async def _send_report_stream_start(self, duration_ms: int) -> None:
        """Enqueue RPT_START count=0 via best transport."""
        cmd_bytes = self.commands.request_iot_sys(
            rpt_act=RptAct.RPT_START,
            rpt_info_type=_REPORT_CHANNELS,
            timeout=duration_ms,
            period=3000,
            no_change_period=4000,
            count=0,
        )

        async def _send() -> None:
            await self._send_rpt_start_verified(cmd_bytes, self.send_raw)

        await self.queue.enqueue(_send, priority=Priority.BACKGROUND, skip_if_saga_active=True)

    async def _send_report_stream_keep(self) -> None:
        """Enqueue RPT_KEEP to refresh an already-active continuous stream."""
        cmd_bytes = self.commands.request_iot_sys(
            rpt_act=RptAct.RPT_KEEP,
            rpt_info_type=_REPORT_CHANNELS,
            count=0,
        )

        async def _send() -> None:
            await self.broker.send_and_wait(lambda: self.send_raw(cmd_bytes), expected_field="toapp_report_data")

        await self.queue.enqueue(_send, priority=Priority.BACKGROUND, skip_if_saga_active=True)

    async def _send_report_stream_stop(self) -> None:
        """Enqueue RPT_STOP count=1 to tear down the continuous stream."""
        cmd_bytes = self.commands.request_iot_sys(
            rpt_act=RptAct.RPT_STOP,
            rpt_info_type=_REPORT_CHANNELS,
            timeout=10_000,
            count=1,
        )

        async def _send() -> None:
            await self.send_raw(cmd_bytes)

        await self.queue.enqueue(_send, priority=Priority.BACKGROUND, skip_if_saga_active=True)

    async def _send_one_shot_report(self) -> None:
        """Enqueue a one-shot ``request_iot_sys(count=1)`` data refresh.

        Routes via the best available transport — BLE if connected and preferred,
        MQTT otherwise — matching the same transport-priority rules as user commands.
        """
        cmd_bytes = self.commands.request_iot_sys(
            rpt_act=RptAct.RPT_START,
            rpt_info_type=_REPORT_CHANNELS,
            timeout=10_000,
            count=1,
        )

        async def _send() -> None:
            await self._send_rpt_start_verified(cmd_bytes, self.send_raw)

        await self.queue.enqueue(
            _send,
            priority=Priority.BACKGROUND,
            skip_if_saga_active=True,
            dedup_key="one_shot_report",
        )

    async def request_reports(self, count: int = 1, timeout: int = 10_000) -> None:
        """Enqueue a one-shot "request_iot_sys(count=count)" data refresh."""
        cmd_bytes = self.commands.request_iot_sys(
            rpt_act=RptAct.RPT_START,
            rpt_info_type=_REPORT_CHANNELS,
            timeout=timeout,
            count=count,
        )

        async def _send() -> None:
            await self._send_rpt_start_verified(cmd_bytes, self.send_raw)

        await self.queue.enqueue(_send, priority=Priority.BACKGROUND, skip_if_saga_active=True)

    async def _enqueue_ble_stream_command(self, act: RptAct, count: int) -> None:
        """Enqueue a BLE-pinned ``request_iot_sys`` config command.

        ``count=0`` (with ``RPT_START``) starts/renews the continuous stream;
        ``count=1`` (with ``RPT_STOP``) tears it down.  Sent via
        ``send_heartbeat`` directly on the BLE transport so it (a) doesn't
        count against the cloud quota — these are subscription keep-alives,
        not user-driven polls — and (b) doesn't reset the BLE idle-disconnect
        timer.  Routed through the command queue with
        ``skip_if_saga_active=True`` so saga-exclusive operations are never
        preempted.

        RPT_START is verified via ``_send_rpt_start_verified``: the device
        must respond with a ``toapp_report_data`` frame before we flip
        ``_ble_stream_active = True``.  Without that gate the polling loop
        previously assumed every RPT_START succeeded and would fire RPT_KEEP
        against a stream that never started.
        """
        cmd_bytes = self.commands.request_iot_sys(
            rpt_act=act,
            rpt_info_type=_REPORT_CHANNELS,
            timeout=10_000,
            period=1000,
            no_change_period=4000,
            count=count,
        )

        async def _send() -> None:
            ble = self._transports.get(TransportType.BLE)
            if ble is None or not ble.is_connected:
                return

            async def _ble_send(payload: bytes) -> None:
                await ble.send_heartbeat(payload, iot_id=self.iot_id)

            if act is RptAct.RPT_START:
                if await self._send_rpt_start_verified(cmd_bytes, _ble_send):
                    self._ble_stream_active = True
                return
            try:
                await _ble_send(cmd_bytes)
            except TransportError:
                _logger.debug("ble_polling [%s]: stream command send failed", self.device_name, exc_info=True)

        await self.queue.enqueue(_send, priority=Priority.BACKGROUND, skip_if_saga_active=True)

    # ------------------------------------------------------------------
    # Public transport API (replaces private _transports access from HA)
    # ------------------------------------------------------------------

    def transport_status(self) -> dict[TransportType, TransportAvailability]:
        """Return availability status for all registered transports."""
        return {tt: t.availability for tt, t in self._transports.items()}

    def has_transport(self, transport_type: TransportType) -> bool:
        """Check if a transport of the given type is registered."""
        return transport_type in self._transports

    def get_transport(self, transport_type: TransportType) -> Transport | None:
        """Return the registered transport of the given type, or None."""
        return self._transports.get(transport_type)

    def _has_usable_mqtt(self) -> bool:
        """True when an MQTT transport is registered and the cloud hasn't reported the device offline."""
        if self._availability.mqtt_reported_offline:
            return False
        return any(tt is not TransportType.BLE for tt in self._transports)

    @property
    def is_stopping(self) -> bool:
        """True once stop() has been called; new emits should be suppressed."""
        return self._stopping

    async def emit_state_changed(self, snapshot: DeviceSnapshot) -> None:
        """Emit *snapshot* on the state-changed bus unless the handle is stopping.

        Public hook for callers that build snapshots externally (e.g.
        MammotionClient applying RTK properties) and want the same
        suppress-on-stop semantics the internal reducer uses.
        """
        if not self._stopping:
            await self._state_changed_bus.emit(snapshot)

    def is_transport_connected(self, transport_type: TransportType) -> bool:
        """Check if a specific transport is connected."""
        t = self._transports.get(transport_type)
        return t is not None and t.is_connected

    async def connect_transport(self, transport_type: TransportType) -> None:
        """Connect a specific transport by type."""
        t = self._transports.get(transport_type)
        if t is not None and not t.is_connected:
            await t.connect()

    async def disconnect_transport(self, transport_type: TransportType) -> None:
        """Disconnect a specific transport by type."""
        t = self._transports.get(transport_type)
        if t is not None and t.is_connected:
            await t.disconnect()

    async def wait_until_connected(self, *, timeout: float = 15.0, mqtt_stable_for: float = 2.0) -> bool:
        """Block until a transport is ready to carry commands, or *timeout* elapses.

        Readiness mirrors how the transports actually behave at startup:

        * **BLE** counts as ready the moment it reports connected — it's the
          preferred, lowest-latency path with no cloud-side settling delay.
        * **MQTT** (either cloud variant) counts as ready only once it has stayed
          continuously connected for *mqtt_stable_for* seconds. A freshly opened
          MQTT session can drop and re-subscribe in its first few seconds, and
          commands sent during that window would time out waiting for a reply; if
          the connection drops, the stability timer restarts.

        This only *waits* — it does not initiate connects. MQTT auto-connects
        after login; callers that want BLE connected (e.g. when ``prefer_ble``)
        must call :meth:`connect_transport` before awaiting this.

        Args:
            timeout:         Maximum time to wait, in seconds. On expiry the
                             method returns ``False`` so the caller can proceed
                             anyway rather than block startup indefinitely.
            mqtt_stable_for: How long MQTT must stay continuously connected before
                             it counts as ready.

        Returns:
            ``True`` if a transport became ready within *timeout*, ``False`` if it
            timed out (caller should continue regardless).

        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        mqtt_connected_since: float | None = None
        poll_interval = 0.5

        while True:
            now = loop.time()

            # BLE is ready as soon as it connects — no settling window needed.
            if self.is_transport_connected(TransportType.BLE):
                return True

            # MQTT is ready only after holding the connection for mqtt_stable_for.
            mqtt_connected = self.is_transport_connected(TransportType.CLOUD_MAMMOTION) or self.is_transport_connected(
                TransportType.CLOUD_ALIYUN
            )
            if mqtt_connected:
                if mqtt_connected_since is None:
                    mqtt_connected_since = now
                elif now - mqtt_connected_since >= mqtt_stable_for:
                    return True
            else:
                mqtt_connected_since = None

            remaining = deadline - now
            if remaining <= 0:
                _logger.debug(
                    "DeviceHandle[%s]: no transport ready after %.0fs — continuing anyway",
                    self.device_name,
                    timeout,
                )
                return False
            await asyncio.sleep(min(poll_interval, remaining))

    def schedule_ble_connection(self, ble: BLETransport) -> None:
        """Kick a background BLE connect, single-flight.

        No-op if a connect attempt is already in flight — the stored task is the
        single-flight guard so a burst of sends (or the poll loop) can't spawn
        concurrent ``ble.connect()`` calls.  The task reference is retained so it is
        not garbage-collected mid-connect and can be cancelled by :meth:`stop`.
        """
        if self._ble_connect_task is not None and not self._ble_connect_task.done():
            return
        self._ble_connect_task = asyncio.get_running_loop().create_task(self.attempt_ble_connection(ble))

    async def attempt_ble_connection(self, ble: BLETransport) -> None:
        """Connect *ble*, serialised by ``_ble_connect_lock`` so it never runs concurrently.

        Errors are swallowed (logged) because this runs as a detached background task:
        an unretrieved exception would otherwise surface as a noisy
        "Task exception was never retrieved" warning.
        """
        async with self._ble_connect_lock:
            if ble.is_connected:
                return
            try:
                await ble.connect()
            except BLEUnavailableError as exc:
                # Expected/transient: proxy out of slots, device out of range, cooldown.
                _logger.debug(
                    "BLE unavailable, connection failed for '%s' (%s)",
                    self.device_name,
                    exc,
                )
            except Exception:  # noqa: BLE001 — detached task must swallow everything
                # Any other failure (BleakError, TransportError, timeout, ...) must not
                # escape the detached task; log it so it's visible without crashing the loop.
                _logger.warning(
                    "BLE background connection failed unexpectedly for '%s'",
                    self.device_name,
                    exc_info=True,
                )

    async def send_raw(self, payload: bytes, *, prefer_ble: bool | None = None) -> None:
        """Send raw bytes via the best available transport, with BLE fallback on offline."""
        _logger.debug(
            "send_raw '%s': %d bytes prefer_ble=%s transports=%s",
            self.device_name,
            len(payload),
            prefer_ble,
            {k.value: v.is_connected for k, v in self._transports.items()},
        )

        use_ble = self.prefer_ble if prefer_ble is None else prefer_ble
        _ble_fallback = False  # True when BLE was intended but fell back to MQTT
        if use_ble:
            ble = self._transports.get(TransportType.BLE)
            if ble is not None and not ble.is_connected:
                if not ble.is_usable:
                    # BLE in cooldown or no cached BLEDevice — connect would fail
                    # immediately or burn a slot. Skip and let active_transport()
                    # fall through to MQTT (or raise if neither is available).
                    _logger.debug(
                        "BLE not usable for '%s' (cooldown or no cached device) — skipping reconnect",
                        self.device_name,
                    )
                    prefer_ble = False
                    _ble_fallback = True
                else:
                    _logger.debug("BLE preferred but disconnected for '%s' — reconnecting", self.device_name)
                    self.schedule_ble_connection(cast(BLETransport, ble))
        try:
            transport = self.active_transport(prefer_ble=prefer_ble)
        except NoTransportAvailableError:
            ble = self._transports.get(TransportType.BLE)
            if ble is not None and not ble.is_connected and ble.is_usable:
                _logger.debug("BLE disconnected for '%s' — reconnecting before send", self.device_name)
                await ble.connect()
                transport = self.active_transport(prefer_ble=prefer_ble)
            else:
                raise
        _logger.debug("send_raw '%s': sending via %s", self.device_name, transport.transport_type.value)
        try:
            await self._send_marked(transport, payload)
        except TransportRateLimitedError:
            _logger.debug("send_raw '%s': transport rate-limited — send blocked", self.device_name)
        except TooManyRequestsException:
            _logger.warning("send_raw '%s': rate limited by cloud — blocking MQTT sends for 12h", self.device_name)
            transport.set_rate_limited()
        except DeviceOfflineException:
            ble = self._on_device_offline(transport)
            if ble is None:
                raise
            await self._send_marked(ble, payload)
        except DeviceUnboundException:
            ble = await self._on_device_unbound(transport)
            if ble is None:
                raise
            await self._send_marked(ble, payload)
        except TransportError:
            if transport.transport_type is not TransportType.BLE:
                raise
            mqtt: Transport | None = None
            for transport_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
                t = self._transports.get(transport_type)
                if t is not None:
                    mqtt = t
                    break
            if mqtt is None:
                _logger.warning(
                    "Device '%s' BLE send failed and no MQTT transport available — giving up",
                    self.device_name,
                )
                raise
            _logger.debug(
                "Device '%s' BLE send failed — falling back to %s",
                self.device_name,
                mqtt.transport_type.value,
            )
            await self._send_marked(mqtt, payload)

    # ------------------------------------------------------------------
    # Error bus
    # ------------------------------------------------------------------

    def subscribe_errors(
        self,
        handler: Callable[[Exception], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to critical errors (AuthError, SagaFailedError, etc.)."""
        return self._error_bus.subscribe(handler)

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------

    @property
    def readiness(self) -> ReadinessStatus | None:
        """Check device readiness. Returns None if no checker configured."""
        if self._readiness_checker is None:
            return None
        return self._readiness_checker.check(cast("MowingDevice", self.snapshot.raw))

    @property
    def is_ready(self) -> bool:
        """True if device has base-level data, or no checker is configured."""
        status = self.readiness
        return status is None or status.is_ready

    def commands_to_fetch_missing(self) -> list[str]:
        """Return command names needed to populate missing data."""
        if self._readiness_checker is None:
            return []
        return self._readiness_checker.commands_to_fetch_missing(cast("MowingDevice", self.snapshot.raw))

    @property
    def prefer_ble(self) -> bool:
        """True if BLE is preferred over MQTT for this device."""
        return self._prefer_ble

    def set_prefer_ble(self, *, value: bool) -> None:
        """Change the transport preference at runtime (e.g. when BLE connects/disconnects)."""
        self._prefer_ble = value

    @property
    def mow_path_fetch_enabled(self) -> bool:
        """True if MowPathSaga is allowed to run over MQTT."""
        return self._mow_path_fetch_enabled

    def set_mow_path_fetch_enabled(self, *, value: bool) -> None:
        """Gate MowPathSaga fetches over MQTT. BLE fetches are never gated."""
        self._mow_path_fetch_enabled = value

    @property
    def ble_stream_active(self) -> bool:
        """True when the BLE polling loop is renewing a continuous count=0 report stream.

        Callers (HA-Luba's coordinators, primarily) use this to decide whether
        a one-shot count=1 poll is needed on a state-change event: if the
        stream is already feeding fresh data, the extra poll is redundant.
        """
        return self._ble_stream_active

    @ble_stream_active.setter
    def ble_stream_active(self, value: bool) -> None:
        """Set by the BLE polling loop.

        and by ``_enqueue_ble_stream_command``
        on a verified RPT_START) to reflect whether a continuous stream is
        currently being renewed.  Exposed as a setter so loops don't need to
        reach into ``_ble_stream_active`` directly.
        """
        self._ble_stream_active = value

    @property
    def ble_heartbeat_failures(self) -> int:
        """Consecutive BLE heartbeat send failures observed by ``ble_activity_loop``.

        Reset to 0 on each successful heartbeat; reaching
        ``_BLE_HEARTBEAT_FAIL_LIMIT`` causes the BLE loop to exit and
        fall back to MQTT.
        """
        return self._ble_heartbeat_failures

    @ble_heartbeat_failures.setter
    def ble_heartbeat_failures(self, value: int) -> None:
        """Setter so the BLE loop can update the counter without reaching into ``_ble_heartbeat_failures`` directly."""
        self._ble_heartbeat_failures = value

    @property
    def has_usable_transport(self) -> bool:
        """Single source of truth: would a send right now find a usable transport.

        Wraps :meth:`active_transport` in a try/except — True when the selector
        would return a transport, False when it would raise
        ``NoTransportAvailableError`` (cloud-reported offline + no BLE,
        BLE-in-cooldown + no MQTT, nothing registered, …).

        All send-path gates should use this rather than re-implementing the
        check.  The MQTT poll loop pre-flights with this; ``send_command_with_args``
        skips up-front when False to avoid enqueueing work guaranteed to fail.
        Sagas / internal sends can call ``send_raw`` directly and rely on the
        queue to swallow ``NoTransportAvailableError`` quietly.
        """
        try:
            self.active_transport()
        except NoTransportAvailableError:
            return False
        return True

    def cloud_transport(self) -> TransportType | None:
        mqtt = None
        for transport_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
            t = self._transports.get(transport_type)
            if t is not None:
                mqtt = transport_type
                break
        return mqtt

    def active_transport(self, *, prefer_ble: bool | None = None) -> Transport:
        """Return the best transport to send on *right now*.

        Selection order (``prefer_ble`` does NOT change it — see below):
          1. **BLE if it's actively connected** — lower latency, bypasses the cloud
             throttle.  Connected implies usable.
          2. **MQTT if usable** — chosen over a merely-usable-but-disconnected BLE so a
             send is never blocked waiting for BLE to connect.
          3. **Usable BLE** — only when no usable MQTT exists (e.g. BLE-only device).

        Because BLE connection is now a *background* task (see
        :meth:`schedule_ble_connection`), a disconnected BLE never pre-empts a working
        MQTT: the command goes over MQTT immediately while BLE reconnects in the
        background and wins on the next send once it is actively connected.

        BLE is considered usable when it has a cached ``BLEDevice`` and isn't in a
        connect-failure cooldown (see :attr:`BLETransport.is_usable`).  MQTT is unusable
        when the cloud has reported the device offline (``mqtt_reported_offline`` is True,
        auto-cleared by ``on_raw_message`` on the next inbound frame).

        Args:
            prefer_ble: Accepted for call-site compatibility and to bias the
                        selection-change log de-dup key, but it no longer affects which
                        transport is returned (a connected BLE always wins; otherwise a
                        usable MQTT wins).  When None the handle's ``_prefer_ble`` is used.

        Raises:
            NoTransportAvailableError: if nothing usable is registered.

        """
        use_ble_first = self._prefer_ble if prefer_ble is None else prefer_ble

        ble = self._transports.get(TransportType.BLE)
        ble_connected = ble is not None and ble.is_connected
        ble_usable = ble is not None and ble.is_usable

        mqtt_reported_offline = self._availability.mqtt_reported_offline
        mqtt: Transport | None = None
        for transport_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
            t = self._transports.get(transport_type)
            if t is not None:
                mqtt = t
                break
        mqtt_usable = mqtt is not None and not mqtt_reported_offline and mqtt.is_usable

        def _log_selection(path: str, *args: Any) -> None:
            """Log only when the (path, prefer_ble, ble_usable, mqtt_usable) tuple changes.

            Senders churn on this every poll; logging on every call buries the
            transitions that actually matter (BLE drop / recover, MQTT offline).
            """
            key = (path, use_ble_first, ble_usable, mqtt_usable)
            if self._last_active_transport_log == key:
                return
            self._last_active_transport_log = key
            _logger.debug(path, self.device_name, *args)

        # Rule 1: an actively-connected BLE link always wins.
        if ble_connected and ble is not None:
            _log_selection("active_transport '%s': selected BLE (actively connected)")
            return ble

        if mqtt_usable and mqtt is not None:
            _log_selection("active_transport '%s': selected %s", mqtt.transport_type)
            return mqtt
        if ble_usable and ble is not None:
            _log_selection("active_transport '%s': MQTT unusable — falling back to BLE")
            return ble

        transport_states = (
            ", ".join(f"{tt.value}={t.availability.value}" for tt, t in self._transports.items()) or "none registered"
        )
        offline_suffix = " (mqtt_reported_offline=True)" if mqtt_reported_offline else ""
        msg = f"No transport available for device '{self.device_id}' [{transport_states}]{offline_suffix}"
        _logger.debug("active_transport '%s': %s", self.device_name, msg)
        raise NoTransportAvailableError(msg)


class DeviceRegistry:
    """Maps device_id → DeviceHandle. Thread-safe via asyncio.Lock."""

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._devices: dict[str, DeviceHandle] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def register(self, handle: DeviceHandle) -> None:
        """Register a device handle by its device_id."""
        async with self._lock:
            self._devices[handle.device_id] = handle

    async def unregister(self, device_id: str) -> None:
        """Stop and remove the device handle."""
        async with self._lock:
            handle = self._devices.pop(device_id, None)
        if handle is not None:
            await handle.stop()

    def get(self, device_id: str) -> DeviceHandle | None:
        """Return the DeviceHandle for the given device_id, or None."""
        return self._devices.get(device_id)

    def get_by_name(self, name: str) -> DeviceHandle | None:
        """Return the first DeviceHandle with matching device_name, or None."""
        for handle in self._devices.values():
            if handle.device_name == name:
                return handle
        return None

    @property
    def all_devices(self) -> list[DeviceHandle]:
        """Return all registered device handles."""
        return list(self._devices.values())
