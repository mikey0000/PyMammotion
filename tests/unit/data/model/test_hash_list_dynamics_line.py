"""``HashList`` assembles the lidar dynamics line (type 18) the way the APK does.

APK ``HashDataManager.updateDynamicsLine``: frames are banked under ``hash:frame``,
frame 1 starts a new set, a repeated key is dropped, a ``result != 0`` frame carries
nothing, and the line is replaced wholesale only once every frame of the final
frame's hash is present.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.hash_list import CommDataCouple, HashList, NavGetCommData, PathType

_HASH = 6150000000000000001
_OTHER_HASH = 6150000000000000002
_OLD_LINE = [CommDataCouple(x=-1.0, y=-1.0), CommDataCouple(x=-2.0, y=-2.0)]


def _frame(current: int, total: int, *points: float, hash_: int = _HASH, result: int = 0) -> NavGetCommData:
    return NavGetCommData(
        action=8,
        type=PathType.DYNAMICS_LINE,
        hash=hash_,
        result=result,
        current_frame=current,
        total_frame=total,
        data_couple=[CommDataCouple(x=p, y=p) for p in points],
    )


def _xs(line: list[CommDataCouple]) -> list[float]:
    return [p.x for p in line]


def test_a_complete_set_replaces_the_line_in_frame_order() -> None:
    hash_list = HashList(dynamics_line=list(_OLD_LINE))

    hash_list.update(_frame(1, 2, 1.0, 2.0))
    hash_list.update(_frame(2, 2, 3.0))

    assert _xs(hash_list.dynamics_line) == [1.0, 2.0, 3.0]


@pytest.mark.regression
def test_a_retransmitted_frame_is_not_drawn_twice() -> None:
    """The device resends a frame whose ack it missed; each copy was appended, doubling that segment back."""
    hash_list = HashList()

    hash_list.update(_frame(1, 3, 1.0))
    hash_list.update(_frame(2, 3, 2.0))
    hash_list.update(_frame(2, 3, 2.0))
    hash_list.update(_frame(3, 3, 3.0))

    assert _xs(hash_list.dynamics_line) == [1.0, 2.0, 3.0]


@pytest.mark.regression
def test_the_previous_line_is_kept_until_the_new_set_is_complete() -> None:
    """Frame 1 emptied the stored line, so a fetch that stalled mid-set left a truncated path drawn."""
    hash_list = HashList(dynamics_line=list(_OLD_LINE))

    hash_list.update(_frame(1, 2, 1.0))

    assert hash_list.dynamics_line == _OLD_LINE


@pytest.mark.regression
def test_frames_from_another_hash_do_not_complete_the_set() -> None:
    """Frames were joined by number alone, so a set spliced from two snapshots drew a jumping path."""
    hash_list = HashList(dynamics_line=list(_OLD_LINE))

    hash_list.update(_frame(1, 2, 1.0))
    hash_list.update(_frame(2, 2, 2.0, hash_=_OTHER_HASH))

    assert hash_list.dynamics_line == _OLD_LINE


@pytest.mark.regression
def test_a_failed_frame_carries_no_points() -> None:
    """The APK re-requests a ``result != 0`` frame and stores nothing from it."""
    hash_list = HashList(dynamics_line=list(_OLD_LINE))

    hash_list.update(_frame(1, 2, 1.0))
    hash_list.update(_frame(2, 2, 9.0, result=1))

    assert hash_list.dynamics_line == _OLD_LINE


def test_update_reports_only_a_completed_line() -> None:
    hash_list = HashList()

    assert not hash_list.update(_frame(1, 2, 1.0))
    assert hash_list.update(_frame(2, 2, 2.0))


def test_banked_frames_are_not_persisted() -> None:
    hash_list = HashList()
    hash_list.update(_frame(1, 2, 1.0))

    restored = HashList.from_dict(hash_list.to_dict())
    restored.update(_frame(2, 2, 2.0))

    assert restored.dynamics_line == []


def test_clearing_drops_the_line_its_geojson_and_any_partial_set() -> None:
    hash_list = HashList(dynamics_line=list(_OLD_LINE), generated_dynamics_line_geojson={"features": [{}]})
    hash_list.update(_frame(1, 2, 1.0))

    hash_list.clear_dynamics_line()
    hash_list.update(_frame(2, 2, 2.0))

    assert hash_list.dynamics_line == []
    assert hash_list.generated_dynamics_line_geojson == {}


def test_a_new_frame_one_restarts_the_set() -> None:
    """A fresh request resends frame 1; the abandoned set's frames must not leak into the new line."""
    hash_list = HashList()

    hash_list.update(_frame(1, 2, 1.0))
    hash_list.update(_frame(1, 2, 5.0))
    hash_list.update(_frame(2, 2, 6.0))

    assert _xs(hash_list.dynamics_line) == [5.0, 6.0]
