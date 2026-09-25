"""Mow progress rebuilt by ``MowerStateReducer`` when a cover path completes outside a saga."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import MowPath
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import CoverPathUploadT, LubaMsg, MctlNav
from pymammotion.utility.constant.device_enums import WorkMode

_FIXTURE = Path(__file__).parents[2] / "fixtures" / "yuka_fixture.json"


def _device_missing_last_frame(sys_status: WorkMode) -> tuple[MowerDevice, dict]:
    """Return a device holding every cover-path frame but the last, plus that last frame's raw dict."""
    fixture = json.loads(_FIXTURE.read_text())
    device = MowerDevice(name=fixture["update_check"]["device_name"])
    device.location.RTK.latitude = fixture["location"]["RTK"]["latitude"]
    device.location.RTK.longitude = fixture["location"]["RTK"]["longitude"]
    device.report_data.dev.sys_status = sys_status.value
    frames = [frame for tx in fixture["map"]["current_mow_path"].values() for frame in tx.values()]
    for frame in frames[:-1]:
        device.map.update_mow_path(MowPath.from_dict(frame))
    return device, frames[-1]


def _cover_path_msg(frame: dict) -> LubaMsg:
    return LubaMsg(nav=MctlNav(cover_path_upload=CoverPathUploadT.from_dict(MowPath.from_dict(frame).to_dict())))


@pytest.mark.parametrize("sys_status", [WorkMode.MODE_WORKING, WorkMode.MODE_PAUSE, WorkMode.MODE_RETURNING])
def test_unrequested_cover_path_completing_builds_progress(sys_status: WorkMode) -> None:
    """Frames another client requested still produce progress once the path is complete.

    The position watcher alone never rebuilds it when the path lands after the mower paused.
    """
    device, last_frame = _device_missing_last_frame(sys_status)

    updated = MowerStateReducer().apply(device, _cover_path_msg(last_frame))

    assert not updated.map.find_missing_mow_path_frames()
    assert updated.map.generated_mow_path_geojson["features"]
    assert updated.map.generated_mow_progress_geojson["features"]


def test_cover_path_completing_outside_a_job_builds_no_progress() -> None:
    device, last_frame = _device_missing_last_frame(WorkMode.MODE_CHARGING)

    updated = MowerStateReducer().apply(device, _cover_path_msg(last_frame))

    assert updated.map.generated_mow_path_geojson["features"]
    assert updated.map.generated_mow_progress_geojson == {}


def test_cover_path_completing_during_a_saga_defers_to_the_saga() -> None:
    device, last_frame = _device_missing_last_frame(WorkMode.MODE_PAUSE)

    updated = MowerStateReducer(is_saga_active=lambda: True).apply(device, _cover_path_msg(last_frame))

    assert updated.map.generated_mow_progress_geojson == {}
