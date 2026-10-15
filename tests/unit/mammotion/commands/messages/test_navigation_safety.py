"""Safety builders select the parameter carrier by mower type; hardware support is tested separately."""

from __future__ import annotations

import pytest
import time_machine

from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg, MsgCmdType, MsgDevice


@pytest.mark.parametrize(
    ("device_name", "on_nav"), [("Luba-ABCDEF", False), ("Luba-VS6ABCDE", True), ("Yuka-MN12345", True)]
)
@pytest.mark.parametrize(("command", "param_id"), [("read_child_safety", 17), ("read_reverse_safety_mode", 18)])
def test_safety_read_uses_model_parameter_carrier(device_name: str, on_nav: bool, command: str, param_id: int) -> None:
    with time_machine.travel("2026-01-01", tick=False):
        msg = LubaMsg().parse(getattr(MammotionCommand(device_name, 1), command)())

    assert msg.msgtype == (MsgCmdType.NAV if on_nav else MsgCmdType.EMBED_SYS)
    assert msg.rcver == (MsgDevice.DEV_NAVIGATION if on_nav else MsgDevice.DEV_MAINCTL)
    assert (msg.sys is None) is on_nav
    assert (msg.nav is None) is not on_nav
    param = msg.nav.nav_sys_param_cmd if on_nav else msg.sys.bidire_comm_cmd
    assert (param.id, param.rw, param.context) == (param_id, 0, 0)


@pytest.mark.parametrize(
    ("device_name", "on_nav"), [("Luba-ABCDEF", False), ("Luba-VS6ABCDE", True), ("Yuka-MN12345", True)]
)
@pytest.mark.parametrize(("command", "param_id"), [("set_child_safety", 17), ("set_reverse_safety_mode", 18)])
@pytest.mark.parametrize("enabled", [False, True])
def test_safety_write_uses_model_parameter_carrier(
    device_name: str, on_nav: bool, command: str, param_id: int, enabled: bool
) -> None:
    with time_machine.travel("2026-01-01", tick=False):
        msg = LubaMsg().parse(getattr(MammotionCommand(device_name, 1), command)(enabled=enabled))

    assert msg.msgtype == (MsgCmdType.NAV if on_nav else MsgCmdType.EMBED_SYS)
    assert msg.rcver == (MsgDevice.DEV_NAVIGATION if on_nav else MsgDevice.DEV_MAINCTL)
    assert (msg.sys is None) is on_nav
    assert (msg.nav is None) is not on_nav
    param = msg.nav.nav_sys_param_cmd if on_nav else msg.sys.bidire_comm_cmd
    assert (param.id, param.rw, param.context) == (param_id, 1, int(enabled))
