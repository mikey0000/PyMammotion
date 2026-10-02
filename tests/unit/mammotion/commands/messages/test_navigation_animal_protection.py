"""WildGuard (animal protection): ``nav_sys_param_cmd`` ids 12 (mode) and 13 (status), on every device type.

APK: ``MACommandHelper.allAnimalProtect(12, mode, 1)`` / ``getAnimalProtectMode(12, 0)`` /
``getAllAnimalProtect(13, 0)`` always build ``MctlNav.nav_sys_param_cmd``; id 13 is never written.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg, MsgCmdType, NavSysParamMsg

DEVICE_NAMES = ["Luba-ABCDEF", "Luba-VS6ABCDE", "Yuka-MN12345"]


def _sys_param(payload: bytes) -> NavSysParamMsg:
    msg = LubaMsg().parse(payload)
    assert msg.msgtype == MsgCmdType.NAV
    assert msg.nav.nav_sys_param_cmd is not None
    return msg.nav.nav_sys_param_cmd


@pytest.mark.parametrize("device_name", DEVICE_NAMES)
@pytest.mark.parametrize("mode", [0, 1, 2])
def test_setting_the_mode_writes_id_12_with_the_mode_as_context(device_name: str, mode: int) -> None:
    param = _sys_param(MammotionCommand(device_name, 1).set_animal_protection_mode(mode))
    assert (param.id, param.rw, param.context) == (12, 1, mode)


@pytest.mark.parametrize("device_name", DEVICE_NAMES)
@pytest.mark.parametrize(
    ("build", "param_id"),
    [(MammotionCommand.read_animal_protection_mode, 12), (MammotionCommand.read_animal_protection_status, 13)],
    ids=["mode", "status"],
)
def test_reading_sends_its_id_with_rw_zero(
    device_name: str, build: Callable[[MammotionCommand], bytes], param_id: int
) -> None:
    param = _sys_param(build(MammotionCommand(device_name, 1)))
    assert (param.id, param.rw, param.context) == (param_id, 0, 0)


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        (lambda c: c.read_animal_avoidance(), (13, 0, 0)),
        (lambda c: c.set_animal_avoidance(2), (12, 1, 2)),
    ],
    ids=["read_animal_avoidance", "set_animal_avoidance"],
)
def test_the_older_names_send_the_same_parameter(
    alias: Callable[[MammotionCommand], bytes], expected: tuple[int, int, int]
) -> None:
    param = _sys_param(alias(MammotionCommand("Luba-VS6ABCDE", 1)))
    assert (param.id, param.rw, param.context) == expected
