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
        mqtt_transport: Transport | None = None,
        ble_transport: Transport | None = None,
        prefer_ble: bool = False,
        debounce_interval: float = 0.0,
        max_debounce_wait: float = 2.0,
    ) -> None:
        """Initialise the device handle with optional initial transports."""
        self.device_id = device_id
        self.device_name = device_name
        self.iot_id = iot_id
        self.broker = DeviceMessageBroker()
        self.queue = DeviceCommandQueue()
        self.state_machine = DeviceStateMachine(device_id, initial_device)
        self._availability = DeviceAvailability()
        self._transports: dict[TransportType, Transport] = {}
        self._state_changed_bus: _DebouncedBus = _DebouncedBus(debounce_interval, max_debounce_wait)
        self._prefer_ble: bool = prefer_ble
        self._reducer: StateReducer = StateReducer()

        if mqtt_transport is not None:
            mqtt_transport.on_message = self._on_raw_message
            self._transports[mqtt_transport.transport_type] = mqtt_transport

        if ble_transport is not None:
            ble_transport.on_message = self._on_raw_message
            self._transports[ble_transport.transport_type] = ble_transport

    async def add_transport(self, transport: Transport) -> None:
        """Register a transport (MQTT or BLE). Replaces any existing transport of the same type."""
        existing = self._transports.get(transport.transport_type)
        if existing is not None:
            await existing.disconnect()
        transport.on_message = self._on_raw_message
        self._transports[transport.transport_type] = transport

    async def remove_transport(self, transport_type: TransportType) -> None:
        """Disconnect and remove a transport by type."""
        transport = self._transports.pop(transport_type, None)
        if transport is not None:
            await transport.disconnect()

    async def _on_raw_message(self, payload: bytes) -> None:
        """Receive raw bytes from transport, decode, update state, route to broker.

        Called by transports instead of broker.on_message directly.
        Steps:
          1. Decode bytes → LubaMsg (log and return on error)
          2. Apply LubaMsg to state via StateReducer
          3. Update DeviceStateMachine, emit to _state_changed_bus if fields changed
          4. Route LubaMsg to broker for request/response correlation
        """
        # 1. Parse bytes → LubaMsg
        try:
            luba_msg = LubaMsg().parse(payload)
        except Exception:
            _logger.exception("Failed to parse incoming bytes as LubaMsg (%d bytes)", len(payload))
            return

        # 2. Apply to state via reducer (returns a new MowingDevice copy)
        updated_device = self._reducer.apply(self.state_machine.current.raw, luba_msg)

        # 3. Update state machine and emit if anything observable changed
        snapshot, changed = self.state_machine.apply(updated_device, self._availability)
        if changed:
            await self._state_changed_bus.emit(snapshot)

        # 4. Route to broker for request/response correlation
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
            await self.broker.send_and_wait(
                send_fn=lambda: self._active_transport().send(cmd),
                expected_field=field,
            )

        await self.queue.enqueue(
            lambda: _do_send(command, expected_field),
            priority=priority,
            skip_if_saga_active=skip_if_saga_active,
        )

    async def enqueue_saga(self, saga: Saga) -> None:
        """Enqueue a saga for exclusive execution."""
        await self.queue.enqueue_saga(saga, self.broker)

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
        if old_state != new_state:
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

    def subscribe_state_changed(
        self,
        handler: Callable[[DeviceSnapshot], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to state changes. Returns RAII Subscription handle."""
        return self._state_changed_bus.subscribe(handler)

    async def start(self) -> None:
        """Start the command queue processor."""
        self.queue.start()

    async def stop(self) -> None:
        """Stop the command queue, broker, debounce task, and disconnect all transports."""
        await self.queue.stop()
        await self.broker.close()
        await self._state_changed_bus.stop()
        for transport in list(self._transports.values()):
            await transport.disconnect()
        self._transports.clear()

    @property
    def prefer_ble(self) -> bool:
        """True if BLE is preferred over MQTT for this device."""
        return self._prefer_ble

    def set_prefer_ble(self, *, value: bool) -> None:
        """Change the transport preference at runtime (e.g. when BLE connects/disconnects)."""
        self._prefer_ble = value

    def _active_transport(self) -> Transport:
        """Return the best connected transport.

        By default: MQTT preferred, BLE fallback.
        If prefer_ble=True: BLE preferred, MQTT fallback.
        Raises NoTransportAvailableError if nothing is connected.
        """
        ble = self._transports.get(TransportType.BLE)
        ble_ok = ble is not None and ble.is_connected

        mqtt: Transport | None = None
        for transport_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
            t = self._transports.get(transport_type)
            if t is not None and t.is_connected:
                mqtt = t
                break
        mqtt_ok = mqtt is not None

        if self._prefer_ble:
            if ble_ok:
                return ble  # type: ignore[return-value]
            if mqtt_ok:
                return mqtt  # type: ignore[return-value]
        else:
            if mqtt_ok:
                return mqtt  # type: ignore[return-value]
            if ble_ok:
                return ble  # type: ignore[return-value]

        msg = f"No connected transport available for device '{self.device_id}'"
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
