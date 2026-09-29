"""``build_route_information``: OperationSettings plus the device's own state -> the route a plan/modify sends.

It is the one home for route building; the HA integration calls it with whatever its
coordinator holds, which is not always a ``MowerDevice`` (maintenance, RTK and Spino
coordinators carry other types), so every device read must fall back rather than raise.

``create_path_order``'s byte layout is covered only by the pinned wire bytes at the end of this module.
"""

from __future__ import annotations

import dataclasses

import betterproto2
import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.device_config import OperationSettings, build_route_information, create_path_order
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg
from tests._helpers import LUBA1_NAME as _LUBA1

_LUBA2_VA = "Luba-VA6ABCDE"
_LUBA2_VS = "Luba-VS6ABCDE"
_YUKA = "Yuka-ABCDEF"


def _mower(*, collector_installed: int = 1, firmware: str = "") -> MowerDevice:
    device = MowerDevice()
    device.report_data.dev.collector_status.collector_installation_status = collector_installed
    device.device_firmwares.device_version = firmware
    return device


def test_builds_the_route_from_the_operation_settings() -> None:
    """Every input carries a distinct value, so a field wired from the wrong setting fails."""
    settings = OperationSettings(
        areas=[11, 22],
        channel_mode=1,
        ultra_wave=3,
        toward_mode=4,
        mowing_laps=5,
        obstacle_laps=6,
        job_mode=7,
        channel_width=21,
        toward=30,
        blade_height=55,
        toward_included_angle=60,
        speed=0.5,
    )

    route = build_route_information(_LUBA2_VA, _mower(), settings)

    assert route.one_hashs == [11, 22]
    assert route.channel_mode == 1
    assert route.ultra_wave == 3
    assert route.toward_mode == 4
    assert route.edge_mode == 5
    assert route.obstacle_laps == 6
    assert route.job_mode == 7
    assert route.channel_width == 21
    assert route.toward == 30
    assert route.blade_height == 55
    assert route.toward_included_angle == 60
    assert route.speed == 0.5
    assert route.path_order == create_path_order(settings, _LUBA2_VA)


def test_route_does_not_alias_the_settings_areas() -> None:
    settings = OperationSettings(areas=[11])

    route = build_route_information(_LUBA2_VA, _mower(), settings)
    route.one_hashs.append(22)

    assert settings.areas == [11]


@pytest.mark.parametrize(("channel_mode", "expected"), [(1, 60), (0, 0), (2, 0)])
def test_toward_included_angle_is_sent_only_in_channel_mode_one(channel_mode: int, expected: int) -> None:
    settings = OperationSettings(channel_mode=channel_mode, toward_included_angle=60, toward_mode=1)

    assert build_route_information(_LUBA2_VA, _mower(), settings).toward_included_angle == expected


def test_luba1_zeroes_toward_mode_and_included_angle() -> None:
    settings = OperationSettings(channel_mode=1, toward_included_angle=60, toward_mode=1)

    route = build_route_information(_LUBA1, _mower(), settings)

    assert (route.toward_mode, route.toward_included_angle) == (0, 0)


def test_without_a_collector_the_settings_are_switched_out_of_dump_mode() -> None:
    """The settings object itself is changed: its callers read ``is_dump`` back afterwards."""
    settings = OperationSettings(is_dump=True)

    build_route_information(_LUBA2_VA, _mower(collector_installed=0), settings)

    assert settings.is_dump is False


def test_with_a_collector_the_dump_setting_is_kept() -> None:
    settings = OperationSettings(is_dump=True)

    build_route_information(_LUBA2_VA, _mower(collector_installed=1), settings)

    assert settings.is_dump is True


def test_a_yuka_mows_at_the_fixed_minus_ten_blade_height() -> None:
    settings = OperationSettings(blade_height=60)

    route = build_route_information(_YUKA, _mower(), settings)

    assert (route.blade_height, settings.blade_height) == (-10, -10)


def test_auto_change_direction_follows_the_devices_firmware() -> None:
    settings = OperationSettings(auto_change_direction=1)

    assert build_route_information(_LUBA2_VA, _mower(firmware="2.3.28.1"), settings).auto_change_direction == 1
    assert build_route_information(_LUBA2_VA, _mower(firmware="2.3.27.9"), settings).auto_change_direction == 0


@pytest.mark.parametrize("device_name", [_LUBA1, _LUBA2_VS, "Yuka-6ABCDEF"], ids=["luba1", "luba2", "yuka"])
def test_auto_change_direction_is_dropped_on_an_excluded_model(device_name: str) -> None:
    """The product owner confirms Luba 1, Luba 2 and the original Yuka never offer it, whatever the firmware."""
    settings = OperationSettings(auto_change_direction=1)

    assert build_route_information(device_name, _mower(firmware="2.3.28.1"), settings).auto_change_direction == 0


