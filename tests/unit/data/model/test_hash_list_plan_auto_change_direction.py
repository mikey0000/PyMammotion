"""``Plan.auto_change_direction``: a schedule's "auto-reverse mowing direction", read from ``NavPlanJobSet`` field 41.

The app stores it in the plan's 32-byte ``reserved2`` (byte 0), which the device echoes +10, and reads it back
the way it reads a route's (``JobScheduleActivity.java:843-855``).  The decode is shared with
``CurrentTaskSettings``, whose tests pin the full rule; these pin that a plan uses it and that saved plans
predating the field still load.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import Plan
from tests._helpers import NEWER_MODEL_NAME, make_stored_plan_frame


@pytest.mark.parametrize(
    ("reserved2", "expected"),
    [([11] + [10] * 31, True), ([10] * 32, False), ([1] + [0] * 31, True), (None, None)],
    ids=["echo-on", "echo-off", "raw-on", "not-reported"],
)
def test_from_wire_reads_auto_change_direction_from_field_41(
    reserved2: list[int] | None, expected: bool | None
) -> None:
    plan = Plan.from_wire(make_stored_plan_frame(reserved2=reserved2), NEWER_MODEL_NAME)

    assert plan.auto_change_direction is expected


@pytest.mark.parametrize("reported", [True, False, None])
def test_plan_auto_change_direction_survives_a_serialisation_round_trip(reported: bool | None) -> None:
    """Plans are persisted decoded, so the stored bool must reload as itself."""
    plan = Plan(plan_id="p1", auto_change_direction=reported)

    assert Plan.from_dict(plan.to_dict()).auto_change_direction is reported


def test_a_device_saved_before_plans_had_the_new_fields_still_restores() -> None:
    """A stored plan written before them has no ``auto_change_direction`` or ``ride_boundary_distance`` key.

    Compatibility guard, not a fixed defect: adding a persisted field must not fail the restore, because when
    the ``work.auto_change_direction`` retype did, Home Assistant fell back to an empty device and lost its
    firmware and every gated entity.  It fails if either new ``Plan`` field loses its default.
    """
    stored = MowerDevice(name=NEWER_MODEL_NAME).to_dict()
    stored["device_firmwares"]["device_version"] = "2.3.30.39"
    old_plan = Plan(plan_id="p1", total_plan_num=1).to_dict()
    old_plan.pop("auto_change_direction", None)
    old_plan.pop("ride_boundary_distance", None)
    stored["map"]["plan"] = {"p1": old_plan}

    restored = MowerDevice.from_dict(stored)

    plan = restored.map.plan["p1"]
    assert (plan.auto_change_direction, plan.ride_boundary_distance) == (None, 0.0)
    assert restored.device_firmwares.device_version == "2.3.30.39"
