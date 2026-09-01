"""BleInventory — the BLEDevice cache and BLE-transport placement.

Extracted from MammotionClient, which had no reason to hold a BLE cache alongside
accounts, transports and sagas.  Unlike the auth code it is a real collaborator: it
needed only the device registry and the handle funnel, and owns the
BLETransportManager outright.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pymammotion.device.ble_inventory import BleInventory
from pymammotion.device.handle import DeviceRegistry
from pymammotion.transport.base import TransportType
from pymammotion.transport.ble import BLETransport
from tests.unit._helpers import make_mock_handle


def _inventory() -> tuple[BleInventory, DeviceRegistry, AsyncMock]:
    registry = DeviceRegistry()
    ensure = AsyncMock()
    return BleInventory(registry, ensure), registry, ensure


def test_the_client_no_longer_owns_the_ble_cache() -> None:
    """The manager moved wholesale; the client only reaches it through this object."""
    from pymammotion.client import MammotionClient

    assert not hasattr(MammotionClient, "_ble_manager")
    inventory, _, _ = _inventory()
    assert inventory._manager is not None


def test_get_entry_is_empty_until_a_device_is_seen() -> None:
    inventory, _, _ = _inventory()
    assert inventory.get_entry("dev1") is None


async def test_add_ble_device_caches_the_entry() -> None:
    inventory, _, _ = _inventory()
    ble_device = MagicMock()

    await inventory.add_ble_device("dev1", ble_device, -55)

    entry = inventory.get_entry("dev1")
    assert entry is not None
    assert entry.ble_device is ble_device
    assert entry.rssi == -55


async def test_clear_ble_device_clears_the_transport_not_the_cache() -> None:
    """It forgets the BLEDevice on the *transport* so the next connect waits for a
    fresh advert; the inventory's own cache entry is deliberately left alone."""
    inventory, registry, _ = _inventory()
    await inventory.add_ble_device("dev1", MagicMock(), -55)
    handle = make_mock_handle("dev1", "Luba-1")
    ble = MagicMock(spec=BLETransport)
    handle.get_transport = MagicMock(return_value=ble)  # type: ignore[method-assign]
    registry.find_ble_owner = MagicMock(return_value=handle)  # type: ignore[method-assign]

    await inventory.clear_ble_device("dev1")

    ble.clear_ble_device.assert_called_once()


async def test_clear_ble_device_is_a_noop_without_a_ble_owner() -> None:
    inventory, _, _ = _inventory()
    await inventory.clear_ble_device("never-seen")  # must not raise


async def test_attach_cached_ble_is_a_noop_without_a_cached_device() -> None:
    inventory, registry, _ = _inventory()
    handle = make_mock_handle("dev1", "Luba-1")
    await registry.register(handle, "acct")

    await inventory.attach_cached_ble(handle, "dev1")  # must not raise

    assert handle.get_transport(TransportType.BLE) is None


async def test_attach_cached_ble_skips_a_device_another_handle_already_owns() -> None:
    """Exactly one handle owns a device's BLETransport (DeviceRegistry.find_ble_owner)."""
    inventory, registry, _ = _inventory()
    await inventory.add_ble_device("dev1", MagicMock(), -55)
    owner = make_mock_handle("dev1", "Luba-1")
    await registry.register(owner, "acct")
    registry.find_ble_owner = MagicMock(return_value=owner)  # type: ignore[method-assign]

    second = make_mock_handle("dev1", "Luba-1")
    await inventory.attach_cached_ble(second, "dev1")

    assert second.get_transport(TransportType.BLE) is None
