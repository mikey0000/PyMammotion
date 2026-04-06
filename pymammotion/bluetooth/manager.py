"""BLETransportManager — per-device BLE connection manager with lazy discovery."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any

from pymammotion.transport.base import BLEUnavailableError, NoBLEAddressKnownError, Transport

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)


def _default_transport_factory(device_id: str, ble_device: Any | None, ble_address: str | None) -> Transport:
    """Create a BLETransport using the standard BLETransportConfig."""
    from pymammotion.transport.ble import BLETransport, BLETransportConfig

    config = BLETransportConfig(device_id=device_id, ble_address=ble_address)
    transport = BLETransport(config)
    if ble_device is not None:
        transport.set_ble_device(ble_device)
    return transport


@dataclass
class BLEDeviceEntry:
    """Per-device state tracked by BLETransportManager."""

    device_id: str
    ble_address: str | None = None
    ble_device: Any | None = None  # bleak BLEDevice — Any to avoid hard import
    transport: Transport | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class BLETransportManager:
    """Manages BLE connections for multiple devices.

    Supports two operating modes:
    - External: HA provides a bleak BLEDevice via register_external_ble_client()
    - Internal: CLI/fleet registers a MAC address via register_ble_address(); connection
      is established lazily on first use.

    Each device has its own asyncio.Lock to prevent concurrent connect attempts.
    """

    def __init__(
        self,
        transport_factory: Callable[[str, Any | None, str | None], Transport] | None = None,
    ) -> None:
        """Initialise the manager with an optional transport factory.

        If transport_factory is None, the default factory that creates BLETransport
        instances is used.
        """
        self._entries: dict[str, BLEDeviceEntry] = {}
        self._factory: Callable[[str, Any | None, str | None], Transport] = (
            transport_factory if transport_factory is not None else _default_transport_factory
        )

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def register_external_ble_client(
        self,
        device_id: str,
        ble_device: Any,
    ) -> None:
        """Register a BLE device provided by Home Assistant.

        Creates or updates the entry for device_id with the given BLEDevice.
        Does NOT attempt connection — that happens lazily via get_or_connect().
        """
        if device_id in self._entries:
            self._entries[device_id].ble_device = ble_device
        else:
            self._entries[device_id] = BLEDeviceEntry(device_id=device_id, ble_device=ble_device)
        _logger.debug("BLETransportManager: registered external BLE client for %s", device_id)

    def update_external_ble_client(
        self,
        device_id: str,
        ble_device: Any,
    ) -> None:
        """Update the BLEDevice for an existing entry (called by HA on BLE scanner update)."""
        if device_id not in self._entries:
            self._entries[device_id] = BLEDeviceEntry(device_id=device_id, ble_device=ble_device)
        else:
            self._entries[device_id].ble_device = ble_device
        _logger.debug("BLETransportManager: updated external BLE client for %s", device_id)

    def register_ble_address(
        self,
        device_id: str,
        mac_address: str,
    ) -> None:
        """Register a MAC address for internal scan-based discovery."""
        if device_id in self._entries:
            self._entries[device_id].ble_address = mac_address
        else:
            self._entries[device_id] = BLEDeviceEntry(device_id=device_id, ble_address=mac_address)
        _logger.debug("BLETransportManager: registered BLE address %s for %s", mac_address, device_id)

    # ------------------------------------------------------------------
    # Transport access
    # ------------------------------------------------------------------

    def get_transport(self, device_id: str) -> Transport | None:
        """Return the existing transport for device_id, or None."""
        entry = self._entries.get(device_id)
        if entry is None:
            return None
        return entry.transport

    async def get_or_connect(
        self,
        device_id: str,
    ) -> Transport:
        """Return the Transport for device_id, connecting if needed.

        Raises:
            NoBLEAddressKnownError: No MAC or BLEDevice registered for device_id.
            BLEUnavailableError: Connection attempt failed.

        """
        if device_id not in self._entries:
            msg = f"No BLE address or BLE device registered for device_id={device_id!r}"
            raise NoBLEAddressKnownError(msg)

        entry = self._entries[device_id]

        if entry.ble_device is None and entry.ble_address is None:
            msg = f"No BLE address or BLE device registered for device_id={device_id!r}"
            raise NoBLEAddressKnownError(msg)

        async with entry.lock:
            # Re-check after acquiring the lock — another coroutine may have connected.
            if entry.transport is not None and entry.transport.is_connected:
                return entry.transport

            # If we have a BLE address but no BLE device, scan for it.
            if entry.ble_device is None and entry.ble_address is not None:
                entry.ble_device = await self._scan_for_device(device_id, entry.ble_address)

            transport = self._factory(device_id, entry.ble_device, entry.ble_address)
            try:
                await transport.connect()
            except Exception as exc:
                msg = f"BLE connection failed for device_id={device_id!r}: {exc}"
                raise BLEUnavailableError(msg) from exc

            entry.transport = transport
            return transport

    # ------------------------------------------------------------------
    # Disconnect helpers
    # ------------------------------------------------------------------

    async def disconnect(self, device_id: str) -> None:
        """Disconnect the BLE transport for device_id if connected."""
        entry = self._entries.get(device_id)
        if entry is not None and entry.transport is not None:
            await entry.transport.disconnect()
            entry.transport = None

    async def disconnect_all(self) -> None:
        """Disconnect all managed BLE transports."""
        for device_id in list(self._entries):
            await self.disconnect(device_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _scan_for_device(self, device_id: str, mac_address: str) -> Any:
        """Scan for a BLE device by MAC address using bleak.

        Returns the BLEDevice if found.
        Raises BLEUnavailableError if the device cannot be located.
        """
        try:
            from bleak import BleakScanner

            device = await BleakScanner.find_device_by_address(mac_address)
        except Exception as exc:
            msg = f"BLE scan failed for device_id={device_id!r} mac={mac_address!r}: {exc}"
            raise BLEUnavailableError(msg) from exc

        if device is None:
            msg = f"BLE device not found during scan: device_id={device_id!r} mac={mac_address!r}"
            raise BLEUnavailableError(msg)

        return device
