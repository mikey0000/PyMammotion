"""Safety settings use navigation registers 17/18, including on the cloud command path."""

from __future__ import annotations

import pytest
import time_machine

from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg, MsgCmdType, MsgDevice


@pytest.mark.parametrize("device_name", ["Luba-VS6ABCDE", "Yuka-MN12345"])
@pytest.mark.parametrize(("command", "param_id"), [("read_child_safety", 17), ("read_reverse_safety_mode", 18)])
def test_safety_read_uses_navigation_register(device_name: str, command: str, param_id: int) -> None:
    with time_machine.travel("2026-01-01", tick=False):
        msg = LubaMsg().parse(getattr(MammotionCommand(device_name, 1), command)())

    assert msg.msgtype == MsgCmdType.NAV
    assert msg.rcver == MsgDevice.DEV_NAVIGATION
    assert msg.sys is None
    param = msg.nav.nav_sys_param_cmd
    assert (param.id, param.rw, param.context) == (param_id, 0, 0)


@pytest.mark.parametrize("device_name", ["Luba-VS6ABCDE", "Yuka-MN12345"])
@pytest.mark.parametrize(("command", "param_id"), [("set_child_safety", 17), ("set_reverse_safety_mode", 18)])
@pytest.mark.parametrize("enabled", [False, True])
def test_safety_write_uses_navigation_register(device_name: str, command: str, param_id: int, enabled: bool) -> None:
    with time_machine.travel("2026-01-01", tick=False):
        msg = LubaMsg().parse(getattr(MammotionCommand(device_name, 1), command)(enabled=enabled))

    assert msg.msgtype == MsgCmdType.NAV
    assert msg.rcver == MsgDevice.DEV_NAVIGATION
    assert msg.sys is None
    param = msg.nav.nav_sys_param_cmd
    assert (param.id, param.rw, param.context) == (param_id, 1, int(enabled))
