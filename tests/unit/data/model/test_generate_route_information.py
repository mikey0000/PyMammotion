"""``GenerateRouteInformation.auto_change_direction`` reaches the wire and back (issue #860)."""

from __future__ import annotations

import dataclasses

import betterproto2
import pytest

from pymammotion.data.model.generate_route_information import GenerateRouteInformation
from pymammotion.data.model.work import CurrentTaskSettings
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg, NavReqCoverPath


def _cover_path(payload: bytes) -> NavReqCoverPath:
    msg = LubaMsg().parse(payload)
    name, value = betterproto2.which_one_of(msg.nav, "SubNavMsg")
    assert name == "bidire_reqconver_path"
    return value


def test_generate_route_carries_auto_change_direction() -> None:
    """The anti-matting toggle reaches the device on the generate-route command."""
    command = MammotionCommand("Luba-VA6ABCDE", 1)
    route = GenerateRouteInformation(one_hashs=[1], auto_change_direction=1)
    assert _cover_path(command.generate_route_information(route)).auto_change_direction == 1


def test_modify_route_carries_auto_change_direction() -> None:
    """Changing the toggle mid-task goes out on the modify-route command too."""
    command = MammotionCommand("Luba-VA6ABCDE", 1)
    route = GenerateRouteInformation(one_hashs=[1], auto_change_direction=1)
    assert _cover_path(command.modify_route_information(route)).auto_change_direction == 1


def test_generate_route_omits_the_field_when_off() -> None:
    """Off is the proto3 default, so a device that never heard of the field sees nothing."""
    command = MammotionCommand("Luba-VS6ABCDE", 1)
    route = GenerateRouteInformation(one_hashs=[1])
    assert _cover_path(command.generate_route_information(route)).auto_change_direction == 0


def test_from_current_task_settings_keeps_the_reported_value() -> None:
    """A task read back from the device reports whether the device is reversing."""
    settings = CurrentTaskSettings(auto_change_direction=1)
    assert GenerateRouteInformation.from_current_task_settings(settings).auto_change_direction == 1


def _wire(field_number: int, wire_type: int, payload: bytes) -> bytes:
    def varint(n: int) -> bytes:
        out = bytearray()
        while True:
            b = n & 0x7F
            n >>= 7
            out.append(b | (0x80 if n else 0))
            if not n:
                return bytes(out)

    return varint((field_number << 3) | wire_type) + payload


@pytest.mark.regression
@pytest.mark.parametrize(
    ("label", "wire"),
    [
        ("packed", _wire(21, 2, bytes([1, 10]))),
        ("scalar", _wire(21, 0, bytes([11]))),
    ],
)
def test_an_unidentified_field_21_does_not_take_the_frame_down(label: str, wire: bytes) -> None:
    """Issue #192: field 21 used to be decoded as auto_change_direction, an int.

    Some firmware sends it length-delimited, betterproto2 read that as a packed list,
    mashumaro rejected the list and every report frame carrying it was dropped.  It is
    declared repeated under a neutral name now, so both wire forms survive and the
    values are visible while we work out what the field means.
    """
    settings = CurrentTaskSettings.from_dict(
        NavReqCoverPath().parse(wire).to_dict(casing=betterproto2.Casing.SNAKE)
    )
    assert settings.unknown_21, label
    assert settings.auto_change_direction == 0, "field 21 is not auto_change_direction"


@pytest.mark.regression
def test_auto_change_direction_rides_on_field_20() -> None:
    """Confirmed by observation: the app's toggle sets field 20, not 21."""
    settings = CurrentTaskSettings.from_dict(
        NavReqCoverPath().parse(_wire(20, 0, bytes([1]))).to_dict(casing=betterproto2.Casing.SNAKE)
    )
    assert settings.auto_change_direction == 1


@pytest.mark.regression
def test_the_model_carries_every_field_the_proto_has() -> None:
    """A field the proto reports but the model lacks is silently dropped on every parse."""
    proto_fields = {f.name for f in dataclasses.fields(NavReqCoverPath)}
    model_fields = {f.name for f in dataclasses.fields(CurrentTaskSettings)}
    assert not proto_fields - model_fields
