"""Unit tests for mower-task helpers (``Plan.with_*`` + ``utility/plan_id``).

Covers the wire-format invariants the HA layer depends on:
* ``Plan.with_enabled`` flips only ``reserved[2]`` and preserves the
  other 7 bytes byte-for-byte.
* ``Plan.is_enabled`` decodes the same byte.
* ``new_mower_plan_id`` produces the APK's 21-char timestamp+random
  layout.
* ``make_copy_name`` skips collisions like the APK's ``getCopyTaskName``.
"""

from __future__ import annotations

from pymammotion.data.model.hash_list import Plan
from pymammotion.utility.plan_id import make_copy_name, new_mower_plan_id


class TestPlanEnabled:
    def test_defaults_to_enabled_when_reserved_is_empty(self) -> None:
        # APK behaviour: missing reserved → treated as enabled.
        assert Plan().is_enabled() is True

    def test_with_enabled_sets_only_byte_two(self) -> None:
        # +10 offset on bytes 0,1,3,4,5,6 mirrors the APK's encoding; we
        # round-trip the buffer verbatim so the helper preserves them.
        original = "".join(chr(c) for c in [11, 12, 1, 13, 14, 15, 16, 0])
        plan = Plan(reserved=original)

        toggled_off = plan.with_enabled(False).reserved.encode("latin-1")
        assert list(toggled_off) == [11, 12, 0, 13, 14, 15, 16, 0]

        toggled_on = plan.with_enabled(True).reserved.encode("latin-1")
        assert list(toggled_on) == [11, 12, 1, 13, 14, 15, 16, 0]

    def test_with_enabled_pads_short_buffer_to_8_bytes(self) -> None:
        plan = Plan(reserved="")  # zero-length buffer
        raw = plan.with_enabled(True).reserved.encode("latin-1")
        assert len(raw) == 8
        assert raw[2] == 1
        # Padding bytes are 0
        for i in (0, 1, 3, 4, 5, 6, 7):
            assert raw[i] == 0

    def test_is_enabled_reads_byte_two(self) -> None:
        plan = Plan(reserved="".join(chr(c) for c in [0, 0, 0, 0, 0, 0, 0, 0]))
        assert plan.is_enabled() is False
        plan = Plan(reserved="".join(chr(c) for c in [0, 0, 1, 0, 0, 0, 0, 0]))
        assert plan.is_enabled() is True

    def test_with_renamed(self) -> None:
        plan = Plan(task_name="A").with_renamed("B")
        assert plan.task_name == "B"


class TestNewMowerPlanId:
    def test_length_is_21(self) -> None:
        assert len(new_mower_plan_id()) == 21

    def test_starts_with_timestamp(self) -> None:
        pid = new_mower_plan_id(now_ms=1622471234567)
        assert pid[:13] == "1622471234567"

    def test_random_suffix_in_0_to_8_range(self) -> None:
        pid = new_mower_plan_id(now_ms=1622471234567)
        for ch in pid[13:]:
            assert ch.isdigit()
            assert 0 <= int(ch) <= 8


class TestMakeCopyName:
    def test_first_slot_when_none_taken(self) -> None:
        assert make_copy_name([]) == "Copy-1"

    def test_skips_existing_slots(self) -> None:
        # APK semantics: iterate 1..N until we find a non-collision.
        assert make_copy_name(["Copy-1", "Copy-2"]) == "Copy-3"

    def test_handles_gaps(self) -> None:
        assert make_copy_name(["Copy-1", "Copy-3"]) == "Copy-2"

    def test_alternative_base(self) -> None:
        assert make_copy_name([], base="Backup") == "Backup-1"
