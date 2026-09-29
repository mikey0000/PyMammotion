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
DRV_CTRL_BLE: DrvCtrlLink
DRV_CTRL_IOT: DrvCtrlLink
DRV_CTRL_LAN: DrvCtrlLink
DRV_CTRL_UNKNOW: DrvCtrlLink
DRV_SESSION_CTRL_BLE_PREEMPT: DrvSessionCtrlResult
DRV_SESSION_CTRL_BURST: DrvSessionCtrlResult
DRV_SESSION_CTRL_DELAY: DrvSessionCtrlResult
DRV_SESSION_CTRL_FPV_STREAM_ERROR: DrvSessionCtrlResult
DRV_SESSION_CTRL_GENERAL_ERROR: DrvSessionCtrlResult
DRV_SESSION_CTRL_INVALID_PARAM: DrvSessionCtrlResult
DRV_SESSION_CTRL_NO_LOC_MAX_MILEAGE: DrvSessionCtrlResult
DRV_SESSION_CTRL_OK: DrvSessionCtrlResult
DRV_SESSION_CTRL_OUT_OF_FENCE: DrvSessionCtrlResult
DRV_SESSION_CTRL_SEQ_INVALID: DrvSessionCtrlResult
DRV_SESSION_CTRL_TOKEN_EXPIRED: DrvSessionCtrlResult
DRV_SESSION_CTRL_TOKEN_INVALID: DrvSessionCtrlResult
DRV_SESSION_EXIT_BLE_PREEMPT: DrvSessionExitReason
DRV_SESSION_EXIT_IDLE_TIMEOUT: DrvSessionExitReason
DRV_SESSION_EXIT_NEW_CFG: DrvSessionExitReason
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

class DrvBuzzEnable(_message.Message):
    __slots__ = ["buzz_enable"]
    BUZZ_ENABLE_FIELD_NUMBER: _ClassVar[int]
    buzz_enable: int
    def __init__(self, buzz_enable: _Optional[int] = ...) -> None: ...

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
    __slots__ = ["channel", "setAngularSpeed", "setLinearSpeed"]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    SETANGULARSPEED_FIELD_NUMBER: _ClassVar[int]
    SETLINEARSPEED_FIELD_NUMBER: _ClassVar[int]
    channel: DrvCtrlLink
    setAngularSpeed: int
    setLinearSpeed: int
    def __init__(self, setLinearSpeed: _Optional[int] = ..., setAngularSpeed: _Optional[int] = ..., channel: _Optional[_Union[DrvCtrlLink, str]] = ...) -> None: ...

class DrvMotionCtrlAck(_message.Message):
    __slots__ = ["delay_ms", "is_drop", "timestamp"]
    DELAY_MS_FIELD_NUMBER: _ClassVar[int]
    IS_DROP_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    delay_ms: int
    is_drop: int
    timestamp: int
    def __init__(self, timestamp: _Optional[int] = ..., is_drop: _Optional[int] = ..., delay_ms: _Optional[int] = ...) -> None: ...

class DrvMotionCtrlTest(_message.Message):
    __slots__ = ["channel", "setAngularSpeed", "setLinearSpeed"]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    SETANGULARSPEED_FIELD_NUMBER: _ClassVar[int]
    SETLINEARSPEED_FIELD_NUMBER: _ClassVar[int]
    channel: DrvCtrlLink
    setAngularSpeed: int
    setLinearSpeed: int
    def __init__(self, setLinearSpeed: _Optional[int] = ..., setAngularSpeed: _Optional[int] = ..., channel: _Optional[_Union[DrvCtrlLink, str]] = ...) -> None: ...

class DrvMowCtrlByHand(_message.Message):
    __slots__ = ["cut_knife_ctrl", "cut_knife_height", "edge_ctrl", "main_ctrl", "max_run_speed"]
    CUT_KNIFE_CTRL_FIELD_NUMBER: _ClassVar[int]
    CUT_KNIFE_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    EDGE_CTRL_FIELD_NUMBER: _ClassVar[int]
    MAIN_CTRL_FIELD_NUMBER: _ClassVar[int]
    MAX_RUN_SPEED_FIELD_NUMBER: _ClassVar[int]
    cut_knife_ctrl: int
    cut_knife_height: int
    edge_ctrl: int
    main_ctrl: int
    max_run_speed: float
    def __init__(self, main_ctrl: _Optional[int] = ..., cut_knife_ctrl: _Optional[int] = ..., cut_knife_height: _Optional[int] = ..., max_run_speed: _Optional[float] = ..., edge_ctrl: _Optional[int] = ...) -> None: ...

