"""Unit tests for pymammotion.data.model.hash_list (HashList + FrameList).

Grouped by the method under test:
  * FrameList.name
  * HashList.computed_areas / .upsert_area_name
  * HashList.update (per-type routing, unknown-type fallback)
  * HashList.find_incomplete_hashes
  * HashList.update_hash_lists (area-name preservation / pruning)
  * HashList.invalidate_breakpoint_line

GeoJSON generation lives in test_generate_geojson.py (it mirrors
generate_geojson.py); saga/state-reducer flows live in their own modules.
"""

from __future__ import annotations

from pymammotion.data.model.hash_list import (
    AreaHashNameList,
    FrameList,
    HashList,
    NavGetCommData,
    NavGetHashListData,
    NavNameTime,
    PathType,
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


def _root(hash_ids: list[int]) -> NavGetHashListData:
    """Single-frame root hash list (sub_cmd=0) for the given IDs."""
    return NavGetHashListData(pver=1, sub_cmd=0, total_frame=1, current_frame=1, data_couple=hash_ids)


def _comm_frame(hash_id: int, type_code: int, current: int = 1, total: int = 1) -> NavGetCommData:
    """A single NavGetCommData frame of the given type for HashList.update()."""
    return NavGetCommData(pver=1, action=8, type=type_code, hash=hash_id, total_frame=total, current_frame=current)


def _line_frame(hash_id: int) -> FrameList:
    """A type-3 (breakpoint line) FrameList for one hash."""
    return FrameList(total_frame=1, sub_cmd=3, data=[NavGetCommData(hash=hash_id)])


def _hash_list_with_lines(*line_hashes: int) -> HashList:
    """Build a HashList pre-populated with type-3 line FrameList entries."""
    hl = HashList()
    for h in line_hashes:
        hl.line[h] = _line_frame(h)
    return hl


# ---------------------------------------------------------------------------
# FrameList.name
# ---------------------------------------------------------------------------


class TestFrameListName:
    def test_returns_name_time_name_when_set(self) -> None:
        fl = FrameList(data=[NavGetCommData(name_time=NavNameTime(name="Voor", create_time=1, modify_time=1))])
        assert fl.name == "Voor"

    def test_returns_empty_when_name_time_name_is_empty(self) -> None:
        fl = FrameList(data=[NavGetCommData(name_time=NavNameTime(name="", create_time=0, modify_time=0))])
        assert fl.name == ""

    def test_returns_empty_when_no_data(self) -> None:
        assert FrameList().name == ""

    def test_uses_first_frame_only(self) -> None:
        """name_time.name from the first frame wins even if later frames differ."""
        fl = FrameList(
            data=[
                NavGetCommData(name_time=NavNameTime(name="First")),
                NavGetCommData(name_time=NavNameTime(name="Second")),
            ]
        )
        assert fl.name == "First"


# ---------------------------------------------------------------------------
# computed_areas — both empty
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
# HashList.update — per-type routing + unknown-type fallback
# ---------------------------------------------------------------------------


class TestUpdateRouting:
    """update() routes each frame into its per-type dict; unknown types fall back.

    Regression context: a toapp_get_commondata_ack with a type pymammotion didn't
    model (radar type=23 on LUBA_VA) used to be dropped, so find_incomplete_hashes
    kept flagging the hash and MapFetchSaga stalled re-requesting it.
    """

    def test_known_type_routes_to_its_dict(self) -> None:
        hl = HashList()
        hl.update_root_hash_list(_root([100]))
        assert hl.update(_comm_frame(100, PathType.AREA)) is True
        assert 100 in hl.area
        assert hl.unknown_type_frames == {}

    def test_unknown_type_routes_to_unknown_type_frames(self) -> None:
        hl = HashList()
        hl.update_root_hash_list(_root([100]))
        assert hl.update(_comm_frame(100, type_code=99)) is True
        assert hl.unknown_type_frames[99].keys() == {100}
        assert 100 not in hl.area and 100 not in hl.obstacle

    def test_no_go_zone_type_23_routes_to_its_own_dict(self) -> None:
        hl = HashList()
        hl.update_root_hash_list(_root([200]))
        assert hl.update(_comm_frame(200, PathType.NO_GO_ZONE)) is True
        assert 200 in hl.no_go_zone
        assert 23 not in hl.unknown_type_frames

    def test_no_go_zone_variant_type_22_distinct_from_type_23(self) -> None:
        hl = HashList()
        hl.update_root_hash_list(_root([600, 601]))
        hl.update(_comm_frame(600, PathType.NO_GO_ZONE_VARIANT))
        hl.update(_comm_frame(601, PathType.NO_GO_ZONE))
        assert 600 in hl.no_go_zone_variant and 600 not in hl.no_go_zone
        assert 601 in hl.no_go_zone and 601 not in hl.no_go_zone_variant
        assert hl.unknown_type_frames == {}

    def test_unknown_type_frames_groups_by_type(self) -> None:
        hl = HashList()
        hl.update_root_hash_list(_root([800, 801, 802]))
        hl.update(_comm_frame(800, type_code=99))
        hl.update(_comm_frame(801, type_code=99))
        hl.update(_comm_frame(802, type_code=150))
        assert hl.unknown_type_frames.keys() == {99, 150}
        assert hl.unknown_type_frames[99].keys() == {800, 801}
        assert hl.unknown_type_frames[150].keys() == {802}

    def test_arbitrary_future_type_numbers_are_accepted(self) -> None:
        """Any unmodelled type must route to the fallback and mark its hash fetched."""
        hl = HashList()
        hl.update_root_hash_list(_root([700, 701, 702]))
        for hash_id, type_code in [(700, 99), (701, 150), (702, 200)]:
            assert hl.update(_comm_frame(hash_id, type_code=type_code)) is True
            assert hash_id in hl.unknown_type_frames[type_code]
        assert hl.find_incomplete_hashes(0) == []


# ---------------------------------------------------------------------------
# HashList.find_incomplete_hashes
# ---------------------------------------------------------------------------


class TestFindIncompleteHashes:
    def test_unfetched_hash_is_incomplete(self) -> None:
        hl = HashList()
        hl.update_root_hash_list(_root([300]))
        assert 300 in hl.find_incomplete_hashes(0)

    def test_unknown_type_single_frame_completes_the_hash(self) -> None:
        hl = HashList()
        hl.update_root_hash_list(_root([300]))
        hl.update(_comm_frame(300, type_code=99))
        assert 300 not in hl.find_incomplete_hashes(0)

    def test_partial_unknown_type_stays_incomplete_until_all_frames(self) -> None:
        hl = HashList()
        hl.update_root_hash_list(_root([400]))
        hl.update(_comm_frame(400, type_code=99, current=1, total=3))
        assert 400 in hl.find_incomplete_hashes(0)
        hl.update(_comm_frame(400, type_code=99, current=2, total=3))
        hl.update(_comm_frame(400, type_code=99, current=3, total=3))
        assert 400 not in hl.find_incomplete_hashes(0)

    def test_mixed_known_and_unknown_types_all_complete(self) -> None:
        hl = HashList()
        hl.update_root_hash_list(_root([500, 501]))
        hl.update(_comm_frame(500, PathType.AREA))
        hl.update(_comm_frame(501, type_code=99))
        assert hl.find_incomplete_hashes(0) == []


# ---------------------------------------------------------------------------
# HashList.update_hash_lists — prunes geometry to the manifest, preserves names
# ---------------------------------------------------------------------------


class TestUpdateHashLists:
    def test_preserves_existing_names_not_in_new_hashlist(self) -> None:
        """area_name entries already resolved must survive a prune (keyed by hash)."""
        hl = HashList()
        hl.area_name = [AreaHashNameList(name="Front", hash=100), AreaHashNameList(name="Back", hash=200)]
        hl.update_hash_lists([100])
        assert {a.hash: a.name for a in hl.area_name} == {100: "Front", 200: "Back"}

    def test_new_hash_does_not_displace_existing_names(self) -> None:
        hl = HashList()
        hl.area_name = [AreaHashNameList(name="Front", hash=100)]
        hl.update_hash_lists([100, 300])
        assert {a.hash: a.name for a in hl.area_name}[100] == "Front"

    def test_empty_hashlist_is_a_noop(self) -> None:
        """An empty manifest must early-return without wiping names (or geometry)."""
        hl = HashList()
        hl.area_name = [AreaHashNameList(name="Front", hash=100)]
        hl.update_hash_lists([])
        assert hl.area_name == [AreaHashNameList(name="Front", hash=100)]

    def test_repeated_calls_do_not_duplicate_names(self) -> None:
        hl = HashList()
        hl.area_name = [AreaHashNameList(name="Front", hash=100)]
        hl.update_hash_lists([100])
        hl.update_hash_lists([100])
        assert hl.area_name == [AreaHashNameList(name="Front", hash=100)]


# ---------------------------------------------------------------------------
# HashList.invalidate_breakpoint_line
# ---------------------------------------------------------------------------

# Real ub_path_hash extracted from a Luba-VA6LZCPX snapshot (active breakpoint line).
_ACTIVE_LINE_HASH = 1623055749216062189


class TestInvalidateBreakpointLine:
    def test_zero_hash_clears_line_and_signals_no_refetch(self) -> None:
        """ub_path_hash=0 means no active line — clear everything, no re-fetch."""
        hl = _hash_list_with_lines(111, 222)
        assert hl.invalidate_breakpoint_line(0) is False
        assert hl.line == {}

    def test_zero_hash_on_empty_line_is_noop(self) -> None:
        assert HashList().invalidate_breakpoint_line(0) is False

    def test_uncached_active_hash_signals_refetch(self) -> None:
        """Active hash not yet cached — caller must re-fetch, line stays empty."""
        hl = HashList()
        assert hl.invalidate_breakpoint_line(_ACTIVE_LINE_HASH) is True
        assert hl.line == {}

    def test_cached_active_hash_signals_no_refetch_and_is_retained(self) -> None:
        hl = _hash_list_with_lines(_ACTIVE_LINE_HASH)
        assert hl.invalidate_breakpoint_line(_ACTIVE_LINE_HASH) is False
        assert _ACTIVE_LINE_HASH in hl.line

    def test_stale_entries_pruned_keeping_only_active(self) -> None:
        hl = _hash_list_with_lines(_ACTIVE_LINE_HASH, 999, 777)
        hl.invalidate_breakpoint_line(_ACTIVE_LINE_HASH)
        assert list(hl.line.keys()) == [_ACTIVE_LINE_HASH]

    def test_only_stale_entries_cleared_and_refetch_signalled(self) -> None:
        hl = _hash_list_with_lines(999, 777)
        assert hl.invalidate_breakpoint_line(_ACTIVE_LINE_HASH) is True
        assert hl.line == {}

    def test_repeated_call_with_cached_hash_is_idempotent(self) -> None:
        hl = _hash_list_with_lines(_ACTIVE_LINE_HASH)
        hl.invalidate_breakpoint_line(_ACTIVE_LINE_HASH)
        hl.invalidate_breakpoint_line(_ACTIVE_LINE_HASH)
        assert _ACTIVE_LINE_HASH in hl.line

    def test_does_not_touch_path_or_area(self) -> None:
        hl = HashList()
        hl.area[111] = _line_frame(111)
        hl.path[999] = _line_frame(999)
        hl.invalidate_breakpoint_line(_ACTIVE_LINE_HASH)
        assert 111 in hl.area and 999 in hl.path


# ---------------------------------------------------------------------------
# computed_areas — post-sync regression (edited area gets a new content hash)
# ---------------------------------------------------------------------------


class TestComputedAreasAfterEdit:
    def test_edited_area_appears_under_new_hash_and_old_is_gone(self) -> None:
        """Editing an area gives it a new hash; computed_areas surfaces only the new one.

        Post-sync state: area + area_name carry only the NEW hash (the pre-edit hash
        was pruned by update_hash_lists), so the old hash must not reappear.
        """
        hl = _make_hash_list(
            area={999: _make_frame_list("Backyard part 1")},
            area_name=[AreaHashNameList(name="Backyard part 1", hash=999)],
        )
        by_hash = {a.hash: a.name for a in hl.computed_areas}
        assert by_hash == {999: "Backyard part 1"}
        assert 111 not in by_hash
