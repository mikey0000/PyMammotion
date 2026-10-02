"""Parse the integer timestamps devices stamp on their reports and events."""

from __future__ import annotations

from datetime import UTC, datetime

#: 2001-09-09.  Firmware stamps a fresh error-log entry with its uptime seconds (rewritten
#: with real time later), pads empty slots with 0 and can send ``ft`` / ``localTime`` as 0.
MIN_DEVICE_EPOCH = 1_000_000_000

#: A seconds value this large is past the year 5000, so anything at or above it is milliseconds.
_MILLIS_FLOOR = 100_000_000_000


def device_epoch(value: float | str | None, *, millis: bool | None = None) -> datetime | None:
    """Return *value* as a UTC datetime, or None when it is not a real time.

    *millis* names the unit; ``None`` guesses, because firmware sends ``localTime`` in
    either.  Non-numeric input and anything before :data:`MIN_DEVICE_EPOCH` give None.
    """
    if value is None:
        return None
    try:
        seconds = int(value)
    except (ValueError, OverflowError):
        return None
    if millis if millis is not None else seconds >= _MILLIS_FLOOR:
        seconds //= 1000
    if seconds < MIN_DEVICE_EPOCH:
        return None
    try:
        return datetime.fromtimestamp(seconds, UTC)
    except (OverflowError, OSError, ValueError):
        return None
