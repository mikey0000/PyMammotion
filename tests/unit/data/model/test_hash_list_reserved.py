"""A plan's ``reserved`` buffer must survive being edited (Mammotion-HA #891).

The device adds +10 to the settings bytes when it stores a plan. Sending the
buffer back exactly as read compounded that offset, so every enable/disable or
rename walked the schedule's settings 10 further from what the user chose until
they wrapped. The app subtracts the offset on every write
(``JobScheduleActivity.java:848-866``); ``Plan.reserved_for_send`` does the same.

On a Luba 1 byte 4 carries ``toward_mode`` both ways (``Plan.from_wire`` / ``reserved_for_send``).
"""

from __future__ import annotations

import betterproto2
import pytest

from pymammotion.data.model.hash_list import Plan
from pymammotion.proto import NavPlanJobSet
from pymammotion.utility.device_type import DeviceType
from tests._helpers import (
    LUBA1_NAME as _LUBA1,
    LUBA1_PRODUCT_KEY as _LUBA1_KEY,
    NEWER_MODEL_NAME as _NEWER,
    UNRECOGNISED_NAME as _UNNAMED,
    make_stored_plan_frame as _stored_frame,
)

#: Bytes the device was measured to echo with +10 (4 and 7 are unused and do not).
_ECHOED = (0, 1, 2, 3, 5, 6)


def _buffer(*values: int) -> str:
    return bytes(values).decode("latin-1")


def _sent(plan: Plan) -> list[int]:
    return list(plan.reserved_for_send().encode("latin-1"))


def _device_echo(sent: str) -> str:
    """Model the device storing a buffer: +10 on the bytes that carry the echo."""
    raw = bytearray(sent.encode("latin-1"))
    for index in _ECHOED:
        raw[index] += 10
    return raw.decode("latin-1")


def test_the_offset_is_removed_from_the_settings_bytes() -> None:
    """One decrement per write, so the device's +10 lands back on the same value."""
    plan = Plan(reserved=_buffer(41, 41, 10, 40, 40, 48, 50, 40))
    assert _sent(plan) == [31, 31, 0, 30, 30, 38, 40, 0]


def test_the_enable_flag_is_written_raw() -> None:
    """The device stores 10/11; it must be sent back as 0/1."""
    enabled = Plan(reserved=_buffer(11, 11, 10, 0, 0, 18, 20, 0))
    assert _sent(enabled)[2] == 0
    disabled = Plan(reserved=_buffer(11, 11, 11, 0, 0, 18, 20, 0))
    assert _sent(disabled)[2] == 1


def test_the_unused_trailing_byte_is_always_zero() -> None:
    """The app writes a literal 0 there rather than carrying it."""
    plan = Plan(reserved=_buffer(11, 11, 10, 0, 0, 18, 20, 99))
    assert _sent(plan)[7] == 0


def test_values_below_the_offset_clamp_instead_of_wrapping() -> None:
    """A locally built plan has no offset to remove."""
    plan = Plan(reserved=_buffer(1, 2, 0, 3, 4, 5, 6, 0))
    assert _sent(plan) == [0, 0, 0, 0, 0, 0, 0, 0]


def test_a_short_buffer_is_padded() -> None:
    """The APK treats anything shorter than three bytes as all-zero."""
    assert _sent(Plan(reserved="")) == [0, 0, 0, 0, 0, 0, 0, 0]
    assert len(Plan(reserved=_buffer(11, 11)).reserved_for_send()) == 8


def test_a_long_buffer_is_truncated() -> None:
    """The app always builds exactly eight bytes."""
    plan = Plan(reserved=_buffer(11, 11, 10, 0, 0, 18, 20, 0, 77, 88))
    assert len(plan.reserved_for_send()) == 8


@pytest.mark.regression
def test_repeated_toggling_does_not_drift_the_settings() -> None:
    """The defect: each edit added another +10 to every settings byte.

    Five toggles took the reporter's [41,41,10,40,40,48,50,40] to
    [91,91,11,90,20,98,100,20] — +50 on every byte but the flag, with two
    wrapping past 100.
    """
    stored = _buffer(11, 11, 10, 30, 10, 18, 20, 10)
    settings = [1, 1, 20, 8, 10]  # bytes 0, 1, 3, 5, 6 with the offset removed

    for index in range(10):
        plan = Plan(reserved=stored).with_enabled(index % 2 == 0)
        sent = plan.reserved_for_send()
        assert [list(sent.encode("latin-1"))[i] for i in (0, 1, 3, 5, 6)] == settings
        stored = _device_echo(sent)

    assert [stored.encode("latin-1")[i] for i in (0, 1, 3, 5, 6)] == [value + 10 for value in settings]


@pytest.mark.regression
def test_renaming_does_not_drift_the_settings_either() -> None:
    """The app normalises on rename too; ours used to resend the buffer as read."""
    stored = _buffer(11, 11, 10, 30, 10, 18, 20, 10)
    for index in range(5):
        plan = Plan(reserved=stored).with_renamed(f"name {index}")
        stored = _device_echo(plan.reserved_for_send())
    assert [stored.encode("latin-1")[i] for i in (0, 1, 3, 5, 6)] == [11, 11, 30, 18, 20]


