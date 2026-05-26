"""Tests for HashList.invalidate_breakpoint_line."""
from __future__ import annotations

from pymammotion.data.model.hash_list import FrameList, HashList, NavGetCommData

# ---------------------------------------------------------------------------
# Real values extracted from
#   config_entry-mammotion-01KKW3Y71JB495W3AYX1ZN459Y.json
# Two devices are present in that snapshot:
#   Device 1 (Luba-VA6LZCPX) — active, has a breakpoint line
#   Device 2 (second entry)  — idle, no active line
# ---------------------------------------------------------------------------
DEVICE1_UB_PATH_HASH = 1623055749216062189
DEVICE2_UB_PATH_HASH = 0  # device has no active breakpoint line


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_frame(hash_id: int) -> FrameList:
    return FrameList(total_frame=1, sub_cmd=3, data=[NavGetCommData(hash=hash_id)])


def _hash_list_with_lines(*line_hashes: int) -> HashList:
    """Build a HashList pre-populated with dummy type-10 line FrameList entries."""
    hl = HashList()
    for h in line_hashes:
        hl.line[h] = _make_frame(h)
    return hl


# ===========================================================================
# invalidate_breakpoint_line
# ===========================================================================


class TestInvalidateBreakpointLine:
    def test_zero_clears_line_and_returns_false(self) -> None:
        """ub_path_hash=0 means no active breakpoint line — clear everything, no re-fetch."""
        hl = _hash_list_with_lines(111, 222)
        assert hl.invalidate_breakpoint_line(0) is False
        assert hl.line == {}

    def test_zero_on_empty_line_returns_false(self) -> None:
        hl = HashList()
        assert hl.invalidate_breakpoint_line(0) is False

    def test_hash_not_cached_returns_true(self) -> None:
        """Active hash not yet in self.line — caller must re-fetch."""
        hl = HashList()
        assert hl.invalidate_breakpoint_line(DEVICE1_UB_PATH_HASH) is True

    def test_hash_not_cached_leaves_line_empty(self) -> None:
        hl = HashList()
        hl.invalidate_breakpoint_line(DEVICE1_UB_PATH_HASH)
        assert hl.line == {}

    def test_hash_already_cached_returns_false(self) -> None:
        """Active hash is already in self.line — no re-fetch needed."""
        hl = _hash_list_with_lines(DEVICE1_UB_PATH_HASH)
        assert hl.invalidate_breakpoint_line(DEVICE1_UB_PATH_HASH) is False

    def test_hash_already_cached_retains_entry(self) -> None:
        hl = _hash_list_with_lines(DEVICE1_UB_PATH_HASH)
        hl.invalidate_breakpoint_line(DEVICE1_UB_PATH_HASH)
        assert DEVICE1_UB_PATH_HASH in hl.line

    def test_stale_entries_pruned_when_hash_changes(self) -> None:
        """Stale cached lines for other hashes are discarded; only the active one is kept."""
        hl = _hash_list_with_lines(DEVICE1_UB_PATH_HASH, 999, 777)
        hl.invalidate_breakpoint_line(DEVICE1_UB_PATH_HASH)
        assert list(hl.line.keys()) == [DEVICE1_UB_PATH_HASH]

    def test_stale_only_entries_cleared_returns_true(self) -> None:
        """self.line has entries but none match the new active hash — re-fetch needed."""
        hl = _hash_list_with_lines(999, 777)
        assert hl.invalidate_breakpoint_line(DEVICE1_UB_PATH_HASH) is True
        assert hl.line == {}

    def test_repeated_call_with_cached_hash_is_noop(self) -> None:
        """Calling with the same cached hash repeatedly is idempotent."""
        hl = _hash_list_with_lines(DEVICE1_UB_PATH_HASH)
        hl.invalidate_breakpoint_line(DEVICE1_UB_PATH_HASH)
        hl.invalidate_breakpoint_line(DEVICE1_UB_PATH_HASH)
        assert DEVICE1_UB_PATH_HASH in hl.line

    def test_does_not_touch_path_or_area(self) -> None:
        """self.path (type 2) and self.area must be completely unaffected."""
        hl = HashList()
        hl.area[111] = _make_frame(111)
        hl.path[999] = _make_frame(999)
        hl.invalidate_breakpoint_line(DEVICE1_UB_PATH_HASH)
        assert 111 in hl.area
        assert 999 in hl.path

    def test_device2_zero_means_no_active_line(self) -> None:
        """Device 2 reports ub_path_hash=0 — line is cleared, no re-fetch."""
        hl = _hash_list_with_lines(123)
        assert hl.invalidate_breakpoint_line(DEVICE2_UB_PATH_HASH) is False
        assert hl.line == {}

    def test_restore_cached_line_no_refetch(self) -> None:
        """If self.line already contains the active hash, no re-fetch is triggered."""
        hl = HashList()
        hl.line[DEVICE1_UB_PATH_HASH] = _make_frame(DEVICE1_UB_PATH_HASH)
        assert hl.invalidate_breakpoint_line(DEVICE1_UB_PATH_HASH) is False

    def test_cold_start_hash_not_cached(self) -> None:
        """Cold start: hash reported by device, nothing cached yet — re-fetch needed."""
        hl = HashList()
        assert hl.invalidate_breakpoint_line(DEVICE1_UB_PATH_HASH) is True
