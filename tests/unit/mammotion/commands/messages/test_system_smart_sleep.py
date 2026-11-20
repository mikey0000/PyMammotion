"""``MessageSystem`` Smart Sleep commands mirror the app's ``dev_low_power_*`` usage."""

from __future__ import annotations

import betterproto2
import pytest

from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import DevLowPowerGet, DevLowPowerSetInfo, LubaMsg, MsgAttr, MsgCmdType

_DEVICE = "Luba-VA6ABCDE"


def _sys_message(payload: bytes) -> tuple[LubaMsg, str, object]:
    msg = LubaMsg().parse(payload)
    name, value = betterproto2.which_one_of(msg.sys, "SubSysMsg")
    return msg, name, value


def test_the_read_is_an_empty_request_the_device_answers_with_both_switches() -> None:
    """An unset sub-message would leave the oneof empty and the frame would ask for nothing."""
    msg, name, value = _sys_message(MammotionCommand(_DEVICE, 1).get_smart_sleep())

    assert (msg.msgtype, msg.msgattr) == (MsgCmdType.EMBED_SYS, MsgAttr.REQ)
    assert name == "to_get_dev_low_power_cmd"
    assert value == DevLowPowerGet()


@pytest.mark.parametrize("enabled", [True, False])
def test_eco_sleep_writes_only_the_docked_switch(enabled: bool) -> None:
    """The ``set_*_sta`` flags say which switch the value is for; the other must stay unflagged."""
    _, name, value = _sys_message(MammotionCommand(_DEVICE, 1).set_eco_sleep(enabled))

    assert name == "to_set_dev_low_power_cmd"
    assert value == DevLowPowerSetInfo(set_charging_lowpower_sta=True, charging_low_power=int(enabled))


@pytest.mark.parametrize("enabled", [True, False])
def test_live_sleep_writes_only_the_off_dock_switch(enabled: bool) -> None:
    _, name, value = _sys_message(MammotionCommand(_DEVICE, 1).set_live_sleep(enabled))

    assert name == "to_set_dev_low_power_cmd"
    assert value == DevLowPowerSetInfo(set_uncharging_lowpower_sta=True, uncharging_low_power=int(enabled))
