"""``work`` (the running job's route settings) follows the job's lifecycle.

From a real run and cancel on a Luba 2: the job started with
``bidire_reqconver_path.job_id = 17905445326500320``; cancelling marked both
zones 5 (ABORTED) in the task-area buffer while the mower headed home in a job
status, then reports showed ``path_hash 1`` with no route.
"""

from __future__ import annotations

from pymammotion.data.model.device import MowerDevice
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import (
    LubaMsg,
    MctlNav,
    MctlSys,
    NavReqCoverPath,
    ReportInfoData,
    RptDevStatus,
    RptWork,
    SystemUpdateBufMsg,
)
from pymammotion.utility.constant.device_enums import WorkMode

_JOB_ID = 17905445326500320
_ZONES = [9054591478795832665, 7095723005866681215]


def _route_settings() -> LubaMsg:
    return LubaMsg(nav=MctlNav(bidire_reqconver_path=NavReqCoverPath(job_id=_JOB_ID, sub_cmd=4, zone_hashs=_ZONES)))


def _zone_states(*statuses: int) -> LubaMsg:
    data = [3, 0, len(statuses)]
    for zone, status in zip(_ZONES, statuses, strict=True):
        data += [zone, status]
    return LubaMsg(sys=MctlSys(system_update_buf=SystemUpdateBufMsg(update_buf_data=data)))


def _report(sys_status: WorkMode, *, path_hash: int, ub_path_hash: int = 0) -> LubaMsg:
    return LubaMsg(
        sys=MctlSys(
            toapp_report_data=ReportInfoData(
                dev=RptDevStatus(sys_status=sys_status.value),
                work=RptWork(path_hash=path_hash, ub_path_hash=ub_path_hash, area=122),
            )
        )
    )


def _running() -> tuple[MowerStateReducer, MowerDevice]:
    reducer = MowerStateReducer()
    device = reducer.apply(MowerDevice(name="Luba-VS563L6H"), _route_settings())
    return reducer, device


def test_route_settings_start_the_job() -> None:
    _reducer, device = _running()

    assert device.work.job_id == _JOB_ID


def test_every_zone_aborted_ends_the_job() -> None:
    """A cancel empties ``work`` straight away, though the mower is still heading home."""
    reducer, device = _running()

    device = reducer.apply(device, _zone_states(5, 5))

    assert device.work.job_id == 0
    assert device.events.work_tasks_event.ids == []


def test_a_partly_aborted_job_keeps_running() -> None:
    """Only a job with no zone left is over."""
    reducer, device = _running()

    device = reducer.apply(device, _zone_states(5, 2))

    assert device.work.job_id == _JOB_ID


def test_a_report_mid_job_keeps_the_job() -> None:
    reducer, device = _running()

    device = reducer.apply(device, _report(WorkMode.MODE_RETURNING, path_hash=1))

    assert device.work.job_id == _JOB_ID


def test_a_report_with_no_job_ends_it() -> None:
    """Out of a job status with no route: the job id goes too, not just the zones."""
    reducer, device = _running()

    device = reducer.apply(device, _report(WorkMode.MODE_READY, path_hash=1))

    assert device.work.job_id == 0


def test_a_paused_resumable_job_is_kept() -> None:
    """Ready with a route still reported is a resumable job, not a finished one."""
    reducer, device = _running()

    device = reducer.apply(device, _report(WorkMode.MODE_READY, path_hash=1, ub_path_hash=2925952933437268886))

    assert device.work.job_id == _JOB_ID


def test_the_report_keeps_its_plan_field() -> None:
    """``rpt_work.plan`` used to be dropped: the model called it ``path``."""
    reducer = MowerStateReducer()
    msg = LubaMsg(sys=MctlSys(toapp_report_data=ReportInfoData(work=RptWork(plan=7))))

    device = reducer.apply(MowerDevice(name="Luba-VS563L6H"), msg)

    assert device.report_data.work.plan == 7
