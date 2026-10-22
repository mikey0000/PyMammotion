"""Safety state stays unknown until the mower reports it; X5 write acknowledgements carry no value."""

from __future__ import annotations

import pytest

from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import (
    AppBatchQueryResp,
    AppBatchSetResp,
    Batchcfg,
    BatchConfigType,
    BatchSetRes,
    ChildProtection,
    LubaMsg,
    MctlNav,
    MctlSys,
    NavSysParamMsg,
    ResResult,
    ReverseMode,
    SysCommCmd,
)
from tests.unit.device._helpers import make_reducer_device


def make_safety_message(carrier: str, param_id: int, rw: int, enabled: bool) -> LubaMsg:
    if carrier == "nav":
        return LubaMsg(nav=MctlNav(nav_sys_param_cmd=NavSysParamMsg(id=param_id, rw=rw, context=int(enabled))))
    return LubaMsg(sys=MctlSys(bidire_comm_cmd=SysCommCmd(id=param_id, rw=rw, context=int(enabled))))


@pytest.mark.parametrize("carrier", ["nav", "sys"])
@pytest.mark.parametrize(("param_id", "field"), [(17, "child_safety"), (18, "reverse_safety_mode")])
@pytest.mark.parametrize("enabled", [False, True])
def test_safety_readback_updates_only_the_reported_setting(
    carrier: str, param_id: int, field: str, enabled: bool
) -> None:
    current = make_reducer_device()
    msg = make_safety_message(carrier, param_id, 0, enabled)

    updated = MowerStateReducer().apply(current, msg)

    assert getattr(updated.mower_state, field) is enabled
    assert current.mower_state.child_safety is None
    assert current.mower_state.reverse_safety_mode is None
    other = "reverse_safety_mode" if field == "child_safety" else "child_safety"
    assert getattr(updated.mower_state, other) is None
    assert updated.map is current.map


@pytest.mark.regression
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    ("field", "cfgtype", "payload", "payload_type", "mode"),
    [
        ("child_safety", BatchConfigType.CFG_TYPE_CHILD_PRO_CFG, "child_pro", ChildProtection, "child_protection_mode"),
        (
            "reverse_safety_mode",
            BatchConfigType.CFG_TYPE_REVERSE_MODE_CFG,
            "reverse_mode",
            ReverseMode,
            "reverse_safety_mode",
        ),
    ],
)
def test_x5_safety_batch_readback_updates_only_the_reported_setting(
    field: str,
    cfgtype: BatchConfigType,
    payload: str,
    payload_type: type[ChildProtection | ReverseMode],
    mode: str,
    enabled: bool,
) -> None:
    """The reducer ignored X5 batch safety readbacks, leaving both flags unknown."""
    current = make_reducer_device()
    cfg = Batchcfg(cfgtype=cfgtype, **{payload: payload_type(**{mode: int(enabled)})})
    msg = LubaMsg(sys=MctlSys(batch_query_resp=AppBatchQueryResp(req_id=7, cfgs=[cfg])))

    updated = MowerStateReducer().apply(current, msg)

    assert getattr(updated.mower_state, field) is enabled
    assert current.mower_state.child_safety is None
    assert current.mower_state.reverse_safety_mode is None
    other = "reverse_safety_mode" if field == "child_safety" else "child_safety"
    assert getattr(updated.mower_state, other) is None
    assert updated.map is current.map


@pytest.mark.parametrize("cfgtype", [BatchConfigType.CFG_TYPE_CHILD_PRO_CFG, BatchConfigType.CFG_TYPE_REVERSE_MODE_CFG])
def test_x5_safety_reply_without_its_payload_preserves_unknown_state(cfgtype: BatchConfigType) -> None:
    current = make_reducer_device()
    msg = LubaMsg(sys=MctlSys(batch_query_resp=AppBatchQueryResp(cfgs=[Batchcfg(cfgtype=cfgtype)])))

    updated = MowerStateReducer().apply(current, msg)

    assert updated.mower_state.child_safety is None
    assert updated.mower_state.reverse_safety_mode is None


def test_x5_safety_write_acknowledgement_does_not_confirm_a_value() -> None:
    current = make_reducer_device()
    msg = LubaMsg(
        sys=MctlSys(
            batch_set_resp=AppBatchSetResp(
                res_data=[
                    BatchSetRes(type=BatchConfigType.CFG_TYPE_CHILD_PRO_CFG, res_result=ResResult.RES_SUCCESS),
                    BatchSetRes(type=BatchConfigType.CFG_TYPE_REVERSE_MODE_CFG, res_result=ResResult.RES_SUCCESS),
                ]
            )
        )
    )

    updated = MowerStateReducer().apply(current, msg)

    assert updated.mower_state.child_safety is None
    assert updated.mower_state.reverse_safety_mode is None
    assert updated.map is current.map


@pytest.mark.parametrize("mode", [-1, 2])
def test_x5_safety_batch_readback_ignores_unknown_modes(mode: int) -> None:
    current = make_reducer_device()
    current.mower_state.child_safety = False
    current.mower_state.reverse_safety_mode = False
    msg = LubaMsg(
        sys=MctlSys(
            batch_query_resp=AppBatchQueryResp(
                cfgs=[
                    Batchcfg(
                        cfgtype=BatchConfigType.CFG_TYPE_CHILD_PRO_CFG,
                        child_pro=ChildProtection(child_protection_mode=mode),
                    ),
                    Batchcfg(
                        cfgtype=BatchConfigType.CFG_TYPE_REVERSE_MODE_CFG,
                        reverse_mode=ReverseMode(reverse_safety_mode=mode),
                    ),
                ]
            )
        )
    )

    updated = MowerStateReducer().apply(current, msg)

    assert updated.mower_state.child_safety is False
    assert updated.mower_state.reverse_safety_mode is False


@pytest.mark.parametrize("carrier", ["nav", "sys"])
@pytest.mark.parametrize(("param_id", "field"), [(17, "child_safety"), (18, "reverse_safety_mode")])
@pytest.mark.parametrize("reported", [None, False, True])
@pytest.mark.parametrize("enabled", [False, True])
def test_safety_write_echo_updates_the_reported_setting(
    carrier: str, param_id: int, field: str, reported: bool | None, enabled: bool
) -> None:
    current = make_reducer_device()
    assert getattr(current.mower_state, field) is None
    setattr(current.mower_state, field, reported)
    msg = make_safety_message(carrier, param_id, 1, enabled)

    updated = MowerStateReducer().apply(current, msg)

    assert getattr(updated.mower_state, field) is enabled
    assert getattr(current.mower_state, field) is reported
    other = "reverse_safety_mode" if field == "child_safety" else "child_safety"
    assert getattr(updated.mower_state, other) is None
