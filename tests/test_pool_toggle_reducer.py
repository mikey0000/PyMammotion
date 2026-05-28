"""Tests for PoolStateReducer applying SysCommCmd (allpowerfullRW) pool toggles.

The Spino reports its on/off toggles (buzzer / turbo clean / platform cleaning /
waterline parking) via the generic ``SysCommCmd`` read/ack — ``id`` selects the
toggle (see SpinoToggle) and ``context`` carries the 0/1 value.  The reducer maps
``SpinoToggle(id).name`` straight onto the matching PoolState boolean field.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import PoolCleanerDevice
from pymammotion.data.model.pool_state import SpinoToggle
from pymammotion.device.state_reducer import PoolStateReducer
from pymammotion.proto import LubaMsg, MctlSys, SysCommCmd


def _apply(device: PoolCleanerDevice, *, toggle_id: int, value: int) -> PoolCleanerDevice:
    msg = LubaMsg(sys=MctlSys(bidire_comm_cmd=SysCommCmd(id=toggle_id, context=value, rw=0)))
    return PoolStateReducer().apply(device, msg)


@pytest.mark.parametrize(
    ("toggle", "field"),
    [
        (SpinoToggle.buzzer, "buzzer"),
        (SpinoToggle.turbo_clean, "turbo_clean"),
        (SpinoToggle.platform_cleaning, "platform_cleaning"),
        (SpinoToggle.waterline_parking, "waterline_parking"),
    ],
)
def test_toggle_on(toggle: SpinoToggle, field: str) -> None:
    result = _apply(PoolCleanerDevice(name="Spino-E1abc"), toggle_id=int(toggle), value=1)
    assert getattr(result.pool_state, field) is True


def test_toggle_off_clears_previous_value() -> None:
    device = PoolCleanerDevice(name="Spino-E1abc")
    device.pool_state.turbo_clean = True
    result = _apply(device, toggle_id=int(SpinoToggle.turbo_clean), value=0)
    assert result.pool_state.turbo_clean is False


def test_member_names_match_pool_state_fields() -> None:
    # The reducer relies on SpinoToggle.name == the PoolState field name.
    state = PoolCleanerDevice().pool_state
    for toggle in SpinoToggle:
        assert hasattr(state, toggle.name), f"PoolState missing field for {toggle.name}"


def test_unknown_sys_comm_id_ignored() -> None:
    # A generic/mower SysCommCmd id we don't model must not raise or alter state.
    device = PoolCleanerDevice(name="Spino-E1abc")
    result = _apply(device, toggle_id=6, value=1)  # 6 = a Luba-Pro RW id, not a pool toggle
    assert result.pool_state.buzzer is False
    assert result.pool_state.turbo_clean is False
