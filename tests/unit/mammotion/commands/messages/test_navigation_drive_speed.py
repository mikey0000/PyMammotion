"""Autonomous drive speed (param 16) goes out on nav in tenths of m/s, as the app's slider sends it."""

from __future__ import annotations

import pytest
import time_machine

from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg, MsgCmdType

X5 = "Luba-VA000001"


def test_read_autonomous_drive_speed_reads_param_16_with_context_0() -> None:
    """``readAutonomousDriveSpeed`` sends ``allpowerfullRW(16, 0, 0)``."""
    with time_machine.travel("2026-01-01", tick=False):
        msg = LubaMsg().parse(MammotionCommand(X5, 1).read_autonomous_drive_speed())

    assert msg.msgtype == MsgCmdType.NAV
    param = msg.nav.nav_sys_param_cmd
    assert (param.id, param.context, param.rw) == (16, 0, 0)


@pytest.mark.parametrize(("speed", "tenths"), [(0.2, 2), (0.6, 6), (0.57, 6), (0.29, 3), (1.0, 10)])
def test_set_autonomous_drive_speed_sends_tenths_of_a_metre_per_second(speed: float, tenths: int) -> None:
    """The app sends ``Math.round(speedMs * 10)``."""
    with time_machine.travel("2026-01-01", tick=False):
        msg = LubaMsg().parse(MammotionCommand(X5, 1).set_autonomous_drive_speed(speed))

    assert msg.msgtype == MsgCmdType.NAV
    param = msg.nav.nav_sys_param_cmd
    assert (param.id, param.context, param.rw) == (16, tenths, 1)
