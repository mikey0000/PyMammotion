"""How HashList identifies an area across a re-hash, and labels one the mower has no name for.

``area_id`` is the identity a host keys an area's entity on; ``computed_areas`` fills in the
"Area N" label from the area's position in the device's root hash list, as the app's map does.
The hashes, ids and creation stamps below are from real mowers before and after a re-hash.
"""

from __future__ import annotations

import json

import pytest

from pymammotion.data.model.hash_list import (
    AreaHashNameList,
    FrameList,
    HashList,
    NavGetCommData,
    NavGetHashListData,
    NavNameTime,
)

# Luba 3 (X5): every hash changed on a map re-save; paternal_hash_b and create_time did not.
LUBA3_BEFORE, LUBA3_AFTER, LUBA3_ID, LUBA3_CREATED = 6630234128293022052, 8166184650364246260, 6, 1783885114
# Yuka: its area "Front yard" was edited; paternal_hash_b is 0 on this family.
YUKA_BEFORE, YUKA_AFTER, YUKA_CREATED = 8323694340871879373, 1813495770584210795, 1747177645


def _area(hash_id: int, *, name: str = "", created: int = 0, area_id: int = 0) -> FrameList:
    """One complete area as the mower sends it."""
    frame = NavGetCommData(
        type=0,
        hash=hash_id,
        paternal_hash_b=area_id,
        total_frame=1,
        current_frame=1,
        name_time=NavNameTime(name=name, create_time=created),
    )
    return FrameList(total_frame=1, data=[frame])


def _map(areas: dict[int, FrameList], root: list[int] | None = None) -> HashList:
    """A map holding *areas*, with *root* as the device's area root hash list."""
    hash_list = HashList(area=areas)
    if root is not None:
        hash_list.update_root_hash_list(
            NavGetHashListData(pver=1, sub_cmd=0, total_frame=1, current_frame=1, data_couple=root)
        )
    return hash_list


def _labels(hash_list: HashList) -> dict[int, str]:
    return {a.hash: a.name for a in hash_list.computed_areas}


class TestAreaId:
    @pytest.mark.parametrize(
        ("before", "after"),
        [
            pytest.param(
                _area(LUBA3_BEFORE, created=LUBA3_CREATED, area_id=LUBA3_ID),
                _area(LUBA3_AFTER, created=LUBA3_CREATED, area_id=LUBA3_ID),
                id="luba3-paternal-hash-b",
            ),
            pytest.param(
                _area(YUKA_BEFORE, created=YUKA_CREATED), _area(YUKA_AFTER, created=YUKA_CREATED), id="yuka-create-time"
            ),
        ],
    )
    def test_a_rehashed_area_keeps_its_id(self, before: FrameList, after: FrameList) -> None:
        old_hash, new_hash = before.data[0].hash, after.data[0].hash
        assert _map({old_hash: before}).area_id(old_hash) == _map({new_hash: after}).area_id(new_hash)

    def test_paternal_hash_b_wins_over_the_creation_stamp(self) -> None:
        hash_list = _map({LUBA3_AFTER: _area(LUBA3_AFTER, created=LUBA3_CREATED, area_id=LUBA3_ID)})
        assert hash_list.area_id(LUBA3_AFTER) == LUBA3_ID

    def test_the_creation_stamp_is_the_id_when_paternal_hash_b_is_zero(self) -> None:
        assert _map({YUKA_AFTER: _area(YUKA_AFTER, created=YUKA_CREATED)}).area_id(YUKA_AFTER) == YUKA_CREATED

    def test_a_creation_stamp_two_areas_share_identifies_neither(self) -> None:
        """Seen while a re-hashed area's old and new hash are both stored; it would pair them wrongly."""
        hash_list = _map({10: _area(10, created=YUKA_CREATED), 20: _area(20, created=YUKA_CREATED)})
        assert (hash_list.area_id(10), hash_list.area_id(20)) == (None, None)

    @pytest.mark.parametrize(
        "frames",
        [
            pytest.param(_area(10), id="luba2-area-without-a-stamp"),
            pytest.param(FrameList(), id="names-only-no-frames"),
        ],
    )
    def test_an_area_without_an_id_or_stamp_has_no_id(self, frames: FrameList) -> None:
        assert _map({10: frames}).area_id(10) is None

    def test_an_unknown_hash_has_no_id(self) -> None:
        assert _map({}).area_id(10) is None

    def test_a_map_stored_before_the_frames_carried_ids_still_loads(self) -> None:
        """A stored frame without paternal_hash_b or name_time loads with no id rather than failing."""
        stored = {"area": {"10": {"total_frame": 1, "data": [{"hash": 10, "total_frame": 1, "current_frame": 1}]}}}
        assert HashList.from_dict(stored).area_id(10) is None

    def test_the_id_survives_a_storage_round_trip(self) -> None:
        hash_list = _map({LUBA3_AFTER: _area(LUBA3_AFTER, created=LUBA3_CREATED, area_id=LUBA3_ID)})
        restored = HashList.from_dict(json.loads(json.dumps(hash_list.to_dict())))
        assert restored.area_id(LUBA3_AFTER) == LUBA3_ID


