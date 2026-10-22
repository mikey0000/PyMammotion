"""Autonomous drive speed (nav param 16) arrives in tenths of m/s and is held in m/s."""

from __future__ import annotations

import pytest

from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import LubaMsg, MctlNav, NavSysParamMsg
from tests.unit.device._helpers import make_reducer_device


@pytest.mark.parametrize("rw", [0, 1])
@pytest.mark.parametrize(("context", "speed"), [(0, 0.0), (2, 0.2), (6, 0.6), (10, 1.0)])
def test_nav_param_16_sets_autonomous_drive_speed_in_metres_per_second(rw: int, context: int, speed: float) -> None:
    current = make_reducer_device()
    msg = LubaMsg(nav=MctlNav(nav_sys_param_cmd=NavSysParamMsg(id=16, context=context, rw=rw)))

    updated = MowerStateReducer().apply(current, msg)

    assert updated.mower_state.autonomous_drive_speed == pytest.approx(speed)
    assert current.mower_state.autonomous_drive_speed is None
