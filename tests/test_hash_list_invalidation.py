"""Tests for HashList.invalidate_zones and HashList.invalidate_paths."""
from __future__ import annotations

import pytest

from pymammotion.data.model.hash_list import FrameList, HashList, NavGetCommData

# ---------------------------------------------------------------------------
# Real values extracted from
#   config_entry-mammotion-01KKW3Y71JB495W3AYX1ZN459Y.json
# Two devices are present in that snapshot:
#   Device 1 (Luba-VA6LZCPX) — active, has zones and paths
#   Device 2 (second entry)  — idle, no paths
# ---------------------------------------------------------------------------
DEVICE1_UB_ZONE_HASH = 6835024942066213120
DEVICE1_UB_PATH_HASH = 1623055749216062189

DEVICE2_UB_ZONE_HASH = 4620586938793048438
DEVICE2_UB_PATH_HASH = 0  # device has no recorded paths


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_list_with_zones(*zone_hashes: int) -> HashList:
    """Build a HashList pre-populated with dummy zone FrameList entries."""
    hl = HashList()
    for h in zone_hashes:
        hl.area[h] = FrameList(total_frame=1, sub_cmd=0, data=[NavGetCommData(hash=h)])
    return hl


def _hash_list_with_paths(*path_hashes: int) -> HashList:
    """Build a HashList pre-populated with dummy path FrameList entries."""
    hl = HashList()
    for h in path_hashes:
        hl.path[h] = FrameList(total_frame=1, sub_cmd=0, data=[NavGetCommData(hash=h)])
    return hl


# ===========================================================================
# invalidate_zones
# ===========================================================================


class TestInvalidateZones:
    def test_first_call_with_nonzero_returns_true(self) -> None:
        hl = HashList()
        assert hl.invalidate_zones(DEVICE1_UB_ZONE_HASH) is True

    def test_first_call_stores_hash(self) -> None:
        hl = HashList()
        hl.invalidate_zones(DEVICE1_UB_ZONE_HASH)
        assert hl.last_ub_zone_hash == DEVICE1_UB_ZONE_HASH

    def test_first_call_clears_root_hash_lists(self) -> None:
        from pymammotion.data.model.hash_list import NavGetHashListData, RootHashList
        hl = HashList()
        hl.root_hash_lists = [RootHashList(total_frame=1, sub_cmd=0, data=[NavGetHashListData()])]
        hl.invalidate_zones(DEVICE1_UB_ZONE_HASH)
        assert hl.root_hash_lists == []

    def test_same_hash_returns_false(self) -> None:
        hl = HashList()
        hl.invalidate_zones(DEVICE1_UB_ZONE_HASH)  # first call — accepted
        assert hl.invalidate_zones(DEVICE1_UB_ZONE_HASH) is False  # repeated — no-op

    def test_zero_is_ignored(self) -> None:
        hl = HashList()
        assert hl.invalidate_zones(0) is False
        assert hl.last_ub_zone_hash == 0

    def test_zero_after_valid_hash_does_not_reset(self) -> None:
        """Zero sentinel must never overwrite a previously learned hash."""
        hl = HashList()
        hl.invalidate_zones(DEVICE1_UB_ZONE_HASH)
        assert hl.invalidate_zones(0) is False
        assert hl.last_ub_zone_hash == DEVICE1_UB_ZONE_HASH

    def test_hash_change_returns_true(self) -> None:
        hl = HashList()
        hl.invalidate_zones(DEVICE1_UB_ZONE_HASH)
        assert hl.invalidate_zones(DEVICE2_UB_ZONE_HASH) is True

    def test_hash_change_updates_stored_hash(self) -> None:
        hl = HashList()
        hl.invalidate_zones(DEVICE1_UB_ZONE_HASH)
        hl.invalidate_zones(DEVICE2_UB_ZONE_HASH)
        assert hl.last_ub_zone_hash == DEVICE2_UB_ZONE_HASH

    def test_hash_change_clears_root_hash_lists(self) -> None:
        from pymammotion.data.model.hash_list import NavGetHashListData, RootHashList
        hl = HashList()
        hl.invalidate_zones(DEVICE1_UB_ZONE_HASH)
        hl.root_hash_lists = [RootHashList(total_frame=1, sub_cmd=0, data=[NavGetHashListData()])]
        hl.invalidate_zones(DEVICE2_UB_ZONE_HASH)
        assert hl.root_hash_lists == []

    def test_area_data_not_cleared(self) -> None:
        """invalidate_zones only clears root_hash_lists, not already-fetched area frames."""
        hl = _hash_list_with_zones(111, 222)
        hl.invalidate_zones(DEVICE1_UB_ZONE_HASH)
        # Area frames should still be present — only root_hash_lists is cleared
        assert 111 in hl.area
        assert 222 in hl.area

    def test_device2_zero_path_hash_ignored(self) -> None:
        """Device 2 has ub_zone_hash but ub_path_hash==0 — zone check still works."""
        hl = HashList()
        assert hl.invalidate_zones(DEVICE2_UB_ZONE_HASH) is True
        assert hl.last_ub_zone_hash == DEVICE2_UB_ZONE_HASH