class TestFallbackLabels:
    def test_an_unnamed_area_is_labelled_by_its_place_among_the_root_lists_areas(self) -> None:
        """Hash 5 is an obstacle in the root list, so it takes no place."""
        hash_list = _map({30: _area(30), 10: _area(10, name="Front"), 20: _area(20)}, root=[10, 5, 20, 30])
        assert _labels(hash_list) == {10: "Front", 20: "Area 2", 30: "Area 3"}

    def test_areas_the_root_list_does_not_hold_follow_in_arrival_order(self) -> None:
        hash_list = _map({30: _area(30), 10: _area(10), 20: _area(20)}, root=[20])
        assert _labels(hash_list) == {20: "Area 1", 30: "Area 2", 10: "Area 3"}

    def test_a_hash_listed_twice_takes_one_place(self) -> None:
        """A stale and a fresh root list can both be held, repeating hashes."""
        hash_list = _map({10: _area(10), 20: _area(20)})
        for frame in (1, 2):
            hash_list.update_root_hash_list(
                NavGetHashListData(pver=1, sub_cmd=0, total_frame=frame, current_frame=1, data_couple=[10, 20])
            )
        assert _labels(hash_list) == {10: "Area 1", 20: "Area 2"}

    @pytest.mark.regression
    def test_an_untouched_unnamed_area_keeps_its_label_when_a_neighbour_is_rehashed(self) -> None:
        """Labels were the lowest free number in ``self.area`` order, which a re-hash reorders.

        ``update_hash_lists`` filters ``area``, so the re-hashed area lands last and its untouched
        unnamed neighbour slid from "Area 3" to "Area 2", pointing the label at another lawn.
        """
        before = _map({10: _area(10, name="Front"), 20: _area(20), 30: _area(30)}, root=[10, 20, 30])
        after = _map({10: _area(10, name="Front"), 30: _area(30), 21: _area(21)}, root=[10, 21, 30])

        assert (_labels(before)[30], _labels(after)[30]) == ("Area 3", "Area 3")
        assert (_labels(before)[20], _labels(after)[21]) == ("Area 2", "Area 2")

    def test_a_stored_label_is_kept(self) -> None:
        hash_list = _map({10: _area(10)}, root=[10])
        hash_list.area_name = [AreaHashNameList(name="area 4", hash=10)]
        assert _labels(hash_list) == {10: "area 4"}


class TestFillAreaNamesFromFrames:
    def test_each_area_is_named_from_its_frames(self) -> None:
        hash_list = _map({10: _area(10, name="Voor"), 20: _area(20)})
        hash_list.fill_area_names_from_frames()
        assert {a.hash: a.name for a in hash_list.area_name} == {10: "Voor", 20: ""}

    def test_a_label_stored_earlier_is_replaced(self) -> None:
        """Older versions stored their own "area N" labels; the frames are what the mower reports."""
        hash_list = _map({10: _area(10)})
        hash_list.area_name = [AreaHashNameList(name="area 3", hash=10)]
        hash_list.fill_area_names_from_frames()
        assert _labels(hash_list) == {10: "Area 1"}
