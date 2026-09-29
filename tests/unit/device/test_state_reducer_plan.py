"""MowerStateReducer's ``todev_planjob_set`` case: how a stored schedule the device returns is decoded.

The model decides where ``toward_mode`` is read from — ``reserved[4]`` (echoed +10) on a Luba 1, field 37
elsewhere — and a Luba 1 may be recognisable only by ``mower_state.product_key``.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import LubaMsg, MctlNav, NavPlanJobSet
from pymammotion.utility.device_type import DeviceType
from tests._helpers import (
    LUBA1_NAME,
    LUBA1_PRODUCT_KEY,
    NEWER_MODEL_NAME,
    UNRECOGNISED_NAME,
    make_stored_plan_frame,
)
from tests.unit.device._helpers import make_reducer_device as _make_device


def test_planjob_set_stores_the_schedules_ride_boundary_distance() -> None:
    """A stored schedule's Edge Coverage value is what an edit sends back, so it must survive the read."""
    plan_frame = NavPlanJobSet(plan_id="p1", total_plan_num=1, edge_mode=1, ride_boundary_distance=0.5)

    updated = MowerStateReducer().apply(_make_device(), LubaMsg(nav=MctlNav(todev_planjob_set=plan_frame)))

    assert updated.map.plan["p1"].ride_boundary_distance == 0.5


def _planjob_with_toward_modes(reserved_byte_4: int, field_37: int) -> LubaMsg:
    return LubaMsg(nav=MctlNav(todev_planjob_set=make_stored_plan_frame(reserved_byte_4, field_37)))


@pytest.mark.regression
def test_planjob_set_decodes_a_luba1_plans_toward_mode_from_reserved() -> None:
    """The reducer took field 37 for every model; a Luba 1 keeps the mode in ``reserved[4]`` (echoed +10)."""
    luba1 = MowerDevice(name=LUBA1_NAME)

    updated = MowerStateReducer().apply(luba1, _planjob_with_toward_modes(reserved_byte_4=12, field_37=0))

    assert updated.map.plan["p1"].toward_mode == 2


def test_planjob_set_decodes_a_newer_models_toward_mode_from_field_37() -> None:
    newer = MowerDevice(name=NEWER_MODEL_NAME)

    updated = MowerStateReducer().apply(newer, _planjob_with_toward_modes(reserved_byte_4=12, field_37=1))

    assert updated.map.plan["p1"].toward_mode == 1


def test_planjob_set_decodes_toward_mode_from_reserved_on_a_luba1_known_only_by_product_key() -> None:
    """The name matches no rule, so only ``mower_state.product_key`` can tell the reducer this is a Luba 1."""
    device = MowerDevice(name=UNRECOGNISED_NAME)
    device.mower_state.product_key = LUBA1_PRODUCT_KEY
    assert not DeviceType.is_luba1(device.name), "the name alone must not identify a Luba 1"

    updated = MowerStateReducer().apply(device, _planjob_with_toward_modes(reserved_byte_4=12, field_37=0))

    assert updated.map.plan["p1"].toward_mode == 2


def test_planjob_set_stores_the_schedules_auto_change_direction() -> None:
    """An edit re-sends field 41 from the stored plan, so the reducer's decode must keep it."""
    frame = make_stored_plan_frame(reserved2=[11] + [10] * 31)

    updated = MowerStateReducer().apply(_make_device(), LubaMsg(nav=MctlNav(todev_planjob_set=frame)))

    assert updated.map.plan["p1"].auto_change_direction is True
