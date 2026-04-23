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
from pymammotion.device.staleness_watcher import MapStalenessWatcher
from pymammotion.device.state_reducer import StateReducer, get_state_reducer
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_queue import DeviceCommandQueue, Priority
from pymammotion.proto import LubaMsg
from pymammotion.state.device_state import DeviceAvailability, DeviceSnapshot, DeviceStateMachine
from pymammotion.transport.base import (
    EventBus,
    NoTransportAvailableError,
    Subscription,
    Transport,
    TransportAvailability,
    TransportError,
    TransportType,
)
from pymammotion.utility.constant import MOWING_ACTIVE_MODES

_T = TypeVar("_T")

#: Keep-alive interval when the mower is actively working / returning, or when
#: sending over BLE — matches the APK's 20 s ``todev_ble_sync`` heartbeat.
_KEEP_ALIVE_INTERVAL: float = 20.0
#: Extended keep-alive interval used when the device is docked/paused/idle AND
#: the active transport is MQTT — reduces cloud-path chatter while docked.
#: BLE always uses the short interval regardless of sys_status.
_KEEP_ALIVE_IDLE_INTERVAL: float = 600.0  # 10 minutes
#: ``sync_type`` for BLE heartbeats (matches APK ``sendBlueToothDeviceSync(2, ...)``).
_KEEP_ALIVE_SYNC_TYPE_BLE: int = 2
#: ``sync_type`` for MQTT/IoT heartbeats.
_KEEP_ALIVE_SYNC_TYPE_MQTT: int = 3

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
        self._readiness_checker: ReadinessChecker | None = readiness_checker
        self._staleness_watcher: MapStalenessWatcher | None = None
        self._stopping: bool = False
        self._keep_alive_task: asyncio.Task[None] | None = None

        # Wire up critical error propagation from queue
        self.queue.on_critical_error = self._on_critical_error

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
            self.update_availability(transport_type, state)

        return _handler

    async def _on_critical_error(self, error: Exception) -> None:
        """Propagate critical errors to the error bus."""
        await self._error_bus.emit(error)

    async def add_transport(self, transport: Transport) -> None:
        """Register a transport (MQTT or BLE). Replaces any existing transport of the same type."""
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
        except Exception:
            _logger.exception("Failed to parse incoming bytes as LubaMsg (%d bytes)", len(payload))
            return

        _logger.debug("← %s  %s", self.device_name, luba_msg.to_dict(include_default_values=False))

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

        async def _do_send(cmd: bytes, field: str) -> None:
            _logger.debug(
                "_do_send '%s': field=%s transports=%s",
                self.device_name,
                field,
                {k.value: v.is_connected for k, v in self._transports.items()},
            )
            if self._prefer_ble:
                ble = self._transports.get(TransportType.BLE)
                if ble is not None and not ble.is_connected:
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
                if ble is not None and not ble.is_connected:
                    _logger.debug("BLE disconnected for '%s' — reconnecting before send", self.device_name)
                    await ble.connect()
                    transport = self.active_transport()
                else:
                    raise
            _logger.debug(
                "_do_send '%s': sending field=%s via %s", self.device_name, field, transport.transport_type.value
            )
            try:
                if not transport.is_connected and transport.transport_type in (
                    TransportType.CLOUD_ALIYUN,
                    TransportType.CLOUD_MAMMOTION,
                ):
                    await transport.send(cmd, iot_id=self.iot_id)
                else:
                    await self.broker.send_and_wait(
                        send_fn=lambda: transport.send(cmd, iot_id=self.iot_id),
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
                        send_fn=lambda: ble.send(cmd, iot_id=self.iot_id),
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
            skip_if_saga_active=skip_if_saga_active,
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
        mqtt_reported_offline: bool = False,
    ) -> None:
        """Update transport availability and emit state_changed if connection state changed."""
        old_state = self._availability.connection_state
        state_avail = availability

        if transport_type == TransportType.BLE:
            self._availability = DeviceAvailability(
                mqtt=self._availability.mqtt,
                ble=state_avail,
                mqtt_reported_offline=self._availability.mqtt_reported_offline,
            )
        else:
            self._availability = DeviceAvailability(
                mqtt=state_avail,
                ble=self._availability.ble,
                mqtt_reported_offline=mqtt_reported_offline,
            )

        new_state = self._availability.connection_state
        if old_state != new_state and not self._stopping:
            snapshot, _ = self.state_machine.apply(self.state_machine.current.raw, self._availability)
            asyncio.get_event_loop().create_task(self._state_changed_bus.emit(snapshot))

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

    async def start(self) -> None:
        """Start the command queue processor and the 20 s keep-alive loop."""
        self._stopping = False
        self.queue.start()
        if self._keep_alive_task is None or self._keep_alive_task.done():
            self._keep_alive_task = asyncio.get_running_loop().create_task(self._keep_alive_loop())

    async def stop(self) -> None:
        """Stop the command queue, broker, debounce task, and disconnect all transports."""
        self._stopping = True
        if self._keep_alive_task is not None and not self._keep_alive_task.done():
            self._keep_alive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._keep_alive_task
        self._keep_alive_task = None
        if self._staleness_watcher is not None:
            self._staleness_watcher.stop()
        await self.queue.stop()
        await self.broker.close()
        await self._state_changed_bus.stop()
        for transport in list(self._transports.values()):
            await transport.disconnect()
        self._transports.clear()

    def keep_alive_interval(self) -> float:
        """Return the keep-alive sleep duration in seconds for the current state.

        - BLE active → always 20 s.
        - MQTT active + mower actively mowing/returning → 20 s.
        - MQTT active + mower docked/paused/idle → 10 min (reduces cloud chatter).
        - No transport → 20 s so we re-check availability quickly.
        """
        try:
            transport = self.active_transport()
        except NoTransportAvailableError:
            return _KEEP_ALIVE_INTERVAL
        if transport.transport_type == TransportType.BLE:
            return _KEEP_ALIVE_INTERVAL
        raw = self.state_machine.current.raw
        report_data = getattr(raw, "report_data", None)
        sys_status = getattr(getattr(report_data, "dev", None), "sys_status", 0) if report_data else 0
        if sys_status in MOWING_ACTIVE_MODES:
            return _KEEP_ALIVE_INTERVAL
        return _KEEP_ALIVE_IDLE_INTERVAL

    async def _keep_alive_loop(self) -> None:
        """Send ``send_todev_ble_sync`` on a variable schedule over the active transport.

        Mirrors the APK's ``handler.sendEmptyMessageDelayed(10001, 20000L)``
        heartbeat (see ``MACarDataManager.java:13346``), extended with a
        10-minute interval when the mower is idle over MQTT.  ``sync_type``
        differs per transport: 2 over BLE, 3 over MQTT/IoT.
        """
        while not self._stopping:
            interval = self.keep_alive_interval()
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                return
            if self._stopping:
                return
            try:
                transport = self.active_transport()
            except NoTransportAvailableError:
                continue
            sync_type = (
                _KEEP_ALIVE_SYNC_TYPE_BLE
                if transport.transport_type == TransportType.BLE
                else _KEEP_ALIVE_SYNC_TYPE_MQTT
            )
            try:
                cmd_bytes = self.commands.send_todev_ble_sync(sync_type=sync_type)
                await transport.send(cmd_bytes, iot_id=self.iot_id)
            except DeviceOfflineException:
                # Cloud rejected the send as "device offline" (code 6205).
                # Flip the availability flag so subsequent active_transport()
                # calls skip MQTT until a message arrives (on_raw_message
                # clears the flag automatically).
                if transport.transport_type != TransportType.BLE:
                    self.update_availability(
                        transport.transport_type,
                        self._availability.mqtt,
                        mqtt_reported_offline=True,
                    )
                _logger.debug(
                    "keep_alive [%s]: %s reports device offline — marking mqtt_reported_offline",
                    self.device_name,
                    transport.transport_type.value,
                )
            except Exception:  # noqa: BLE001
                _logger.debug(
                    "keep_alive [%s]: send via %s failed",
                    self.device_name,
                    transport.transport_type.value,
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Public transport API (replaces private _transports access from HA)
    # ------------------------------------------------------------------

    def transport_status(self) -> dict[TransportType, TransportAvailability]:
        """Return availability status for all registered transports."""
        return {tt: t.availability for tt, t in self._transports.items()}

    def has_transport(self, transport_type: TransportType) -> bool:
        """Check if a transport of the given type is registered."""
        return transport_type in self._transports

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

    async def send_raw(self, payload: bytes, *, prefer_ble: bool = False) -> None:
        """Send raw bytes via the best available transport, with BLE fallback on offline."""
        _logger.debug(
            "send_raw '%s': %d bytes prefer_ble=%s transports=%s",
            self.device_name,
            len(payload),
            prefer_ble,
            {k.value: v.is_connected for k, v in self._transports.items()},
        )
        use_ble = prefer_ble or self._prefer_ble
        if use_ble:
            ble = self._transports.get(TransportType.BLE)
            if ble is not None and not ble.is_connected:
                _logger.debug("BLE preferred but disconnected for '%s' — reconnecting", self.device_name)
                await ble.connect()
        try:
            transport = self.active_transport(prefer_ble=prefer_ble)
        except NoTransportAvailableError:
            ble = self._transports.get(TransportType.BLE)
            if ble is not None and not ble.is_connected:
                _logger.debug("BLE disconnected for '%s' — reconnecting before send", self.device_name)
                await ble.connect()
                transport = self.active_transport(prefer_ble=prefer_ble)
            else:
                raise
        _logger.debug("send_raw '%s': sending via %s", self.device_name, transport.transport_type.value)
        try:
            await transport.send(payload, iot_id=self.iot_id)
        except TooManyRequestsException:
            _logger.warning("Device '%s' rate limited", self.device_name)
        except DeviceOfflineException:
            self.update_availability(
                transport.transport_type,
                self._availability.mqtt,
                mqtt_reported_offline=True,
            )
            ble = self._transports.get(TransportType.BLE)
            if ble is not None and ble.is_connected:
                _logger.warning("Device '%s' offline via MQTT, retrying over BLE", self.device_name)
                await ble.send(payload, iot_id=self.iot_id)
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
            await mqtt.send(payload, iot_id=self.iot_id)

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

    # ------------------------------------------------------------------
    # Staleness watcher
    # ------------------------------------------------------------------

    def enable_staleness_watcher(
        self,
        on_maps_stale: Callable[[], Awaitable[None]],
        on_plans_stale: Callable[[], Awaitable[None]],
        on_area_names_stale: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Enable auto-refetch of stale maps, plans, and area names.

        *on_area_names_stale* is called when map data is valid but area names
        are missing.  Defaults to *on_maps_stale* (full re-fetch) when omitted.
        """
        watcher = MapStalenessWatcher(
            on_maps_stale=on_maps_stale,
            on_plans_stale=on_plans_stale,
            on_area_names_stale=on_area_names_stale,
            is_saga_active=lambda: self.queue.is_saga_active,
        )
        sub = self._state_changed_bus.subscribe(watcher.on_state_changed)
        watcher._subscription = sub  # noqa: SLF001
        self._staleness_watcher = watcher

    @property
    def prefer_ble(self) -> bool:
        """True if BLE is preferred over MQTT for this device."""
        return self._prefer_ble

    def set_prefer_ble(self, *, value: bool) -> None:
        """Change the transport preference at runtime (e.g. when BLE connects/disconnects)."""
        self._prefer_ble = value

    def active_transport(self, *, prefer_ble: bool | None = None) -> Transport:
        """Return the best transport to send on.

        Selection order:
          1. **BLE if it's actively connected** — always preferred because it's
             lower latency and bypasses the cloud throttle (unconditional,
             regardless of ``prefer_ble``).
          2. If ``prefer_ble`` is True (via argument or ``self._prefer_ble``):
             registered-but-disconnected BLE (caller is expected to reconnect),
             falling back to MQTT when MQTT is usable.
          3. Otherwise: MQTT if usable, falling back to registered BLE.

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
        ble_registered = ble is not None
        ble_connected = ble_registered and ble.is_connected

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
            "active_transport '%s': prefer_ble=%s ble_registered=%s ble_connected=%s"
            " mqtt_registered=%s mqtt_usable=%s mqtt_offline=%s",
            self.device_name,
            use_ble_first,
            ble_registered,
            ble_connected,
            mqtt_registered,
            mqtt_usable,
            mqtt_reported_offline,
        )

        # Rule 1: an actively-connected BLE link always wins.
        if ble_connected:
            _logger.debug("active_transport '%s': selected BLE (actively connected)", self.device_name)
            return ble

        if use_ble_first:
            if ble_registered:
                _logger.debug(
                    "active_transport '%s': BLE preferred and registered — returning BLE for caller to (re)connect",
                    self.device_name,
                )
                return ble
            if mqtt_usable:
                _logger.debug(
                    "active_transport '%s': BLE preferred but not registered — falling back to %s",
                    self.device_name,
                    mqtt.transport_type,
                )
                return mqtt
        else:
            if mqtt_usable:
                _logger.debug("active_transport '%s': selected %s", self.device_name, mqtt.transport_type)
                return mqtt
            if ble_registered:
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
