"""Wire layout of ``mctrl_sys_config.proto``: the batch settings read/write (app 2.3.20.30).

These messages ride in ``MctlSys`` fields 83-86 (pinned in ``test_mctrl_sys_pb2.py``).  Frames are
hand-encoded from explicit tags so a renumbered field or enum value fails here.
"""

from __future__ import annotations

from pymammotion.proto import AppBatchQueryReq, AppBatchSetReq, AppBatchSetResp, BatchConfigType, ResResult

#: The app's BATCH_CONFIG_TYPE numbering, 0..12 in declaration order.
_APP_BATCH_CONFIG_TYPES = [
    BatchConfigType.CFG_TYPE_FORBID_WORK_TIME,
    BatchConfigType.CFG_TYPE_RAIN_STATUS,
    BatchConfigType.CFG_TYPE_SIDE_LAMP_SWITCH,
    BatchConfigType.CFG_TYPE_MEDIA_VOICE_CONFIG,
    BatchConfigType.CFG_TYPE_AUX_LIGHT_SWITCH,
    BatchConfigType.CFG_TYPE_TURN_AROUND_MODE,
    BatchConfigType.CFG_TYPE_RECHARGE_MODE,
    BatchConfigType.CFG_TYPE_SPEED_MODE,
    BatchConfigType.CFG_TYPE_LORA_CFG,
    BatchConfigType.CFG_TYPE_RAINPRO_CFG,
    BatchConfigType.CFG_TYPE_CHILD_PRO_CFG,
    BatchConfigType.CFG_TYPE_REVERSE_MODE_CFG,
    BatchConfigType.CFG_TYPE_MAX,
]


def test_batch_query_request_reads_every_config_type_by_its_app_number() -> None:
    # req_id=5 on field 1; type_list packed on field 2 (tag 0x12) holding 0..12.
    type_list = bytes(range(13))
    request = AppBatchQueryReq().parse(b"\x08\x05" + b"\x12" + bytes([len(type_list)]) + type_list)

    assert request.req_id == 5
    assert request.type_list == _APP_BATCH_CONFIG_TYPES


def test_batch_set_request_reads_a_rain_protection_config() -> None:
    # cfgs (field 2) = batchcfg{cfgtype=9, rain_pro (field 11: (11 << 3) | 2 = 0x5A) = {mode=1, delay=6}}.
    rain_pro = b"\x10\x01\x18\x06"
    cfg = b"\x08\x09" + b"\x5a" + bytes([len(rain_pro)]) + rain_pro
    request = AppBatchSetReq().parse(b"\x12" + bytes([len(cfg)]) + cfg)

    (only,) = request.cfgs
    assert only.cfgtype is BatchConfigType.CFG_TYPE_RAINPRO_CFG
    assert only.rain_pro is not None
    assert (only.rain_pro.rain_protection_mode, only.rain_pro.custom_delay_hours) == (1, 6)


def test_batch_set_response_reads_a_per_type_failure() -> None:
    # res_data (field 2) = batch_set_res{type=7, res_result=RES_FAILURE (1)}.
    response = AppBatchSetResp().parse(b"\x08\x05" + b"\x12\x04\x08\x07\x10\x01")

    (only,) = response.res_data
    assert (only.type, only.res_result) == (BatchConfigType.CFG_TYPE_SPEED_MODE, ResResult.RES_FAILURE)
