"""RapidState.from_raw — decoding of the rapid-state tunnel message.

``from_raw`` runs on every rapid-state frame (via ``MowingDevice.run_state_update``),
and had no coverage: when the duplicate 3-member ``RTKStatus`` was consolidated onto
the canonical 5-member one, the ``RTKStatus.FINE``/``BAD`` references left behind
raised ``AttributeError`` on every frame with nothing to catch it.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.enums import RTKStatus
from pymammotion.data.model.rapid_state import RapidState

# tard_state_data is indexed positionally; anything past [0] is irrelevant here.
def _raw(rtk_value: int) -> list[int]:
    raw = [0] * 20
    raw[0] = rtk_value
    return raw


@pytest.mark.parametrize(
    ("wire_value", "expected"),
    [
        (0, RTKStatus.NONE),
        (1, RTKStatus.SINGLE),
        (2, RTKStatus.SINGLE),
        (4, RTKStatus.FIX),
        (5, RTKStatus.FLOAT),
        (99, RTKStatus.UNKNOWN),
    ],
)
def test_rtk_status_decodes_the_wire_value(wire_value: int, expected: RTKStatus) -> None:
    """The enum's values are the wire values, so from_value is the whole mapping."""
    assert RapidState.from_raw(_raw(wire_value)).rtk_status is expected


def test_from_raw_does_not_raise_on_any_plausible_rtk_value() -> None:
    """The regression itself: an unmodelled value must degrade, not blow up the frame."""
    for wire_value in range(256):
        assert isinstance(RapidState.from_raw(_raw(wire_value)).rtk_status, RTKStatus)


def test_from_raw_populates_the_positional_fields() -> None:
    raw = list(range(20))
    raw[0] = 4
    state = RapidState.from_raw(raw)
    assert state.rtk_status is RTKStatus.FIX
    assert state.pos_level == raw[1]
    assert state.satellites_total == raw[2]
    assert state.satellites_l2 == raw[6]
