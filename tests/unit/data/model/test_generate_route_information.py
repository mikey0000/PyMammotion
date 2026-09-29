"""``GenerateRouteInformation``: the auto change direction setting on the wire and the ``reserved`` echo offset."""

from __future__ import annotations

import dataclasses

import betterproto2
import pytest

from pymammotion.data.model.generate_route_information import (
    ADVANCED_TASK_SETTINGS,
    GenerateRouteInformation,
    PathOrderSettings,
)
from pymammotion.data.model.work import CurrentTaskSettings
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg, NavReqCoverPath
from tests.unit.data.model._helpers import make_task_settings, make_wire_field


#: Field 21 (``reserved2``, packed): tag 0xAA 0x01, length 32.  Field 20 (int32): tag 0xA0 0x01, value 1.
_FIELD_21_TAG = bytes([0xAA, 0x01, 0x20])
_FIELD_20_ONE = bytes([0xA0, 0x01, 0x01])


def _field_21_on_wire(cover_path: NavReqCoverPath) -> bytes:
    payload = bytes(cover_path)
    assert _FIELD_21_TAG in payload, f"no 32-byte field 21 in {payload.hex()}"
    start = payload.index(_FIELD_21_TAG) + len(_FIELD_21_TAG)
    return payload[start : start + 32]


def _cover_path(payload: bytes) -> NavReqCoverPath:
    msg = LubaMsg().parse(payload)
    name, value = betterproto2.which_one_of(msg.nav, "SubNavMsg")
    assert name == "bidire_reqconver_path"
    return value


@pytest.mark.regression
@pytest.mark.parametrize("build", ["generate_route_information", "modify_route_information"])
def test_route_commands_carry_auto_change_direction_on_field_21(build: str) -> None:
    """The auto change direction toggle went out on field 20, which the app uses for its settings screen.

    Field 21 is the app's 32-byte ``reserved2`` with the setting in byte 0 (``WorkSettingViewModel.getReserved2``).
    """
    command = MammotionCommand("Luba-VA6ABCDE", 1)
    route = GenerateRouteInformation(one_hashs=[1], auto_change_direction=1)
    cover_path = _cover_path(getattr(command, build)(route))
    assert _field_21_on_wire(cover_path) == bytes([1] + [0] * 31), bytes(cover_path).hex()
    assert cover_path.auto_change_direction == [1] + [0] * 31
    assert _FIELD_20_ONE in bytes(cover_path), "field 20 is the settings-screen flag, not this toggle"


@pytest.mark.parametrize("build", ["generate_route_information", "modify_route_information"])
def test_route_commands_ask_for_the_advanced_task_settings_screen(build: str) -> None:
    """Field 20 is always sent as the app sends it by default, whatever the auto change direction toggle says."""
    command = MammotionCommand("Luba-VA6ABCDE", 1)
    route = GenerateRouteInformation(one_hashs=[1])
    cover_path = _cover_path(getattr(command, build)(route))
    assert cover_path.task_settings_mode == ADVANCED_TASK_SETTINGS
    assert _FIELD_20_ONE in bytes(cover_path), "the flag must be on the wire as field 20"


@pytest.mark.regression
@pytest.mark.parametrize("build", ["generate_route_information", "modify_route_information"])
def test_route_commands_send_32_zero_bytes_when_auto_change_direction_is_off(build: str) -> None:
    """Off was left off the wire; the app always sends the 32-byte ``reserved2``, zeroed when off, to every model."""
    command = MammotionCommand("Luba-VS6ABCDE", 1)
    route = GenerateRouteInformation(one_hashs=[1])
    cover_path = _cover_path(getattr(command, build)(route))
    assert _field_21_on_wire(cover_path) == bytes(32), bytes(cover_path).hex()
    assert cover_path.auto_change_direction == [0] * 32


@pytest.mark.parametrize(("reported", "expected"), [(True, 1), (False, 0), (None, 0)], ids=["on", "off", "not-reported"])
def test_from_current_task_settings_keeps_the_reported_auto_change_direction(
    reported: bool | None, expected: int
) -> None:
    """A task read back from the device is re-sent with the auto change direction it is running with."""
    settings = CurrentTaskSettings(auto_change_direction=reported)
    assert GenerateRouteInformation.from_current_task_settings(settings).auto_change_direction == expected


@pytest.mark.regression
@pytest.mark.parametrize(
    ("label", "wire", "expected"),
    [
        ("packed", make_wire_field(21, 2, bytes([1, 10])), False),
        ("scalar", make_wire_field(21, 0, bytes([11])), True),
    ],
)
def test_field_21_does_not_take_the_frame_down(label: str, wire: bytes, expected: bool) -> None:
    """Issue #192: some firmware sends field 21 length-delimited; decoded as an int it dropped every frame.

    The packed case is one value, 10 (length byte 1): the echo of "off", decided by byte 0 as the app does.
    """
    assert make_task_settings(wire).auto_change_direction is expected, label


