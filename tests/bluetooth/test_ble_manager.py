"""Tests for BLETransportManager."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.bluetooth.manager import BLEDeviceEntry, BLETransportManager
from pymammotion.transport.base import BLEUnavailableError, NoBLEAddressKnownError, Transport


def _make_mock_transport(connected: bool = False) -> AsyncMock:
    """Return an AsyncMock that satisfies the Transport interface."""
    mock = AsyncMock(spec=Transport)
    mock.is_connected = connected
    mock.connect = AsyncMock()
    mock.disconnect = AsyncMock()
    return mock


def _make_factory(transport: AsyncMock):
    """Return a transport factory that always returns the given mock."""
    def factory(device_id: str, ble_device: object, ble_address: object) -> Transport:
        return transport  # type: ignore[return-value]

    return factory


# ---------------------------------------------------------------------------
# 1. register_external_ble_client stores entry
# ---------------------------------------------------------------------------


def test_register_external_creates_entry() -> None:
    manager = BLETransportManager()
    fake_device = MagicMock()
    manager.register_external_ble_client("dev1", fake_device)

    assert "dev1" in manager._entries
    entry = manager._entries["dev1"]
    assert entry.device_id == "dev1"
    assert entry.ble_device is fake_device
    assert entry.ble_address is None
    assert entry.transport is None


# ---------------------------------------------------------------------------
# 2. update_external_ble_client replaces BLEDevice
# ---------------------------------------------------------------------------


def test_update_external_updates_ble_device() -> None:
    manager = BLETransportManager()
    device_v1 = MagicMock(name="dev_v1")
    device_v2 = MagicMock(name="dev_v2")

    manager.register_external_ble_client("dev1", device_v1)
    manager.update_external_ble_client("dev1", device_v2)

    assert manager._entries["dev1"].ble_device is device_v2


def test_update_external_creates_entry_if_missing() -> None:
    manager = BLETransportManager()
    fake_device = MagicMock()
    manager.update_external_ble_client("new_dev", fake_device)

    assert "new_dev" in manager._entries
    assert manager._entries["new_dev"].ble_device is fake_device


# ---------------------------------------------------------------------------
# 3. register_ble_address stores MAC
# ---------------------------------------------------------------------------


def test_register_ble_address_stores_mac() -> None:
    manager = BLETransportManager()
    manager.register_ble_address("dev1", "AA:BB:CC:DD:EE:FF")

    assert "dev1" in manager._entries
    entry = manager._entries["dev1"]
    assert entry.ble_address == "AA:BB:CC:DD:EE:FF"
    assert entry.ble_device is None


# ---------------------------------------------------------------------------
# 4. get_transport returns None before connect
# ---------------------------------------------------------------------------


def test_get_transport_returns_none_before_connect() -> None:
    manager = BLETransportManager()
    manager.register_external_ble_client("dev1", MagicMock())

    result = manager.get_transport("dev1")
    assert result is None


def test_get_transport_returns_none_for_unknown_device() -> None:
    manager = BLETransportManager()
    assert manager.get_transport("unknown") is None


# ---------------------------------------------------------------------------
# 5. get_or_connect raises NoBLEAddressKnownError when nothing registered
# ---------------------------------------------------------------------------


async def test_get_or_connect_raises_when_no_ble_known() -> None:
    manager = BLETransportManager()

    with pytest.raises(NoBLEAddressKnownError):
        await manager.get_or_connect("nonexistent")


async def test_get_or_connect_raises_when_entry_has_no_device_or_address() -> None:
    manager = BLETransportManager()
    # Manually insert a bare entry with neither device nor address
    manager._entries["bare"] = BLEDeviceEntry(device_id="bare")

    with pytest.raises(NoBLEAddressKnownError):
        await manager.get_or_connect("bare")


# ---------------------------------------------------------------------------
# 6. get_or_connect uses per-device lock (concurrent calls don't both connect)
# ---------------------------------------------------------------------------


async def test_get_or_connect_uses_per_device_lock() -> None:
    """Two concurrent get_or_connect calls should result in only one connect() call."""
    connect_calls = 0
    connected_flag = False

    async def slow_connect() -> None:
        nonlocal connect_calls, connected_flag
        connect_calls += 1
        await asyncio.sleep(0)  # yield to allow other coroutines to run
        connected_flag = True

    mock_transport = AsyncMock(spec=Transport)
    mock_transport.connect = slow_connect

    # After the first connect, is_connected must return True so the second
    # coroutine (which re-checks under the lock) sees it connected.
    type(mock_transport).is_connected = property(lambda self: connected_flag)

    manager = BLETransportManager(transport_factory=_make_factory(mock_transport))
    manager.register_external_ble_client("dev1", MagicMock())

    # Run two concurrent get_or_connect calls
    results = await asyncio.gather(
        manager.get_or_connect("dev1"),
        manager.get_or_connect("dev1"),
    )

    # Both should return the same transport
    assert results[0] is mock_transport
    assert results[1] is mock_transport
    # connect() should have been called only once
    assert connect_calls == 1


# ---------------------------------------------------------------------------
# 7. disconnect_all calls transport.disconnect
# ---------------------------------------------------------------------------


async def test_disconnect_all_calls_disconnect() -> None:
    mock_t1 = _make_mock_transport(connected=True)
    mock_t2 = _make_mock_transport(connected=True)

    manager = BLETransportManager()
    manager._entries["dev1"] = BLEDeviceEntry(device_id="dev1", transport=mock_t1)
    manager._entries["dev2"] = BLEDeviceEntry(device_id="dev2", transport=mock_t2)

    await manager.disconnect_all()

    mock_t1.disconnect.assert_awaited_once()
    mock_t2.disconnect.assert_awaited_once()
    assert manager._entries["dev1"].transport is None
    assert manager._entries["dev2"].transport is None


# ---------------------------------------------------------------------------
# Additional: disconnect single device
# ---------------------------------------------------------------------------


async def test_disconnect_single_device() -> None:
    mock_t = _make_mock_transport(connected=True)
    manager = BLETransportManager()
    manager._entries["dev1"] = BLEDeviceEntry(device_id="dev1", transport=mock_t)

    await manager.disconnect("dev1")

    mock_t.disconnect.assert_awaited_once()
    assert manager._entries["dev1"].transport is None


async def test_disconnect_unknown_device_is_noop() -> None:
    manager = BLETransportManager()
    # Should not raise
    await manager.disconnect("ghost")


# ---------------------------------------------------------------------------
# Additional: successful get_or_connect with external BLE device
# ---------------------------------------------------------------------------


async def test_get_or_connect_external_connects_and_returns_transport() -> None:
    mock_transport = _make_mock_transport(connected=False)
    # After connect is called, report as connected
    mock_transport.connect.side_effect = lambda: setattr(mock_transport, "is_connected", True)

    manager = BLETransportManager(transport_factory=_make_factory(mock_transport))
    manager.register_external_ble_client("dev1", MagicMock())

    result = await manager.get_or_connect("dev1")

    assert result is mock_transport
    mock_transport.connect.assert_awaited_once()
    assert manager.get_transport("dev1") is mock_transport


# ---------------------------------------------------------------------------
# Additional: get_or_connect wraps connection errors in BLEUnavailableError
# ---------------------------------------------------------------------------


async def test_get_or_connect_wraps_connect_error() -> None:
    mock_transport = _make_mock_transport()
    mock_transport.connect.side_effect = OSError("radio off")

    manager = BLETransportManager(transport_factory=_make_factory(mock_transport))
    manager.register_external_ble_client("dev1", MagicMock())

    with pytest.raises(BLEUnavailableError, match="radio off"):
        await manager.get_or_connect("dev1")


# ---------------------------------------------------------------------------
# Additional: internal scan mode — BleakScanner.find_device_by_address called
# ---------------------------------------------------------------------------


async def test_get_or_connect_internal_mode_scans_for_device() -> None:
    fake_ble_device = MagicMock(name="found_device")
    mock_transport = _make_mock_transport()

    captured: dict[str, object] = {}

    def factory(device_id: str, ble_device: object, ble_address: object) -> Transport:
        captured["ble_device"] = ble_device
        return mock_transport  # type: ignore[return-value]

    manager = BLETransportManager(transport_factory=factory)
    manager.register_ble_address("dev1", "AA:BB:CC:DD:EE:FF")

    # Patch the lazy import inside _scan_for_device by replacing the bleak module in sys.modules
    mock_bleak = MagicMock()
    mock_bleak.BleakScanner.find_device_by_address = AsyncMock(return_value=fake_ble_device)
    with patch.dict("sys.modules", {"bleak": mock_bleak}):
        result = await manager.get_or_connect("dev1")

    assert result is mock_transport
    assert captured["ble_device"] is fake_ble_device


async def test_get_or_connect_internal_mode_raises_when_device_not_found() -> None:
    manager = BLETransportManager()
    manager.register_ble_address("dev1", "AA:BB:CC:DD:EE:FF")

    with patch.dict("sys.modules", {"bleak": MagicMock(BleakScanner=MagicMock(
        find_device_by_address=AsyncMock(return_value=None)
    ))}):
        with pytest.raises(BLEUnavailableError, match="not found"):
            await manager.get_or_connect("dev1")
