"""Smart Sleep (EcoSleep / LiveSleep) decoding in ``MowerStateReducer``."""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import DevLowPowerGet, DevLowPowerSetInfo, LubaMsg, MctlSys
from tests.unit.device._helpers import make_reducer_device


def test_the_switches_are_unknown_until_read() -> None:
    mower_state = make_reducer_device().mower_state

    assert (mower_state.eco_sleep, mower_state.live_sleep) == (None, None)


@pytest.mark.parametrize(
    ("charging", "uncharging", "expected"),
    [(1, 0, (True, False)), (0, 1, (False, True)), (1, 1, (True, True)), (0, 0, (False, False))],
)
def test_a_read_reply_sets_both_switches(charging: int, uncharging: int, expected: tuple[bool, bool]) -> None:
    """EcoSleep is the charging (docked) value, LiveSleep the uncharging one."""
    current = make_reducer_device()
    reply = DevLowPowerGet(charging_low_power=charging, uncharging_low_power=uncharging)

    updated = MowerStateReducer().apply(current, LubaMsg(sys=MctlSys(to_get_dev_low_power_cmd=reply)))

    assert (updated.mower_state.eco_sleep, updated.mower_state.live_sleep) == expected
    assert current.mower_state.eco_sleep is None, "the previous snapshot must not be mutated"


def test_a_write_reply_is_not_read_as_state() -> None:
    """Its values are the app's result code, not the switch positions."""
    current = make_reducer_device()
    reply = DevLowPowerSetInfo(charging_low_power=1, uncharging_low_power=1)

    updated = MowerStateReducer().apply(current, LubaMsg(sys=MctlSys(to_set_dev_low_power_cmd=reply)))

    assert (updated.mower_state.eco_sleep, updated.mower_state.live_sleep) == (None, None)


def test_a_device_saved_before_the_switches_existed_still_restores() -> None:
    stored = MowerDevice(name="Luba-VA6ABCDE").to_dict()
    del stored["mower_state"]["eco_sleep"], stored["mower_state"]["live_sleep"]

    restored = MowerDevice.from_dict(stored)

    assert (restored.mower_state.eco_sleep, restored.mower_state.live_sleep) == (None, None)
