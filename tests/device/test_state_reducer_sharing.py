"""Verifies the sub-tree sharing contract in MowerStateReducer (#125).

Each nav sub-message's ``apply()`` case only deep-copies the sub-trees its
handler actually mutates.  Fields that are not copied must be shared by
identity between ``current`` and the returned snapshot; copied fields must
be distinct instances so mutations through one do not leak to the other.
"""

from __future__ import annotations

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import AreaHashNameList
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import (
    LubaMsg,
    MctlNav,
    NavGetAllPlanTask,
    NavReqCoverPath,
    NavSysParamMsg,
    NavUnableTimeSet,
)

_ALL_FIELDS = ("map", "work", "mower_state", "non_work_hours", "work_session_result")


def _make_device() -> MowerDevice:
    device = MowerDevice(name="Luba-Test")
    device.map.area_name = [AreaHashNameList(name="zone-1", hash=111)]
    return device


def _assert_sharing(
    current: MowerDevice, updated: MowerDevice, copied_fields: tuple[str, ...]
) -> None:
    """Fields in copied_fields must be distinct; others must share identity."""
    for name in _ALL_FIELDS:
        current_val = getattr(current, name)
        updated_val = getattr(updated, name)
        if name in copied_fields:
            assert updated_val is not current_val, (
                f"{name} was declared as copied but still shares identity with current"
            )
        else:
            assert updated_val is current_val, (
                f"{name} was not declared as copied but was deep-copied anyway"
            )


def test_nav_sys_param_cmd_only_copies_mower_state() -> None:
    reducer = MowerStateReducer()
    current = _make_device()
    msg = LubaMsg(nav=MctlNav(nav_sys_param_cmd=NavSysParamMsg(id=3, context=1)))
    updated = reducer.apply(current, msg)
    _assert_sharing(current, updated, copied_fields=("mower_state",))
    assert updated.mower_state.rain_detection is True
    assert current.mower_state.rain_detection is False


def test_unable_time_set_only_copies_non_work_hours() -> None:
    reducer = MowerStateReducer()
    current = _make_device()
    msg = LubaMsg(
        nav=MctlNav(
            todev_unable_time_set=NavUnableTimeSet(
                sub_cmd=1, unable_start_time="22:00", unable_end_time="06:00"
            )
        )
    )
    updated = reducer.apply(current, msg)
    _assert_sharing(current, updated, copied_fields=("non_work_hours",))
    assert updated.non_work_hours.start_time == "22:00"
    assert current.non_work_hours.start_time == ""


def test_all_plan_task_only_copies_map() -> None:
    reducer = MowerStateReducer()
    current = _make_device()
    msg = LubaMsg(nav=MctlNav(all_plan_task=NavGetAllPlanTask(tasks=[])))
    updated = reducer.apply(current, msg)
    _assert_sharing(current, updated, copied_fields=("map",))


def test_bidire_reqconver_path_copies_nothing_but_rebinds_work() -> None:
    """bidire_reqconver_path wholesale-rebinds device.work — no prior deep-copy needed."""
    reducer = MowerStateReducer()
    current = _make_device()
    original_work = current.work
    msg = LubaMsg(nav=MctlNav(bidire_reqconver_path=NavReqCoverPath(job_mode=1)))
    updated = reducer.apply(current, msg)
    # Nothing was deep-copied (work was rebuilt by the handler, not pre-copied)
    assert updated.map is current.map
    assert updated.mower_state is current.mower_state
    assert updated.non_work_hours is current.non_work_hours
    assert updated.work_session_result is current.work_session_result
    # But device.work was rebuilt by the handler and current.work is untouched
    assert updated.work is not original_work
    assert current.work is original_work


