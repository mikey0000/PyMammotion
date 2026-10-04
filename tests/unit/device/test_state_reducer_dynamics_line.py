"""The reducer keeps a lidar mower's dynamics line (type 18) and drops it when the job is over."""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import CommDataCouple, PathType
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import (
    CommDataCouple as ProtoCommDataCouple,
    LubaMsg,
    MctlNav,
    MctlSys,
    NavGetCommDataAck,
    ReportInfoData,
    RptDevStatus,
    RptWork,
)
from pymammotion.utility.constant.device_enums import WorkMode

_HASH = 6150000000000000001
_LINE = [CommDataCouple(x=1.0, y=1.0), CommDataCouple(x=2.0, y=2.0)]


def _frame(current: int, total: int, x: float) -> LubaMsg:
    return LubaMsg(
        nav=MctlNav(
            toapp_get_commondata_ack=NavGetCommDataAck(
                action=8,
                type=PathType.DYNAMICS_LINE,
                hash=_HASH,
                current_frame=current,
                total_frame=total,
                data_couple=[ProtoCommDataCouple(x=x, y=x)],
            )
        )
    )


def _report(sys_status: WorkMode, *, ub_path_hash: int) -> LubaMsg:
    return LubaMsg(
        sys=MctlSys(
            toapp_report_data=ReportInfoData(
                dev=RptDevStatus(sys_status=sys_status.value), work=RptWork(ub_path_hash=ub_path_hash, area=122)
            )
        )
    )


def _mower_with_line() -> MowerDevice:
    device = MowerDevice(name="Luba-LA123")
    device.map.dynamics_line = list(_LINE)
    device.map.generated_dynamics_line_geojson = {"features": [{}]}
    return device


def test_a_completed_line_is_drawn_without_waiting_for_a_saga() -> None:
    """Frames the app's own fetch provokes arrive unsolicited and must still produce the drawn line."""
    device = MowerDevice(name="Luba-LA123")
    device.location.RTK.latitude = 0.9
    device.location.RTK.longitude = 0.1
    reducer = MowerStateReducer()

    device = reducer.apply(device, _frame(1, 2, 1.0))
    device = reducer.apply(device, _frame(2, 2, 2.0))

    assert [p.x for p in device.map.dynamics_line] == [1.0, 2.0]
    assert device.map.generated_dynamics_line_geojson["features"]


@pytest.mark.regression
def test_the_line_is_dropped_once_the_job_is_over() -> None:
    """Nothing cleared the line, so the last job's path stayed drawn into the next one.

    HA fetches over the cloud only while no line is drawn, so the new job's line was never
    fetched.  APK ``getDynamicsLine``: not working and ``ub_path_hash == 0`` clears it.
    """
    device = MowerStateReducer().apply(_mower_with_line(), _report(WorkMode.MODE_READY, ub_path_hash=0))

    assert device.map.dynamics_line == []
    assert device.map.generated_dynamics_line_geojson == {}


def test_the_line_is_kept_while_mowing_even_without_a_ub_path_hash() -> None:
    device = MowerStateReducer().apply(_mower_with_line(), _report(WorkMode.MODE_WORKING, ub_path_hash=0))

    assert device.map.dynamics_line == _LINE


def test_the_line_is_kept_after_the_job_while_the_device_still_reports_one() -> None:
    device = MowerStateReducer().apply(_mower_with_line(), _report(WorkMode.MODE_READY, ub_path_hash=1))

    assert device.map.dynamics_line == _LINE
