"""Wire layout of the ``mctrl_sys.proto`` fields and enum values added from app 2.3.20.30.

Frames are hand-encoded from explicit tags so a renumbered field or enum value fails here rather
than round-tripping through its own generated class.  The batch-config messages the new MctlSys
fields carry are pinned in ``test_mctrl_sys_config_pb2.py``.
"""

from __future__ import annotations

import betterproto2
import pytest

from pymammotion.proto import (
    AppDownlinkCmdT,
    AppDownlinkCmdTypeE,
    MappingType,
    MctlSys,
    MqttRtkConnect,
    NetUsedType,
    RptConnectStatus,
    RptDevStatus,
    RptRtk,
    RptWork,
    RtkUsedType,
    SpinoSysStatus,
    WallMaterialE,
)

#: rpt_work field 24, message: (24 << 3) | 2 = 194 -> 0xC2 0x01.
_WORK_TEXTURE_MAP_INFO_TAG = b"\xc2\x01"
#: MctlSys field 87, message: (87 << 3) | 2 = 698 -> 0xBA 0x05.
_SYS_MESSAGE_RESET_REQ_TAG = b"\xba\x05"


@pytest.mark.parametrize(
    ("tag", "field"),
    [
        # (n << 3) | 2 for n = 82..88: 658, 666, 674, 682, 690, 698, 706 -> low 7 bits | 0x80, then 0x05.
        (b"\x92\x05", "map_offset_data"),
        (b"\x9a\x05", "batch_query_req"),
        (b"\xa2\x05", "batch_query_resp"),
        (b"\xaa\x05", "batch_set_req"),
        (b"\xb2\x05", "batch_set_resp"),
        (b"\xba\x05", "to_dev_message_reset_req"),
        (b"\xc2\x05", "to_app_message_reset_resp"),
    ],
    ids=lambda value: value if isinstance(value, str) else value.hex(),
)
def test_mctl_sys_reads_the_new_oneof_fields_82_to_88(tag: bytes, field: str) -> None:
    name, _ = betterproto2.which_one_of(MctlSys().parse(tag + b"\x00"), "SubSysMsg")

    assert name == field


def test_mctl_sys_reads_a_message_reset_request_body() -> None:
    _, value = betterproto2.which_one_of(MctlSys().parse(_SYS_MESSAGE_RESET_REQ_TAG + b"\x02\x08\x01"), "SubSysMsg")

    assert value.reset_command == 1


def test_rpt_work_reads_texture_map_info_from_field_24() -> None:
    texture = b"\x0a\x03abc"  # rpt_texture_map_info.file_hash, field 1 string.
    work = RptWork().parse(_WORK_TEXTURE_MAP_INFO_TAG + bytes([len(texture)]) + texture)

    assert work.texture_map_info is not None
    assert work.texture_map_info.file_hash == "abc"


def test_rpt_rtk_reads_rtcm_ready_from_field_15() -> None:
    assert RptRtk().parse(b"\x78\x01").rtcm_ready is True  # (15 << 3) = 120 -> 0x78.


def test_rpt_dev_status_reads_battery_heat_flag_from_field_14() -> None:
    assert RptDevStatus().parse(b"\x70\x01").battery_heat_flag == 1  # (14 << 3) = 112 -> 0x70.


def test_downlink_cmd_reads_app_mapping_cmd_and_its_mapping_param() -> None:
    # cmd=7 on field 1; mapping on field 10: (10 << 3) | 2 = 82 -> 0x52, carrying type=1, timestamp=5.
    cmd = AppDownlinkCmdT().parse(b"\x08\x07" + b"\x52\x04\x08\x01\x10\x05")

    assert cmd.cmd is AppDownlinkCmdTypeE.app_mapping_cmd
    assert cmd.mapping is not None
    assert (cmd.mapping.type, cmd.mapping.timestamp) == (MappingType.MAPPING_START, 5)


def test_downlink_cmd_wall_material_3_is_pvc() -> None:
    """``wall_material`` stays int32 on the wire (the app types it as the enum); 3 is PVC."""
    cmd = AppDownlinkCmdT().parse(b"\x18\x03")

    assert WallMaterialE(cmd.wall_material) is WallMaterialE.WALL_PVC


def test_mqtt_rtk_connect_reads_rtk_used_nrtk_box_as_3() -> None:
    assert MqttRtkConnect().parse(b"\x08\x03").rtk_switch is RtkUsedType.RTK_USED_NRTK_BOX


def test_rpt_connect_status_reads_used_net_3_as_tc_mnet() -> None:
    assert RptConnectStatus().parse(b"\x38\x03").used_net is NetUsedType.TC_MNET  # (7 << 3) = 56 -> 0x38.


@pytest.mark.parametrize(
    ("value", "member"),
    [
        (4, SpinoSysStatus.SYS_STA_PAUSE_GO_CHARGE),
        (5, SpinoSysStatus.SYS_STA_END_GO_CHARGE),
        (6, SpinoSysStatus.SYS_STA_CHARGING),
        (7, SpinoSysStatus.SYS_STA_LEAVE_DOCK),
        (8, SpinoSysStatus.SYS_STA_RECALLING),
        (9, SpinoSysStatus.SYS_STA_SILENT_WAIT),
        (10, SpinoSysStatus.SYS_STA_BUILD_MAP),
    ],
    ids=lambda value: value.name if isinstance(value, SpinoSysStatus) else str(value),
)
def test_spino_sys_status_numbers_the_added_states_as_the_app_does(value: int, member: SpinoSysStatus) -> None:
    """No message field carries this enum (``sys_status`` is int32), so the value mapping is the contract."""
    assert SpinoSysStatus(value) is member
