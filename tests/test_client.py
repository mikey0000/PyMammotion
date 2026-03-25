"""Tests for MammotionClient (Wave 4 top-level API)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.transport.base import TransportType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mowing_device() -> MagicMock:
    """Return a MagicMock shaped like a MowingDevice."""
    device = MagicMock()
    device.online = True
    device.enabled = True
    device.report_data.dev.battery_val = 75
    device.report_data.dev.sys_status = "idle"
    device.report_data.work.knife_height = 40
    return device


def make_handle(device_id: str = "dev1", device_name: str = "Luba-Test") -> DeviceHandle:
    """Build a real DeviceHandle backed by a mock MowingDevice."""
    return DeviceHandle(
        device_id=device_id,
        device_name=device_name,
        initial_device=make_mowing_device(),
    )


# ---------------------------------------------------------------------------
# test 1: stop() is idempotent
# ---------------------------------------------------------------------------


async def test_stop_is_idempotent() -> None:
    """Calling stop() twice must complete without error and without double-teardown."""
    client = MammotionClient()
    # First call should work fine
    await client.stop()
    # Second call must not raise
    await client.stop()


# ---------------------------------------------------------------------------
# test 2: stop() calls stop() on all registered handles
# ---------------------------------------------------------------------------


async def test_stop_calls_device_handle_stop() -> None:
    """stop() must call stop() on every registered DeviceHandle."""
    client = MammotionClient()

    handle1 = make_handle("dev1", "Mower-A")
    handle2 = make_handle("dev2", "Mower-B")

    handle1.stop = AsyncMock()  # type: ignore[method-assign]
    handle2.stop = AsyncMock()  # type: ignore[method-assign]

    await client._device_registry.register(handle1)
    await client._device_registry.register(handle2)

    await client.stop()

    handle1.stop.assert_awaited_once()
    handle2.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# test 3: remove_device schedules unregister as a task
# ---------------------------------------------------------------------------


async def test_remove_device_schedules_unregister() -> None:
    """remove_device() must schedule a task that eventually unregisters the handle."""
    client = MammotionClient()

    handle = make_handle("dev1", "Luba-One")
    handle.stop = AsyncMock()  # type: ignore[method-assign]
    await client._device_registry.register(handle)

    # Verify handle is present before removal
    assert client._device_registry.get_by_name("Luba-One") is handle

    client.remove_device("Luba-One")

    # Let the scheduled task run
    await asyncio.sleep(0)

    # Handle should now be unregistered (stop was called inside unregister)
    handle.stop.assert_awaited_once()
    assert client._device_registry.get_by_name("Luba-One") is None


# ---------------------------------------------------------------------------
# test 4: get_device_by_name returns None for unknown device
# ---------------------------------------------------------------------------


async def test_get_device_by_name_returns_none_for_unknown() -> None:
    """Unknown device name must return None, not raise."""
    client = MammotionClient()
    result = client.get_device_by_name("nonexistent-mower")
    assert result is None


# ---------------------------------------------------------------------------
# test 5: send_command_with_args raises KeyError for missing device
# ---------------------------------------------------------------------------


async def test_send_command_with_args_raises_for_unknown_device() -> None:
    """send_command_with_args must raise KeyError when device is not registered."""
    client = MammotionClient()

    with pytest.raises(KeyError, match="Device 'ghost-mower' not registered"):
        await client.send_command_with_args("ghost-mower", "start_mow")


# ---------------------------------------------------------------------------
# test 6: add_ble_device calls BLETransportManager.register_external_ble_client
# ---------------------------------------------------------------------------


async def test_add_ble_device_calls_manager() -> None:
    """add_ble_device must delegate to BLETransportManager.register_external_ble_client."""
    client = MammotionClient()

    fake_ble_device = MagicMock()
    client._ble_manager.register_external_ble_client = MagicMock()  # type: ignore[method-assign]

    await client.add_ble_device("dev-xyz", fake_ble_device)

    client._ble_manager.register_external_ble_client.assert_called_once_with("dev-xyz", fake_ble_device)


# ---------------------------------------------------------------------------
# test 7: mower() returns the DeviceHandle (or None for unknown)
# ---------------------------------------------------------------------------


async def test_mower_returns_handle() -> None:
    """mower(name) must return the registered DeviceHandle for that name."""
    client = MammotionClient()

    handle = make_handle("dev1", "Yuka-Prime")
    await client._device_registry.register(handle)

    result = client.mower("Yuka-Prime")
    assert result is handle

    # Unknown name returns None
    assert client.mower("no-such-device") is None


# ---------------------------------------------------------------------------
# test 8: get_device_by_name returns MowingDevice (snapshot.raw)
# ---------------------------------------------------------------------------


async def test_get_device_by_name_returns_mowing_device() -> None:
    """get_device_by_name must return the MowingDevice stored in snapshot.raw."""
    client = MammotionClient()

    handle = make_handle("dev99", "Luba-X")
    await client._device_registry.register(handle)

    result = client.get_device_by_name("Luba-X")
    assert result is handle.snapshot.raw


# ---------------------------------------------------------------------------
# test 9: send_command_with_args succeeds for a registered device (logs, no raise)
# ---------------------------------------------------------------------------


async def test_send_command_with_args_succeeds_for_known_device() -> None:
    """send_command_with_args must complete without error for a registered device."""
    client = MammotionClient()

    mqtt_transport = MagicMock()
    mqtt_transport.transport_type = TransportType.CLOUD_ALIYUN
    mqtt_transport.is_connected = True
    mqtt_transport.send = AsyncMock()

    handle = make_handle("dev1", "Luba-Runner")
    await handle.add_transport(mqtt_transport)
    await client._device_registry.register(handle)

    # Should not raise
    await client.send_command_with_args("Luba-Runner", "start_job")


# ---------------------------------------------------------------------------
# test 10: device_registry and account_registry properties
# ---------------------------------------------------------------------------


async def test_properties_return_correct_objects() -> None:
    """device_registry and account_registry must return the internal instances."""
    client = MammotionClient()

    assert client.device_registry is client._device_registry
    assert client.account_registry is client._account_registry
