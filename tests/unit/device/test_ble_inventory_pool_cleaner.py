"""A pool cleaner can be registered over BLE alone.

``add_ble_only_device`` passes ``initial_device`` straight through to the
handle, which already accepts the base ``Device`` and picks its reducer from
the device *name* — so a Spino gets the pool reducer.  Only the annotation said
``MowingDevice``, which stopped a host offering BLE-only setup for one
(Mammotion-HA: a Spino can only be added through the cloud).
"""

from __future__ import annotations

import inspect

from pymammotion.data.model.device import Device, MowingDevice, PoolCleanerDevice
from pymammotion.device.ble_inventory import BleInventory
from pymammotion.device.state_reducer import PoolStateReducer, get_state_reducer


def test_the_registration_call_accepts_any_device_kind() -> None:
    """A PoolCleanerDevice is not a MowingDevice; the annotation excluded it."""
    annotation = inspect.signature(BleInventory.add_ble_only_device).parameters[
        "initial_device"
    ].annotation
    assert annotation in (Device, "Device")


def test_a_spino_name_selects_the_pool_reducer() -> None:
    """What makes BLE-only Spino viable: the reducer follows the name, not the cloud."""
    reducer = get_state_reducer("Spino-E1C36JT4", "", is_saga_active=lambda: False)
    assert isinstance(reducer, PoolStateReducer)


def test_a_mower_name_still_selects_its_own_reducer() -> None:
    """The widening must not blur the two apart."""
    reducer = get_state_reducer("Luba-VS123456", "", is_saga_active=lambda: False)
    assert not isinstance(reducer, PoolStateReducer)


def test_both_device_models_share_the_base_the_handle_takes() -> None:
    """DeviceHandle has always taken Device; only these two hops were narrower."""
    assert issubclass(PoolCleanerDevice, Device)
    assert issubclass(MowingDevice, Device)
