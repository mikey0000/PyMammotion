"""Rain protection in ``MowerStateReducer``: the batch-config reply and self-check 34.

No report field carries the mode or delay, so the RAINPRO ``batch_query_resp`` is
the only source of state; self-check 34 ("Rain Protection active") is the one
unsolicited proof that the firmware has the feature.  Every batch config type
shares ``batch_query_resp``, so replies for the other types must be ignored.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.device_info import RainProtectionSettings
from pymammotion.data.model.mowing_modes import RainProtectionMode
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import (
    AppBatchQueryResp,
    AppBatchSetResp,
    Batchcfg,
    BatchConfigType,
    BatchSetRes,
    LubaMsg,
    MctlSys,
    RainProtection,
    ReportInfoData,
    ResResult,
    RptDevStatus,
    SpeedModeCfg,
)
from tests.unit.device._helpers import make_reducer_device


def _query_reply(*cfgs: Batchcfg) -> LubaMsg:
    return LubaMsg(sys=MctlSys(batch_query_resp=AppBatchQueryResp(req_id=7, cfgs=list(cfgs))))


def _rain_cfg(mode: int, delay: int) -> Batchcfg:
    return Batchcfg(
        cfgtype=BatchConfigType.CFG_TYPE_RAINPRO_CFG,
        rain_pro=RainProtection(result=1, rain_protection_mode=mode, custom_delay_hours=delay),
    )


def _with_rain(settings: RainProtectionSettings) -> MowerDevice:
    device = make_reducer_device()
    device.mower_state.rain_protection = settings
    return device


def _self_check(code: int) -> LubaMsg:
    return LubaMsg(sys=MctlSys(toapp_report_data=ReportInfoData(dev=RptDevStatus(self_check_status=code))))


def test_a_rain_protection_reply_sets_mode_delay_and_proves_support() -> None:
    current = make_reducer_device()

    updated = MowerStateReducer().apply(current, _query_reply(_rain_cfg(2, 6)))

    assert updated.mower_state.rain_protection == RainProtectionSettings(
        supported=True, mode=RainProtectionMode.sensor, delay_hours=6
    )
    assert current.mower_state.rain_protection == RainProtectionSettings(), "the reducer mutated its input"


def test_a_smart_mode_reply_keeps_the_remembered_sensor_delay() -> None:
    current = _with_rain(RainProtectionSettings(supported=True, mode=RainProtectionMode.sensor, delay_hours=48))

    updated = MowerStateReducer().apply(current, _query_reply(_rain_cfg(1, 0)))

    assert (updated.mower_state.rain_protection.mode, updated.mower_state.rain_protection.delay_hours) == (1, 48)


def test_an_unknown_mode_is_stored_without_failing_the_frame() -> None:
    updated = MowerStateReducer().apply(make_reducer_device(), _query_reply(_rain_cfg(9, 3)))

    assert updated.mower_state.rain_protection.mode == 9
    assert updated.mower_state.rain_protection.supported is True


def test_the_legacy_rain_switch_is_left_alone() -> None:
    """What id 3 means on rain-protection firmware is unverified, so the reply does not derive it."""
    current = make_reducer_device()
    current.mower_state.rain_detection = True

    updated = MowerStateReducer().apply(current, _query_reply(_rain_cfg(0, 0)))

    assert updated.mower_state.rain_detection is True


def test_a_reply_for_another_config_type_is_ignored() -> None:
    other = Batchcfg(cfgtype=BatchConfigType.CFG_TYPE_SPEED_MODE, mode=SpeedModeCfg(current_cutter_mode=1))

    updated = MowerStateReducer().apply(make_reducer_device(), _query_reply(other))

    assert updated.mower_state.rain_protection == RainProtectionSettings()


def test_a_rain_payload_under_another_config_type_is_ignored() -> None:
    """The app switches on ``cfgtype`` (``handleBatchConfigQuery``), not on which payload is set."""
    mislabelled = Batchcfg(
        cfgtype=BatchConfigType.CFG_TYPE_SPEED_MODE,
        rain_pro=RainProtection(result=1, rain_protection_mode=2, custom_delay_hours=6),
    )

    updated = MowerStateReducer().apply(make_reducer_device(), _query_reply(mislabelled))

    assert updated.mower_state.rain_protection == RainProtectionSettings()


def test_a_rainpro_entry_without_its_payload_does_not_prove_support() -> None:
    """How unsupported firmware answers is unknown; an empty entry must not light the entities up."""
    bare = Batchcfg(cfgtype=BatchConfigType.CFG_TYPE_RAINPRO_CFG)

    updated = MowerStateReducer().apply(make_reducer_device(), _query_reply(bare))

    assert updated.mower_state.rain_protection.supported is None


def test_an_empty_reply_does_not_prove_support() -> None:
    updated = MowerStateReducer().apply(make_reducer_device(), _query_reply())

    assert updated.mower_state.rain_protection.supported is None


def test_the_rain_entry_is_found_among_other_types() -> None:
    other = Batchcfg(cfgtype=BatchConfigType.CFG_TYPE_SPEED_MODE, mode=SpeedModeCfg(current_cutter_mode=1))

    updated = MowerStateReducer().apply(make_reducer_device(), _query_reply(other, _rain_cfg(0, 0)))

    assert updated.mower_state.rain_protection.mode == RainProtectionMode.off


def test_a_set_ack_does_not_touch_the_rain_state() -> None:
    """The ack carries no values; the caller applies what it sent."""
    current = _with_rain(RainProtectionSettings(supported=True, mode=RainProtectionMode.off))
    ack = LubaMsg(
        sys=MctlSys(
            batch_set_resp=AppBatchSetResp(
                req_id=7,
                res_data=[BatchSetRes(type=BatchConfigType.CFG_TYPE_RAINPRO_CFG, res_result=ResResult.RES_SUCCESS)],
            )
        )
    )

    updated = MowerStateReducer().apply(current, ack)

    assert updated.mower_state.rain_protection == current.mower_state.rain_protection


def test_self_check_34_proves_support_without_inventing_a_mode() -> None:
    current = make_reducer_device()

    updated = MowerStateReducer().apply(current, _self_check(34))

    assert updated.mower_state.rain_protection == RainProtectionSettings(supported=True)
    assert current.mower_state.rain_protection.supported is None, "the reducer mutated its input"


@pytest.mark.parametrize("code", [0, 20, 23])
def test_other_self_checks_prove_nothing(code: int) -> None:
    updated = MowerStateReducer().apply(make_reducer_device(), _self_check(code))

    assert updated.mower_state.rain_protection.supported is None


def test_a_report_leaves_the_mower_state_shared_once_support_is_known() -> None:
    """The report is the hot path; it must not copy ``mower_state`` on every frame."""
    current = _with_rain(RainProtectionSettings(supported=True, mode=RainProtectionMode.smart))

    updated = MowerStateReducer().apply(current, _self_check(34))

    assert updated.mower_state is current.mower_state
