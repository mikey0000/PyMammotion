"""``device_epoch`` — turning a device-stamped integer into a UTC datetime, or None.

Firmware stamps a fresh error-log entry with its uptime seconds and rewrites it with
real time later, pads empty slots with 0, and sends 0 in a warning event's ``ft`` /
``localTime``.  None of those is a date, and rendering one shows "1970".
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pymammotion.utility.device_time import MIN_DEVICE_EPOCH, device_epoch

_REAL = 1_725_159_492  # 2024-09-01T02:58:12Z


def test_device_epoch_parses_real_seconds_as_utc() -> None:
    assert device_epoch(_REAL) == datetime(2024, 9, 1, 2, 58, 12, tzinfo=UTC)


def test_device_epoch_detects_milliseconds() -> None:
    assert device_epoch(_REAL * 1000) == device_epoch(_REAL)


def test_device_epoch_honours_an_explicit_unit() -> None:
    assert device_epoch(_REAL * 1000, millis=True) == device_epoch(_REAL)
    assert device_epoch(_REAL, millis=False) == device_epoch(_REAL)


@pytest.mark.parametrize(
    "value",
    [0, 3_600, MIN_DEVICE_EPOCH - 1, -5, None, "", "garbage", 10**20],
    ids=["padding", "uptime", "just-below-floor", "negative", "none", "empty", "garbage", "overflow"],
)
def test_device_epoch_is_none_for_a_value_that_is_not_a_date(value: object) -> None:
    assert device_epoch(value) is None


def test_device_epoch_is_none_for_milliseconds_of_uptime() -> None:
    """``millis=True`` divides first, so 1.2e9 ms of uptime (~14 days) is not a 2008 date."""
    assert device_epoch(1_200_000_000, millis=True) is None


def test_device_epoch_accepts_a_numeric_string() -> None:
    """``localTime`` arrives inside a JSON string and may stay a string."""
    assert device_epoch(str(_REAL * 1000)) == device_epoch(_REAL)
