"""HashList loaded from state an older version saved: what loading heals."""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.hash_list import HashList, NavGetCommData, NavGetHashListData, PathType

_AREA, _SAVED_DUMP, _TEMPORARY_DUMP = 100, 200, 900


def _hash_list_frame(sub_cmd: int, hashes: list[int]) -> NavGetHashListData:
    return NavGetHashListData(pver=1, sub_cmd=sub_cmd, total_frame=1, current_frame=1, data_couple=hashes)


def _frame(hash_id: int, path_type: PathType) -> NavGetCommData:
    return NavGetCommData(pver=1, action=8, type=path_type, hash=hash_id, total_frame=1, current_frame=1)


def _saved_by_an_older_version() -> dict:
    hl = HashList()
    hl.update_root_hash_list(_hash_list_frame(0, [_AREA, _SAVED_DUMP]))
    hl.update_root_hash_list(_hash_list_frame(4, [_TEMPORARY_DUMP]))
    for hash_id, path_type in ((_AREA, PathType.AREA), (_SAVED_DUMP, PathType.DUMP), (_TEMPORARY_DUMP, PathType.DUMP)):
        hl.update(_frame(hash_id, path_type))
    return hl.to_dict()


@pytest.mark.regression
def test_a_saved_dump_hash_list_is_dropped_on_load() -> None:
    """A sub_cmd=4 list saved by a version that requested it was never cleared again.

    ``invalidate_maps`` keeps every list but sub_cmd 0 and ``hashlist`` includes it, so its
    temporary dump points stayed in the manifest and their ``dump`` entries stayed alive.
    """
    hl = HashList.from_dict(_saved_by_an_older_version())

    assert {rl.sub_cmd for rl in hl.root_hash_lists} == {0}


def test_dump_points_only_the_dropped_list_named_are_pruned_by_the_next_sync() -> None:
    hl = HashList.from_dict(_saved_by_an_older_version())

    hl.update_hash_lists(hl.hashlist)

    assert set(hl.dump) == {_SAVED_DUMP}
    assert set(hl.area) == {_AREA}


def test_a_saved_device_state_drops_its_dump_hash_list_too() -> None:
    """Home Assistant restores the whole ``MowingDevice``, so the nested map must heal on that path."""
    saved = MowingDevice().to_dict()
    saved["map"] = _saved_by_an_older_version()

    assert {rl.sub_cmd for rl in MowingDevice.from_dict(saved).map.root_hash_lists} == {0}
