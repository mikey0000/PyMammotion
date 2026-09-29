"""Wire layout of the ``mctrl_nav.proto`` fields added from app 2.3.20.30.

The device only sees bytes, so these pin tags and encodings rather than the generated classes:
a renumbered or retyped field still round-trips through its own class and would pass anything
weaker.  Each expected byte string is built from explicit tags; the tag arithmetic is in the
constant's comment.
"""

from __future__ import annotations

import struct

import betterproto2

from pymammotion.proto import (
    CommDataCouple,
    ManualElementMessage,
    MctlNav,
    NavPlanJobSet,
    NavReqCoverPath,
    WorkReportStartWorkingMsg,
)

#: NavReqCoverPath field 19, fixed32 float: (19 << 3) | 5 = 157 -> 0x9D 0x01.
_ROUTE_RIDE_BOUNDARY_DISTANCE_TAG = b"\x9d\x01"
#: NavReqCoverPath field 20, varint: (20 << 3) | 0 = 160 -> 0xA0 0x01.
_ROUTE_TASK_SETTINGS_MODE_TAG = b"\xa0\x01"
#: NavReqCoverPath field 21, length-delimited: (21 << 3) | 2 = 170 -> 0xAA 0x01.
_ROUTE_AUTO_CHANGE_DIRECTION_LEN_TAG = b"\xaa\x01"
#: NavPlanJobSet field 39, fixed32 float: (39 << 3) | 5 = 317 -> 0xBD 0x02.
_PLAN_RIDE_BOUNDARY_DISTANCE_TAG = b"\xbd\x02"

#: NavPlanJobSet field 40, varint: (40 << 3) | 0 = 320 -> 0xC0 0x02.
_PLAN_TASK_SETTINGS_MODE_TAG = b"\xc0\x02"
#: NavPlanJobSet field 41, length-delimited: (41 << 3) | 2 = 330 -> 0xCA 0x02.
_PLAN_AUTO_CHANGE_DIRECTION_LEN_TAG = b"\xca\x02"
#: NavPlanJobSet field 41, bare varint: (41 << 3) | 0 = 328 -> 0xC8 0x02.
_PLAN_AUTO_CHANGE_DIRECTION_VARINT_TAG = b"\xc8\x02"
#: MctlNav field 65, length-delimited: (65 << 3) | 2 = 522 -> 0x8A 0x04.
_NAV_START_WORKING_MSG_TAG = b"\x8a\x04"


def test_plan_job_set_puts_task_settings_mode_on_field_40() -> None:
    assert bytes(NavPlanJobSet(task_settings_mode=1)) == _PLAN_TASK_SETTINGS_MODE_TAG + b"\x01"


def test_plan_job_set_packs_auto_change_direction_on_field_41() -> None:
    """Packed is the shape the app's ``reserved2`` byte string has on the wire."""
    assert bytes(NavPlanJobSet(auto_change_direction=[1])) == _PLAN_AUTO_CHANGE_DIRECTION_LEN_TAG + b"\x01\x01"


def test_plan_job_set_puts_ride_boundary_distance_on_field_39_as_a_float() -> None:
    assert bytes(NavPlanJobSet(ride_boundary_distance=0.5)) == _PLAN_RIDE_BOUNDARY_DISTANCE_TAG + struct.pack("<f", 0.5)


def test_cover_path_request_puts_ride_boundary_distance_on_field_19_as_a_float() -> None:
    assert bytes(NavReqCoverPath(ride_boundary_distance=0.5)) == _ROUTE_RIDE_BOUNDARY_DISTANCE_TAG + struct.pack(
        "<f", 0.5
    )


def test_cover_path_request_puts_task_settings_mode_on_field_20() -> None:
    assert bytes(NavReqCoverPath(task_settings_mode=1)) == _ROUTE_TASK_SETTINGS_MODE_TAG + b"\x01"


def test_cover_path_request_packs_auto_change_direction_on_field_21() -> None:
    assert bytes(NavReqCoverPath(auto_change_direction=[1])) == _ROUTE_AUTO_CHANGE_DIRECTION_LEN_TAG + b"\x01\x01"


def test_plan_job_set_reads_the_apps_32_byte_reserved2_as_auto_change_direction() -> None:
    """The app writes ``reserved2`` as a 32-byte string ``[on] + [0] * 31``; each byte is a packed varint < 128."""
    reserved2 = b"\x01" + b"\x00" * 31
    payload = _PLAN_AUTO_CHANGE_DIRECTION_LEN_TAG + bytes([len(reserved2)]) + reserved2

    assert NavPlanJobSet().parse(payload).auto_change_direction == [1] + [0] * 31


def test_plan_job_set_reads_a_bare_varint_echo_on_field_41() -> None:
    """The device echoes the setting +10 (11 = on), and some firmware sends it unpacked."""
    assert NavPlanJobSet().parse(_PLAN_AUTO_CHANGE_DIRECTION_VARINT_TAG + b"\x0b").auto_change_direction == [11]


def test_start_working_msg_is_mctl_nav_field_65_with_fields_1_to_5_in_order() -> None:
    nav = MctlNav(
        todev_work_report_start_working_msg=WorkReportStartWorkingMsg(
            account_id=42, work_id=7, stamp=1000, result=1, type=2
        )
    )
    # 1000 = 0x3E8 -> varint 0xE8 0x07.
    inner = b"\x08\x2a" + b"\x10\x07" + b"\x18\xe8\x07" + b"\x20\x01" + b"\x28\x02"

    assert bytes(nav) == _NAV_START_WORKING_MSG_TAG + bytes([len(inner)]) + inner


def test_start_working_msg_carries_a_full_width_uint64_work_id() -> None:
    """Work ids are cloud ids parsed with ``Long.parseLong``; uint64 must not truncate them to 32 bits."""
    work_id = 1_968_123_456_789_012_345
    parsed = MctlNav().parse(
        bytes(MctlNav(todev_work_report_start_working_msg=WorkReportStartWorkingMsg(work_id=work_id)))
    )

    name, value = betterproto2.which_one_of(parsed, "SubNavMsg")
    assert name == "todev_work_report_start_working_msg"
    assert value.work_id == work_id


def test_manual_element_message_puts_point_count_and_data_couples_on_fields_14_and_15() -> None:
    element = ManualElementMessage(point_count=1, data_couple=[CommDataCouple(x=1.0, y=2.0)])
    # Field 14 varint: (14 << 3) = 112 -> 0x70.  Field 15 message: (15 << 3) | 2 = 122 -> 0x7A.
    # CommDataCouple x/y are floats on fields 1/2: tags 0x0D / 0x15, 1.0f = 00 00 80 3F, 2.0f = 00 00 00 40.
    couple = b"\x0d\x00\x00\x80\x3f" + b"\x15\x00\x00\x00\x40"

    assert bytes(element) == b"\x70\x01" + b"\x7a" + bytes([len(couple)]) + couple
