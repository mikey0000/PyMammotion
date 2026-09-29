from pymammotion.proto import luba_mul_pb2 as _luba_mul_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

CFG_TYPE_AUX_LIGHT_SWITCH: BATCH_CONFIG_TYPE
CFG_TYPE_CHILD_PRO_CFG: BATCH_CONFIG_TYPE
CFG_TYPE_FORBID_WORK_TIME: BATCH_CONFIG_TYPE
CFG_TYPE_LORA_CFG: BATCH_CONFIG_TYPE
CFG_TYPE_MAX: BATCH_CONFIG_TYPE
CFG_TYPE_MEDIA_VOICE_CONFIG: BATCH_CONFIG_TYPE
CFG_TYPE_RAINPRO_CFG: BATCH_CONFIG_TYPE
CFG_TYPE_RAIN_STATUS: BATCH_CONFIG_TYPE
CFG_TYPE_RECHARGE_MODE: BATCH_CONFIG_TYPE
CFG_TYPE_REVERSE_MODE_CFG: BATCH_CONFIG_TYPE
CFG_TYPE_SIDE_LAMP_SWITCH: BATCH_CONFIG_TYPE
CFG_TYPE_SPEED_MODE: BATCH_CONFIG_TYPE
CFG_TYPE_TURN_AROUND_MODE: BATCH_CONFIG_TYPE
DESCRIPTOR: _descriptor.FileDescriptor
RES_FAILURE: ResResult
RES_SUCCESS: ResResult

class ChildProtection(_message.Message):
    __slots__ = ["childProtectionMode", "result"]
    CHILDPROTECTIONMODE_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    childProtectionMode: int
    result: int
    def __init__(self, result: _Optional[int] = ..., childProtectionMode: _Optional[int] = ...) -> None: ...

class FillLightState(_message.Message):
    __slots__ = ["ctrl_lamp_bright", "lamp_bright", "lamp_ctrl", "lamp_manual_ctrl", "lamp_power_ctrl", "result"]
    CTRL_LAMP_BRIGHT_FIELD_NUMBER: _ClassVar[int]
    LAMP_BRIGHT_FIELD_NUMBER: _ClassVar[int]
    LAMP_CTRL_FIELD_NUMBER: _ClassVar[int]
    LAMP_MANUAL_CTRL_FIELD_NUMBER: _ClassVar[int]
    LAMP_POWER_CTRL_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ctrl_lamp_bright: bool
    lamp_bright: int
    lamp_ctrl: _luba_mul_pb2.lamp_ctrl_sta
    lamp_manual_ctrl: _luba_mul_pb2.lamp_manual_ctrl_sta
    lamp_power_ctrl: int
    result: int
    def __init__(self, result: _Optional[int] = ..., lamp_power_ctrl: _Optional[int] = ..., lamp_ctrl: _Optional[_Union[_luba_mul_pb2.lamp_ctrl_sta, str]] = ..., ctrl_lamp_bright: bool = ..., lamp_bright: _Optional[int] = ..., lamp_manual_ctrl: _Optional[_Union[_luba_mul_pb2.lamp_manual_ctrl_sta, str]] = ...) -> None: ...

class LoraCfg(_message.Message):
    __slots__ = ["cfg", "fac_cfg", "op", "result"]
    CFG_FIELD_NUMBER: _ClassVar[int]
    FAC_CFG_FIELD_NUMBER: _ClassVar[int]
    OP_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    cfg: str
    fac_cfg: str
    op: int
    result: int
    def __init__(self, result: _Optional[int] = ..., op: _Optional[int] = ..., cfg: _Optional[str] = ..., fac_cfg: _Optional[str] = ...) -> None: ...

class MulVoiceCfg(_message.Message):
    __slots__ = ["au_language", "au_switch", "au_volume", "audio_cfg_type", "result", "sex"]
    AUDIO_CFG_TYPE_FIELD_NUMBER: _ClassVar[int]
    AU_LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    AU_SWITCH_FIELD_NUMBER: _ClassVar[int]
    AU_VOLUME_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SEX_FIELD_NUMBER: _ClassVar[int]
    au_language: _luba_mul_pb2.MUL_LANGUAGE
    au_switch: int
    au_volume: int
    audio_cfg_type: int
    result: int
    sex: _luba_mul_pb2.MUL_SEX
    def __init__(self, result: _Optional[int] = ..., audio_cfg_type: _Optional[int] = ..., au_switch: _Optional[int] = ..., au_language: _Optional[_Union[_luba_mul_pb2.MUL_LANGUAGE, str]] = ..., sex: _Optional[_Union[_luba_mul_pb2.MUL_SEX, str]] = ..., au_volume: _Optional[int] = ...) -> None: ...

