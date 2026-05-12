"""DeviceHandle — per-device facade unifying transport, broker, queue, and state."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import dataclasses
import logging
import time
from typing import TYPE_CHECKING, TypeVar

from pymammotion.aliyun.exceptions import DeviceOfflineException, TooManyRequestsException
from pymammotion.data.mqtt.event import DeviceProtobufMsgEventParams
from pymammotion.device.state_reducer import StateReducer, get_state_reducer
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_queue import DeviceCommandQueue, Priority
from pymammotion.proto import LubaMsg, RptAct, RptInfoType
from pymammotion.state.device_state import (
    DeviceAvailability,
    DeviceConnectionState,
    DeviceShutdownEvent,
    DeviceSnapshot,
    DeviceStateMachine,
)
from pymammotion.transport.base import (
    BLEUnavailableError,
    EventBus,
    NoTransportAvailableError,
    Subscription,
    Transport,
    TransportAvailability,
    TransportError,
    TransportRateLimitedError,
    TransportType,
)
from pymammotion.utility.constant import MOWING_ACTIVE_MODES, NO_REQUEST_MODES
from pymammotion.utility.device_type import DeviceType

_T = TypeVar("_T")


# The cadence loops live in their own modules so this file stays focused on the
# DeviceHandle facade.  Constants and tables live with the loops; consumers that
# need them (tests, external code) should import directly from those modules.
from pymammotion.device.ble_loop import ble_activity_loop, ble_polling_loop
from pymammotion.device.modes import _DeviceMode
from pymammotion.device.mqtt_loop import mqtt_activity_loop, poll_interval

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

    from pymammotion.data.model.device import Device
    from pymammotion.data.mqtt.event import ThingEventMessage
    from pymammotion.data.mqtt.properties import ThingPropertiesMessage
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
        self._prefer_ble: bool = prefer_ble
        # Pick a reducer matching the device kind. PoolCleanerDevice instances
        # get a PoolStateReducer (currently a stub); everything else gets the
        # full mower reducer. Decided once at construction so the per-message
        # hot path doesn't pay an isinstance check.
        self._reducer: StateReducer = get_state_reducer(device_name)
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
        #: Set by ``record_user_command`` to interrupt a long sleep and re-arm
        #: the activity loop immediately with the short window.
        self._rearm_event: asyncio.Event = asyncio.Event()
        #: True when the device name identifies an RTK base station — keep-alive
        #: (``send_todev_ble_sync``) is suppressed for these devices entirely.
        self._is_rtk: bool = DeviceType.is_rtk(device_name)
        #: Consecutive BLE heartbeat failures in _ble_activity_loop.  Reset on
        #: successful BLE connection.  Once it reaches _BLE_HEARTBEAT_FAIL_LIMIT
        #: the BLE loop exits and BLE is marked disconnected.
        self._ble_heartbeat_failures: int = 0
        #: Task running the BLE-specific 20 s heartbeat loop (separate from MQTT loop).
        self._ble_keep_alive_task: asyncio.Task[None] | None = None
        #: Task running the BLE polling/streaming loop (renews continuous stream while
        #: mowing, falls back to count=1 polls when docked).
        self._ble_polling_task: asyncio.Task[None] | None = None
        #: True while the BLE continuous (count=0) report stream is active.  The MQTT
        #: activity loop checks this and skips its own poll while the stream is feeding.
        self._ble_stream_active: bool = False
        #: Monotonic timestamp of the last successfully-parsed inbound LubaMsg.
        #: Used by ensure_fresh_state to decide whether a snapshot poll is needed.
        self._last_report_at: float = 0.0
        #: Timer handle for the transient continuous-stream auto-stop.
        self._report_stream_timer: asyncio.TimerHandle | None = None
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
                        # Cancel the BLE polling loop so the MQTT loop can resume
                        # without waiting up to _BLE_MODE_RECHECK_INTERVAL for
                        # the loop to detect the disconnect on its own.
                        task = self._ble_polling_task
                        if task is not None and not task.done():
                            task.cancel()
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
                self.queue.resume_after_reconnect()

        return _handler

    async def _on_ble_connected(self) -> None:
        """Called when the BLE transport transitions to CONNECTED.

        Resets BLE failure counters, fires a one-shot ``get_report_cfg(count=1)``
        for an immediate state refresh, and starts both the BLE keep-alive
        heartbeat loop and the BLE polling/streaming loop.  The MQTT loop is
        nudged via ``_rearm_event`` so it can re-evaluate the new transport
        topology immediately.
        """
        _logger.debug("_on_ble_connected [%s]: starting BLE loops and requesting report", self.device_name)
        self._ble_heartbeat_failures = 0
        self._rearm_event.set()  # wake MQTT loop early so it sees BLE is now connected
        self._start_ble_loop()
        self._start_ble_polling_loop()
        try:
            cmd = self.commands.get_report_cfg()
            await self.send_raw(cmd, prefer_ble=True)
        except Exception:
            _logger.debug("_on_ble_connected [%s]: report_cfg request failed", self.device_name, exc_info=True)

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

        last = transport.last_send_monotonic
        # this will always be BLE as ble constantly pings 20s ble sync messages
        if last != 0.0 and time.monotonic() - last > 50:
            # No commands sent for 50 seconds — prepend a BLE sync so the
            # device knows we are still connected before the real payload.
            sync = self.commands.send_todev_ble_sync(sync_type=3)
            await transport.send(sync, iot_id=self.iot_id)

        await transport.send(payload, iot_id=self.iot_id)

    async def _on_critical_error(self, error: Exception) -> None:
        """Propagate critical errors to the error bus."""
        await self._error_bus.emit(error)

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

    async def on_raw_message(self, payload: bytes, transport_type: TransportType = TransportType.CLOUD_ALIYUN) -> None:
        """Receive raw bytes from transport, decode, update state, route to broker.

        Called via the per-transport closure created in _make_message_handler so
        that transport_type is always known.

        Steps:
          1. Decode bytes → LubaMsg (log and return on error)
          2. Clear mqtt_reported_offline if this message arrived over a cloud transport
          3. Apply LubaMsg to state via StateReducer
          4. Update DeviceStateMachine and emit the new snapshot
          5. Route LubaMsg to broker for request/response correlation
        """
        # 1. Parse bytes → LubaMsg
        try:
            luba_msg = LubaMsg().parse(payload)
        except UnicodeDecodeError:
            return
        except Exception:
            _logger.info("Failed to parse incoming bytes as LubaMsg (%d bytes)", len(payload))
            return

        _logger.debug("← %s  %s", self.device_name, luba_msg.to_dict(include_default_values=False))
        self._last_report_at = time.monotonic()

        if self._availability.mqtt_reported_offline and transport_type != TransportType.BLE:
            self.update_availability(transport_type, self._availability.mqtt, mqtt_reported_offline=False)

        # 3. Apply to state via reducer (returns a new MowingDevice copy)
        updated_device = self._reducer.apply(self.state_machine.current.raw, luba_msg)

        # 4. Update state machine and emit if anything in the model changed.
        # _diff now walks `raw`, so deep-field mutations (e.g.
        # report_data.dev.sys_status) correctly produce a non-empty `changed`.
        snapshot, changed = self.state_machine.apply(updated_device, self._availability)
        if changed and not self._stopping:
            await self._state_changed_bus.emit(snapshot)

        # 5. Route to broker for request/response correlation
        await self.broker.on_message(luba_msg)

        # 6. Emit map_updated when the device sends a fresh area-name list.
        if luba_msg.nav is not None and luba_msg.nav.toapp_all_hash_name is not None:
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
        """Store status_properties on the device model from a thing/status message."""
        updated = dataclasses.replace(self.state_machine.current.raw, status_properties=msg)
        snapshot, _ = self.state_machine.apply(updated, self._availability)
        if not self._stopping:
            await self._state_changed_bus.emit(snapshot)
            await self._status_bus.emit(msg)

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
                    await ble.connect()
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
                self.update_availability(
                    transport.transport_type,
                    self._availability.mqtt,
                    mqtt_reported_offline=True,
                )
                ble = self._transports.get(TransportType.BLE)
                if ble is not None and ble.is_connected:
                    _logger.warning("Device '%s' offline via MQTT, retrying over BLE", self.device_name)
                    await self.broker.send_and_wait(
                        send_fn=lambda: self._send_marked(ble, cmd),
                        expected_field=field,
                    )
                else:
                    _logger.warning(
                        "Device '%s' reported offline by cloud — marking %s unavailable",
                        self.device_name,
                        transport.transport_type,
                    )
                    raise

        await self.queue.enqueue(
            lambda: _do_send(command, expected_field),
            priority=priority,
            skip_if_saga_active=False,
        )

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

        RTK base stations skip the activity task entirely.  The BLE keepalive
        and polling loops are started exclusively by ``_on_ble_connected``
        when the BLE availability listener observes a CONNECTED transition.
        """
        self._stopping = False
        self.queue.start()
        if not self._is_rtk and (self._keep_alive_task is None or self._keep_alive_task.done()):
            self._keep_alive_task = asyncio.get_running_loop().create_task(mqtt_activity_loop(self))

    def _start_ble_loop(self) -> None:
        """Start (or restart) the BLE heartbeat task if not already running."""
        if self._is_rtk or self._stopping:
            return
        if self._ble_keep_alive_task is None or self._ble_keep_alive_task.done():
            _logger.debug("start_ble_loop [%s]: starting BLE activity loop", self.device_name)
            self._ble_keep_alive_task = asyncio.get_running_loop().create_task(ble_activity_loop(self))

    def _start_ble_polling_loop(self) -> None:
        """Start (or restart) the BLE polling/streaming loop if not already running."""
        if self._is_rtk or self._stopping:
            return
        if self._ble_polling_task is None or self._ble_polling_task.done():
            _logger.debug("start_ble_polling_loop [%s]: starting BLE polling loop", self.device_name)
            self._ble_polling_task = asyncio.get_running_loop().create_task(ble_polling_loop(self))

    async def restart_keep_alive(self) -> None:
        """Restart the MQTT activity loop if it has exited or was never started."""
        if self._is_rtk or self._stopping:
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
        for task in (self._keep_alive_task, self._ble_keep_alive_task, self._ble_polling_task):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._keep_alive_task = None
        self._ble_keep_alive_task = None
        self._ble_polling_task = None
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

    def _device_mode(self) -> _DeviceMode:
        """Return the coarse device-mode bucket used for cadence selection.

        ACTIVE        — sys_status in ``MOWING_ACTIVE_MODES`` (mowing/returning).
        DOCKED_FULL   — on dock and battery at 100%.
        DOCKED_CHARGING — on dock but battery below 100%.
        IDLE          — anything else (paused, locked, lost, …).
        """
        try:
            dev = self.state_machine.current.raw.report_data.dev
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

    def _in_no_request_mode(self) -> bool:
        try:
            return self.state_machine.current.raw.report_data.dev.sys_status in NO_REQUEST_MODES
        except (AttributeError, TypeError):
            return False

    async def _sleep_or_rearm(self, seconds: float) -> bool:
        """Sleep for *seconds*, returning ``True`` early if ``_rearm_event`` fires.

        The event is *consumed* (cleared) only after the wait observes it.  This
        preserves a ``set()`` delivered between iterations — the next call sees
        the event already set and returns ``True`` immediately, instead of
        clearing the signal and sleeping the full interval.
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
        if self._device_mode() != _DeviceMode.ACTIVE:
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

    async def _send_report_stream_start(self, duration_ms: int) -> None:
        """Enqueue RPT_START count=0 via best transport."""
        cmd_bytes = self.commands.request_iot_sys(
            rpt_act=RptAct.RPT_START,
            rpt_info_type=_REPORT_CHANNELS,
            timeout=duration_ms,
            period=1000,
            no_change_period=4000,
            count=0,
        )

        await self.send_raw(cmd_bytes)

    async def _send_report_stream_keep(self) -> None:
        """Enqueue RPT_KEEP to refresh an already-active continuous stream."""
        cmd_bytes = self.commands.request_iot_sys(
            rpt_act=RptAct.RPT_KEEP,
            rpt_info_type=_REPORT_CHANNELS,
            count=0,
        )

        async def _send() -> None:
            await self.send_raw(cmd_bytes)

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
            await self.send_raw(cmd_bytes)

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
        await self.send_raw(cmd_bytes)

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
            try:
                await ble.send_heartbeat(cmd_bytes, iot_id=self.iot_id)
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
                else:
                    _logger.debug("BLE preferred but disconnected for '%s' — reconnecting", self.device_name)
                    try:
                        await ble.connect()
                    except BLEUnavailableError as exc:
                        # ESPHome proxy out of connection slots, BLE adapter unavailable, etc.
                        # If MQTT is registered and usable, route this send through it instead
                        # of dropping the request entirely.
                        if self._has_usable_mqtt():
                            _logger.warning(
                                "BLE unavailable for '%s' (%s) — falling back to MQTT for this send",
                                self.device_name,
                                exc,
                            )
                            prefer_ble = False  # force active_transport() to pick MQTT below
                        else:
                            raise
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
            self.update_availability(
                transport.transport_type,
                self._availability.mqtt,
                mqtt_reported_offline=True,
            )
            ble = self._transports.get(TransportType.BLE)
            if ble is not None and ble.is_connected:
                _logger.warning("Device '%s' offline via MQTT, retrying over BLE", self.device_name)
                await self._send_marked(ble, payload)
            else:
                _logger.warning(
                    "Device '%s' reported offline by cloud — marking %s unavailable",
                    self.device_name,
                    transport.transport_type,
                )
                raise
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
        return self._readiness_checker.check(self.snapshot.raw)

    @property
    def is_ready(self) -> bool:
        """True if device has base-level data, or no checker is configured."""
        status = self.readiness
        return status is None or status.is_ready

    def commands_to_fetch_missing(self) -> list[str]:
        """Return command names needed to populate missing data."""
        if self._readiness_checker is None:
            return []
        return self._readiness_checker.commands_to_fetch_missing(self.snapshot.raw)

    @property
    def prefer_ble(self) -> bool:
        """True if BLE is preferred over MQTT for this device."""
        return self._prefer_ble

    def set_prefer_ble(self, *, value: bool) -> None:
        """Change the transport preference at runtime (e.g. when BLE connects/disconnects)."""
        self._prefer_ble = value

    @property
    def ble_stream_active(self) -> bool:
        """True when the BLE polling loop is renewing a continuous count=0 report stream.

        Callers (HA-Luba's coordinators, primarily) use this to decide whether
        a one-shot count=1 poll is needed on a state-change event: if the
        stream is already feeding fresh data, the extra poll is redundant.
        """
        return self._ble_stream_active

    @property
    def has_usable_transport(self) -> bool:
        """Single source of truth: would a send right now find a usable transport?

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

    def active_transport(self, *, prefer_ble: bool | None = None) -> Transport:
        """Return the best transport to send on.

        Selection order:
          1. **BLE if it's actively connected** — always preferred because it's
             lower latency and bypasses the cloud throttle (unconditional,
             regardless of ``prefer_ble``).  Connected implies usable.
          2. If ``prefer_ble`` is True (via argument or ``self._prefer_ble``):
             usable BLE (caller is expected to reconnect), falling back to MQTT
             when MQTT is usable.
          3. Otherwise: MQTT if usable, falling back to usable BLE.

        BLE is considered usable when it has a cached ``BLEDevice`` and isn't
        in a connect-failure cooldown (see :attr:`BLETransport.is_usable`).
        Returning a non-usable BLE transport would cause callers to attempt a
        connect we already know will fail.

        MQTT is considered unusable when the cloud has reported the device as
        offline (``mqtt_reported_offline`` is True).  In that state we raise
        ``NoTransportAvailableError`` rather than firing commands into the
        cloud that the device can't receive.  The flag is automatically
        cleared by ``on_raw_message`` as soon as any MQTT frame arrives.

        Args:
            prefer_ble: Per-call override.  When None (default) the handle's
                        ``_prefer_ble`` attribute is used.  Pass True to force
                        BLE for a single call without mutating the handle state.

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
        mqtt_registered = mqtt is not None
        mqtt_usable = mqtt_registered and not mqtt_reported_offline

        _logger.debug(
            "active_transport '%s': prefer_ble=%s ble_connected=%s ble_usable=%s"
            " mqtt_registered=%s mqtt_usable=%s mqtt_offline=%s",
            self.device_name,
            use_ble_first,
            ble_connected,
            ble_usable,
            mqtt_registered,
            mqtt_usable,
            mqtt_reported_offline,
        )

        # Rule 1: an actively-connected BLE link always wins.
        if ble_connected and ble is not None:
            _logger.debug("active_transport '%s': selected BLE (actively connected)", self.device_name)
            return ble

        if use_ble_first:
            if ble_usable and ble is not None:
                _logger.debug(
                    "active_transport '%s': BLE preferred and usable — returning BLE for caller to (re)connect",
                    self.device_name,
                )
                return ble
            if mqtt_usable and mqtt is not None:
                _logger.debug(
                    "active_transport '%s': BLE preferred but not usable — falling back to %s",
                    self.device_name,
                    mqtt.transport_type,
                )
                return mqtt
        else:
            if mqtt_usable and mqtt is not None:
                _logger.debug("active_transport '%s': selected %s", self.device_name, mqtt.transport_type)
                return mqtt
            if ble_usable and ble is not None:
                _logger.debug("active_transport '%s': MQTT unusable — falling back to BLE", self.device_name)
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