class DrvSessionCtrlAck(_message.Message):
    __slots__ = ["appSendTsMs", "ctrlSeq", "fenceExceedDistance", "localizationValid", "measuredDelayMs", "preemptAccount", "result", "vehicleSendTsMs"]
    APPSENDTSMS_FIELD_NUMBER: _ClassVar[int]
    CTRLSEQ_FIELD_NUMBER: _ClassVar[int]
    FENCEEXCEEDDISTANCE_FIELD_NUMBER: _ClassVar[int]
    LOCALIZATIONVALID_FIELD_NUMBER: _ClassVar[int]
    MEASUREDDELAYMS_FIELD_NUMBER: _ClassVar[int]
    PREEMPTACCOUNT_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    VEHICLESENDTSMS_FIELD_NUMBER: _ClassVar[int]
    appSendTsMs: int
    ctrlSeq: int
    fenceExceedDistance: float
    localizationValid: bool
    measuredDelayMs: int
    preemptAccount: int
    result: DrvSessionCtrlResult
    vehicleSendTsMs: int
    def __init__(self, ctrlSeq: _Optional[int] = ..., appSendTsMs: _Optional[int] = ..., vehicleSendTsMs: _Optional[int] = ..., result: _Optional[_Union[DrvSessionCtrlResult, str]] = ..., localizationValid: bool = ..., fenceExceedDistance: _Optional[float] = ..., measuredDelayMs: _Optional[int] = ..., preemptAccount: _Optional[int] = ...) -> None: ...

class DrvSessionCtrlReq(_message.Message):
    __slots__ = ["appSendTsMs", "channel", "ctrlSeq", "setAngularSpeed", "setLinearSpeed", "token", "vehicleSendTsMs"]
    APPSENDTSMS_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    CTRLSEQ_FIELD_NUMBER: _ClassVar[int]
    SETANGULARSPEED_FIELD_NUMBER: _ClassVar[int]
    SETLINEARSPEED_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    VEHICLESENDTSMS_FIELD_NUMBER: _ClassVar[int]
    appSendTsMs: int
    channel: DrvCtrlLink
    ctrlSeq: int
    setAngularSpeed: int
    setLinearSpeed: int
    token: str
    vehicleSendTsMs: int
    def __init__(self, ctrlSeq: _Optional[int] = ..., setLinearSpeed: _Optional[int] = ..., setAngularSpeed: _Optional[int] = ..., channel: _Optional[_Union[DrvCtrlLink, str]] = ..., appSendTsMs: _Optional[int] = ..., vehicleSendTsMs: _Optional[int] = ..., token: _Optional[str] = ...) -> None: ...

class DrvSessionExitAppNfty(_message.Message):
    __slots__ = ["channel", "token"]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    channel: DrvCtrlLink
    token: str
    def __init__(self, token: _Optional[str] = ..., channel: _Optional[_Union[DrvCtrlLink, str]] = ...) -> None: ...

class DrvSessionExitNfty(_message.Message):
    __slots__ = ["preemptAccount", "reason"]
    PREEMPTACCOUNT_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    preemptAccount: int
    reason: DrvSessionExitReason
    def __init__(self, reason: _Optional[_Union[DrvSessionExitReason, str]] = ..., preemptAccount: _Optional[int] = ...) -> None: ...

class DrvSrSpeed(_message.Message):
    __slots__ = ["rw", "speed"]
    RW_FIELD_NUMBER: _ClassVar[int]
    SPEED_FIELD_NUMBER: _ClassVar[int]
    rw: int
    speed: float
    def __init__(self, rw: _Optional[int] = ..., speed: _Optional[float] = ...) -> None: ...

