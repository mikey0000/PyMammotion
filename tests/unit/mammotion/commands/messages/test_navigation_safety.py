"""Safety builders select the parameter carrier by mower type; hardware support is tested separately."""

from __future__ import annotations

import time

import pytest
import time_machine

from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import BatchConfigType, LubaMsg, MsgCmdType, MsgDevice


@pytest.fixture
def fixed_batch_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the monotonic request-ID source separately from wall-clock travel."""
    monkeypatch.setattr(time, "monotonic", lambda: 1234.0)


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


@pytest.mark.regression
@pytest.mark.usefixtures("fixed_batch_clock")
@pytest.mark.parametrize("device_name", ["Luba-VA000001", "Yuka-MV000001", "Ezy-VT000001"])
@pytest.mark.parametrize(
    ("command", "cfgtype"),
    [
        ("read_child_safety", BatchConfigType.CFG_TYPE_CHILD_PRO_CFG),
        ("read_reverse_safety_mode", BatchConfigType.CFG_TYPE_REVERSE_MODE_CFG),
    ],
)
def test_x5_safety_reads_query_batch_config(device_name: str, command: str, cfgtype: BatchConfigType) -> None:
    """X5 safety reads used navigation registers instead of the app's batch-query carrier."""
    with time_machine.travel("2026-01-01", tick=False):
        msg = LubaMsg().parse(getattr(MammotionCommand(device_name, 1), command)())

    assert msg.msgtype == MsgCmdType.EMBED_SYS
    assert msg.rcver == MsgDevice.DEV_MAINCTL
    assert msg.nav is None
    assert msg.sys.bidire_comm_cmd is None
    assert msg.sys.batch_query_req.type_list == [cfgtype]
    assert msg.sys.batch_query_req.req_id == 1234000


@pytest.mark.regression
@pytest.mark.usefixtures("fixed_batch_clock")
@pytest.mark.parametrize("device_name", ["Luba-VA000001", "Yuka-MV000001", "Ezy-VT000001"])
@pytest.mark.parametrize(
    ("command", "cfgtype", "payload", "mode"),
    [
        ("set_child_safety", BatchConfigType.CFG_TYPE_CHILD_PRO_CFG, "child_pro", "child_protection_mode"),
        ("set_reverse_safety_mode", BatchConfigType.CFG_TYPE_REVERSE_MODE_CFG, "reverse_mode", "reverse_safety_mode"),
    ],
)
@pytest.mark.parametrize("enabled", [False, True])
def test_x5_safety_writes_set_only_the_requested_batch_config(
    device_name: str, command: str, cfgtype: BatchConfigType, payload: str, mode: str, enabled: bool
) -> None:
    """X5 writes used the navigation carrier and could not configure the batch setting."""
    with time_machine.travel("2026-01-01", tick=False):
        msg = LubaMsg().parse(getattr(MammotionCommand(device_name, 1), command)(enabled))

    assert msg.msgtype == MsgCmdType.EMBED_SYS
    assert msg.rcver == MsgDevice.DEV_MAINCTL
    assert msg.nav is None
    assert msg.sys.bidire_comm_cmd is None
    request = msg.sys.batch_set_req
    assert request.req_id == 1234000
    assert len(request.cfgs) == 1
    cfg = request.cfgs[0]
    assert cfg.cfgtype == cfgtype
    assert getattr(getattr(cfg, payload), mode) == int(enabled)