# ===========================================================================
# invalidate_paths
# ===========================================================================


class TestInvalidatePaths:
    def test_first_call_with_nonzero_returns_true(self) -> None:
        hl = HashList()
        assert hl.invalidate_paths(DEVICE1_UB_PATH_HASH) is True

    def test_first_call_stores_hash(self) -> None:
        hl = HashList()
        hl.invalidate_paths(DEVICE1_UB_PATH_HASH)
        assert hl.last_ub_path_hash == DEVICE1_UB_PATH_HASH

    def test_first_call_clears_path_dict(self) -> None:
        hl = _hash_list_with_paths(999, 1234)
        hl.invalidate_paths(DEVICE1_UB_PATH_HASH)
        assert hl.path == {}

    def test_same_hash_returns_false(self) -> None:
        hl = HashList()
        hl.invalidate_paths(DEVICE1_UB_PATH_HASH)
        assert hl.invalidate_paths(DEVICE1_UB_PATH_HASH) is False

    def test_same_hash_does_not_clear_paths(self) -> None:
        hl = _hash_list_with_paths(999)
        hl.invalidate_paths(DEVICE1_UB_PATH_HASH)  # first — clears
        hl.path[999] = FrameList(total_frame=1, sub_cmd=0, data=[NavGetCommData(hash=999)])
        hl.invalidate_paths(DEVICE1_UB_PATH_HASH)  # same — should not clear
        assert 999 in hl.path

    def test_zero_is_ignored(self) -> None:
        hl = HashList()
        assert hl.invalidate_paths(DEVICE2_UB_PATH_HASH) is False  # DEVICE2 has 0
        assert hl.last_ub_path_hash == 0

    def test_zero_after_valid_hash_does_not_reset(self) -> None:
        hl = HashList()
        hl.invalidate_paths(DEVICE1_UB_PATH_HASH)
        assert hl.invalidate_paths(0) is False
        assert hl.last_ub_path_hash == DEVICE1_UB_PATH_HASH

    def test_hash_change_returns_true(self) -> None:
        hl = HashList()
        hl.invalidate_paths(DEVICE1_UB_PATH_HASH)
        assert hl.invalidate_paths(DEVICE1_UB_PATH_HASH + 1) is True

    def test_hash_change_clears_path_dict(self) -> None:
        hl = _hash_list_with_paths(777)
        hl.last_ub_path_hash = DEVICE1_UB_PATH_HASH
        hl.invalidate_paths(DEVICE1_UB_PATH_HASH + 1)
        assert hl.path == {}

    def test_area_data_not_cleared(self) -> None:
        """invalidate_paths must not touch area or other map data."""
        hl = _hash_list_with_zones(111)
        hl.invalidate_paths(DEVICE1_UB_PATH_HASH)
        assert 111 in hl.area

    def test_device2_zero_path_means_no_paths_to_sync(self) -> None:
        """Device 2 reports ub_path_hash=0 (no recorded paths) — no sync triggered."""
        hl = HashList()
        result = hl.invalidate_paths(DEVICE2_UB_PATH_HASH)
        assert result is False
        assert hl.last_ub_path_hash == 0


# ===========================================================================
# Combined behaviour
# ===========================================================================


class TestCombined:
    def test_zone_and_path_independent(self) -> None:
        """Zone invalidation must not affect path tracking, and vice versa."""
        hl = HashList()
        hl.invalidate_zones(DEVICE1_UB_ZONE_HASH)
        hl.invalidate_paths(DEVICE1_UB_PATH_HASH)
        assert hl.last_ub_zone_hash == DEVICE1_UB_ZONE_HASH
        assert hl.last_ub_path_hash == DEVICE1_UB_PATH_HASH

    def test_restore_from_persisted_state_no_spurious_trigger(self) -> None:
        """Simulates restoring saved state: if the hashes are already stored,
        receiving the same values from the device must not re-trigger a sync."""
        hl = HashList()
        hl.last_ub_zone_hash = DEVICE1_UB_ZONE_HASH
        hl.last_ub_path_hash = DEVICE1_UB_PATH_HASH

        assert hl.invalidate_zones(DEVICE1_UB_ZONE_HASH) is False
        assert hl.invalidate_paths(DEVICE1_UB_PATH_HASH) is False

    def test_real_device1_values(self) -> None:
        """End-to-end with values from the actual config-entry snapshot."""
        hl = HashList()
        assert hl.invalidate_zones(DEVICE1_UB_ZONE_HASH) is True
        assert hl.invalidate_paths(DEVICE1_UB_PATH_HASH) is True
        # Second report with same values — no further triggers
        assert hl.invalidate_zones(DEVICE1_UB_ZONE_HASH) is False
        assert hl.invalidate_paths(DEVICE1_UB_PATH_HASH) is False

    def test_real_device2_values(self) -> None:
        """Device 2 has zones but no paths — only zone invalidation fires."""
        hl = HashList()
        assert hl.invalidate_zones(DEVICE2_UB_ZONE_HASH) is True
        assert hl.invalidate_paths(DEVICE2_UB_PATH_HASH) is False  # 0 — ignored