class NavUnableTime(_message.Message):
    __slots__ = ["deviceId", "reserved", "result", "subCmd", "trigger", "unableEndTime", "unableStartTime"]
    DEVICEID_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TRIGGER_FIELD_NUMBER: _ClassVar[int]
    UNABLEENDTIME_FIELD_NUMBER: _ClassVar[int]
    UNABLESTARTTIME_FIELD_NUMBER: _ClassVar[int]
    deviceId: str
    reserved: str
    result: int
    subCmd: int
    trigger: int
    unableEndTime: str
    unableStartTime: str
    def __init__(self, result: _Optional[int] = ..., subCmd: _Optional[int] = ..., deviceId: _Optional[str] = ..., unableStartTime: _Optional[str] = ..., unableEndTime: _Optional[str] = ..., reserved: _Optional[str] = ..., trigger: _Optional[int] = ...) -> None: ...

class RainProtection(_message.Message):
    __slots__ = ["customDelayHours", "rainProtectionMode", "result"]
    CUSTOMDELAYHOURS_FIELD_NUMBER: _ClassVar[int]
    RAINPROTECTIONMODE_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    customDelayHours: int
    rainProtectionMode: int
    result: int
    def __init__(self, result: _Optional[int] = ..., rainProtectionMode: _Optional[int] = ..., customDelayHours: _Optional[int] = ...) -> None: ...

class RainStateCfg(_message.Message):
    __slots__ = ["rain_status", "result"]
    RAIN_STATUS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    rain_status: int
    result: int
    def __init__(self, result: _Optional[int] = ..., rain_status: _Optional[int] = ...) -> None: ...

class ReturnChargeMode(_message.Message):
    __slots__ = ["re_mode", "result"]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    RE_MODE_FIELD_NUMBER: _ClassVar[int]
    re_mode: int
    result: int
    def __init__(self, result: _Optional[int] = ..., re_mode: _Optional[int] = ...) -> None: ...

class ReverseMode(_message.Message):
    __slots__ = ["result", "reverseSafetyMode"]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    REVERSESAFETYMODE_FIELD_NUMBER: _ClassVar[int]
    result: int
    reverseSafetyMode: int
    def __init__(self, result: _Optional[int] = ..., reverseSafetyMode: _Optional[int] = ...) -> None: ...

class SideLedCfg(_message.Message):
    __slots__ = ["action", "enable", "end_hour", "end_min", "operate", "result", "start_hour", "start_min"]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    ENABLE_FIELD_NUMBER: _ClassVar[int]
    END_HOUR_FIELD_NUMBER: _ClassVar[int]
    END_MIN_FIELD_NUMBER: _ClassVar[int]
    OPERATE_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    START_HOUR_FIELD_NUMBER: _ClassVar[int]
    START_MIN_FIELD_NUMBER: _ClassVar[int]
    action: int
    enable: int
    end_hour: int
    end_min: int
    operate: int
    result: int
    start_hour: int
    start_min: int
    def __init__(self, result: _Optional[int] = ..., operate: _Optional[int] = ..., enable: _Optional[int] = ..., start_hour: _Optional[int] = ..., start_min: _Optional[int] = ..., end_hour: _Optional[int] = ..., end_min: _Optional[int] = ..., action: _Optional[int] = ...) -> None: ...

class SpeedModeCfg(_message.Message):
    __slots__ = ["current_cutter_mode", "current_cutter_rpm", "result"]
    CURRENT_CUTTER_MODE_FIELD_NUMBER: _ClassVar[int]
    CURRENT_CUTTER_RPM_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    current_cutter_mode: int
    current_cutter_rpm: int
    result: int
    def __init__(self, result: _Optional[int] = ..., current_cutter_mode: _Optional[int] = ..., current_cutter_rpm: _Optional[int] = ...) -> None: ...

class UturnMode(_message.Message):
    __slots__ = ["result", "turn_mode"]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    TURN_MODE_FIELD_NUMBER: _ClassVar[int]
    result: int
    turn_mode: int
    def __init__(self, result: _Optional[int] = ..., turn_mode: _Optional[int] = ...) -> None: ...

class app_batch_query_req(_message.Message):
    __slots__ = ["req_id", "type_list"]
    REQ_ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_LIST_FIELD_NUMBER: _ClassVar[int]
    req_id: int
    type_list: _containers.RepeatedScalarFieldContainer[BATCH_CONFIG_TYPE]
    def __init__(self, req_id: _Optional[int] = ..., type_list: _Optional[_Iterable[_Union[BATCH_CONFIG_TYPE, str]]] = ...) -> None: ...

