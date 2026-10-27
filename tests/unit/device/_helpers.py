"""Shared builders for the device-package unit tests."""

from __future__ import annotations

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import AreaHashNameList
from pymammotion.device.handle import DeviceHandle


def make_reducer_device() -> MowerDevice:
    """Return the baseline mower the state-reducer tests apply messages to."""
    device = MowerDevice(name="Luba-Test")
    device.map.area_name = [AreaHashNameList(name="zone-1", hash=111)]
    return device


def make_handle(device_name: str = "Luba-Test") -> DeviceHandle:
    """Return an unstarted DeviceHandle over a real, empty MowerDevice."""
    return DeviceHandle(
        device_id=f"dev-{device_name}",
        device_name=device_name,
        initial_device=MowerDevice(name=device_name),
    )
