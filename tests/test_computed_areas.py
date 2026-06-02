"""Unit tests for HashList.computed_areas.

Edge cases covered
------------------
* Both area and area_name empty → empty result.
* area_name only (no area) → returned as-is (no mutation of originals).
* area only, frame has a name → used directly.
* area only, frame has no name → auto-assigned "Area N" with gap-filling.
* area_name has matching hash with real name → kept, area.name ignored.
* area_name has matching hash with empty name, area has name → filled from area.
* area_name has matching hash with empty name, area has no name → auto "Area N".
* area_name has hashes NOT in area → preserved in output.
* Multiple auto-named areas → no duplicate numbers.
* Gap-fill: "Area 1" and "Area 3" present → next generated is "Area 2".
* computed_areas never mutates self.area_name (shallow-copy safety).
* Repeated calls produce identical results (idempotent).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from pymammotion.data.model.hash_list import (
    AreaHashNameList,
    FrameList,
    HashList,
    NavGetCommData,
    NavNameTime,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_frame_list(name: str = "") -> FrameList:
    """Return a one-frame FrameList whose name_time.name is *name*."""
    frame = NavGetCommData(name_time=NavNameTime(name=name))
    return FrameList(total_frame=1, data=[frame])


def _make_empty_frame_list() -> FrameList:
    """Return a FrameList with no frames (name returns '')."""
    return FrameList()


def _make_hash_list(
    area: dict[int, FrameList] | None = None,
    area_name: list[AreaHashNameList] | None = None,
) -> HashList:
    hl = HashList()
    if area is not None:
        hl.area = area
    if area_name is not None:
        hl.area_name = area_name
    return hl


# ---------------------------------------------------------------------------
# Tests: both empty
# ---------------------------------------------------------------------------


class TestBothEmpty:
    def test_empty_area_and_area_name_returns_empty(self) -> None:
        hl = _make_hash_list()
        assert hl.computed_areas == []


# ---------------------------------------------------------------------------
# Tests: area_name only (no area)
# ---------------------------------------------------------------------------


class TestAreaNameOnly:
    def test_area_name_only_returned_as_is(self) -> None:
        entries = [
            AreaHashNameList(name="Front", hash=1),
            AreaHashNameList(name="Back", hash=2),
        ]
        hl = _make_hash_list(area={}, area_name=entries)
        result = hl.computed_areas
        assert len(result) == 2
        assert {a.name for a in result} == {"Front", "Back"}

    def test_area_name_only_does_not_mutate_original(self) -> None:
        original = [AreaHashNameList(name="Front", hash=1)]
        hl = _make_hash_list(area={}, area_name=original)
        _ = hl.computed_areas
        # original list and its element must be untouched
        assert original[0].name == "Front"


# ---------------------------------------------------------------------------
# Tests: area only
# ---------------------------------------------------------------------------


class TestAreaOnly:
    def test_area_with_name_uses_frame_name(self) -> None:
        hl = _make_hash_list(area={10: _make_frame_list("Garden")})
        result = hl.computed_areas
        assert len(result) == 1
        assert result[0].name == "Garden"
        assert result[0].hash == 10

    def test_area_without_name_gets_area_1(self) -> None:
        hl = _make_hash_list(area={10: _make_empty_frame_list()})
        result = hl.computed_areas
        assert len(result) == 1
        assert result[0].name == "Area 1"
        assert result[0].hash == 10

    def test_multiple_unnamed_areas_numbered_sequentially(self) -> None:
        hl = _make_hash_list(area={
            10: _make_empty_frame_list(),
            20: _make_empty_frame_list(),
            30: _make_empty_frame_list(),
        })
        result = hl.computed_areas
        names = {a.name for a in result}
        assert names == {"Area 1", "Area 2", "Area 3"}

    def test_no_duplicate_numbers_across_auto_areas(self) -> None:
        hl = _make_hash_list(area={i: _make_empty_frame_list() for i in range(1, 6)})
        result = hl.computed_areas
        numbers = [int(a.name.split()[-1]) for a in result]
        assert len(numbers) == len(set(numbers)), "each Area N must be unique"


# ---------------------------------------------------------------------------
# Tests: area_name has matching hash — various name states
# ---------------------------------------------------------------------------


class TestMatchingHash:
    def test_area_name_with_real_name_kept_area_name_ignored(self) -> None:
        """Device-provided name takes precedence over frame name."""
        hl = _make_hash_list(
            area={42: _make_frame_list("Frame Name")},
            area_name=[AreaHashNameList(name="Device Name", hash=42)],
        )
        result = hl.computed_areas
        assert len(result) == 1
        assert result[0].name == "Device Name"

    def test_area_name_empty_fills_from_frame_name(self) -> None:
        """Empty area_name entry gets filled from the frame's name_time.name."""
        hl = _make_hash_list(
            area={42: _make_frame_list("From Frame")},
            area_name=[AreaHashNameList(name="", hash=42)],
        )
        result = hl.computed_areas
        assert result[0].name == "From Frame"

    def test_area_name_empty_no_frame_name_gets_auto_name(self) -> None:
        """Entry with empty name and empty frame name gets auto-assigned."""
        hl = _make_hash_list(
            area={42: _make_empty_frame_list()},
            area_name=[AreaHashNameList(name="", hash=42)],
        )
        result = hl.computed_areas
        assert result[0].name == "Area 1"

    def test_area_name_with_name_not_overwritten_even_if_frame_has_name(self) -> None:
        """Existing non-empty area_name.name is never overwritten."""
        hl = _make_hash_list(
            area={42: _make_frame_list("Should Be Ignored")},
            area_name=[AreaHashNameList(name="Correct Name", hash=42)],
        )
        result = hl.computed_areas
        assert result[0].name == "Correct Name"


