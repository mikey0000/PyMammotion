"""PoolStateReducer tests for the ``LubaMsg.ctrl.plan_job_set`` path.

The Spino plan flow is brand new in pymammotion; these tests pin the
core invariants the rest of the stack depends on:

* a ``plan_job_set`` frame with ``enable=0`` lands as ``enabled=True``
  on ``PoolPlan`` (the inversion happens at the boundary, not in the
  consumer).
* ``totalplannum`` larger than the count we hold flips ``plans_stale``
  to True, and the flag clears once they're equal.
* The mower path (``LubaMsg.nav.todev_planjob_set``) is unaffected.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import PoolCleanerDevice
from pymammotion.device.state_reducer import PoolStateReducer
from pymammotion.proto import LubaMsg, PlanJobSet, SpinoCtrl


def _frame(**kwargs) -> LubaMsg:
    """Build a LubaMsg envelope wrapping a single PlanJobSet."""
    return LubaMsg(ctrl=SpinoCtrl(plan_job_set=PlanJobSet(**kwargs)))


class TestPlanJobSetReducer:
    def test_upserts_plan_keyed_by_jobid(self) -> None:
        reducer = PoolStateReducer()
        msg = _frame(cmd=4, jobid=0xABCDEF12, jobname="Daily", work_mode=1, enable=0)
        device = reducer.apply(PoolCleanerDevice(name="Spino-Test"), msg)

        assert 0xABCDEF12 in device.plans
        plan = device.plans[0xABCDEF12]
        assert plan.jobname == "Daily"
        assert plan.work_mode == 1

    def test_enable_field_is_inverted_at_the_boundary(self) -> None:
        reducer = PoolStateReducer()
        # ``enable=0`` on the wire ⇒ ``enabled=True`` in Python
        enabled_msg = _frame(cmd=4, jobid=1, enable=0)
        device = reducer.apply(PoolCleanerDevice(name="x"), enabled_msg)
        assert device.plans[1].enabled is True

        # ``enable=1`` ⇒ ``enabled=False``
        disabled_msg = _frame(cmd=4, jobid=2, enable=1)
        device = reducer.apply(device, disabled_msg)
        assert device.plans[2].enabled is False

    def test_weeks_and_submode_lists_are_copied(self) -> None:
        reducer = PoolStateReducer()
        msg = _frame(
            cmd=4, jobid=42, weeks=[1, 2, 3, 4, 5], sub_mode=[2, 3], enable=0
        )
        device = reducer.apply(PoolCleanerDevice(name="x"), msg)
        plan = device.plans[42]
        assert plan.weeks == [1, 2, 3, 4, 5]
        assert plan.sub_mode == [2, 3]

    def test_plans_stale_set_when_total_exceeds_known(self) -> None:
        reducer = PoolStateReducer()
        msg = _frame(cmd=4, jobid=1, totalplannum=3, enable=0)
        device = reducer.apply(PoolCleanerDevice(name="x"), msg)
        # one plan stored, device says three exist → stale
        assert device.plans_stale is True

    def test_plans_stale_clears_when_counts_match(self) -> None:
        reducer = PoolStateReducer()
        device = PoolCleanerDevice(name="x")
        device = reducer.apply(device, _frame(cmd=4, jobid=1, totalplannum=2, enable=0))
        assert device.plans_stale is True
        device = reducer.apply(device, _frame(cmd=4, jobid=2, totalplannum=2, enable=0))
        assert device.plans_stale is False

    def test_zero_jobid_frame_is_ignored(self) -> None:
        # DELETE_ALL echoes / error responses can arrive with jobid=0 —
        # storing those would clutter the plans dict.
        reducer = PoolStateReducer()
        msg = _frame(cmd=5, jobid=0, totalplannum=0)
        device = reducer.apply(PoolCleanerDevice(name="x"), msg)
        assert device.plans == {}

    def test_returns_a_copy_not_a_mutation(self) -> None:
        """Reducers MUST return a new dataclass to keep snapshot semantics."""
        reducer = PoolStateReducer()
        original = PoolCleanerDevice(name="x")
        updated = reducer.apply(original, _frame(cmd=4, jobid=99, enable=0))
        assert updated is not original
        assert 99 not in original.plans  # original untouched


class TestNonCtrlEnvelopes:
    """Non-ctrl frames must not accidentally route into the plan path."""

    def test_sys_frame_with_no_recognised_subtype_is_a_noop(self) -> None:
        # Mower-style nav frame; the pool reducer ignores nav entirely.
        from pymammotion.proto import MctlNav

        reducer = PoolStateReducer()
        device = PoolCleanerDevice(name="x")
        # An empty MctlNav has no SubNavMsg set; reducer should not crash.
        result = reducer.apply(device, LubaMsg(nav=MctlNav()))
        assert result.plans == {}


# Smoke test that PoolPlan helpers work as the reducer expects.
def test_pool_plan_with_enabled_round_trip() -> None:
    from pymammotion.data.model.pool_state import PoolPlan

    plan = PoolPlan(jobid=1, enabled=True)
    assert plan.with_enabled(False).enabled is False
    assert plan.with_renamed("foo").jobname == "foo"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
