"""The lamp set reply carries the manual light's new state in its acked set id."""

from __future__ import annotations

import pytest

from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import LubaMsg, Setlamprsp, SocMul
from tests.unit.device._helpers import make_reducer_device


@pytest.mark.parametrize(
    ("was_on", "set_ids", "expected"),
    [
        pytest.param(False, 1125, True, id="on_ack"),
        pytest.param(True, 1127, False, id="off_ack"),
    ],
)
def test_set_lamp_rsp_updates_manual_light(was_on: bool, set_ids: int, expected: bool) -> None:
    """The acked set id is the manual light's new state, as in the app.

    The reply was dropped, so ``manual_light`` kept its pre-command value and
    Home Assistant's switch fell back a few seconds after being turned on
    (Mammotion-HA #964).
    """
    current = make_reducer_device()
    current.mower_state.lamp_info.manual_light = was_on
    msg = LubaMsg(mul=SocMul(set_lamp_rsp=Setlamprsp(set_ids=set_ids, result=0)))

    updated = MowerStateReducer().apply(current, msg)

    assert updated.mower_state.lamp_info.manual_light is expected
    assert current.mower_state.lamp_info.manual_light is was_on


@pytest.mark.parametrize(
    ("set_ids", "result"),
    [
        pytest.param(1125, 1, id="rejected_manual_on"),
        pytest.param(1121, 0, id="night_light_ack"),
    ],
)
def test_set_lamp_rsp_leaves_manual_light_alone(set_ids: int, result: int) -> None:
    """A rejected set, or the night light's ack, says nothing about the manual light."""
    msg = LubaMsg(mul=SocMul(set_lamp_rsp=Setlamprsp(set_ids=set_ids, result=result)))

    updated = MowerStateReducer().apply(make_reducer_device(), msg)

    assert updated.mower_state.lamp_info.manual_light is False
    assert updated.mower_state.lamp_info.night_light is False
