"""``MessageSystem`` battery charge-limit commands mirror the app's ``BmsCtrlInfoMsg`` usage (issue #857)."""

from __future__ import annotations

import betterproto2

from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import BmsCtrlInfoMsg, LubaMsg, MsgAttr, MsgCmdType


def _bms_info(payload: bytes) -> tuple[LubaMsg, BmsCtrlInfoMsg]:
    msg = LubaMsg().parse(payload)
    name, value = betterproto2.which_one_of(msg.sys, "SubSysMsg")
    assert name == "bms_ctrl_info_msg"
    return msg, value


def test_query_battery_info_probes_with_minus_one_switches() -> None:
    """The probe sends both switches as -1 so the device replies instead of writing."""
    msg, info = _bms_info(MammotionCommand("Luba-VS6ABCDE", 1).query_battery_info())
    assert msg.msgtype == MsgCmdType.EMBED_SYS
    assert msg.msgattr == MsgAttr.REQ
    assert (info.smart_charge_switch, info.peak_valley_charge_switch) == (-1, -1)
    assert info.charge_soc_threshold == 0


def test_set_battery_info_custom_limit_uses_inverted_smart_switch() -> None:
    """A fixed limit is smart_charge_switch=1 with the requested threshold and off-peak window."""
    _, info = _bms_info(
        MammotionCommand("Luba-VS6ABCDE", 1).set_battery_info(
            smart_charge=False,
            charge_limit=85,
            peak_valley_charge=True,
            valley_charge_start_time=1320,
            valley_charge_end_time=360,
        )
    )
    assert info.smart_charge_switch == 1
    assert info.charge_soc_threshold == 85
    assert info.peak_valley_charge_switch == 1
    assert (info.valley_charge_start_time, info.valley_charge_end_time) == (1320, 360)


def test_set_battery_info_smart_forces_threshold_to_100() -> None:
    """The app overwrites the threshold with 100 whenever smart charging is on."""
    _, info = _bms_info(MammotionCommand("Luba-VS6ABCDE", 1).set_battery_info(smart_charge=True, charge_limit=80))
    assert info.smart_charge_switch == 0
    assert info.charge_soc_threshold == 100
    assert info.peak_valley_charge_switch == 0
