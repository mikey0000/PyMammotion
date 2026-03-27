"""BLETransport — concrete Transport wrapping bleak for Mammotion BLE devices."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from pymammotion.bluetooth.const import UUID_NOTIFICATION_CHARACTERISTIC, UUID_WRITE_CHARACTERISTIC
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

_logger = logging.getLogger(__name__)


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
    """

    on_message: Callable[[bytes], Awaitable[None]] | None = None

    def __init__(self, config: BLETransportConfig) -> None:
        """Initialise the transport with the supplied configuration."""
        self._config = config
        self._ble_device: BLEDevice | None = None
        self._client: BleakClientWithServiceCache | None = None
        self._availability: TransportAvailability = TransportAvailability.DISCONNECTED
        self._disconnect_on_idle: bool = True

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
        )

        await self._client.start_notify(UUID_NOTIFICATION_CHARACTERISTIC, self._notification_handler)
        await self._notify_availability(TransportAvailability.CONNECTED)
        _logger.debug("BLETransport connected to %s", self._config.device_id)

    async def disconnect(self) -> None:
        """Gracefully disconnect the BLE client."""
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()
        self._client = None
        await self._notify_availability(TransportAvailability.DISCONNECTED)

    async def send(self, payload: bytes, iot_id: str = "") -> None:
        """Write payload to the GATT write characteristic.

        Raises TransportError if not connected.
        """
        if self._client is None or not self._client.is_connected:
            msg = "BLETransport is not connected; cannot send payload"
            raise TransportError(msg)
        await self._client.write_gatt_char(UUID_WRITE_CHARACTERISTIC, payload, response=False)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    async def _notify_availability(self, state: TransportAvailability) -> None:
        """Update internal state and notify the availability callback."""
        self._availability = state
        if self.on_availability_changed is not None:
            try:
                await self.on_availability_changed(state)
            except Exception:
                _logger.exception("on_availability_changed callback failed")

    def _handle_disconnect(self, _client: Any) -> None:
        """Handle unexpected disconnect reported by bleak."""
        _logger.warning("BLETransport: device %s disconnected", self._config.device_id)
        self._availability = TransportAvailability.DISCONNECTED
        # Fire availability callback from sync context
        if self.on_availability_changed is not None:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.on_availability_changed(TransportAvailability.DISCONNECTED))
            except RuntimeError:
                pass

    async def _notification_handler(self, _characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle incoming BLE notifications and forward to on_message."""
        if self.on_message is not None:
            await self.on_message(bytes(data))
