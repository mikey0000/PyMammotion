"""``CurrentTaskSettings``: the auto change direction setting as the device reports it."""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.work import CurrentTaskSettings
from pymammotion.proto import NavReqCoverPath
from tests.unit.data.model._helpers import make_task_settings, make_wire_field

#: Fields 1-19 of two frames captured from one Luba 2 (Luba-VAME9R5S), identical in both.
_CAPTURED_HEAD = bytes(
    NavReqCoverPath(
        pver=1,
        job_mode=4,
        sub_cmd=2,
        edge_mode=3,
        knife_height=50,
        channel_width=25,
        ultra_wave=10,
        speed=0.3,
        zone_hashs=[1],
        reserved="\x0b\n\n\n\n\x12\x14(",
        toward_included_angle=90,
        ride_boundary_distance=0.5,
    )
)
#: Field 20 read 1 in both frames, whichever way the auto change direction setting was.
_FIELD_20_SET = make_wire_field(20, 0, bytes([1]))


@pytest.mark.regression
@pytest.mark.parametrize(
    ("field_21", "expected"),
    [
        (bytes.fromhex("aa01010b"), True),
        (bytes.fromhex("aa01010a"), False),
        (bytes.fromhex("a8010a"), False),
        (b"", None),
    ],
    ids=["packed-on", "packed-off", "varint-off", "not-reported"],
)
def test_auto_change_direction_is_read_from_field_21(field_21: bytes, expected: bool | None) -> None:
    """The setting is field 21, echoed as 11 on / 10 off, in either wire form.

    Field 20 was decoded as the setting, so both captured frames read "on" although
    field 21 showed the mower had it off in one of them.
    """
    settings = make_task_settings(_CAPTURED_HEAD + _FIELD_20_SET + field_21)
    assert settings.auto_change_direction is expected


def _packed_field_21(values: list[int]) -> bytes:
    return make_wire_field(21, 2, bytes([len(values), *values]))


@pytest.mark.regression
@pytest.mark.parametrize(
    ("echo", "expected"),
    [
        ([1], True),
        ([0], False),
        ([11] + [10] * 31, True),
        ([1, 10], True),
        ([10, 11], False),
    ],
    ids=["raw-on", "raw-off", "echo-on-then-offs", "raw-first-then-echo", "echo-off-then-on"],
)
def test_auto_change_direction_is_decided_by_the_first_value_like_the_app(echo: list[int], expected: bool) -> None:
    """The app reads byte 0 of ``reserved2`` and takes 10 off only when it is >= 10 (``WorkingOptionView``).

    The decoder took the last value and always subtracted 10, so a raw ``[1]`` or ``[0]`` read as not
    reported, ``[1, 10]`` read as off and ``[10, 11]`` as on: the opposite of what the app shows.
    """
    assert make_task_settings(_packed_field_21(echo)).auto_change_direction is expected


@pytest.mark.parametrize(
    ("first", "expected"),
    [(11, True), (10, False), (0, False), (1, True), (2, None), (9, None), (12, None), (20, None)],
)
def test_auto_change_direction_byte_0_boundaries(first: int, expected: bool | None) -> None:
    """The real device shape: byte 0 then a zero tail.  10 comes off only from 10 up, so 9 and 20 are neither.

    ``None`` for a value other than 0/1 is our choice for a ``bool | None`` field: the app keeps the stripped
    int as is (``WorkingOptionView.java:77-86`` ``setAuto_change_direction(i10)``).
    """
    settings = make_task_settings(_packed_field_21([first] + [0] * 31))
    assert settings.auto_change_direction is expected


def test_an_empty_auto_change_direction_list_is_not_reported() -> None:
    assert CurrentTaskSettings.from_dict({"auto_change_direction": []}).auto_change_direction is None


@pytest.mark.parametrize("reported", [True, False, None])
def test_auto_change_direction_survives_a_serialisation_round_trip(reported: bool | None) -> None:
    """The decoded value is what gets cached and reloaded, so it must read back as itself."""
    settings = CurrentTaskSettings(auto_change_direction=reported)

    assert CurrentTaskSettings.from_dict(settings.to_dict()).auto_change_direction is reported


@pytest.mark.regression
@pytest.mark.parametrize("legacy", [0, 1, 11])
def test_a_task_stored_before_the_rename_still_loads(legacy: int) -> None:
    """A device state saved by 0.9.9 holds ``work.auto_change_direction`` as a bare int (the old field 20).

    The decoder indexed it like the echo list and raised, so restoring the saved state failed as a whole:
    Home Assistant fell back to an empty device, and every entity gated on firmware read from that
    empty state (smart charging among them) was never created.  The old scalar carries no usable
    setting, so it loads as "not reported".
    """
    settings = CurrentTaskSettings.from_dict({"auto_change_direction": legacy, "unknown_21": [11]})

    assert settings.auto_change_direction is None


@pytest.mark.regression
def test_a_whole_device_stored_before_the_rename_still_restores_its_firmware() -> None:
    """One stale field must not cost the rest of the saved device its data."""
    stored = MowerDevice(name="Luba-Test").to_dict()
    stored["device_firmwares"]["device_version"] = "2.3.30.39"
    stored["work"]["auto_change_direction"] = 1

    restored = MowerDevice.from_dict(stored)

    assert restored.device_firmwares.device_version == "2.3.30.39"
