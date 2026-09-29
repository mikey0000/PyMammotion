"""Tests for MowingDevice JSON serialization with int-keyed HashList fields."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pymammotion.data.model.device import Device, MowerDevice, MowingDevice, RTKBaseStationDevice, create_device
from pymammotion.data.model.enums import FuseLocalizationStatus, TaskAreaStatus
from pymammotion.data.model.hash_list import FrameList, HashList, MowPath, NavGetCommData
from pymammotion.http.model.http import CheckDeviceVersion
from pymammotion.proto import SystemUpdateBufMsg


def _make_hash_list_with_int_keys() -> HashList:
    hl = HashList()
    hl.area[12345] = FrameList(total_frame=2, sub_cmd=0, data=[NavGetCommData(hash=12345)])
    hl.obstacle[99999] = FrameList(total_frame=1, sub_cmd=1)
    hl.path[77777] = FrameList(total_frame=3, sub_cmd=2)
    hl.current_mow_path[1] = {0: MowPath(area=12345, total_frame=1)}
    return hl


def test_mowing_device_to_json_with_int_keys() -> None:
    """MowingDevice.to_json() must not raise when HashList has int-keyed dicts."""
    device = MowingDevice(name="test-device")
    device.map = _make_hash_list_with_int_keys()

    json_str = device.to_json()
    assert isinstance(json_str, str)

    data = json.loads(json_str)
    # orjson serialises int keys as strings in JSON (the JSON spec requires string keys)
    assert "12345" in data["map"]["area"]
    assert "99999" in data["map"]["obstacle"]
    assert "77777" in data["map"]["path"]
    assert "1" in data["map"]["current_mow_path"]


def test_mowing_device_to_jsonb_with_int_keys() -> None:
    """MowingDevice.to_jsonb() must not raise and return bytes."""
    device = MowingDevice(name="test-device")
    device.map = _make_hash_list_with_int_keys()

    raw = device.to_jsonb()
    assert isinstance(raw, bytes)
    assert b"12345" in raw


def test_empty_mowing_device_roundtrip() -> None:
    """Empty MowingDevice serialises and deserialises cleanly."""
    device = MowingDevice(name="empty")
    json_str = device.to_json()
    assert json_str
    data = json.loads(json_str)
    assert data["name"] == "empty"


# The OTA check (CheckDeviceVersion.current_version) is the cloud's view of the installed firmware.

def _check(version: str, *, device_id: str = "iot-1") -> CheckDeviceVersion:
    return CheckDeviceVersion(current_version=version, device_id=device_id)


def test_mower_seeds_device_version() -> None:
    device = MowerDevice(name="Luba-VS123")
    check = _check("1.12.0.466")
    device.apply_version_check(check)
    assert device.update_check is check
    assert device.device_firmwares.device_version == "1.12.0.466"


def test_rtk_seeds_device_version() -> None:
    device = RTKBaseStationDevice(name="RTK-abc")
    device.apply_version_check(_check("3.0.1"))
    assert device.device_firmwares.device_version == "3.0.1"


def test_empty_current_version_does_not_overwrite() -> None:
    device = MowerDevice(name="Luba-VS123")
    device.device_firmwares.device_version = "1.12.0.466"
    device.apply_version_check(_check(""))  # empty cloud value
    assert device.device_firmwares.device_version == "1.12.0.466"  # preserved


def test_base_device_without_firmware_field_is_safe() -> None:
    # Base Device has update_check but no device_firmwares — must not raise.
    device = Device(name="x")
    device.apply_version_check(_check("9.9.9"))
    assert device.update_check.current_version == "9.9.9"


def test_seeds_version_feeds_detection_gate() -> None:
    # End-to-end: OTA version flows into the firmware-gated obstacle options.
    from pymammotion.data.model.mowing_modes import DetectionStrategy

    device = create_device("Luba-VS123", "a1pvCnb3PPu")
    device.apply_version_check(_check("1.11.0"))  # below the 1.12.0 threshold
    options = DetectionStrategy.for_device(device.name, device.device_firmwares.device_version)
    assert DetectionStrategy.slow_touch in options  # old-firmware option set


def _task_areas(*pairs: int) -> SystemUpdateBufMsg:
    return SystemUpdateBufMsg(update_buf_data=[3, 0, len(pairs) // 2, *pairs])


@pytest.mark.regression
def test_the_task_area_placeholder_hash_is_not_a_zone() -> None:
    """A Luba 3 sitting idle sent ``[3, 0, 1, 1, 2]``: one zone, hash ``1``, mowing.

    ``1`` is the device's "no hash" placeholder (as for ``path_hash``), but it was
    stored as a zone of the task, so Home Assistant showed a "Task area" sensor
    with no job running.
    """
    device = MowerDevice(name="Luba-VAME9R5S")

    device.buffer(_task_areas(1, 2))

    assert device.events.work_tasks_event.ids == []
    assert device.events.work_tasks_event.hash_area_map == {}


def test_real_zones_are_kept_beside_the_placeholder() -> None:
    zone = 8377881458226819852
    device = MowerDevice(name="Luba-VAME9R5S")

    device.buffer(_task_areas(1, 2, zone, 1))

    assert device.events.work_tasks_event.ids == [zone]
    assert device.events.work_tasks_event.hash_area_map == {zone: TaskAreaStatus.WAITING}


#: ``tests/data``: saved HA states from before the positioning properties existed (location and IMEI zeroed).
_DATA = Path(__file__).parents[3] / "data"


def test_a_saved_luba_3_state_loads_and_reads_its_fuse_byte() -> None:
    """``vslam_status`` 257 stored as a plain int is RTK fixed, so the LiDAR row reads Good."""
    device = MowingDevice.from_dict(json.loads((_DATA / "saved_state_luba_3.json").read_text()))

    assert device.report_data.dev.fuse_localization_status is FuseLocalizationStatus.RTK_FIXED
    assert device.report_data.dev.lidar_positioning_ok is True


def test_a_saved_luba_2_state_loads() -> None:
    """Saved before any report arrived: only its identity is non-default."""
    device = MowingDevice.from_dict(json.loads((_DATA / "saved_state_luba_2.json").read_text()))

    assert device.mower_state.product_key == "a1LLmy1zc0j"
    assert device.report_data.dev.fuse_localization_status is FuseLocalizationStatus.NO_POSE
