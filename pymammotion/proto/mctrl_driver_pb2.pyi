from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

COLLECT_ABNORMAL: CollectMotorState
COLLECT_CLOSE: CollectMotorState
COLLECT_OPEN: CollectMotorState
COLLECT_STUCK: CollectMotorState
CUTTER_ECONOMIC: CutterWorkMode
CUTTER_PERFORMANCE: CutterWorkMode
CUTTER_STANDARD: CutterWorkMode
DESCRIPTOR: _descriptor.FileDescriptor
UNLOAD_CLOSE: UnloadMotorState
UNLOAD_OPEN: UnloadMotorState
UNLOAD_RUNNING: UnloadMotorState
UNLOAD_STOP: UnloadMotorState

class AppGetCutterWorkMode(_message.Message):
    __slots__ = ["QueryResult", "current_cutter_mode", "current_cutter_rpm"]
    CURRENT_CUTTER_MODE_FIELD_NUMBER: _ClassVar[int]
    CURRENT_CUTTER_RPM_FIELD_NUMBER: _ClassVar[int]
    QUERYRESULT_FIELD_NUMBER: _ClassVar[int]
    QueryResult: int
    current_cutter_mode: int
    current_cutter_rpm: int
    def __init__(self, current_cutter_mode: _Optional[int] = ..., current_cutter_rpm: _Optional[int] = ..., QueryResult: _Optional[int] = ...) -> None: ...

class AppSetCutterWorkMode(_message.Message):
    __slots__ = ["CutterMode", "SetResult"]
    CUTTERMODE_FIELD_NUMBER: _ClassVar[int]
    CutterMode: int
    SETRESULT_FIELD_NUMBER: _ClassVar[int]
    SetResult: int
    def __init__(self, CutterMode: _Optional[int] = ..., SetResult: _Optional[int] = ...) -> None: ...

class DrvCollectCtrlByHand(_message.Message):
    __slots__ = ["collect_ctrl", "unload_ctrl"]
    COLLECT_CTRL_FIELD_NUMBER: _ClassVar[int]
    UNLOAD_CTRL_FIELD_NUMBER: _ClassVar[int]
    collect_ctrl: int
    unload_ctrl: int
    def __init__(self, collect_ctrl: _Optional[int] = ..., unload_ctrl: _Optional[int] = ...) -> None: ...

class DrvKnifeChangeReport(_message.Message):
    __slots__ = ["cur_height", "end_height", "is_start", "start_height"]
    CUR_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    END_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    IS_START_FIELD_NUMBER: _ClassVar[int]
    START_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    cur_height: int
    end_height: int
    is_start: int
    start_height: int
    def __init__(self, is_start: _Optional[int] = ..., start_height: _Optional[int] = ..., end_height: _Optional[int] = ..., cur_height: _Optional[int] = ...) -> None: ...

class DrvKnifeHeight(_message.Message):
    __slots__ = ["knifeHeight"]
    KNIFEHEIGHT_FIELD_NUMBER: _ClassVar[int]
    knifeHeight: int
    def __init__(self, knifeHeight: _Optional[int] = ...) -> None: ...

class DrvKnifeStatus(_message.Message):
    __slots__ = ["knife_status"]
    KNIFE_STATUS_FIELD_NUMBER: _ClassVar[int]
    knife_status: int
    def __init__(self, knife_status: _Optional[int] = ...) -> None: ...

class DrvMotionCtrl(_message.Message):
    __slots__ = ["setAngularSpeed", "setLinearSpeed"]
    SETANGULARSPEED_FIELD_NUMBER: _ClassVar[int]
    SETLINEARSPEED_FIELD_NUMBER: _ClassVar[int]
    setAngularSpeed: int
    setLinearSpeed: int
    def __init__(self, setLinearSpeed: _Optional[int] = ..., setAngularSpeed: _Optional[int] = ...) -> None: ...

class DrvMowCtrlByHand(_message.Message):
    __slots__ = ["cut_knife_ctrl", "cut_knife_height", "main_ctrl", "max_run_Speed"]
    CUT_KNIFE_CTRL_FIELD_NUMBER: _ClassVar[int]
    CUT_KNIFE_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    MAIN_CTRL_FIELD_NUMBER: _ClassVar[int]
    MAX_RUN_SPEED_FIELD_NUMBER: _ClassVar[int]
    cut_knife_ctrl: int
    cut_knife_height: int
    main_ctrl: int
    max_run_Speed: float
    def __init__(self, main_ctrl: _Optional[int] = ..., cut_knife_ctrl: _Optional[int] = ..., cut_knife_height: _Optional[int] = ..., max_run_Speed: _Optional[float] = ...) -> None: ...

class DrvSrSpeed(_message.Message):
    __slots__ = ["rw", "speed"]
    RW_FIELD_NUMBER: _ClassVar[int]
    SPEED_FIELD_NUMBER: _ClassVar[int]
    rw: int
    speed: float
    def __init__(self, rw: _Optional[int] = ..., speed: _Optional[float] = ...) -> None: ...