class MctlDriver(_message.Message):
    __slots__ = ["bidire_knife_height_report", "bidire_speed_read_set", "collect_ctrl_by_hand", "current_cutter_mode", "cutter_mode_ctrl_by_hand", "drv_buzz_enable", "mow_ctrl_by_hand", "rtk_cfg_req", "rtk_cfg_req_ack", "rtk_sys_mask_query", "rtk_sys_mask_query_ack", "toapp_devmotion_ctrl_ack", "toapp_knife_status", "toapp_knife_status_change", "toapp_session_ctrl_ack", "toapp_session_exit_nfty", "todev_devmotion_ctrl", "todev_devmotion_ctrl_test", "todev_knife_height_set", "todev_session_ctrl_req", "todev_session_exit_nfty"]
    BIDIRE_KNIFE_HEIGHT_REPORT_FIELD_NUMBER: _ClassVar[int]
    BIDIRE_SPEED_READ_SET_FIELD_NUMBER: _ClassVar[int]
    COLLECT_CTRL_BY_HAND_FIELD_NUMBER: _ClassVar[int]
    CURRENT_CUTTER_MODE_FIELD_NUMBER: _ClassVar[int]
    CUTTER_MODE_CTRL_BY_HAND_FIELD_NUMBER: _ClassVar[int]
    DRV_BUZZ_ENABLE_FIELD_NUMBER: _ClassVar[int]
    MOW_CTRL_BY_HAND_FIELD_NUMBER: _ClassVar[int]
    RTK_CFG_REQ_ACK_FIELD_NUMBER: _ClassVar[int]
    RTK_CFG_REQ_FIELD_NUMBER: _ClassVar[int]
    RTK_SYS_MASK_QUERY_ACK_FIELD_NUMBER: _ClassVar[int]
    RTK_SYS_MASK_QUERY_FIELD_NUMBER: _ClassVar[int]
    TOAPP_DEVMOTION_CTRL_ACK_FIELD_NUMBER: _ClassVar[int]
    TOAPP_KNIFE_STATUS_CHANGE_FIELD_NUMBER: _ClassVar[int]
    TOAPP_KNIFE_STATUS_FIELD_NUMBER: _ClassVar[int]
    TOAPP_SESSION_CTRL_ACK_FIELD_NUMBER: _ClassVar[int]
    TOAPP_SESSION_EXIT_NFTY_FIELD_NUMBER: _ClassVar[int]
    TODEV_DEVMOTION_CTRL_FIELD_NUMBER: _ClassVar[int]
    TODEV_DEVMOTION_CTRL_TEST_FIELD_NUMBER: _ClassVar[int]
    TODEV_KNIFE_HEIGHT_SET_FIELD_NUMBER: _ClassVar[int]
    TODEV_SESSION_CTRL_REQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_SESSION_EXIT_NFTY_FIELD_NUMBER: _ClassVar[int]
    bidire_knife_height_report: DrvKnifeHeight
    bidire_speed_read_set: DrvSrSpeed
    collect_ctrl_by_hand: DrvCollectCtrlByHand
    current_cutter_mode: AppGetCutterWorkMode
    cutter_mode_ctrl_by_hand: AppSetCutterWorkMode
    drv_buzz_enable: DrvBuzzEnable
    mow_ctrl_by_hand: DrvMowCtrlByHand
    rtk_cfg_req: rtk_cfg_req_t
    rtk_cfg_req_ack: rtk_cfg_req_ack_t
    rtk_sys_mask_query: rtk_sys_mask_query_t
    rtk_sys_mask_query_ack: rtk_sys_mask_query_ack_t
    toapp_devmotion_ctrl_ack: DrvMotionCtrlAck
    toapp_knife_status: DrvKnifeStatus
    toapp_knife_status_change: DrvKnifeChangeReport
    toapp_session_ctrl_ack: DrvSessionCtrlAck
    toapp_session_exit_nfty: DrvSessionExitNfty
    todev_devmotion_ctrl: DrvMotionCtrl
    todev_devmotion_ctrl_test: DrvMotionCtrlTest
    todev_knife_height_set: DrvKnifeHeight
    todev_session_ctrl_req: DrvSessionCtrlReq
    todev_session_exit_nfty: DrvSessionExitAppNfty
    def __init__(self, todev_devmotion_ctrl: _Optional[_Union[DrvMotionCtrl, _Mapping]] = ..., todev_knife_height_set: _Optional[_Union[DrvKnifeHeight, _Mapping]] = ..., bidire_speed_read_set: _Optional[_Union[DrvSrSpeed, _Mapping]] = ..., bidire_knife_height_report: _Optional[_Union[DrvKnifeHeight, _Mapping]] = ..., toapp_knife_status: _Optional[_Union[DrvKnifeStatus, _Mapping]] = ..., mow_ctrl_by_hand: _Optional[_Union[DrvMowCtrlByHand, _Mapping]] = ..., rtk_cfg_req: _Optional[_Union[rtk_cfg_req_t, _Mapping]] = ..., rtk_cfg_req_ack: _Optional[_Union[rtk_cfg_req_ack_t, _Mapping]] = ..., rtk_sys_mask_query: _Optional[_Union[rtk_sys_mask_query_t, _Mapping]] = ..., rtk_sys_mask_query_ack: _Optional[_Union[rtk_sys_mask_query_ack_t, _Mapping]] = ..., toapp_knife_status_change: _Optional[_Union[DrvKnifeChangeReport, _Mapping]] = ..., collect_ctrl_by_hand: _Optional[_Union[DrvCollectCtrlByHand, _Mapping]] = ..., cutter_mode_ctrl_by_hand: _Optional[_Union[AppSetCutterWorkMode, _Mapping]] = ..., current_cutter_mode: _Optional[_Union[AppGetCutterWorkMode, _Mapping]] = ..., todev_devmotion_ctrl_test: _Optional[_Union[DrvMotionCtrlTest, _Mapping]] = ..., toapp_devmotion_ctrl_ack: _Optional[_Union[DrvMotionCtrlAck, _Mapping]] = ..., drv_buzz_enable: _Optional[_Union[DrvBuzzEnable, _Mapping]] = ..., todev_session_ctrl_req: _Optional[_Union[DrvSessionCtrlReq, _Mapping]] = ..., toapp_session_ctrl_ack: _Optional[_Union[DrvSessionCtrlAck, _Mapping]] = ..., todev_session_exit_nfty: _Optional[_Union[DrvSessionExitAppNfty, _Mapping]] = ..., toapp_session_exit_nfty: _Optional[_Union[DrvSessionExitNfty, _Mapping]] = ...) -> None: ...

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

class DrvCtrlLink(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class DrvSessionCtrlResult(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class DrvSessionExitReason(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
