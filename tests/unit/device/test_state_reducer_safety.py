"""Safety state stays unknown until read back; write echoes cannot confirm a setting."""

from __future__ import annotations

import pytest

from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import LubaMsg, MctlNav, NavSysParamMsg
from tests.unit.device._helpers import make_reducer_device


@pytest.mark.parametrize(("param_id", "field"), [(17, "child_safety"), (18, "reverse_safety_mode")])
@pytest.mark.parametrize("enabled", [False, True])
def test_safety_readback_updates_only_the_reported_setting(param_id: int, field: str, enabled: bool) -> None:
    current = make_reducer_device()
    msg = LubaMsg(nav=MctlNav(nav_sys_param_cmd=NavSysParamMsg(id=param_id, rw=0, context=int(enabled))))

    updated = MowerStateReducer().apply(current, msg)

    assert getattr(updated.mower_state, field) is enabled
    assert current.mower_state.child_safety is None
    assert current.mower_state.reverse_safety_mode is None
    other = "reverse_safety_mode" if field == "child_safety" else "child_safety"
    assert getattr(updated.mower_state, other) is None
    assert updated.map is current.map


@pytest.mark.parametrize(("param_id", "field"), [(17, "child_safety"), (18, "reverse_safety_mode")])
@pytest.mark.parametrize("reported", [None, False, True])
@pytest.mark.parametrize("enabled", [False, True])
def test_safety_write_echo_preserves_the_last_readback(
    param_id: int, field: str, reported: bool | None, enabled: bool
) -> None:
    current = make_reducer_device()
    assert getattr(current.mower_state, field) is None
    setattr(current.mower_state, field, reported)
    msg = LubaMsg(nav=MctlNav(nav_sys_param_cmd=NavSysParamMsg(id=param_id, rw=1, context=int(enabled))))

    updated = MowerStateReducer().apply(current, msg)

    assert getattr(updated.mower_state, field) is reported
    assert getattr(current.mower_state, field) is reported
    other = "reverse_safety_mode" if field == "child_safety" else "child_safety"
    assert getattr(updated.mower_state, other) is None
