"""Tests for WorkMode, device_mode and the breakpoint-reason table.

Values mirror the APK's DeviceWorkState enum (2.3.8.201,
device/source/device/enums/DeviceWorkState.java:5-38) and the breakpoint-flag
switch in map/fragment/BaseMapFragment.java:2400-2558.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.report_info import WorkData
from pymammotion.utility.constant import NO_REQUEST_MODES, BreakPointReason, WorkMode, device_mode

# Every value the APK's DeviceWorkState models, with its member name here.
APK_WORK_STATES = {
    0: "MODE_NOT_ACTIVE",
    1: "MODE_ONLINE",
    2: "MODE_OFFLINE",
    8: "MODE_DISABLE",
    10: "MODE_INITIALIZATION",
    11: "MODE_READY",
    12: "MODE_UNCONNECTED",
    13: "MODE_WORKING",
    14: "MODE_RETURNING",
    15: "MODE_CHARGING",
    16: "MODE_UPDATING",
    17: "MODE_LOCK",
    18: "MODE_SYSTEM_ERROR",
    19: "MODE_PAUSE",
    20: "MODE_MANUAL_MOWING",
    22: "MODE_UPDATE_SUCCESS",
    23: "MODE_OTA_UPGRADE_FAIL",
    31: "MODE_JOB_DRAW",
    32: "MODE_OBSTACLE_DRAW",
    34: "MODE_CHANNEL_DRAW",
    35: "MODE_ERASER_DRAW",
    36: "MODE_EDIT_BOUNDARY",  # the APK calls this MODE_SECOND_EDIT
    37: "MODE_LOCATION_ERROR",
    38: "MODE_BOUNDARY_JUMP",
    39: "MODE_CHARGING_PAUSE",
    43: "MODE_AUTO_ERASER_DRAW",
    44: "MODE_CORRIDOR_DRAW",
    45: "MODE_CORRIDOR_WORKING",
    46: "MODE_CORRIDOR_PAUSE",
    47: "MODE_CORRIDOR_RETURNING",
    48: "MODE_SLEEPING",
    50: "MODE_RESET_CHARGE",
    51: "MODE_BACKING_UP",
    52: "MODE_RECOVERY",
}


@pytest.mark.parametrize(("value", "name"), APK_WORK_STATES.items())
def test_work_mode_matches_apk(value: int, name: str) -> None:
    assert WorkMode(value).name == name


def test_unmodelled_status_does_not_raise() -> None:
    """sys_status is wire-coerced, so a newer firmware value must not crash."""
    assert WorkMode(199) is WorkMode.UNKNOWN
    assert device_mode(199) == "Invalid mode"


def test_unknown_sentinel_is_not_reported_as_a_mode_name() -> None:
    assert device_mode(WorkMode.UNKNOWN.value) == "Invalid mode"


@pytest.mark.parametrize(
    "mode",
    [
        WorkMode.MODE_SLEEPING,
        WorkMode.MODE_AUTO_ERASER_DRAW,
        WorkMode.MODE_CORRIDOR_DRAW,
        WorkMode.MODE_BACKING_UP,
        WorkMode.MODE_RECOVERY,
    ],
)
def test_modes_that_must_not_be_polled(mode: WorkMode) -> None:
    """Planning, storage rewrites and sleep all reject unsolicited polls."""
    assert mode in NO_REQUEST_MODES


def test_no_request_modes_has_no_duplicates() -> None:
    assert len(NO_REQUEST_MODES) == len(set(NO_REQUEST_MODES))


# bp_info wire code -> reason, from the APK's breakpoint-flag switch.
APK_BREAK_POINT_FLAGS = {
    -1: BreakPointReason.NONE,
    0: BreakPointReason.NONE,
    2: BreakPointReason.NONE,
    6: BreakPointReason.NONE,
    1: BreakPointReason.PAUSED_MANUALLY,
    15: BreakPointReason.PAUSED_MANUALLY,
    3: BreakPointReason.BLADE_FAULT,
    20: BreakPointReason.BLADE_FAULT,
    4: BreakPointReason.STUCK,
    21: BreakPointReason.STUCK,
    5: BreakPointReason.OUTSIDE_BOUNDARY,
    7: BreakPointReason.NEEDS_POSITIONING,
    8: BreakPointReason.NEEDS_CHARGE,
    9: BreakPointReason.BUMPER_DISCONNECTED,
    10: BreakPointReason.LOW_BATTERY,
    14: BreakPointReason.LOW_BATTERY,
    11: BreakPointReason.RAIN,
    12: BreakPointReason.POWERED_OFF,
    13: BreakPointReason.AUTO_POSITIONING,
    16: BreakPointReason.AUTO_POSITIONING,
    18: BreakPointReason.SCHEDULE_WINDOW_ENDED,
    19: BreakPointReason.RESUME_PAUSED,
}


@pytest.mark.parametrize(("flag", "reason"), APK_BREAK_POINT_FLAGS.items())
def test_break_point_reason_decodes_apk_flags(flag: int, reason: BreakPointReason) -> None:
    assert BreakPointReason(flag) is reason


def test_break_point_reason_unmodelled_flag() -> None:
    """17 is skipped by the APK switch, so it must fall through, not raise."""
    assert BreakPointReason(17) is BreakPointReason.UNKNOWN


def test_break_point_unknown_sentinel_is_not_minus_one() -> None:
    """-1 is a real 'no breakpoint' code (asserted above), so it can't be the sentinel."""
    assert BreakPointReason.UNKNOWN.value != -1


def test_work_data_exposes_the_reason() -> None:
    assert WorkData(bp_info=11).break_point_reason is BreakPointReason.RAIN
    assert WorkData().break_point_reason is BreakPointReason.NONE
