"""``MessageSystem`` rain-protection builders: the app's batch-config read and write.

``MACommandHelper.x5RainyWeatherProtectionSetting`` / ``queryX5RainyWeatherProtection``
(APK 2.3.20.30): both ride ``MctlSys`` fields 83/85 with ``CFG_TYPE_RAINPRO_CFG``,
and the write sets ``customDelayHours`` only in Sensor mode.
"""

from __future__ import annotations

import betterproto2
import pytest

from pymammotion.data.model.mowing_modes import RAIN_PROTECTION_DELAY_HOURS, RainProtectionMode
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import BatchConfigType, LubaMsg, MsgAttr, MsgCmdType, RainProtection

_LUBA_3 = "Luba-VAME9R5S"


def _sys_leaf(payload: bytes, expected: str) -> tuple[LubaMsg, object]:
    msg = LubaMsg().parse(payload)
    name, value = betterproto2.which_one_of(msg.sys, "SubSysMsg")
    assert name == expected
    return msg, value


def _written(payload: bytes) -> RainProtection:
    _, request = _sys_leaf(payload, "batch_set_req")
    assert len(request.cfgs) == 1
    cfg = request.cfgs[0]
    assert cfg.cfgtype == BatchConfigType.CFG_TYPE_RAINPRO_CFG
    assert betterproto2.which_one_of(cfg, "SysCfg")[0] == "rain_pro"
    return cfg.rain_pro


def test_the_read_queries_only_the_rain_protection_config() -> None:
    msg, request = _sys_leaf(MammotionCommand(_LUBA_3, 1).get_rain_protection(), "batch_query_req")

    assert (msg.msgtype, msg.msgattr) == (MsgCmdType.EMBED_SYS, MsgAttr.REQ)
    assert list(request.type_list) == [BatchConfigType.CFG_TYPE_RAINPRO_CFG]
    assert request.req_id > 0


def test_sensor_mode_carries_the_delay_in_hours() -> None:
    """The picker's value goes on the wire unconverted: 24 means 24 hours."""
    rain_pro = _written(MammotionCommand(_LUBA_3, 1).set_rain_protection(RainProtectionMode.sensor, 24))

    assert (rain_pro.rain_protection_mode, rain_pro.custom_delay_hours) == (2, 24)
    assert rain_pro.result == 0, "the app never sets result on a write"


@pytest.mark.parametrize("mode", [RainProtectionMode.off, RainProtectionMode.smart])
def test_other_modes_leave_the_delay_out_even_when_one_is_given(mode: RainProtectionMode) -> None:
    rain_pro = _written(MammotionCommand(_LUBA_3, 1).set_rain_protection(mode, 12))

    assert rain_pro.rain_protection_mode == mode.value
    assert rain_pro.custom_delay_hours == 0


def test_every_offered_delay_builds() -> None:
    command = MammotionCommand(_LUBA_3, 1)

    sent = [_written(command.set_rain_protection(RainProtectionMode.sensor, h)) for h in RAIN_PROTECTION_DELAY_HOURS]

    assert [rp.custom_delay_hours for rp in sent] == list(RAIN_PROTECTION_DELAY_HOURS)


@pytest.mark.parametrize("delay", [13, 23, 25, -1, 72])
def test_a_delay_the_app_does_not_offer_is_refused(delay: int) -> None:
    with pytest.raises(ValueError, match="delay"):
        MammotionCommand(_LUBA_3, 1).set_rain_protection(RainProtectionMode.sensor, delay)


def test_a_mode_outside_the_enum_is_refused() -> None:
    with pytest.raises(ValueError, match="RainProtectionMode"):
        MammotionCommand(_LUBA_3, 1).set_rain_protection(3, 0)  # type: ignore[arg-type]


def test_a_plain_int_mode_is_accepted() -> None:
    """Hosts pass the stored int back; it must build the same frame as the enum."""
    rain_pro = _written(MammotionCommand(_LUBA_3, 1).set_rain_protection(2, 6))  # type: ignore[arg-type]

    assert (rain_pro.rain_protection_mode, rain_pro.custom_delay_hours) == (2, 6)
