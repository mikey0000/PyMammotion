"""DeviceHandle — per-device facade unifying transport, broker, queue, and state."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_queue import DeviceCommandQueue, Priority
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
        mqtt_transport: Transport | None = None,
        ble_transport: Transport | None = None,
        prefer_ble: bool = False,
    ) -> None:
        """Initialise the device handle with optional initial transports."""
        self.device_id = device_id
        self.device_name = device_name
        self.broker = DeviceMessageBroker()
        self.queue = DeviceCommandQueue()
        self.state_machine = DeviceStateMachine(device_id, initial_device)
        self._availability = DeviceAvailability()
        self._transports: dict[TransportType, Transport] = {}
        self._state_changed_bus: EventBus[DeviceSnapshot] = EventBus()
        self._prefer_ble: bool = prefer_ble

        if mqtt_transport is not None:
            mqtt_transport.on_message = self.broker.on_message
            self._transports[mqtt_transport.transport_type] = mqtt_transport

        if ble_transport is not None:
            ble_transport.on_message = self.broker.on_message
            self._transports[ble_transport.transport_type] = ble_transport

    async def add_transport(self, transport: Transport) -> None:
        """Register a transport (MQTT or BLE). Replaces any existing transport of the same type."""
        existing = self._transports.get(transport.transport_type)
        if existing is not None:
            await existing.disconnect()
        transport.on_message = self.broker.on_message
        self._transports[transport.transport_type] = transport

    async def remove_transport(self, transport_type: TransportType) -> None:
        """Disconnect and remove a transport by type."""
        transport = self._transports.pop(transport_type, None)
        if transport is not None:
            await transport.disconnect()

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
        """Stop the command queue, broker, and disconnect all transports."""
        await self.queue.stop()
        await self.broker.close()
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
