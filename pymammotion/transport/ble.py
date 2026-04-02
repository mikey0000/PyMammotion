"""BLETransport — concrete Transport wrapping bleak for Mammotion BLE devices."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from pymammotion.bluetooth.const import UUID_NOTIFICATION_CHARACTERISTIC
from pymammotion.transport.base import (
    NoBLEAddressKnownError,
    Transport,
    TransportAvailability,
    TransportError,
    TransportType,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bleak import BLEDevice
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from pymammotion.bluetooth.ble_message import BleMessage

_logger = logging.getLogger(__name__)

# How long between periodic BLE keepalive syncs (seconds) — matches the working
# MammotionBaseBLEDevice implementation.
_BLE_SYNC_INTERVAL = 130


@dataclass(frozen=True)
class BLETransportConfig:
    """Frozen configuration for a BLETransport instance."""

    device_id: str
    ble_address: str | None = None


class BLETransport(Transport):
    """Concrete Transport wrapping bleak for Mammotion BLE devices.

    A BLEDevice must be supplied via set_ble_device() before calling connect().
    Incoming BLE notifications are forwarded to the on_message callback set by
    the broker layer.

    Outbound payloads are framed via BleMessage.post_custom_data_bytes() which
    applies the BluFi packet header, sequence numbering, and fragmentation
    required by the Mammotion BLE protocol.  Inbound notifications are
    reassembled by BleMessage.parseNotification() before being forwarded.
    """

    on_message: Callable[[bytes], Awaitable[None]] | None = None

    def __init__(self, config: BLETransportConfig) -> None:
        """Initialise the transport with the supplied configuration."""
        super().__init__()
        self._config = config
        self._ble_device: BLEDevice | None = None
        self._client: BleakClientWithServiceCache | None = None
        self._message: BleMessage | None = None
        self._availability: TransportAvailability = TransportAvailability.DISCONNECTED
        self._disconnect_on_idle: bool = True
        self._ble_sync_task: asyncio.TimerHandle | None = None

    # ------------------------------------------------------------------
    # Public device management
    # ------------------------------------------------------------------

    def set_ble_device(self, device: BLEDevice) -> None:
        """Supply (or update) the bleak BLEDevice used for the next connect()."""
        self._ble_device = device

    def set_disconnect_strategy(self, *, disconnect: bool = True) -> None:
        """Set whether the BLE connection should be dropped when the device is idle.

        When disconnect=True (default) the transport will disconnect after
        commands complete, reducing power consumption.  When disconnect=False
        the connection is kept alive (suitable for stay-connected-Bluetooth mode).
        """
        self._disconnect_on_idle = disconnect

    # ------------------------------------------------------------------
    # Transport ABC
    # ------------------------------------------------------------------

    @property
    def transport_type(self) -> TransportType:
        """Return the transport type for this implementation."""
        return TransportType.BLE

    @property
    def is_connected(self) -> bool:
        """True when the bleak client exists and reports itself connected."""
        return self._client is not None and self._client.is_connected

    @property
    def availability(self) -> TransportAvailability:
        """Current availability state of this transport."""
        return self._availability

    async def connect(self) -> None:
        """Establish the BLE connection and start receiving notifications.

        Raises NoBLEAddressKnownError if no BLEDevice has been registered.
        """
        if self._ble_device is None:
            msg = f"No BLEDevice registered for device_id={self._config.device_id!r}; call set_ble_device() first"
            raise NoBLEAddressKnownError(msg)

        if self.is_connected:
            _logger.debug("BLETransport.connect() called while already connected — ignoring")
            return

        await self._notify_availability(TransportAvailability.CONNECTING)
        _logger.debug("BLETransport connecting to %s", self._config.device_id)

        self._client = await establish_connection(
            BleakClientWithServiceCache,
            self._ble_device,
            self._config.device_id,
            self._handle_disconnect,
            max_attempts=10,
            ble_device_callback=lambda: self._ble_device,  # type: ignore[arg-type,return-value]
        )

        from pymammotion.bluetooth.ble_message import BleMessage

        self._message = BleMessage(self._client)

        await self._client.start_notify(UUID_NOTIFICATION_CHARACTERISTIC, self._notification_handler)
        await self._notify_availability(TransportAvailability.CONNECTED)
        _logger.debug("BLETransport connected to %s", self._config.device_id)

        await self._ble_sync()
        self._schedule_ble_sync()

    async def disconnect(self) -> None:
        """Gracefully disconnect the BLE client."""
        self._cancel_ble_sync()
        if self._client is not None and self._client.is_connected:
            await self._ble_sync()
            await self._client.disconnect()
        self._client = None
        self._message = None
        await self._notify_availability(TransportAvailability.DISCONNECTED)

    async def send(self, payload: bytes, iot_id: str = "") -> None:
        """Frame and write payload via the BleMessage codec.

        Raises TransportError if not connected.
        """
        if self._client is None or not self._client.is_connected or self._message is None:
            msg = "BLETransport is not connected; cannot send payload"
            raise TransportError(msg)
        _logger.debug("BLETransport send: %d bytes to %s", len(payload), self._config.device_id)
        await self._message.post_custom_data_bytes(payload)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    async def _notify_availability(self, state: TransportAvailability) -> None:
        """Update internal state and notify all availability listeners."""
        self._availability = state
        await self._fire_availability_listeners(state)

    def _handle_disconnect(self, _client: Any) -> None:
        """Handle unexpected disconnect reported by bleak."""
        _logger.warning("BLETransport: device %s disconnected", self._config.device_id)
        self._cancel_ble_sync()
        self._message = None
        self._availability = TransportAvailability.DISCONNECTED
        if self._availability_listeners:
            import asyncio as _asyncio

            try:
                loop = _asyncio.get_running_loop()
                loop.create_task(self._fire_availability_listeners(TransportAvailability.DISCONNECTED))
            except RuntimeError:
                pass

    async def _notification_handler(self, _characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Parse incoming BLE notifications through the BluFi codec and forward complete frames."""
        if self._message is None:
            return

        result = self._message.parseNotification(data)
        if result != 0:
            # result == 1  → fragment received, waiting for more
            # result == 2  → duplicate sequence, already processed
            # result < 0   → parse error
            return

        payload = await self._message.parseBlufiNotifyData(True)
        self._message.clear_notification()

        if payload and self.on_message is not None:
            await self.on_message(bytes(payload))

    # ------------------------------------------------------------------
    # BLE keepalive sync
    # ------------------------------------------------------------------

    async def _ble_sync(self) -> None:
        """Send a BLE sync keepalive to the device."""
        if self._client is None or not self._client.is_connected or self._message is None:
            return
        from pymammotion.mammotion.commands.mammotion_command import MammotionCommand

        command_bytes = MammotionCommand(self._config.device_id, 0).send_todev_ble_sync(2)
        await self._message.post_custom_data_bytes(command_bytes)

    def _schedule_ble_sync(self) -> None:
        """Schedule the next periodic BLE sync."""
        if not self.is_connected:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._ble_sync_task = loop.call_later(
            _BLE_SYNC_INTERVAL,
            lambda: asyncio.ensure_future(self._run_periodic_sync()),
        )

    async def _run_periodic_sync(self) -> None:
        """Send BLE sync and reschedule."""
        try:
            await self._ble_sync()
        finally:
            self._schedule_ble_sync()

    def _cancel_ble_sync(self) -> None:
        """Cancel any pending BLE sync timer."""
        if self._ble_sync_task is not None:
            self._ble_sync_task.cancel()
            self._ble_sync_task = None
