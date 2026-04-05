"""DeviceHandle — per-device facade unifying transport, broker, queue, and state."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING

from pymammotion.device.state_reducer import StateReducer
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
    TransportType,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.data.model.device import MowingDevice
    from pymammotion.device.readiness import ReadinessChecker, ReadinessStatus
    from pymammotion.device.staleness_watcher import MapStalenessWatcher
    from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
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
        initial_device: MowingDevice,
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
        self._prefer_ble: bool = prefer_ble
        self._reducer: StateReducer = StateReducer()
        self._error_bus: EventBus[Exception] = EventBus()
        self._readiness_checker: ReadinessChecker | None = readiness_checker
        self._staleness_watcher: MapStalenessWatcher | None = None
        self._stopping: bool = False

        # Wire up critical error propagation from queue
        self.queue.on_critical_error = self._on_critical_error

        if mqtt_transport is not None:
            self._wire_transport(mqtt_transport)

        if ble_transport is not None:
            self._wire_transport(ble_transport)

    @property
    def commands(self) -> MammotionCommand:
        """Return a MammotionCommand builder for this device."""
        from pymammotion.mammotion.commands.mammotion_command import MammotionCommand

        return MammotionCommand(self.device_name, self.user_account)

    def _wire_transport(self, transport: Transport) -> None:
        """Wire callbacks on a transport and register it."""
        transport.on_message = self._make_message_handler(transport.transport_type)
        transport.add_availability_listener(self._make_availability_handler(transport.transport_type))
        self._transports[transport.transport_type] = transport

    def _make_message_handler(self, transport_type: TransportType) -> Callable[[bytes], Awaitable[None]]:
        """Create a per-transport message callback that carries the transport type."""

        async def _handler(payload: bytes) -> None:
            await self._on_raw_message(payload, transport_type)

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

    async def _on_raw_message(self, payload: bytes, transport_type: TransportType = TransportType.CLOUD_ALIYUN) -> None:
        """Receive raw bytes from transport, decode, update state, route to broker.

        Called via the per-transport closure created in _make_message_handler so
        that transport_type is always known.

        Steps:
          1. Decode bytes → LubaMsg (log and return on error)
          2. Clear mqtt_reported_offline if this message arrived over a cloud transport
          3. Apply LubaMsg to state via StateReducer
          4. Update DeviceStateMachine, emit to _state_changed_bus if fields changed
          5. Route LubaMsg to broker for request/response correlation
        """
        # 1. Parse bytes → LubaMsg
        try:
            luba_msg = LubaMsg().parse(payload)
        except Exception:
            _logger.exception("Failed to parse incoming bytes as LubaMsg (%d bytes)", len(payload))
            return

        _logger.debug("← %s  %s", self.device_name, luba_msg.to_dict(include_default_values=False))

        # 2. Clear mqtt_reported_offline — device is clearly reachable if it's sending messages
        if self._availability.mqtt_reported_offline and transport_type != TransportType.BLE:
            self.update_availability(transport_type, self._availability.mqtt, mqtt_reported_offline=False)

        # 3. Apply to state via reducer (returns a new MowingDevice copy)
        updated_device = self._reducer.apply(self.state_machine.current.raw, luba_msg)

        # 4. Update state machine and emit if anything observable changed
        snapshot, changed = self.state_machine.apply(updated_device, self._availability)
        if changed:
            await self._state_changed_bus.emit(snapshot)

        # 5. Route to broker for request/response correlation
        await self.broker.on_message(luba_msg)

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
            from pymammotion.aliyun.exceptions import DeviceOfflineException

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
                    if mqtt_t is not None and not mqtt_t.is_connected:
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
                await self.broker.send_and_wait(
                    send_fn=lambda: transport.send(cmd, iot_id=self.iot_id),
                    expected_field=field,
                )
            except DeviceOfflineException:
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
                    self.update_availability(
                        transport.transport_type,
                        self._availability.mqtt,
                        mqtt_reported_offline=True,
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

    def restore_device(self, device: MowingDevice) -> None:
        """Restore previously saved device state (e.g. from HA storage)."""
        self.state_machine.restore(device)

    def subscribe_state_changed(
        self,
        handler: Callable[[DeviceSnapshot], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to state changes. Returns RAII Subscription handle."""
        return self._state_changed_bus.subscribe(handler)

    async def start(self) -> None:
        """Start the command queue processor."""
        self._stopping = False
        self.queue.start()

    async def stop(self) -> None:
        """Stop the command queue, broker, debounce task, and disconnect all transports."""
        self._stopping = True
        if self._staleness_watcher is not None:
            self._staleness_watcher.stop()
        await self.queue.stop()
        await self.broker.close()
        await self._state_changed_bus.stop()
        for transport in list(self._transports.values()):
            await transport.disconnect()
        self._transports.clear()

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
        from pymammotion.aliyun.exceptions import DeviceOfflineException

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
        except DeviceOfflineException:
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
                self.update_availability(
                    transport.transport_type,
                    self._availability.mqtt,
                    mqtt_reported_offline=True,
                )
                raise

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
        from pymammotion.device.staleness_watcher import MapStalenessWatcher

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
        """Return the best connected transport.

        By default: MQTT preferred, BLE fallback.
        If prefer_ble=True (either from the handle setting or the per-call override):
        BLE preferred, MQTT fallback.

        Args:
            prefer_ble: Per-call override.  When None (default) the handle's
                        ``_prefer_ble`` attribute is used.  Pass True to force
                        BLE for a single call without mutating the handle state.

        Raises:
            NoTransportAvailableError: if nothing is connected.

        """
        use_ble_first = self._prefer_ble if prefer_ble is None else prefer_ble

        ble = self._transports.get(TransportType.BLE)
        ble_ok = ble is not None

        mqtt_reported_offline = self._availability.mqtt_reported_offline
        mqtt: Transport | None = None
        for transport_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
            t = self._transports.get(transport_type)
            if t is not None and t.is_connected and not mqtt_reported_offline:
                mqtt = t
                break
        mqtt_ok = mqtt is not None

        _logger.debug(
            "active_transport '%s': prefer_ble=%s ble_registered=%s ble_connected=%s mqtt_connected=%s mqtt_offline=%s",
            self.device_name,
            use_ble_first,
            ble is not None,
            ble_ok,
            mqtt_ok,
            mqtt_reported_offline,
        )

        if use_ble_first:
            if ble_ok:
                _logger.debug("active_transport '%s': selected BLE", self.device_name)
                return ble
            if mqtt_ok:
                _logger.debug(
                    "active_transport '%s': BLE preferred but not connected — falling back to %s",
                    self.device_name,
                    mqtt.transport_type,
                )
                return mqtt
        else:
            if mqtt_ok:
                _logger.debug("active_transport '%s': selected %s", self.device_name, mqtt.transport_type)
                return mqtt
            if ble_ok:
                _logger.debug("active_transport '%s': MQTT not connected — falling back to BLE", self.device_name)
                return ble

        transport_states = (
            ", ".join(f"{tt.value}={t.availability.value}" for tt, t in self._transports.items()) or "none registered"
        )
        msg = f"No connected transport available for device '{self.device_id}' [{transport_states}]"
        _logger.warning("active_transport '%s': %s", self.device_name, msg)
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