@pytest.mark.regression
def test_the_model_carries_every_field_the_proto_has() -> None:
    """A field the proto reports but the model lacks is silently dropped on every parse."""
    proto_fields = {f.name for f in dataclasses.fields(NavReqCoverPath)}
    model_fields = {f.name for f in dataclasses.fields(CurrentTaskSettings)}
    assert not proto_fields - model_fields


CAPTURED_RESERVED = "\x0b\n\n\n\n\x12\x14("


@pytest.mark.regression
def test_decode_path_order_removes_the_device_echo_offset() -> None:
    """The device echoes ``reserved`` with +10 per byte; decoding returned those raw bytes (11, 10, 10, ...)."""
    decoded = GenerateRouteInformation.decode_path_order(CAPTURED_RESERVED)
    assert tuple(decoded) == (1, 0, 0, 0, 8, 10, 30)


@pytest.mark.regression
def test_from_current_task_settings_does_not_compound_the_echo_offset() -> None:
    """Cloning a reported task kept the echoed buffer as ``path_order``, so re-sending it added another +10."""
    route = GenerateRouteInformation.from_current_task_settings(CurrentTaskSettings(reserved=CAPTURED_RESERVED))
    assert route.path_order.encode("latin-1") == bytes([1, 0, 0, 0, 0, 8, 10, 0])
    assert route.obstacle_laps == 0


def test_decode_path_order_short_buffer_gives_defaults() -> None:
    """A buffer of two bytes or fewer is not a settings buffer, as in the APK."""
    assert GenerateRouteInformation.decode_path_order("") == GenerateRouteInformation.decode_path_order("\x0b\x0a")
    assert GenerateRouteInformation.decode_path_order("").edge_mode == 1


@pytest.mark.parametrize(
    ("echoed", "sent"),
    [
        (bytes([11, 10, 11, 10, 10, 18, 20, 40]), bytes([1, 0, 1, 0, 0, 8, 10, 0])),
        (bytes([3, 5, 0, 9, 10, 10, 10, 10]), bytes([0, 0, 0, 0, 0, 0, 0, 0])),
        (bytes([11, 10, 10, 10]), bytes([1, 0, 0, 0, 0, 0, 0, 0])),
    ],
    ids=["disabled-flag", "below-offset-clamps", "short-pads"],
)
def test_normalise_path_order(echoed: bytes, sent: bytes) -> None:
    """The offset comes off bytes 0-6 (floored at 0), byte 7 is zeroed and a short buffer is padded to 8."""
    assert GenerateRouteInformation.normalise_path_order(echoed.decode("latin-1")).encode("latin-1") == sent


@pytest.mark.regression
def test_byte_2_is_not_surfaced_as_a_rain_setting() -> None:
    """Byte 2 is the plan enable flag, but decoding exposed it as ``rain_tactics``, a rain setting no app sends.

    The bytes either side of it must still decode to their own fields.
    """
    decoded = GenerateRouteInformation.decode_path_order("\x0b\x0c\x0b\x0d\n\x12\x14(")

    assert "rain_tactics" not in PathOrderSettings._fields
    assert "rain_tactics" not in {f.name for f in dataclasses.fields(GenerateRouteInformation)}
    assert (decoded.obstacle_laps, decoded.start_progress) == (2, 3)


def test_from_current_task_settings_leaves_an_empty_buffer_empty() -> None:
    """No buffer reported means none is cloned, so the device is not sent zero-padded settings."""
    route = GenerateRouteInformation.from_current_task_settings(CurrentTaskSettings(reserved=""))
    assert route.path_order == ""


@pytest.mark.parametrize("build", ["generate_route_information", "modify_route_information"])
def test_route_commands_carry_the_ride_boundary_distance(build: str) -> None:
    """The app sets it on both the plan (sub_cmd 0) and the modify (sub_cmd 3) request."""
    command = MammotionCommand("Luba-VA6ABCDE", 1)
    route = GenerateRouteInformation(one_hashs=[1], ride_boundary_distance=0.5)
    assert _cover_path(getattr(command, build)(route)).ride_boundary_distance == 0.5


def test_from_current_task_settings_keeps_the_reported_ride_boundary_distance() -> None:
    """A modify re-sends the whole route, so a running job's distance must survive or it is reset to 0."""
    settings = CurrentTaskSettings(ride_boundary_distance=0.5)
    assert GenerateRouteInformation.from_current_task_settings(settings).ride_boundary_distance == 0.5
