"""``GenerateRouteInformation.auto_change_direction`` reaches the wire and back (issue #860)."""

from __future__ import annotations

import betterproto2

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
