"""Charge-settings decoding in ``MowerStateReducer`` — split from test_state_reducer.py for size."""

from __future__ import annotations

from pymammotion.data.model.device import MowerDevice
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import BmsCtrlInfoMsg, LubaMsg, MctlSys
from tests.unit.device._helpers import make_reducer_device as _make_device

_ALL_FIELDS = ("map", "work", "mower_state", "non_work_hours", "work_session_result")


def _assert_sharing(current: MowerDevice, updated: MowerDevice, copied_fields: tuple[str, ...]) -> None:
    """Fields in copied_fields must be distinct; others must share identity."""
    for name in _ALL_FIELDS:
        current_val = getattr(current, name)
        updated_val = getattr(updated, name)
        if name in copied_fields:
            assert updated_val is not current_val, f"{name} was declared as copied but still shares identity"
        else:
            assert updated_val is current_val, f"{name} was not declared as copied but was deep-copied anyway"


def test_bms_ctrl_info_updates_charge_settings_and_only_copies_mower_state() -> None:
    reducer = MowerStateReducer()
    current = _make_device()
    msg = LubaMsg(
        sys=MctlSys(
            bms_ctrl_info_msg=BmsCtrlInfoMsg(
                bat_cycle_times=42,
                bat_health_state=1,
                smart_charge_switch=1,
                charge_soc_threshold=85,
                peak_valley_charge_switch=1,
                valley_charge_start_time=1320,
                valley_charge_end_time=360,
            )
        )
    )
    updated = reducer.apply(current, msg)
    _assert_sharing(current, updated, copied_fields=("mower_state",))
    settings = updated.mower_state.charge_settings
    assert settings.smart_charge is False
    assert settings.charge_limit == 85
    assert settings.peak_valley_charge is True
    assert (settings.valley_charge_start_time, settings.valley_charge_end_time) == (1320, 360)
    assert (settings.bat_cycle_times, settings.bat_health_state) == (42, 1)
    assert current.mower_state.charge_settings.charge_limit == 0


def test_bms_ctrl_info_smart_charge_switch_zero_means_smart_on() -> None:
    reducer = MowerStateReducer()
    msg = LubaMsg(sys=MctlSys(bms_ctrl_info_msg=BmsCtrlInfoMsg(smart_charge_switch=0, charge_soc_threshold=100)))
    updated = reducer.apply(_make_device(), msg)
    assert updated.mower_state.charge_settings.smart_charge is True
    assert updated.mower_state.charge_settings.charge_limit == 100