def test_ride_boundary_distance_is_gated_by_model_and_edge_laps() -> None:
    with_edge_laps = OperationSettings(mowing_laps=1, ride_boundary_distance=0.5)
    no_edge_laps = OperationSettings(mowing_laps=0, ride_boundary_distance=0.5)

    assert build_route_information(_LUBA2_VA, _mower(), with_edge_laps).ride_boundary_distance == 0.5
    assert build_route_information(_LUBA2_VS, _mower(), with_edge_laps).ride_boundary_distance == 0.0
    assert build_route_information(_LUBA2_VA, _mower(), no_edge_laps).ride_boundary_distance == 0.0


@pytest.mark.parametrize("device", [None, object()], ids=["none", "not-a-mower"])
def test_a_missing_or_foreign_device_builds_without_its_state(device: object) -> None:
    """No collector to read keeps the dump setting; no firmware to read drops the firmware-gated field."""
    settings = OperationSettings(is_dump=True, auto_change_direction=1, mowing_laps=1, ride_boundary_distance=0.5)

    route = build_route_information(_LUBA2_VA, device, settings)

    assert settings.is_dump is True
    assert route.auto_change_direction == 0
    assert route.ride_boundary_distance == 0.5


#: ``create_path_order`` output and the ``NavReqCoverPath`` bytes of the plan and modify requests, generated from
#: the working tree just before the dead ``rain_tactics`` field was removed (not a device capture). Byte 2 of the
#: path order is the plan enable flag, always sent as 0.
_PINNED_WIRE = {
    _LUBA1: (
        "0102000301000000",
        "08012004300140194802659a99993e6a100b0000000000000016000000000000007a080102000301000000a00101aa0120"
        + "00" * 32,
        "080120042803300140194802659a99993e6a100b0000000000000016000000000000007a080102000301000000a00101aa0120"
        + "00" * 32,
    ),
    _LUBA2_VA: (
        "0102000300080a00",
        "08012004300140194802659a99993e6a100b0000000000000016000000000000007a080102000300080a00880101a00101aa0120"
        + "00" * 32,
        "080120042803300140194802659a99993e6a100b0000000000000016000000000000007a080102000300080a00a00101aa0120"
        + "00" * 32,
    ),
    "Yuka-6ABCDEF": (
        "01020003000a0a00",
        "08012004300138f6ffffffffffffffff0140194802659a99993e6a100b0000000000000016000000000000007a0801020003000a0a00"
        "880101a00101aa0120" + "00" * 32,
        "080120042803300138f6ffffffffffffffff0140194802659a99993e6a100b0000000000000016000000000000007a0801020003000a0a00"
        "a00101aa0120" + "00" * 32,
    ),
}


def _pinned_settings() -> OperationSettings:
    return OperationSettings(
        areas=[11, 22],
        border_mode=1,
        obstacle_laps=2,
        start_progress=3,
        toward_mode=1,
        collect_grass_frequency=7,
        is_edge=True,
    )


def _cover_path_hex(payload: bytes) -> str:
    _, cover_path = betterproto2.which_one_of(LubaMsg().parse(payload).nav, "SubNavMsg")
    return bytes(cover_path).hex()


@pytest.mark.parametrize("device_name", list(_PINNED_WIRE), ids=["luba1", "luba2", "yuka"])
def test_route_wire_bytes_match_the_pinned_capture(device_name: str) -> None:
    """Removing ``rain_tactics`` from the models must not move a single byte the mower receives."""
    path_order, plan, modify = _PINNED_WIRE[device_name]
    settings = _pinned_settings()
    route = build_route_information(device_name, MowerDevice(), settings)
    command = MammotionCommand(device_name, 1)

    assert create_path_order(settings, device_name).encode("latin-1").hex() == path_order
    assert _cover_path_hex(command.generate_route_information(route)) == plan
    assert _cover_path_hex(command.modify_route_information(route)) == modify


@pytest.mark.regression
def test_operation_settings_has_no_rain_setting_and_still_loads_one_saved_with_it() -> None:
    """``rain_tactics`` was a dead setting: nothing put it on the wire, byte 2 being the plan enable flag.

    State saved while the field existed must still load; the stale key is dropped rather than raising.
    """
    saved = dataclasses.asdict(OperationSettings(areas=[11], obstacle_laps=2)) | {"rain_tactics": 1}

    loaded = OperationSettings.from_dict(saved)

    assert "rain_tactics" not in {f.name for f in dataclasses.fields(OperationSettings)}
    assert (loaded.areas, loaded.obstacle_laps) == ([11], 2)
