"""BLETransportManager — caches BLEDevices keyed by device_id for the live BLETransport.

This manager is intentionally minimal: it stores the latest ``BLEDevice``
provided by an external source (HA's bluetooth integration, a manual scan, …)
so that ``MammotionClient.add_ble_device`` and ``update_ble_device`` have a
canonical place to record per-device state independent of whether a
``DeviceHandle`` exists yet.

The standalone "give me a connected transport" entry point lives on
``MammotionClient.add_ble_only_device(...)`` and ``BLETransport.connect()``
with ``self_managed_scanning=True`` — both go through ``DeviceHandle``,
which is the only path that wires the availability listeners required for
the canonical ``_on_ble_connected`` lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass
class BLEDeviceEntry:
    """Per-device state tracked by BLETransportManager."""

    device_id: str
    ble_device: Any | None = None  # bleak BLEDevice — Any to avoid hard import
    rssi: int | None = None


class BLETransportManager:
    """Stores externally-provided BLEDevices keyed by device_id.

    Managed lifecycle (connect, scan, retry, cooldown) lives on
    :class:`~pymammotion.transport.ble.BLETransport` itself.  This class is
    only a registry for the latest ``BLEDevice`` so that callers who don't
    yet have a ``DeviceHandle`` registered can hand off the object.
    """

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._entries: dict[str, BLEDeviceEntry] = {}

    def register_external_ble_client(self, device_id: str, ble_device: Any, rssi: int | None = None) -> None:
        """Record the latest BLEDevice (and advertisement RSSI) for *device_id*.

        Creates or updates the entry.  Does not attempt connection.
        """
        if (entry := self._entries.get(device_id)) is None:
            self._entries[device_id] = BLEDeviceEntry(device_id=device_id, ble_device=ble_device, rssi=rssi)
        else:
            entry.ble_device = ble_device
            entry.rssi = rssi
        _logger.debug("BLETransportManager: registered external BLE client for %s", device_id)

    def update_external_ble_client(self, device_id: str, ble_device: Any, rssi: int | None = None) -> None:
        """Update the BLEDevice for an existing entry (or create one)."""
        self.register_external_ble_client(device_id, ble_device, rssi)

    def get_entry(self, device_id: str) -> BLEDeviceEntry | None:
        """Return the cached entry for *device_id*, or None."""
        return self._entries.get(device_id)

    def get_ble_device(self, device_id: str) -> Any | None:
        """Return the cached BLEDevice for device_id, or None."""
        entry = self._entries.get(device_id)
        return entry.ble_device if entry is not None else None