# ---------------------------------------------------------------------------
# Tests: area_name hashes NOT in area are preserved
# ---------------------------------------------------------------------------


class TestAreaNameHashesNotInArea:
    def test_extra_area_name_entries_preserved(self) -> None:
        """Hashes in area_name but absent from area are kept in the result."""
        hl = _make_hash_list(
            area={10: _make_frame_list("Active")},
            area_name=[
                AreaHashNameList(name="Active", hash=10),
                AreaHashNameList(name="Stale", hash=99),
            ],
        )
        result = hl.computed_areas
        hashes = {a.hash for a in result}
        assert 99 in hashes
        assert next(a.name for a in result if a.hash == 99) == "Stale"


# ---------------------------------------------------------------------------
# Tests: gap-fill numbering
# ---------------------------------------------------------------------------


class TestGapFillNumbering:
    def test_gap_filled_when_area_1_and_area_3_present(self) -> None:
        """When 'Area 1' and 'Area 3' exist, next unnamed gets 'Area 2'."""
        hl = _make_hash_list(
            area={10: _make_empty_frame_list()},
            area_name=[
                AreaHashNameList(name="Area 1", hash=1),
                AreaHashNameList(name="Area 3", hash=3),
            ],
        )
        result = hl.computed_areas
        new_entry = next(a for a in result if a.hash == 10)
        assert new_entry.name == "Area 2"

    def test_next_after_1_and_2_is_3(self) -> None:
        hl = _make_hash_list(
            area={10: _make_empty_frame_list()},
            area_name=[
                AreaHashNameList(name="Area 1", hash=1),
                AreaHashNameList(name="Area 2", hash=2),
            ],
        )
        result = hl.computed_areas
        new_entry = next(a for a in result if a.hash == 10)
        assert new_entry.name == "Area 3"

    def test_multiple_unnamed_fill_gaps_in_order(self) -> None:
        """Two unnamed areas fill the two lowest available gaps."""
        hl = _make_hash_list(
            area={
                10: _make_empty_frame_list(),
                20: _make_empty_frame_list(),
            },
            area_name=[
                AreaHashNameList(name="Area 2", hash=2),
            ],
        )
        result = hl.computed_areas
        auto_names = {a.name for a in result if a.hash in (10, 20)}
        # Area 1 and Area 3 are the two lowest available numbers
        assert auto_names == {"Area 1", "Area 3"}


# ---------------------------------------------------------------------------
# Tests: immutability — computed_areas must never mutate self.area_name
# ---------------------------------------------------------------------------


