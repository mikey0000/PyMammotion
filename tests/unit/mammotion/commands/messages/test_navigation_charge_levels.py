"""Recharge / resume battery levels: ``nav_sys_param_cmd`` ids 14 and 15, as the app's Battery page sends them.

APK: ``MACommandHelper.get/setRechargeAndContinueWorking`` always build ``MctlNav.nav_sys_param_cmd``
(no ``bidire_comm_cmd`` routing); the RN page bounds the sliders 15-30 and 40-100 and sends -1 for smart.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pymammotion.data.model.device_info import SMART_CHARGE_LEVEL
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg, MsgCmdType, NavSysParamMsg


def _sys_param(payload: bytes) -> NavSysParamMsg:
    msg = LubaMsg().parse(payload)
    assert msg.msgtype == MsgCmdType.NAV
    assert msg.nav.nav_sys_param_cmd is not None
    return msg.nav.nav_sys_param_cmd


def _command() -> MammotionCommand:
    return MammotionCommand("Luba-VS6ABCDE", 1)


@pytest.mark.parametrize(
    ("build", "param_id"),
    [(MammotionCommand.read_recharge_level, 14), (MammotionCommand.read_resume_level, 15)],
    ids=["recharge", "resume"],
)
def test_reading_a_level_sends_its_id_with_rw_zero(build: Callable[[MammotionCommand], bytes], param_id: int) -> None:
    param = _sys_param(build(_command()))
    assert (param.id, param.rw, param.context) == (param_id, 0, 0)


@pytest.mark.parametrize(
    ("build", "param_id", "level"),
    [
        (MammotionCommand.set_recharge_level, 14, 15),
        (MammotionCommand.set_recharge_level, 14, 30),
        (MammotionCommand.set_recharge_level, 14, SMART_CHARGE_LEVEL),
        (MammotionCommand.set_resume_level, 15, 40),
        (MammotionCommand.set_resume_level, 15, 100),
        (MammotionCommand.set_resume_level, 15, SMART_CHARGE_LEVEL),
    ],
)
def test_setting_a_level_writes_it_as_the_context(
    build: Callable[[MammotionCommand, int], bytes], param_id: int, level: int
) -> None:
    param = _sys_param(build(_command(), level))
    assert (param.id, param.rw, param.context) == (param_id, 1, level)


@pytest.mark.parametrize(
    ("build", "level"),
    [
        (MammotionCommand.set_recharge_level, 14),
        (MammotionCommand.set_recharge_level, 31),
        (MammotionCommand.set_recharge_level, 0),
        (MammotionCommand.set_resume_level, 39),
        (MammotionCommand.set_resume_level, 101),
        (MammotionCommand.set_resume_level, 0),
    ],
)
def test_a_level_outside_the_apps_slider_is_refused(
    build: Callable[[MammotionCommand, int], bytes], level: int
) -> None:
    with pytest.raises(ValueError, match=rf"^charge level {level} is neither smart"):
        build(_command(), level)
