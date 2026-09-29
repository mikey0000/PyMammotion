"""WorkTaskEvent: the per-zone status of the running task."""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.enums import TaskAreaStatus
from pymammotion.data.model.events import WorkTaskEvent


@pytest.mark.regression
def test_a_stored_placeholder_zone_is_dropped_on_load() -> None:
    """A store saved before the placeholder was filtered holds ``ids: [1]``.

    Loaded as is, it brought the phantom "Task area" sensor back after every
    restart until the mower next sent its task areas.
    """
    stored = {"hash_area_map": {"1": 2, "5281050466362529553": 3}, "ids": [1, 5281050466362529553]}

    device = MowerDevice.from_dict({"name": "Luba-VAME9R5S", "events": {"work_tasks_event": stored}})

    assert device.events.work_tasks_event == WorkTaskEvent(
        hash_area_map={5281050466362529553: TaskAreaStatus.COMPLETE}, ids=[5281050466362529553]
    )


def test_a_stored_event_with_no_zones_loads_empty() -> None:
    """The load-time placeholder filter must tolerate empty containers, not just drop entries."""
    assert WorkTaskEvent.from_dict({}) == WorkTaskEvent()
