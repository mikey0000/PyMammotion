"""A ``todev_taskctrl_ack`` acknowledges a job command; the mode comes from reports.

From a resume on a Luba 2 AWD 5000X: the ack carried ``nav_state 13`` (WORKING)
100 ms after ``resume_execute_task``, the next report still said ``sys_status 19``
(PAUSE), and WORKING was only reported 15 s later, once the route was rebuilt.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import (
    LubaMsg,
    MctlNav,
    MctlSys,
    NavTaskCtrlAck,
    ReportInfoData,
    RptDevStatus,
)
from pymammotion.utility.constant.device_enums import WorkMode

#: ``type`` and ``action`` of the ack captured after ``resume_execute_task``.
_RESUME_ACK_TYPE = 1
_RESUME_ACK_ACTION = 3


def _ack(nav_state: WorkMode) -> LubaMsg:
    return LubaMsg(
        nav=MctlNav(
            todev_taskctrl_ack=NavTaskCtrlAck(
                type=_RESUME_ACK_TYPE, action=_RESUME_ACK_ACTION, nav_state=nav_state.value
            )
        )
    )


def _report(sys_status: WorkMode) -> LubaMsg:
    return LubaMsg(sys=MctlSys(toapp_report_data=ReportInfoData(dev=RptDevStatus(sys_status=sys_status.value))))


def _paused() -> tuple[MowerStateReducer, MowerDevice]:
    reducer = MowerStateReducer()
    device = reducer.apply(MowerDevice(name="Luba-VPF44DJ7"), _report(WorkMode.MODE_PAUSE))
    return reducer, device


@pytest.mark.regression
def test_a_resume_ack_does_not_report_the_mower_working() -> None:
    """The ack's ``nav_state`` was written to ``sys_status``.

    It is the mode the mower is heading to, so after a resume the mower showed
    WORKING, then PAUSE again on the next report, for the 15 s it took to start.
    """
    reducer, device = _paused()

    device = reducer.apply(device, _ack(WorkMode.MODE_WORKING))

    assert device.report_data.dev.sys_status == WorkMode.MODE_PAUSE