class TestNoMutation:
    def test_empty_name_in_area_name_not_mutated(self) -> None:
        """Calling computed_areas must not change area_name entries in place."""
        original_entry = AreaHashNameList(name="", hash=42)
        hl = _make_hash_list(
            area={42: _make_empty_frame_list()},
            area_name=[original_entry],
        )
        _ = hl.computed_areas
        assert original_entry.name == "", "area_name must not be mutated by computed_areas"
        assert hl.area_name[0].name == ""

    def test_area_name_list_itself_not_mutated(self) -> None:
        """computed_areas must not add entries to the original area_name list."""
        hl = _make_hash_list(
            area={99: _make_empty_frame_list()},
            area_name=[],
        )
        _ = hl.computed_areas
        assert hl.area_name == []

    def test_multiple_calls_produce_same_result(self) -> None:
        """computed_areas is idempotent: calling it twice gives equal results."""
        hl = _make_hash_list(
            area={
                1: _make_frame_list("Garden"),
                2: _make_empty_frame_list(),
            },
            area_name=[AreaHashNameList(name="", hash=1)],
        )
        first = hl.computed_areas
        second = hl.computed_areas
        assert [(a.hash, a.name) for a in first] == [(a.hash, a.name) for a in second]


# ---------------------------------------------------------------------------
# Tests: mixed scenarios
# ---------------------------------------------------------------------------


class TestMixedScenarios:
    def test_named_and_unnamed_areas_coexist(self) -> None:
        """Mix of named (via area_name) and unnamed (auto) areas in one call."""
        hl = _make_hash_list(
            area={
                1: _make_frame_list("Front Lawn"),
                2: _make_empty_frame_list(),
                3: _make_empty_frame_list(),
            },
            area_name=[AreaHashNameList(name="Front Lawn", hash=1)],
        )
        result = hl.computed_areas
        assert len(result) == 3
        name_for_1 = next(a.name for a in result if a.hash == 1)
        assert name_for_1 == "Front Lawn"
        auto_names = {a.name for a in result if a.hash in (2, 3)}
        assert auto_names == {"Area 1", "Area 2"}

    def test_area_name_entry_without_matching_area_hash_preserved(self) -> None:
        """area_name entries with no corresponding area hash pass through unchanged."""
        hl = _make_hash_list(
            area={},
            area_name=[
                AreaHashNameList(name="Old Area", hash=555),
            ],
        )
        result = hl.computed_areas
        assert len(result) == 1
        assert result[0].name == "Old Area"
        assert result[0].hash == 555

    def test_real_world_storage_pattern(self) -> None:
        """Mirrors the real storage file: area_name and area both populated with
        matching hashes and real user-assigned names."""
        h1, h2, h3 = 3688811148440690651, 7095723005866681215, 8077478246857054394
        hl = _make_hash_list(
            area={
                h1: _make_frame_list("Backyard part 3"),
                h2: _make_frame_list("Backyard part 2"),
                h3: _make_frame_list("Backyard part 1"),
            },
            area_name=[
                AreaHashNameList(name="back backyard 2", hash=2328695440254478069),
                AreaHashNameList(name="Backyard part 3", hash=h1),
                AreaHashNameList(name="Backyard part 2", hash=h2),
            ],
        )
        result = hl.computed_areas
        by_hash = {a.hash: a.name for a in result}
        # area_name entries kept as-is
        assert by_hash[h1] == "Backyard part 3"
        assert by_hash[h2] == "Backyard part 2"
        # area_name entry with no matching area hash preserved
        assert by_hash[2328695440254478069] == "back backyard 2"
        # h3 has no area_name entry → filled from frame name
        assert by_hash[h3] == "Backyard part 1"


# ---------------------------------------------------------------------------
# Tests: upsert_area_name (single-area rename echo, toapp_map_name_msg path)
# ---------------------------------------------------------------------------


