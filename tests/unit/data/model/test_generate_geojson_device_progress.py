"""``apply_device_mow_progress_geojson`` — mow progress built from a device's latest report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.generate_geojson import apply_device_mow_progress_geojson
from pymammotion.data.model.hash_list import MowPath
from pymammotion.utility.constant.device_enums import WorkMode

_FIXTURE = Path(__file__).parents[3] / "fixtures" / "yuka_fixture.json"


def _device(sys_status: WorkMode) -> MowerDevice:
    """Return a device holding the Yuka fixture's full cover path, with an RTK fix."""
    fixture = json.loads(_FIXTURE.read_text())
    device = MowerDevice(name=fixture["update_check"]["device_name"])
    device.location.RTK.latitude = 0.3
    device.location.RTK.longitude = fixture["location"]["RTK"]["longitude"]
    for frames in fixture["map"]["current_mow_path"].values():
        for frame in frames.values():
            device.map.update_mow_path(MowPath.from_dict(frame))
    device.report_data.dev.sys_status = sys_status.value
    return device


@pytest.mark.parametrize(
    "sys_status",
    [WorkMode.MODE_WORKING, WorkMode.MODE_PAUSE, WorkMode.MODE_RETURNING, WorkMode.MODE_CHARGING_PAUSE],
)
def test_builds_while_a_job_is_in_progress(sys_status: WorkMode) -> None:
    """Paused and returning still show progress — the cover path often lands after the mower stopped."""
    device = _device(sys_status)

    apply_device_mow_progress_geojson(device)

    assert device.map.generated_mow_progress_geojson["features"]


@pytest.mark.parametrize("sys_status", [WorkMode.MODE_READY, WorkMode.MODE_CHARGING, WorkMode.MODE_UPDATING])
def test_skips_outside_a_job(sys_status: WorkMode) -> None:
    """No progress is drawn once the job is over."""
    device = _device(sys_status)

    apply_device_mow_progress_geojson(device)

    assert device.map.generated_mow_progress_geojson == {}
