"""A full plan fetch is authoritative — schedules the device dropped must go.

``update_plan`` only ever adds, and the one branch that removes a plan
(``all_plan_task`` in the reducer) is never requested, so a schedule deleted on
the mower stayed in ``map.plan`` and — being persisted — survived restarts.  The
user saw four schedule buttons for ``total_plan_num = 3`` (Mammotion-HA #892).

It is not only cosmetic: ``set_task_enabled`` goes out as ``edit_plan``, and
sent against an id the device no longer has, the device recreates the schedule.
"""

from __future__ import annotations

from pymammotion.data.model.hash_list import HashList, Plan


def _plan(plan_id: str, name: str, index: int, total: int = 3) -> Plan:
    return Plan(
        plan_id=plan_id,
        task_name=name,
        plan_index=index,
        total_plan_num=total,
    )


def _stored_with_a_stale_plan() -> tuple[HashList, dict[str, Plan]]:
    """The reporter's state: three live schedules plus one deleted on the device."""
    live = {
        "885782": _plan("885782", "Garage", 0),
        "623471": _plan("623471", "Arriere", 1),
        "734080": _plan("734080", "En bas", 2),
    }
    hash_list = HashList()
    # The stale one shares its name, index and time with a live schedule — it was
    # edited on the device, which re-created it under a new id.
    hash_list.update_plan(_plan("818260", "Garage", 0))
    for plan in live.values():
        hash_list.update_plan(plan)
    return hash_list, live


def test_update_plan_never_removes() -> None:
    """The root cause, stated plainly: the cache only grows."""
    hash_list, live = _stored_with_a_stale_plan()
    assert set(hash_list.plan) == {"818260", *live}


def test_a_completed_fetch_drops_what_the_device_no_longer_has() -> None:
    """The bug: four stored schedules for a device reporting three."""
    hash_list, live = _stored_with_a_stale_plan()

    hash_list.replace_plans(live)

    assert set(hash_list.plan) == set(live)
    assert "818260" not in hash_list.plan


def test_replacing_keeps_the_returned_plans_intact() -> None:
    """Pruning must not disturb the schedules that are still there."""
    hash_list, live = _stored_with_a_stale_plan()

    hash_list.replace_plans(live)

    assert hash_list.plan["623471"].task_name == "Arriere"
    assert hash_list.plan["734080"].plan_index == 2


def test_a_device_with_no_schedules_left_ends_up_empty() -> None:
    """Deleting the last schedule has to clear the cache, not leave it frozen."""
    hash_list, _ = _stored_with_a_stale_plan()

    hash_list.replace_plans({})

    assert hash_list.plan == {}


def test_replacing_does_not_alias_the_caller_s_dict() -> None:
    """The saga reuses its result dict across runs."""
    hash_list, live = _stored_with_a_stale_plan()

    hash_list.replace_plans(live)
    live.clear()

    assert len(hash_list.plan) == 3