class app_batch_query_resp(_message.Message):
    __slots__ = ["cfgs", "req_id"]
    CFGS_FIELD_NUMBER: _ClassVar[int]
    REQ_ID_FIELD_NUMBER: _ClassVar[int]
    cfgs: _containers.RepeatedCompositeFieldContainer[batchcfg]
    req_id: int
    def __init__(self, req_id: _Optional[int] = ..., cfgs: _Optional[_Iterable[_Union[batchcfg, _Mapping]]] = ...) -> None: ...

class app_batch_set_req(_message.Message):
    __slots__ = ["cfgs", "req_id"]
    CFGS_FIELD_NUMBER: _ClassVar[int]
    REQ_ID_FIELD_NUMBER: _ClassVar[int]
    cfgs: _containers.RepeatedCompositeFieldContainer[batchcfg]
    req_id: int
    def __init__(self, req_id: _Optional[int] = ..., cfgs: _Optional[_Iterable[_Union[batchcfg, _Mapping]]] = ...) -> None: ...

class app_batch_set_resp(_message.Message):
    __slots__ = ["req_id", "res_data"]
    REQ_ID_FIELD_NUMBER: _ClassVar[int]
    RES_DATA_FIELD_NUMBER: _ClassVar[int]
    req_id: int
    res_data: _containers.RepeatedCompositeFieldContainer[batch_set_res]
    def __init__(self, req_id: _Optional[int] = ..., res_data: _Optional[_Iterable[_Union[batch_set_res, _Mapping]]] = ...) -> None: ...

class batch_set_res(_message.Message):
    __slots__ = ["res_result", "type"]
    RES_RESULT_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    res_result: ResResult
    type: BATCH_CONFIG_TYPE
    def __init__(self, type: _Optional[_Union[BATCH_CONFIG_TYPE, str]] = ..., res_result: _Optional[_Union[ResResult, str]] = ...) -> None: ...

class batchcfg(_message.Message):
    __slots__ = ["cfgtype", "child_pro", "light_sta", "lora", "mode", "mul_cfg", "rain_cfg", "rain_pro", "re_mode", "reverse_mode", "sideled", "time", "u_mode"]
    CFGTYPE_FIELD_NUMBER: _ClassVar[int]
    CHILD_PRO_FIELD_NUMBER: _ClassVar[int]
    LIGHT_STA_FIELD_NUMBER: _ClassVar[int]
    LORA_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    MUL_CFG_FIELD_NUMBER: _ClassVar[int]
    RAIN_CFG_FIELD_NUMBER: _ClassVar[int]
    RAIN_PRO_FIELD_NUMBER: _ClassVar[int]
    REVERSE_MODE_FIELD_NUMBER: _ClassVar[int]
    RE_MODE_FIELD_NUMBER: _ClassVar[int]
    SIDELED_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    U_MODE_FIELD_NUMBER: _ClassVar[int]
    cfgtype: BATCH_CONFIG_TYPE
    child_pro: ChildProtection
    light_sta: FillLightState
    lora: LoraCfg
    mode: SpeedModeCfg
    mul_cfg: MulVoiceCfg
    rain_cfg: RainStateCfg
    rain_pro: RainProtection
    re_mode: ReturnChargeMode
    reverse_mode: ReverseMode
    sideled: SideLedCfg
    time: NavUnableTime
    u_mode: UturnMode
    def __init__(self, cfgtype: _Optional[_Union[BATCH_CONFIG_TYPE, str]] = ..., time: _Optional[_Union[NavUnableTime, _Mapping]] = ..., rain_cfg: _Optional[_Union[RainStateCfg, _Mapping]] = ..., sideled: _Optional[_Union[SideLedCfg, _Mapping]] = ..., mul_cfg: _Optional[_Union[MulVoiceCfg, _Mapping]] = ..., light_sta: _Optional[_Union[FillLightState, _Mapping]] = ..., u_mode: _Optional[_Union[UturnMode, _Mapping]] = ..., re_mode: _Optional[_Union[ReturnChargeMode, _Mapping]] = ..., mode: _Optional[_Union[SpeedModeCfg, _Mapping]] = ..., lora: _Optional[_Union[LoraCfg, _Mapping]] = ..., rain_pro: _Optional[_Union[RainProtection, _Mapping]] = ..., child_pro: _Optional[_Union[ChildProtection, _Mapping]] = ..., reverse_mode: _Optional[_Union[ReverseMode, _Mapping]] = ...) -> None: ...

class BATCH_CONFIG_TYPE(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class ResResult(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