class TestUpsertAreaName:
    def test_insert_when_hash_absent(self) -> None:
        hl = _make_hash_list()
        hl.upsert_area_name(123, "Front Lawn")
        assert hl.area_name == [AreaHashNameList(name="Front Lawn", hash=123)]

    def test_update_in_place_when_hash_present(self) -> None:
        hl = _make_hash_list(
            area_name=[AreaHashNameList(name="Front Lawn", hash=123)]
        )
        hl.upsert_area_name(123, "Back Lawn")
        # Same single entry, name replaced — no duplicate appended.
        assert hl.area_name == [AreaHashNameList(name="Back Lawn", hash=123)]

    def test_update_leaves_other_entries_untouched(self) -> None:
        hl = _make_hash_list(
            area_name=[
                AreaHashNameList(name="One", hash=111),
                AreaHashNameList(name="Two", hash=222),
            ]
        )
        hl.upsert_area_name(222, "Renamed")
        assert hl.area_name == [
            AreaHashNameList(name="One", hash=111),
            AreaHashNameList(name="Renamed", hash=222),
        ]


# ---------------------------------------------------------------------------
# Tests: computed_areas reflects the post-map-sync state
# ---------------------------------------------------------------------------


class TestComputedAreasAfterMapSync:
    """After a sync, computed_areas must reflect the device's CURRENT areas.

    A sync replaces area_name wholesale (toapp_all_hash_name) and prunes/refetches
    area geometry, so computed_areas — the merged view HA renders — must surface the
    updated set: edited areas under their new hash, renames applied, and no
    pre-edit/removed hashes lingering.
    """

    def test_edited_area_appears_under_new_hash_and_drops_old(self) -> None:
        """Editing an area gives it a new hash; the old hash must not linger."""
        # Post-sync state: only the NEW hash has geometry + a name.
        hl = _make_hash_list(
            area={999: _make_frame_list("Backyard part 1")},
            area_name=[AreaHashNameList(name="Backyard part 1", hash=999)],
        )
        by_hash = {a.hash: a.name for a in hl.computed_areas}
        assert by_hash == {999: "Backyard part 1"}
        assert 111 not in by_hash  # the pre-edit hash is gone

    def test_rename_is_reflected(self) -> None:
        """A renamed area (area_name updated in place) shows the new name."""
        hl = _make_hash_list(
            area={123: _make_frame_list("Old Name")},
            area_name=[AreaHashNameList(name="Front Lawn", hash=123)],
        )
        # area_name (set by toapp_all_hash_name / set_area_name) wins over the frame name.
        by_hash = {a.hash: a.name for a in hl.computed_areas}
        assert by_hash[123] == "Front Lawn"

    def test_full_set_after_sync_matches_geometry_and_names(self) -> None:
        """All synced areas (geometry + names aligned) are returned, none missing/extra."""
        hl = _make_hash_list(
            area={
                111: _make_frame_list("Backyard part 1"),
                222: _make_frame_list("Backyard part 2"),
                333: _make_frame_list("Small strip near plum"),
            },
            area_name=[
                AreaHashNameList(name="Backyard part 1", hash=111),
                AreaHashNameList(name="Backyard part 2", hash=222),
                AreaHashNameList(name="Small strip near plum", hash=333),
            ],
        )
        by_hash = {a.hash: a.name for a in hl.computed_areas}
        assert by_hash == {
            111: "Backyard part 1",
            222: "Backyard part 2",
            333: "Small strip near plum",
        }

    def test_removed_area_not_returned(self) -> None:
        """An area deleted device-side (gone from both geometry and names) is dropped."""
        hl = _make_hash_list(
            area={111: _make_frame_list("Kept")},
            area_name=[AreaHashNameList(name="Kept", hash=111)],
        )
        by_hash = {a.hash: a.name for a in hl.computed_areas}
        assert by_hash == {111: "Kept"}

    def test_new_area_with_geometry_but_missing_name_gets_label(self) -> None:
        """A freshly-fetched area whose name hasn't arrived yet still surfaces."""
        # Geometry present, but area_name doesn't list this hash and the frame is unnamed.
        hl = _make_hash_list(
            area={777: _make_empty_frame_list()},
            area_name=[],
        )
        by_hash = {a.hash: a.name for a in hl.computed_areas}
        assert 777 in by_hash
        assert by_hash[777].startswith("Area ")
