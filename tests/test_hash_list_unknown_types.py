"""Tests for HashList resilience to unknown PathType values.

The 2026-05-22 LUBA_VA log incident showed that ``toapp_get_commondata_ack``
frames can arrive with ``type`` values pymammotion doesn't model (radar-only
type=23 was observed, but the symptom generalises to any future type).
Before the fix, ``update()`` silently returned False so the hash was never
stored — ``find_incomplete_hashes`` then kept flagging the hash as missing
and ``MapFetchSaga`` stalled re-requesting it.

These tests pin the new behaviour: unknown types go into
``unknown_type_frames`` and ``find_incomplete_hashes`` treats the hash as
fetched once a frame lands there.
"""
from __future__ import annotations

from pymammotion.data.model.hash_list import (
    HashList,
    NavGetCommData,
    NavGetHashListData,
    PathType,
)


def _hash_list_root(hash_ids: list[int]) -> NavGetHashListData:
    """Single-frame root hash list (sub_cmd=0) for the given IDs."""
    return NavGetHashListData(
        pver=1,
        sub_cmd=0,
        total_frame=1,
        current_frame=1,
        data_couple=hash_ids,
    )


def _frame(hash_id: int, type_code: int, current: int = 1, total: int = 1) -> NavGetCommData:
    return NavGetCommData(
        pver=1,
        action=8,
        type=type_code,
        hash=hash_id,
        total_frame=total,
        current_frame=current,
    )


# ---------------------------------------------------------------------------
# update() routes unknown types to unknown_type_frames
# ---------------------------------------------------------------------------


def test_update_routes_unknown_type_into_unknown_type_frames() -> None:
    """A frame with a type not in PathType is stored under unknown_type_frames[type][hash]."""
    hl = HashList()
    hl.update_root_hash_list(_hash_list_root([100]))

    # type=99 isn't modelled — must land in unknown_type_frames[99][100]
    assert hl.update(_frame(100, type_code=99)) is True
    assert 99 in hl.unknown_type_frames
    assert 100 in hl.unknown_type_frames[99]
    # Standard buckets must NOT receive it
    assert 100 not in hl.area
    assert 100 not in hl.obstacle


def test_update_routes_known_type_unchanged() -> None:
    """Adding the unknown-type fallback must not affect known-type routing."""
    hl = HashList()
    hl.update_root_hash_list(_hash_list_root([100]))

    assert hl.update(_frame(100, type_code=PathType.AREA)) is True
    assert 100 in hl.area
    assert hl.unknown_type_frames == {}


def test_update_routes_no_go_zone_type_23() -> None:
    """PathType.NO_GO_ZONE (23) — explicitly modelled as a sibling of virtual_wall."""
    hl = HashList()
    hl.update_root_hash_list(_hash_list_root([200]))

    assert hl.update(_frame(200, type_code=PathType.NO_GO_ZONE)) is True
    assert 200 in hl.no_go_zone
    # NO_GO_ZONE is known, so it should NOT fall through to the unknown bucket.
    assert 23 not in hl.unknown_type_frames


# ---------------------------------------------------------------------------
# find_incomplete_hashes consults unknown_type_frames
# ---------------------------------------------------------------------------


def test_find_incomplete_treats_unknown_type_hash_as_complete() -> None:
    """A hash whose only frame is an unknown type must not be reported as incomplete.

    Before the fix, this is the exact stall the LUBA_VA saga hit: type=23
    frames were dropped, the hash had no entry in any per-type dict, and
    find_incomplete_hashes kept returning it forever.
    """
    hl = HashList()
    hl.update_root_hash_list(_hash_list_root([300]))

    # Before any frame arrives, the hash is incomplete.
    assert 300 in hl.find_incomplete_hashes(0)

    # An unknown-type single-frame transaction completes the hash.
    hl.update(_frame(300, type_code=99))
    assert 300 not in hl.find_incomplete_hashes(0)


def test_find_incomplete_still_reports_partial_unknown_type_hash() -> None:
    """If only frame 1 of N arrives for an unknown type, the hash stays incomplete."""
    hl = HashList()
    hl.update_root_hash_list(_hash_list_root([400]))

    # Partial — frame 1 of 3
    hl.update(_frame(400, type_code=99, current=1, total=3))
    assert 400 in hl.find_incomplete_hashes(0)

    # Finishing the transaction marks the hash complete.
    hl.update(_frame(400, type_code=99, current=2, total=3))
    hl.update(_frame(400, type_code=99, current=3, total=3))
    assert 400 not in hl.find_incomplete_hashes(0)


def test_find_incomplete_mixed_known_and_unknown_types() -> None:
    """Two hashes — one filled via AREA, one via unknown type — both complete."""
    hl = HashList()
    hl.update_root_hash_list(_hash_list_root([500, 501]))

    hl.update(_frame(500, type_code=PathType.AREA))
    hl.update(_frame(501, type_code=99))

    assert hl.find_incomplete_hashes(0) == []


# ---------------------------------------------------------------------------
# Type 22 — sibling of NO_GO_ZONE (23), explicitly modelled
# ---------------------------------------------------------------------------


def test_update_routes_no_go_zone_variant_type_22() -> None:
    """PathType.NO_GO_ZONE_VARIANT (22) lands in its own dict, NOT in no_go_zone (23)."""
    hl = HashList()
    hl.update_root_hash_list(_hash_list_root([600, 601]))

    assert hl.update(_frame(600, type_code=PathType.NO_GO_ZONE_VARIANT)) is True
    assert hl.update(_frame(601, type_code=PathType.NO_GO_ZONE)) is True

    assert 600 in hl.no_go_zone_variant
    assert 600 not in hl.no_go_zone
    assert 601 in hl.no_go_zone
    assert 601 not in hl.no_go_zone_variant
    # Neither falls into the unknown bucket
    assert hl.unknown_type_frames == {}
    # Both hashes are considered fetched
    assert hl.find_incomplete_hashes(0) == []


# ---------------------------------------------------------------------------
# Future-proofing: any type pymammotion doesn't know about must NOT stall the saga
# ---------------------------------------------------------------------------


def test_update_catches_arbitrary_future_type_numbers() -> None:
    """The unknown_type_frames fallback must accept any type pymammotion hasn't
    explicitly modelled — even far-future protocol additions (e.g. type=200).

    This is the safety-net that prevents new device firmware from re-introducing
    the LUBA_VA stall when Mammotion adds new types we haven't reverse-engineered.
    """
    hl = HashList()
    hl.update_root_hash_list(_hash_list_root([700, 701, 702]))

    # Three different unknown types — all must route to the fallback bucket
    # and mark their hash as fetched.
    for hash_id, type_code in [(700, 99), (701, 150), (702, 200)]:
        assert hl.update(_frame(hash_id, type_code=type_code)) is True
        assert type_code in hl.unknown_type_frames
        assert hash_id in hl.unknown_type_frames[type_code]

    # All three hashes considered fetched — find_incomplete returns empty.
    assert hl.find_incomplete_hashes(0) == []


def test_unknown_type_frames_groups_by_type() -> None:
    """Multiple hashes under the same unknown type share a sub-dict; different
    types live in separate sub-dicts."""
    hl = HashList()
    hl.update_root_hash_list(_hash_list_root([800, 801, 802]))

    hl.update(_frame(800, type_code=99))
    hl.update(_frame(801, type_code=99))
    hl.update(_frame(802, type_code=150))

    assert set(hl.unknown_type_frames.keys()) == {99, 150}
    assert set(hl.unknown_type_frames[99].keys()) == {800, 801}
    assert set(hl.unknown_type_frames[150].keys()) == {802}
