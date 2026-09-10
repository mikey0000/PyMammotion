"""Shared builders for the device-package unit tests."""

from __future__ import annotations

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import AreaHashNameList


def make_reducer_device() -> MowerDevice:
    """Return the baseline mower the state-reducer tests apply messages to."""
    device = MowerDevice(name="Luba-Test")
    device.map.area_name = [AreaHashNameList(name="zone-1", hash=111)]
    return device
