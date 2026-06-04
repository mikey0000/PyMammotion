"""Tests for BLETransportManager (BLEDevice cache only).

The manager's connection-management responsibilities (lazy scan / connect /
retry) were removed in favour of ``BLETransport.self_managed_scanning`` —
the canonical "give me a connected transport" path now goes through
``MammotionClient.add_ble_only_device(...)`` and ``BLETransport.connect()``,
which fire the availability listener that drives ``_on_ble_connected``.

What remains here is a minimal cache so callers can hand off a ``BLEDevice``
before the corresponding ``DeviceHandle`` is registered.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from pymammotion.bluetooth.manager import BLEDeviceEntry, BLETransportManager


def test_register_external_creates_entry() -> None:
    manager = BLETransportManager()
    fake_device = MagicMock()
    manager.register_external_ble_client("dev1", fake_device)

    assert "dev1" in manager._entries  # noqa: SLF001
    entry = manager._entries["dev1"]  # noqa: SLF001
    assert entry.device_id == "dev1"
    assert entry.ble_device is fake_device


def test_update_external_updates_ble_device() -> None:
    manager = BLETransportManager()
    device_v1 = MagicMock(name="dev_v1")
    device_v2 = MagicMock(name="dev_v2")

    manager.register_external_ble_client("dev1", device_v1)
    manager.update_external_ble_client("dev1", device_v2)

    assert manager._entries["dev1"].ble_device is device_v2  # noqa: SLF001


def test_update_external_creates_entry_if_missing() -> None:
    manager = BLETransportManager()
    fake_device = MagicMock()
    manager.update_external_ble_client("new_dev", fake_device)

    assert "new_dev" in manager._entries  # noqa: SLF001
    assert manager._entries["new_dev"].ble_device is fake_device  # noqa: SLF001


def test_get_ble_device_returns_cached() -> None:
    manager = BLETransportManager()
    fake_device = MagicMock()
    manager.register_external_ble_client("dev1", fake_device)

    assert manager.get_ble_device("dev1") is fake_device


def test_get_ble_device_returns_none_for_unknown() -> None:
    manager = BLETransportManager()
    assert manager.get_ble_device("unknown") is None


def test_ble_device_entry_minimal_fields() -> None:
    """BLEDeviceEntry only carries device_id and ble_device after the cleanup."""
    entry = BLEDeviceEntry(device_id="dev1")
    assert entry.device_id == "dev1"
    assert entry.ble_device is None
