"""Pool-cleaner state models: the parsed device times they expose."""

from __future__ import annotations

from datetime import UTC, datetime

from pymammotion.data.model.pool_state import SpinoErrorEntry


def test_error_entry_logged_at_parses_a_real_timestamp() -> None:
    assert SpinoErrorEntry(code=-1, timestamp=1_725_159_492).logged_at == datetime(2024, 9, 1, 2, 58, 12, tzinfo=UTC)


def test_error_entry_logged_at_is_none_for_an_uptime_stamp() -> None:
    assert SpinoErrorEntry(code=-1, timestamp=3_600).logged_at is None
