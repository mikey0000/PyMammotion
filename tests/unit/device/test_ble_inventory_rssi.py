"""``add_ble_to_device`` must be able to carry the advertisement RSSI.

``BLETransport.is_usable`` fails closed below ``min_rssi``, and only a stronger
RSSI clears it.  Hosts push every advertisement through this call, so dropping
the RSSI here latched a transport unusable for good once the mower had been
seen weakly on its way out of range (HA issue #889's sibling report).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from bleak.backends.device import BLEDevice

from pymammotion.device.ble_inventory import BleInventory
from pymammotion.transport.base import TransportType
from pymammotion.transport.ble import BLETransport, BLETransportConfig


def _ble_device(address: str = "AA:BB:CC:DD:EE:FF") -> BLEDevice:
    return BLEDevice(address=address, name="Luba-TEST", details=None)


def _transport(device: BLEDevice) -> BLETransport:
    transport = BLETransport(BLETransportConfig(device_id="Luba-TEST"))
    transport.set_ble_device(device, -95)
    return transport


def test_a_weak_signal_makes_the_transport_unusable() -> None:
    """The gate that the lost RSSI used to leave latched."""
    transport = _transport(_ble_device())
    assert transport.is_usable is False


def test_a_stronger_advertisement_makes_it_usable_again() -> None:
    """set_ble_device is the only way back, and only when given an RSSI."""
    transport = _transport(_ble_device())
    transport.set_ble_device(_ble_device(), -55)
    assert transport.is_usable is True


def test_refreshing_without_an_rssi_leaves_the_gate_closed() -> None:
    """Why the parameter had to be threaded through rather than defaulted."""
    transport = _transport(_ble_device())
    transport.set_ble_device(_ble_device())
    assert transport.is_usable is False


async def test_add_ble_to_device_forwards_the_rssi() -> None:
    """The host-facing call reaches set_ble_device with the RSSI it was given."""
    device = _ble_device()
    transport = _transport(device)
    handle = MagicMock()
    handle.get_transport.return_value = transport
    handle.device_id = "Luba-TEST"

    inventory = BleInventory.__new__(BleInventory)
    inventory._device_registry = MagicMock()  # noqa: SLF001
    inventory._device_registry.get_by_name.return_value = handle  # noqa: SLF001

    await inventory.add_ble_to_device("Luba-TEST", _ble_device(), None, -55)

    handle.get_transport.assert_called_with(TransportType.BLE)
    assert transport.is_usable is True
