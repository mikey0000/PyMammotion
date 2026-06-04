"""Tests for UnknownTolerantIntEnum — wire→enum coercion never crashes.

Every migrated enum resolves an unmodelled value to its ``UNKNOWN`` member
(logging once) instead of raising ``ValueError``, so device frames carrying
newer/unexpected values can't crash message processing or entities.
"""

from __future__ import annotations

import logging

import pytest

from pymammotion.data.model.enums import TaskAreaStatus
from pymammotion.data.model.pool_state import (
    PoolBottomType,
    SpinoSysStatus,
    SpinoWorkMode,
    WallMaterial,
)
from pymammotion.utility import enum_base
from pymammotion.utility.constant.device_constant import (
    AppConnectType,
    PosType,
    RTKPositionMode,
    VioState,
)
from pymammotion.utility.enum_base import UnknownTolerantIntEnum

MIGRATED = [
    SpinoSysStatus,
    SpinoWorkMode,
    WallMaterial,
    PoolBottomType,
    TaskAreaStatus,
    RTKPositionMode,
    PosType,
    AppConnectType,
    VioState,
]


@pytest.fixture(autouse=True)
def _reset_log_dedupe() -> None:
    """Clear the once-per-value log cache so each test starts fresh."""
    enum_base._logged_unknown.clear()


@pytest.mark.parametrize("enum_cls", MIGRATED)
def test_all_are_unknown_tolerant_with_unknown_member(enum_cls: type[UnknownTolerantIntEnum]) -> None:
    assert issubclass(enum_cls, UnknownTolerantIntEnum)
    assert hasattr(enum_cls, "UNKNOWN"), f"{enum_cls.__name__} must define an UNKNOWN member"


@pytest.mark.parametrize("enum_cls", MIGRATED)
def test_unknown_value_resolves_to_unknown(enum_cls: type[UnknownTolerantIntEnum]) -> None:
    # 9999 is outside every modelled range.
    assert enum_cls(9999) is enum_cls.UNKNOWN


@pytest.mark.parametrize("enum_cls", MIGRATED)
def test_known_value_still_resolves_normally(enum_cls: type[UnknownTolerantIntEnum]) -> None:
    member = next(iter(enum_cls))
    assert enum_cls(int(member)) is member


def test_vio_state_unknown_keeps_signal_unknown_name() -> None:
    # UNKNOWN is an alias of the canonical SIGNAL_UNKNOWN, so .name (used as a
    # translation key in HA) stays "SIGNAL_UNKNOWN".
    assert VioState(172) is VioState.SIGNAL_UNKNOWN
    assert VioState(172).name == "SIGNAL_UNKNOWN"


def test_logs_once_per_value(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger=enum_base.__name__):
        SpinoSysStatus(9999)
        SpinoSysStatus(9999)  # second time must NOT re-log
    matching = [r for r in caplog.records if "9999" in r.getMessage()]
    assert len(matching) == 1