def test_toggling_preserves_the_stored_enable_state_on_rename() -> None:
    """A rename must not flip the flag."""
    disabled = Plan(reserved=_buffer(11, 11, 11, 0, 0, 18, 20, 0))
    assert disabled.with_renamed("x").is_enabled() is False
    assert _sent(disabled.with_renamed("x"))[2] == 1


def test_with_enabled_only_touches_the_flag() -> None:
    """Normalisation happens once, at transmission, so it cannot compound."""
    plan = Plan(reserved=_buffer(41, 41, 10, 40, 40, 48, 50, 40))
    toggled = plan.with_enabled(False)
    raw = list(toggled.reserved.encode("latin-1"))
    assert raw == [41, 41, 1, 40, 40, 48, 50, 40]
    assert toggled.is_enabled() is False


@pytest.mark.regression
@pytest.mark.parametrize(("byte_4", "expected"), [(10, 0), (11, 1), (12, 2)])
def test_a_luba1_plan_reads_its_toward_mode_from_reserved_byte_4(byte_4: int, expected: int) -> None:
    """The Luba 1 plan decoded ``toward_mode`` from field 37, which the app ignores for that model.

    The app takes ``reserved[4] - 10`` instead (``JobScheduleActivity.java:1039-1050``), so a Luba 1
    schedule's path-angle mode read back as whatever field 37 happened to hold.
    """
    plan = Plan.from_wire(_stored_frame(byte_4, field_37=0), _LUBA1)

    assert plan.toward_mode == expected


def test_a_newer_model_reads_its_toward_mode_from_field_37() -> None:
    plan = Plan.from_wire(_stored_frame(byte_4=11, field_37=2), _NEWER)

    assert plan.toward_mode == 2


@pytest.mark.parametrize(("byte_4", "expected"), [(0, 0), (9, 0), (13, 2), (40, 2)])
def test_a_luba1_toward_mode_outside_the_valid_modes_is_clamped(byte_4: int, expected: int) -> None:
    """An unechoed or unknown byte must not decode to a mode the device does not have."""
    assert Plan.from_wire(_stored_frame(byte_4, field_37=1), _LUBA1).toward_mode == expected


def test_a_luba1_plan_without_a_settings_buffer_keeps_field_37() -> None:
    """The app decodes ``reserved`` only when it is longer than two bytes."""
    frame = NavPlanJobSet(plan_id="p1", total_plan_num=1, reserved=_buffer(11, 11), toward_mode=1)

    assert Plan.from_wire(frame, _LUBA1).toward_mode == 1


def test_from_wire_decodes_every_other_field_as_from_dict_does() -> None:
    frame = _stored_frame(byte_4=11, field_37=1)

    assert Plan.from_wire(frame, _NEWER) == Plan.from_dict(frame.to_dict(casing=betterproto2.Casing.SNAKE))


@pytest.mark.parametrize("toward_mode", [0, 1, 2])
def test_a_luba1_plan_sends_its_toward_mode_raw_in_reserved_byte_4(toward_mode: int) -> None:
    """``WorkSettingViewModel.getReserved`` writes ``bArr[4] = towardMode`` with no offset on a Luba 1."""
    stored = Plan(reserved=_buffer(11, 11, 10, 10, 11, 10, 10, 0), toward_mode=toward_mode)

    assert list(stored.reserved_for_send(_LUBA1).encode("latin-1")) == [1, 1, 0, 0, toward_mode, 0, 0, 0]


def test_a_newer_model_keeps_toward_mode_out_of_reserved() -> None:
    """Everywhere else the app writes a literal 0 at byte 4 and sends the mode only as field 37."""
    plan = Plan(reserved="", toward_mode=2)

    assert list(plan.reserved_for_send(_NEWER).encode("latin-1")) == [0] * 8


def test_a_luba1_plan_with_a_three_byte_buffer_decodes_reserved() -> None:
    """``reserved.length > 2`` is the app's guard, so three bytes decode: byte 4 is absent, i.e. mode 0."""
    frame = NavPlanJobSet(plan_id="p1", total_plan_num=1, reserved=_buffer(11, 11, 10), toward_mode=1)

    assert Plan.from_wire(frame, _LUBA1).toward_mode == 0


def test_a_luba1_known_only_by_product_key_reads_its_toward_mode_from_reserved_byte_4() -> None:
    assert not DeviceType.is_luba1(_UNNAMED), "the name alone must not identify a Luba 1"

    plan = Plan.from_wire(_stored_frame(byte_4=12, field_37=0), _UNNAMED, _LUBA1_KEY)

    assert plan.toward_mode == 2


def test_a_luba1_known_only_by_product_key_sends_toward_mode_in_reserved_byte_4() -> None:
    plan = Plan(reserved="", toward_mode=2)

    assert list(plan.reserved_for_send(_UNNAMED, _LUBA1_KEY).encode("latin-1"))[4] == 2


def test_a_luba1_known_only_by_product_key_sends_the_first_of_weeks_as_week() -> None:
    plan = Plan(week=6, weeks=[3, 5])

    assert plan.week_for_send(_UNNAMED, _LUBA1_KEY) == 3


def test_an_unrecognised_device_sends_week_as_held() -> None:
    assert Plan(week=6, weeks=[3, 5]).week_for_send(_UNNAMED) == 6