class MctlDriver(_message.Message):
    __slots__ = ["bidire_knife_height_report", "bidire_speed_read_set", "collect_ctrl_by_hand", "current_cutter_mode", "cutter_mode_ctrl_by_hand", "mow_ctrl_by_hand", "rtk_cfg_req", "rtk_cfg_req_ack", "rtk_sys_mask_query", "rtk_sys_mask_query_ack", "toapp_knife_status", "toapp_knife_status_change", "todev_devmotion_ctrl", "todev_knife_height_set"]
    BIDIRE_KNIFE_HEIGHT_REPORT_FIELD_NUMBER: _ClassVar[int]
    BIDIRE_SPEED_READ_SET_FIELD_NUMBER: _ClassVar[int]
    COLLECT_CTRL_BY_HAND_FIELD_NUMBER: _ClassVar[int]
    CURRENT_CUTTER_MODE_FIELD_NUMBER: _ClassVar[int]
    CUTTER_MODE_CTRL_BY_HAND_FIELD_NUMBER: _ClassVar[int]
    MOW_CTRL_BY_HAND_FIELD_NUMBER: _ClassVar[int]
    RTK_CFG_REQ_ACK_FIELD_NUMBER: _ClassVar[int]
    RTK_CFG_REQ_FIELD_NUMBER: _ClassVar[int]
    RTK_SYS_MASK_QUERY_ACK_FIELD_NUMBER: _ClassVar[int]
    RTK_SYS_MASK_QUERY_FIELD_NUMBER: _ClassVar[int]
    TOAPP_KNIFE_STATUS_CHANGE_FIELD_NUMBER: _ClassVar[int]
    TOAPP_KNIFE_STATUS_FIELD_NUMBER: _ClassVar[int]
    TODEV_DEVMOTION_CTRL_FIELD_NUMBER: _ClassVar[int]
    TODEV_KNIFE_HEIGHT_SET_FIELD_NUMBER: _ClassVar[int]
    bidire_knife_height_report: DrvKnifeHeight
    bidire_speed_read_set: DrvSrSpeed
    collect_ctrl_by_hand: DrvCollectCtrlByHand
    current_cutter_mode: AppGetCutterWorkMode
    cutter_mode_ctrl_by_hand: AppSetCutterWorkMode
    mow_ctrl_by_hand: DrvMowCtrlByHand
    rtk_cfg_req: rtk_cfg_req_t
    rtk_cfg_req_ack: rtk_cfg_req_ack_t
    rtk_sys_mask_query: rtk_sys_mask_query_t
    rtk_sys_mask_query_ack: rtk_sys_mask_query_ack_t
    toapp_knife_status: DrvKnifeStatus
    toapp_knife_status_change: DrvKnifeChangeReport
    todev_devmotion_ctrl: DrvMotionCtrl
    todev_knife_height_set: DrvKnifeHeight
    def __init__(self, todev_devmotion_ctrl: _Optional[_Union[DrvMotionCtrl, _Mapping]] = ..., todev_knife_height_set: _Optional[_Union[DrvKnifeHeight, _Mapping]] = ..., bidire_speed_read_set: _Optional[_Union[DrvSrSpeed, _Mapping]] = ..., bidire_knife_height_report: _Optional[_Union[DrvKnifeHeight, _Mapping]] = ..., toapp_knife_status: _Optional[_Union[DrvKnifeStatus, _Mapping]] = ..., mow_ctrl_by_hand: _Optional[_Union[DrvMowCtrlByHand, _Mapping]] = ..., rtk_cfg_req: _Optional[_Union[rtk_cfg_req_t, _Mapping]] = ..., rtk_cfg_req_ack: _Optional[_Union[rtk_cfg_req_ack_t, _Mapping]] = ..., rtk_sys_mask_query: _Optional[_Union[rtk_sys_mask_query_t, _Mapping]] = ..., rtk_sys_mask_query_ack: _Optional[_Union[rtk_sys_mask_query_ack_t, _Mapping]] = ..., toapp_knife_status_change: _Optional[_Union[DrvKnifeChangeReport, _Mapping]] = ..., collect_ctrl_by_hand: _Optional[_Union[DrvCollectCtrlByHand, _Mapping]] = ..., cutter_mode_ctrl_by_hand: _Optional[_Union[AppSetCutterWorkMode, _Mapping]] = ..., current_cutter_mode: _Optional[_Union[AppGetCutterWorkMode, _Mapping]] = ...) -> None: ...

class rtk_cfg_req_ack_t(_message.Message):
    __slots__ = ["cmd_length", "cmd_response"]
    CMD_LENGTH_FIELD_NUMBER: _ClassVar[int]
    CMD_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    cmd_length: int
    cmd_response: str
    def __init__(self, cmd_length: _Optional[int] = ..., cmd_response: _Optional[str] = ...) -> None: ...

class rtk_cfg_req_t(_message.Message):
    __slots__ = ["cmd_length", "cmd_req"]
    CMD_LENGTH_FIELD_NUMBER: _ClassVar[int]
    CMD_REQ_FIELD_NUMBER: _ClassVar[int]
    cmd_length: int
    cmd_req: str
    def __init__(self, cmd_length: _Optional[int] = ..., cmd_req: _Optional[str] = ...) -> None: ...

class rtk_sys_mask_query_ack_t(_message.Message):
    __slots__ = ["sat_system", "system_mask_bits"]
    SAT_SYSTEM_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_MASK_BITS_FIELD_NUMBER: _ClassVar[int]
    sat_system: int
    system_mask_bits: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, sat_system: _Optional[int] = ..., system_mask_bits: _Optional[_Iterable[int]] = ...) -> None: ...

class rtk_sys_mask_query_t(_message.Message):
    __slots__ = ["sat_system"]
    SAT_SYSTEM_FIELD_NUMBER: _ClassVar[int]
    sat_system: int
    def __init__(self, sat_system: _Optional[int] = ...) -> None: ...

class CutterWorkMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class CollectMotorState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class UnloadMotorState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
