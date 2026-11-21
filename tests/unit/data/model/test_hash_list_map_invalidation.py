"""HashList.invalidate_maps — what a stale area manifest drops, and what it must keep."""

from __future__ import annotations

import pytest

from pymammotion.data.model.hash_list import HashList, NavGetCommData, NavGetHashListData, PathType


def _hash_list_frame(sub_cmd: int, hashes: list[int]) -> NavGetHashListData:
    return NavGetHashListData(pver=1, sub_cmd=sub_cmd, total_frame=1, current_frame=1, data_couple=hashes)


def _area_frame(hash_id: int) -> NavGetCommData:
    return NavGetCommData(pver=1, action=8, type=PathType.AREA, hash=hash_id, total_frame=1, current_frame=1)


@pytest.mark.regression
@pytest.mark.parametrize("held_sub_cmd", [3, 4])
def test_a_stale_manifest_keeps_cached_geometry_while_another_hash_list_is_held(held_sub_cmd: int) -> None:
    """Only the area manifest may go, so the next sync fetches only the elements that changed.

    It pruned every per-type dict against the hash lists left behind; while a route (sub_cmd 3)
    or dump list (sub_cmd 4) was held, that wiped every cached area, so each re-hash during a job
    re-fetched the whole map.
    """
    hl = HashList()
    hl.update_root_hash_list(_hash_list_frame(0, [100, 200]))
    hl.update_root_hash_list(_hash_list_frame(held_sub_cmd, [900]))
    hl.update(_area_frame(100))
    hl.update(_area_frame(200))

    hl.invalidate_maps(hl.computed_bol_hash + 1)

    assert hl.area_root_hashlist == []
    assert set(hl.area) == {100, 200}
    assert [rl.sub_cmd for rl in hl.root_hash_lists] == [held_sub_cmd]


def test_a_matching_hash_leaves_the_manifest_alone() -> None:
    hl = HashList()
    hl.update_root_hash_list(_hash_list_frame(0, [100]))

    hl.invalidate_maps(hl.computed_bol_hash)

    assert hl.area_root_hashlist == [100]
