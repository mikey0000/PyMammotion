"""The report model: ``ReportData.update`` frame mapping, the ``DeviceData`` bit-field accessors and parsed times."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pymammotion.data.model.enums import FuseLocalizationStatus
from pymammotion.data.model.report_info import DeviceData, ReportData, WorkSessionResult
from pymammotion.proto import ReportInfoData, RptTextureMapInfo, RptWork


def test_update_carries_the_work_reports_texture_map_file_hash() -> None:
    report = ReportData()

    report.update(ReportInfoData(work=RptWork(texture_map_info=RptTextureMapInfo(file_hash="abc"))))

    assert report.work.texture_map_info.file_hash == "abc"


#: ``vslam_status`` from the user's devices: every Luba 3 and a settled Luba 2 / Yuka, and a Luba 2 whose
#: RTK fix was being extended (fuse 2) with full vision survival.
_RTK_FIXED_FRAME = 257  # 0x00000101
_RTK_EXTENDED_FRAME = 0x640201


def test_the_luba_3_s_real_frame_is_a_good_lidar_fix() -> None:
    """The app's "LiDAR Positioning: Good" is fuse byte 1 (``refreshRadarStatusUI``)."""
    dev = DeviceData(vslam_status=_RTK_FIXED_FRAME)

    assert dev.fuse_localization_status is FuseLocalizationStatus.RTK_FIXED
    assert dev.lidar_positioning_ok is True


def test_an_extended_fix_carries_its_vision_survival_percent() -> None:
    dev = DeviceData(vslam_status=_RTK_EXTENDED_FRAME)

    assert dev.fuse_localization_status is FuseLocalizationStatus.RTK_EXTENDED_VISION
    assert dev.vision_survival == 100
    assert dev.lidar_positioning_ok is False


@pytest.mark.parametrize("fuse", [2, 3])
def test_vision_survival_is_reported_while_vision_extends_the_fix(fuse: int) -> None:
    """The app shows the survival bar only for kRTkExtended and kVisionExtended."""
    assert DeviceData(vslam_status=(40 << 16) | (fuse << 8)).vision_survival == 40


@pytest.mark.parametrize("fuse", [0, 1, 4, 5])
def test_vision_survival_is_none_outside_a_vision_extension(fuse: int) -> None:
    """A stale byte from an earlier extension must not read as a live percentage."""
    assert DeviceData(vslam_status=(40 << 16) | (fuse << 8)).vision_survival is None


@pytest.mark.parametrize("fuse", [5, 0xFF])
def test_an_unnamed_fuse_byte_is_unknown_and_not_a_good_fix(fuse: int) -> None:
    dev = DeviceData(vslam_status=fuse << 8)

    assert dev.fuse_localization_status is FuseLocalizationStatus.UNKNOWN
    assert dev.lidar_positioning_ok is False


def test_work_session_times_parse_to_utc() -> None:
    session = WorkSessionResult(start_work_time=1_725_159_492, end_work_time=1_725_163_092)
    assert session.started_at == datetime(2024, 9, 1, 2, 58, 12, tzinfo=UTC)
    assert session.ended_at == datetime(2024, 9, 1, 3, 58, 12, tzinfo=UTC)


def test_work_session_times_are_none_before_a_session_has_been_reported() -> None:
    session = WorkSessionResult()
    assert (session.started_at, session.ended_at) == (None, None)
