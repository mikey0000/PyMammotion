from pymammotion.proto import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AppGetAllAreaHashName(_message.Message):
    __slots__ = ["device_id", "hashnames"]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    HASHNAMES_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    hashnames: _containers.RepeatedCompositeFieldContainer[AreaHashName]
    def __init__(self, device_id: _Optional[str] = ..., hashnames: _Optional[_Iterable[_Union[AreaHashName, _Mapping]]] = ...) -> None: ...

class AreaHashName(_message.Message):
    __slots__ = ["hash", "name"]
    HASH_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    hash: int
    name: str
    def __init__(self, name: _Optional[str] = ..., hash: _Optional[int] = ...) -> None: ...

class AreaLabel(_message.Message):
    __slots__ = ["label"]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    label: str
    def __init__(self, label: _Optional[str] = ...) -> None: ...

class MctlNav(_message.Message):
    __slots__ = ["all_plan_task", "app_request_cover_paths", "bidire_reqconver_path", "bidire_taskid", "cover_path_upload", "nav_sys_param_cmd", "plan_task_execute", "plan_task_name_id", "simulation_cmd", "toapp_all_hash_name", "toapp_bp", "toapp_bstate", "toapp_chgpileto", "toapp_costmap", "toapp_get_commondata_ack", "toapp_gethash_ack", "toapp_lat_up", "toapp_map_name_msg", "toapp_opt_border_info", "toapp_opt_line_up", "toapp_opt_obs_info", "toapp_pos_up", "toapp_svg_msg", "toapp_task_info", "toapp_work_report_ack", "toapp_work_report_update_ack", "toapp_work_report_upload", "toapp_zigzag", "todev_cancel_draw_cmd", "todev_cancel_suscmd", "todev_chl_line", "todev_chl_line_data", "todev_chl_line_end", "todev_draw_border", "todev_draw_border_end", "todev_draw_obs", "todev_draw_obs_end", "todev_edgecmd", "todev_get_commondata", "todev_gethash", "todev_lat_up_ack", "todev_mow_task", "todev_one_touch_leave_pile", "todev_opt_border_info_ack", "todev_opt_line_up_ack", "todev_opt_obs_info_ack", "todev_planjob_set", "todev_rechgcmd", "todev_reset_chg_pile", "todev_save_task", "todev_sustask", "todev_svg_msg", "todev_task_info_ack", "todev_taskctrl", "todev_taskctrl_ack", "todev_unable_time_set", "todev_work_report_cmd", "todev_work_report_update_cmd", "todev_zigzag_ack", "vision_ctrl", "zone_start_precent"]
    ALL_PLAN_TASK_FIELD_NUMBER: _ClassVar[int]
    APP_REQUEST_COVER_PATHS_FIELD_NUMBER: _ClassVar[int]
    BIDIRE_REQCONVER_PATH_FIELD_NUMBER: _ClassVar[int]
    BIDIRE_TASKID_FIELD_NUMBER: _ClassVar[int]
    COVER_PATH_UPLOAD_FIELD_NUMBER: _ClassVar[int]
    NAV_SYS_PARAM_CMD_FIELD_NUMBER: _ClassVar[int]
    PLAN_TASK_EXECUTE_FIELD_NUMBER: _ClassVar[int]
    PLAN_TASK_NAME_ID_FIELD_NUMBER: _ClassVar[int]
    SIMULATION_CMD_FIELD_NUMBER: _ClassVar[int]
    TOAPP_ALL_HASH_NAME_FIELD_NUMBER: _ClassVar[int]
    TOAPP_BP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_BSTATE_FIELD_NUMBER: _ClassVar[int]
    TOAPP_CHGPILETO_FIELD_NUMBER: _ClassVar[int]
    TOAPP_COSTMAP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_GETHASH_ACK_FIELD_NUMBER: _ClassVar[int]
    TOAPP_GET_COMMONDATA_ACK_FIELD_NUMBER: _ClassVar[int]
    TOAPP_LAT_UP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_MAP_NAME_MSG_FIELD_NUMBER: _ClassVar[int]
    TOAPP_OPT_BORDER_INFO_FIELD_NUMBER: _ClassVar[int]
    TOAPP_OPT_LINE_UP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_OPT_OBS_INFO_FIELD_NUMBER: _ClassVar[int]
    TOAPP_POS_UP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_SVG_MSG_FIELD_NUMBER: _ClassVar[int]
    TOAPP_TASK_INFO_FIELD_NUMBER: _ClassVar[int]
    TOAPP_WORK_REPORT_ACK_FIELD_NUMBER: _ClassVar[int]
    TOAPP_WORK_REPORT_UPDATE_ACK_FIELD_NUMBER: _ClassVar[int]
    TOAPP_WORK_REPORT_UPLOAD_FIELD_NUMBER: _ClassVar[int]
    TOAPP_ZIGZAG_FIELD_NUMBER: _ClassVar[int]
    TODEV_CANCEL_DRAW_CMD_FIELD_NUMBER: _ClassVar[int]
    TODEV_CANCEL_SUSCMD_FIELD_NUMBER: _ClassVar[int]
    TODEV_CHL_LINE_DATA_FIELD_NUMBER: _ClassVar[int]
    TODEV_CHL_LINE_END_FIELD_NUMBER: _ClassVar[int]
    TODEV_CHL_LINE_FIELD_NUMBER: _ClassVar[int]
    TODEV_DRAW_BORDER_END_FIELD_NUMBER: _ClassVar[int]
    TODEV_DRAW_BORDER_FIELD_NUMBER: _ClassVar[int]
    TODEV_DRAW_OBS_END_FIELD_NUMBER: _ClassVar[int]
    TODEV_DRAW_OBS_FIELD_NUMBER: _ClassVar[int]
    TODEV_EDGECMD_FIELD_NUMBER: _ClassVar[int]
    TODEV_GETHASH_FIELD_NUMBER: _ClassVar[int]
    TODEV_GET_COMMONDATA_FIELD_NUMBER: _ClassVar[int]
    TODEV_LAT_UP_ACK_FIELD_NUMBER: _ClassVar[int]
    TODEV_MOW_TASK_FIELD_NUMBER: _ClassVar[int]
    TODEV_ONE_TOUCH_LEAVE_PILE_FIELD_NUMBER: _ClassVar[int]
    TODEV_OPT_BORDER_INFO_ACK_FIELD_NUMBER: _ClassVar[int]
    TODEV_OPT_LINE_UP_ACK_FIELD_NUMBER: _ClassVar[int]
    TODEV_OPT_OBS_INFO_ACK_FIELD_NUMBER: _ClassVar[int]
    TODEV_PLANJOB_SET_FIELD_NUMBER: _ClassVar[int]
    TODEV_RECHGCMD_FIELD_NUMBER: _ClassVar[int]
    TODEV_RESET_CHG_PILE_FIELD_NUMBER: _ClassVar[int]
    TODEV_SAVE_TASK_FIELD_NUMBER: _ClassVar[int]
    TODEV_SUSTASK_FIELD_NUMBER: _ClassVar[int]
    TODEV_SVG_MSG_FIELD_NUMBER: _ClassVar[int]
    TODEV_TASKCTRL_ACK_FIELD_NUMBER: _ClassVar[int]
    TODEV_TASKCTRL_FIELD_NUMBER: _ClassVar[int]
    TODEV_TASK_INFO_ACK_FIELD_NUMBER: _ClassVar[int]
    TODEV_UNABLE_TIME_SET_FIELD_NUMBER: _ClassVar[int]
    TODEV_WORK_REPORT_CMD_FIELD_NUMBER: _ClassVar[int]
    TODEV_WORK_REPORT_UPDATE_CMD_FIELD_NUMBER: _ClassVar[int]
    TODEV_ZIGZAG_ACK_FIELD_NUMBER: _ClassVar[int]
    VISION_CTRL_FIELD_NUMBER: _ClassVar[int]
    ZONE_START_PRECENT_FIELD_NUMBER: _ClassVar[int]
    all_plan_task: nav_get_all_plan_task
    app_request_cover_paths: app_request_cover_paths_t
    bidire_reqconver_path: NavReqCoverPath
    bidire_taskid: NavTaskIdRw
    cover_path_upload: cover_path_upload_t
    nav_sys_param_cmd: nav_sys_param_msg
    plan_task_execute: nav_plan_task_execute
    plan_task_name_id: plan_task_name_id_t
    simulation_cmd: SimulationCmdData
    toapp_all_hash_name: AppGetAllAreaHashName
    toapp_bp: NavTaskBreakPoint
    toapp_bstate: NavBorderState
    toapp_chgpileto: chargePileType
    toapp_costmap: costmap_t
    toapp_get_commondata_ack: NavGetCommDataAck
    toapp_gethash_ack: NavGetHashListAck
    toapp_lat_up: NavLatLonUp
    toapp_map_name_msg: NavMapNameMsg
    toapp_opt_border_info: NavOptiBorderInfo
    toapp_opt_line_up: NavOptLineUp
    toapp_opt_obs_info: NavOptObsInfo
    toapp_pos_up: NavPosUp
    toapp_svg_msg: SvgMessageAckT
    toapp_task_info: NavTaskInfo
    toapp_work_report_ack: WorkReportInfoAck
    toapp_work_report_update_ack: WorkReportUpdateAck
    toapp_work_report_upload: WorkReportInfoAck
    toapp_zigzag: NavUploadZigZagResult
    todev_cancel_draw_cmd: int
    todev_cancel_suscmd: int
    todev_chl_line: int
    todev_chl_line_data: NavCHlLineData
    todev_chl_line_end: int
    todev_draw_border: int
    todev_draw_border_end: int
    todev_draw_obs: int
    todev_draw_obs_end: int
    todev_edgecmd: int
    todev_get_commondata: NavGetCommData
    todev_gethash: NavGetHashList
    todev_lat_up_ack: int
    todev_mow_task: NavStartJob
    todev_one_touch_leave_pile: int
    todev_opt_border_info_ack: NavResFrame
    todev_opt_line_up_ack: NavResFrame
    todev_opt_obs_info_ack: NavResFrame
    todev_planjob_set: NavPlanJobSet
    todev_rechgcmd: int
    todev_reset_chg_pile: int
    todev_save_task: int
    todev_sustask: int
    todev_svg_msg: SvgMessageAckT
    todev_task_info_ack: NavResFrame
    todev_taskctrl: NavTaskCtrl
    todev_taskctrl_ack: NavTaskCtrlAck
    todev_unable_time_set: NavUnableTimeSet
    todev_work_report_cmd: WorkReportCmdData
    todev_work_report_update_cmd: WorkReportUpdateCmd
    todev_zigzag_ack: NavUploadZigZagResultAck
    vision_ctrl: vision_ctrl_msg
    zone_start_precent: zone_start_precent_t
    def __init__(self, toapp_lat_up: _Optional[_Union[NavLatLonUp, _Mapping]] = ..., toapp_pos_up: _Optional[_Union[NavPosUp, _Mapping]] = ..., todev_chl_line_data: _Optional[_Union[NavCHlLineData, _Mapping]] = ..., toapp_task_info: _Optional[_Union[NavTaskInfo, _Mapping]] = ..., toapp_opt_line_up: _Optional[_Union[NavOptLineUp, _Mapping]] = ..., toapp_opt_border_info: _Optional[_Union[NavOptiBorderInfo, _Mapping]] = ..., toapp_opt_obs_info: _Optional[_Union[NavOptObsInfo, _Mapping]] = ..., todev_task_info_ack: _Optional[_Union[NavResFrame, _Mapping]] = ..., todev_opt_border_info_ack: _Optional[_Union[NavResFrame, _Mapping]] = ..., todev_opt_obs_info_ack: _Optional[_Union[NavResFrame, _Mapping]] = ..., todev_opt_line_up_ack: _Optional[_Union[NavResFrame, _Mapping]] = ..., toapp_chgpileto: _Optional[_Union[chargePileType, _Mapping]] = ..., todev_sustask: _Optional[int] = ..., todev_rechgcmd: _Optional[int] = ..., todev_edgecmd: _Optional[int] = ..., todev_draw_border: _Optional[int] = ..., todev_draw_border_end: _Optional[int] = ..., todev_draw_obs: _Optional[int] = ..., todev_draw_obs_end: _Optional[int] = ..., todev_chl_line: _Optional[int] = ..., todev_chl_line_end: _Optional[int] = ..., todev_save_task: _Optional[int] = ..., todev_cancel_suscmd: _Optional[int] = ..., todev_reset_chg_pile: _Optional[int] = ..., todev_cancel_draw_cmd: _Optional[int] = ..., todev_one_touch_leave_pile: _Optional[int] = ..., todev_mow_task: _Optional[_Union[NavStartJob, _Mapping]] = ..., toapp_bstate: _Optional[_Union[NavBorderState, _Mapping]] = ..., todev_lat_up_ack: _Optional[int] = ..., todev_gethash: _Optional[_Union[NavGetHashList, _Mapping]] = ..., toapp_gethash_ack: _Optional[_Union[NavGetHashListAck, _Mapping]] = ..., todev_get_commondata: _Optional[_Union[NavGetCommData, _Mapping]] = ..., toapp_get_commondata_ack: _Optional[_Union[NavGetCommDataAck, _Mapping]] = ..., bidire_reqconver_path: _Optional[_Union[NavReqCoverPath, _Mapping]] = ..., toapp_zigzag: _Optional[_Union[NavUploadZigZagResult, _Mapping]] = ..., todev_zigzag_ack: _Optional[_Union[NavUploadZigZagResultAck, _Mapping]] = ..., todev_taskctrl: _Optional[_Union[NavTaskCtrl, _Mapping]] = ..., bidire_taskid: _Optional[_Union[NavTaskIdRw, _Mapping]] = ..., toapp_bp: _Optional[_Union[NavTaskBreakPoint, _Mapping]] = ..., todev_planjob_set: _Optional[_Union[NavPlanJobSet, _Mapping]] = ..., todev_unable_time_set: _Optional[_Union[NavUnableTimeSet, _Mapping]] = ..., simulation_cmd: _Optional[_Union[SimulationCmdData, _Mapping]] = ..., todev_work_report_update_cmd: _Optional[_Union[WorkReportUpdateCmd, _Mapping]] = ..., toapp_work_report_update_ack: _Optional[_Union[WorkReportUpdateAck, _Mapping]] = ..., todev_work_report_cmd: _Optional[_Union[WorkReportCmdData, _Mapping]] = ..., toapp_work_report_ack: _Optional[_Union[WorkReportInfoAck, _Mapping]] = ..., toapp_work_report_upload: _Optional[_Union[WorkReportInfoAck, _Mapping]] = ..., app_request_cover_paths: _Optional[_Union[app_request_cover_paths_t, _Mapping]] = ..., cover_path_upload: _Optional[_Union[cover_path_upload_t, _Mapping]] = ..., zone_start_precent: _Optional[_Union[zone_start_precent_t, _Mapping]] = ..., vision_ctrl: _Optional[_Union[vision_ctrl_msg, _Mapping]] = ..., nav_sys_param_cmd: _Optional[_Union[nav_sys_param_msg, _Mapping]] = ..., plan_task_execute: _Optional[_Union[nav_plan_task_execute, _Mapping]] = ..., toapp_costmap: _Optional[_Union[costmap_t, _Mapping]] = ..., plan_task_name_id: _Optional[_Union[plan_task_name_id_t, _Mapping]] = ..., all_plan_task: _Optional[_Union[nav_get_all_plan_task, _Mapping]] = ..., todev_taskctrl_ack: _Optional[_Union[NavTaskCtrlAck, _Mapping]] = ..., toapp_map_name_msg: _Optional[_Union[NavMapNameMsg, _Mapping]] = ..., todev_svg_msg: _Optional[_Union[SvgMessageAckT, _Mapping]] = ..., toapp_svg_msg: _Optional[_Union[SvgMessageAckT, _Mapping]] = ..., toapp_all_hash_name: _Optional[_Union[AppGetAllAreaHashName, _Mapping]] = ...) -> None: ...

class NavBorderDataGet(_message.Message):
    __slots__ = ["borderLen", "currentFrame", "jobId"]
    BORDERLEN_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    JOBID_FIELD_NUMBER: _ClassVar[int]
    borderLen: int
    currentFrame: int
    jobId: int
    def __init__(self, jobId: _Optional[int] = ..., currentFrame: _Optional[int] = ..., borderLen: _Optional[int] = ...) -> None: ...

class NavBorderDataGetAck(_message.Message):
    __slots__ = ["currentFrame", "jobId"]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    JOBID_FIELD_NUMBER: _ClassVar[int]
    currentFrame: int
    jobId: int
    def __init__(self, jobId: _Optional[int] = ..., currentFrame: _Optional[int] = ...) -> None: ...

class NavBorderState(_message.Message):
    __slots__ = ["bdstate"]
    BDSTATE_FIELD_NUMBER: _ClassVar[int]
    bdstate: int
    def __init__(self, bdstate: _Optional[int] = ...) -> None: ...

class NavCHlLineData(_message.Message):
    __slots__ = ["channelLineLen", "currentFrame", "endJobRI", "startJobRI"]
    CHANNELLINELEN_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    ENDJOBRI_FIELD_NUMBER: _ClassVar[int]
    STARTJOBRI_FIELD_NUMBER: _ClassVar[int]
    channelLineLen: int
    currentFrame: int
    endJobRI: int
    startJobRI: int
    def __init__(self, startJobRI: _Optional[int] = ..., endJobRI: _Optional[int] = ..., currentFrame: _Optional[int] = ..., channelLineLen: _Optional[int] = ...) -> None: ...

class NavCHlLineDataAck(_message.Message):
    __slots__ = ["currentFrame", "endJobRI", "startJobRI"]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    ENDJOBRI_FIELD_NUMBER: _ClassVar[int]
    STARTJOBRI_FIELD_NUMBER: _ClassVar[int]
    currentFrame: int
    endJobRI: int
    startJobRI: int
    def __init__(self, startJobRI: _Optional[int] = ..., endJobRI: _Optional[int] = ..., currentFrame: _Optional[int] = ...) -> None: ...

class NavGetCommData(_message.Message):
    __slots__ = ["action", "currentFrame", "dataHash", "hash", "paternalHashA", "paternalHashB", "pver", "reserved", "subCmd", "totalFrame", "type"]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    PATERNALHASHA_FIELD_NUMBER: _ClassVar[int]
    PATERNALHASHB_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TOTALFRAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    action: int
    currentFrame: int
    dataHash: int
    hash: int
    paternalHashA: int
    paternalHashB: int
    pver: int
    reserved: str
    subCmd: int
    totalFrame: int
    type: int
    def __init__(self, pver: _Optional[int] = ..., subCmd: _Optional[int] = ..., action: _Optional[int] = ..., type: _Optional[int] = ..., hash: _Optional[int] = ..., paternalHashA: _Optional[int] = ..., paternalHashB: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., dataHash: _Optional[int] = ..., reserved: _Optional[str] = ...) -> None: ...

class NavGetCommDataAck(_message.Message):
    __slots__ = ["Hash", "action", "areaLabel", "currentFrame", "dataCouple", "dataHash", "dataLen", "paternalHashA", "paternalHashB", "pver", "reserved", "result", "subCmd", "totalFrame", "type"]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    AREALABEL_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DATACOUPLE_FIELD_NUMBER: _ClassVar[int]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    DATALEN_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    Hash: int
    PATERNALHASHA_FIELD_NUMBER: _ClassVar[int]
    PATERNALHASHB_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TOTALFRAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    action: int
    areaLabel: AreaLabel
    currentFrame: int
    dataCouple: _containers.RepeatedCompositeFieldContainer[_common_pb2.CommDataCouple]
    dataHash: int
    dataLen: int
    paternalHashA: int
    paternalHashB: int
    pver: int
    reserved: str
    result: int
    subCmd: int
    totalFrame: int
    type: int
    def __init__(self, pver: _Optional[int] = ..., subCmd: _Optional[int] = ..., result: _Optional[int] = ..., action: _Optional[int] = ..., type: _Optional[int] = ..., Hash: _Optional[int] = ..., paternalHashA: _Optional[int] = ..., paternalHashB: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., dataHash: _Optional[int] = ..., dataLen: _Optional[int] = ..., dataCouple: _Optional[_Iterable[_Union[_common_pb2.CommDataCouple, _Mapping]]] = ..., reserved: _Optional[str] = ..., areaLabel: _Optional[_Union[AreaLabel, _Mapping]] = ...) -> None: ...

class NavGetHashList(_message.Message):
    __slots__ = ["currentFrame", "dataHash", "pver", "reserved", "subCmd", "totalFrame"]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TOTALFRAME_FIELD_NUMBER: _ClassVar[int]
    currentFrame: int
    dataHash: int
    pver: int
    reserved: str
    subCmd: int
    totalFrame: int
    def __init__(self, pver: _Optional[int] = ..., subCmd: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., dataHash: _Optional[int] = ..., reserved: _Optional[str] = ...) -> None: ...

class NavGetHashListAck(_message.Message):
    __slots__ = ["currentFrame", "dataCouple", "dataHash", "hashLen", "pver", "reserved", "result", "subCmd", "totalFrame"]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DATACOUPLE_FIELD_NUMBER: _ClassVar[int]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    HASHLEN_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TOTALFRAME_FIELD_NUMBER: _ClassVar[int]
    currentFrame: int
    dataCouple: _containers.RepeatedScalarFieldContainer[int]
    dataHash: int
    hashLen: int
    pver: int
    reserved: str
    result: int
    subCmd: int
    totalFrame: int
    def __init__(self, pver: _Optional[int] = ..., subCmd: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., dataHash: _Optional[int] = ..., hashLen: _Optional[int] = ..., reserved: _Optional[str] = ..., result: _Optional[int] = ..., dataCouple: _Optional[_Iterable[int]] = ...) -> None: ...

class NavLatLonUp(_message.Message):
    __slots__ = ["lat", "lon"]
    LAT_FIELD_NUMBER: _ClassVar[int]
    LON_FIELD_NUMBER: _ClassVar[int]
    lat: float
    lon: float
    def __init__(self, lat: _Optional[float] = ..., lon: _Optional[float] = ...) -> None: ...

class NavMapNameMsg(_message.Message):
    __slots__ = ["device_id", "hash", "name", "result", "rw"]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    RW_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    hash: int
    name: str
    result: int
    rw: int
    def __init__(self, rw: _Optional[int] = ..., hash: _Optional[int] = ..., name: _Optional[str] = ..., result: _Optional[int] = ..., device_id: _Optional[str] = ...) -> None: ...

class NavObstiBorderDataGet(_message.Message):
    __slots__ = ["currentFrame", "obstacleIndex", "obstaclesLen"]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    OBSTACLEINDEX_FIELD_NUMBER: _ClassVar[int]
    OBSTACLESLEN_FIELD_NUMBER: _ClassVar[int]
    currentFrame: int
    obstacleIndex: int
    obstaclesLen: int
    def __init__(self, obstacleIndex: _Optional[int] = ..., currentFrame: _Optional[int] = ..., obstaclesLen: _Optional[int] = ...) -> None: ...

class NavObstiBorderDataGetAck(_message.Message):
    __slots__ = ["currentFrame", "obstacleIndex"]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    OBSTACLEINDEX_FIELD_NUMBER: _ClassVar[int]
    currentFrame: int
    obstacleIndex: int
    def __init__(self, obstacleIndex: _Optional[int] = ..., currentFrame: _Optional[int] = ...) -> None: ...

class NavOptLineUp(_message.Message):
    __slots__ = ["allFrame", "channelDataLen", "currentFrame", "dc", "endJobRI", "startJobRI"]
    ALLFRAME_FIELD_NUMBER: _ClassVar[int]
    CHANNELDATALEN_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DC_FIELD_NUMBER: _ClassVar[int]
    ENDJOBRI_FIELD_NUMBER: _ClassVar[int]
    STARTJOBRI_FIELD_NUMBER: _ClassVar[int]
    allFrame: int
    channelDataLen: int
    currentFrame: int
    dc: _containers.RepeatedCompositeFieldContainer[_common_pb2.CommDataCouple]
    endJobRI: int
    startJobRI: int
    def __init__(self, startJobRI: _Optional[int] = ..., endJobRI: _Optional[int] = ..., allFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., channelDataLen: _Optional[int] = ..., dc: _Optional[_Iterable[_Union[_common_pb2.CommDataCouple, _Mapping]]] = ...) -> None: ...

class NavOptObsInfo(_message.Message):
    __slots__ = ["allFrame", "currentFrame", "dc", "obstacleDataLen", "obstacleId"]
    ALLFRAME_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DC_FIELD_NUMBER: _ClassVar[int]
    OBSTACLEDATALEN_FIELD_NUMBER: _ClassVar[int]
    OBSTACLEID_FIELD_NUMBER: _ClassVar[int]
    allFrame: int
    currentFrame: int
    dc: _containers.RepeatedCompositeFieldContainer[_common_pb2.CommDataCouple]
    obstacleDataLen: int
    obstacleId: int
    def __init__(self, obstacleId: _Optional[int] = ..., allFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., obstacleDataLen: _Optional[int] = ..., dc: _Optional[_Iterable[_Union[_common_pb2.CommDataCouple, _Mapping]]] = ...) -> None: ...

class NavOptiBorderInfo(_message.Message):
    __slots__ = ["allFrame", "borderDataLen", "currentFrame", "dc", "jobId"]
    ALLFRAME_FIELD_NUMBER: _ClassVar[int]
    BORDERDATALEN_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DC_FIELD_NUMBER: _ClassVar[int]
    JOBID_FIELD_NUMBER: _ClassVar[int]
    allFrame: int
    borderDataLen: int
    currentFrame: int
    dc: _containers.RepeatedCompositeFieldContainer[_common_pb2.CommDataCouple]
    jobId: int
    def __init__(self, jobId: _Optional[int] = ..., allFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., borderDataLen: _Optional[int] = ..., dc: _Optional[_Iterable[_Union[_common_pb2.CommDataCouple, _Mapping]]] = ...) -> None: ...

class NavPlanJobSet(_message.Message):
    __slots__ = ["PlanIndex", "area", "day", "deviceId", "edgeMode", "endDate", "endTime", "id", "jobId", "jobName", "knifeHeight", "model", "planId", "pver", "remained_seconds", "requiredTime", "reserved", "result", "routeAngle", "routeModel", "routeSpacing", "speed", "startDate", "startTime", "subCmd", "taskId", "taskName", "totalPlanNum", "towardIncludedAngle", "towardMode", "triggerType", "ultrasonicBarrier", "userId", "version", "week", "weeks", "workTime", "zoneHashs"]
    AREA_FIELD_NUMBER: _ClassVar[int]
    DAY_FIELD_NUMBER: _ClassVar[int]
    DEVICEID_FIELD_NUMBER: _ClassVar[int]
    EDGEMODE_FIELD_NUMBER: _ClassVar[int]
    ENDDATE_FIELD_NUMBER: _ClassVar[int]
    ENDTIME_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    JOBID_FIELD_NUMBER: _ClassVar[int]
    JOBNAME_FIELD_NUMBER: _ClassVar[int]
    KNIFEHEIGHT_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    PLANID_FIELD_NUMBER: _ClassVar[int]
    PLANINDEX_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    PlanIndex: int
    REMAINED_SECONDS_FIELD_NUMBER: _ClassVar[int]
    REQUIREDTIME_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ROUTEANGLE_FIELD_NUMBER: _ClassVar[int]
    ROUTEMODEL_FIELD_NUMBER: _ClassVar[int]
    ROUTESPACING_FIELD_NUMBER: _ClassVar[int]
    SPEED_FIELD_NUMBER: _ClassVar[int]
    STARTDATE_FIELD_NUMBER: _ClassVar[int]
    STARTTIME_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TASKID_FIELD_NUMBER: _ClassVar[int]
    TASKNAME_FIELD_NUMBER: _ClassVar[int]
    TOTALPLANNUM_FIELD_NUMBER: _ClassVar[int]
    TOWARDINCLUDEDANGLE_FIELD_NUMBER: _ClassVar[int]
    TOWARDMODE_FIELD_NUMBER: _ClassVar[int]
    TRIGGERTYPE_FIELD_NUMBER: _ClassVar[int]
    ULTRASONICBARRIER_FIELD_NUMBER: _ClassVar[int]
    USERID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    WEEKS_FIELD_NUMBER: _ClassVar[int]
    WEEK_FIELD_NUMBER: _ClassVar[int]
    WORKTIME_FIELD_NUMBER: _ClassVar[int]
    ZONEHASHS_FIELD_NUMBER: _ClassVar[int]
    area: int
    day: int
    deviceId: str
    edgeMode: int
    endDate: str
    endTime: str
    id: str
    jobId: str
    jobName: str
    knifeHeight: int
    model: int
    planId: str
    pver: int
    remained_seconds: int
    requiredTime: int
    reserved: str
    result: int
    routeAngle: int
    routeModel: int
    routeSpacing: int
    speed: float
    startDate: str
    startTime: str
    subCmd: int
    taskId: str
    taskName: str
    totalPlanNum: int
    towardIncludedAngle: int
    towardMode: int
    triggerType: int
    ultrasonicBarrier: int
    userId: str
    version: str
    week: int
    weeks: _containers.RepeatedScalarFieldContainer[int]
    workTime: int
    zoneHashs: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, pver: _Optional[int] = ..., subCmd: _Optional[int] = ..., area: _Optional[int] = ..., workTime: _Optional[int] = ..., version: _Optional[str] = ..., id: _Optional[str] = ..., userId: _Optional[str] = ..., deviceId: _Optional[str] = ..., planId: _Optional[str] = ..., taskId: _Optional[str] = ..., jobId: _Optional[str] = ..., startTime: _Optional[str] = ..., endTime: _Optional[str] = ..., week: _Optional[int] = ..., knifeHeight: _Optional[int] = ..., model: _Optional[int] = ..., edgeMode: _Optional[int] = ..., requiredTime: _Optional[int] = ..., routeAngle: _Optional[int] = ..., routeModel: _Optional[int] = ..., routeSpacing: _Optional[int] = ..., ultrasonicBarrier: _Optional[int] = ..., totalPlanNum: _Optional[int] = ..., PlanIndex: _Optional[int] = ..., result: _Optional[int] = ..., speed: _Optional[float] = ..., taskName: _Optional[str] = ..., jobName: _Optional[str] = ..., zoneHashs: _Optional[_Iterable[int]] = ..., reserved: _Optional[str] = ..., startDate: _Optional[str] = ..., endDate: _Optional[str] = ..., triggerType: _Optional[int] = ..., day: _Optional[int] = ..., weeks: _Optional[_Iterable[int]] = ..., remained_seconds: _Optional[int] = ..., towardMode: _Optional[int] = ..., towardIncludedAngle: _Optional[int] = ...) -> None: ...

class NavPosUp(_message.Message):
    __slots__ = ["age", "cHashId", "l2dfStars", "latStddev", "lonStddev", "posLevel", "posType", "stars", "status", "toward", "x", "y"]
    AGE_FIELD_NUMBER: _ClassVar[int]
    CHASHID_FIELD_NUMBER: _ClassVar[int]
    L2DFSTARS_FIELD_NUMBER: _ClassVar[int]
    LATSTDDEV_FIELD_NUMBER: _ClassVar[int]
    LONSTDDEV_FIELD_NUMBER: _ClassVar[int]
    POSLEVEL_FIELD_NUMBER: _ClassVar[int]
    POSTYPE_FIELD_NUMBER: _ClassVar[int]
    STARS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    TOWARD_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    age: float
    cHashId: int
    l2dfStars: int
    latStddev: float
    lonStddev: float
    posLevel: int
    posType: int
    stars: int
    status: int
    toward: int
    x: float
    y: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., status: _Optional[int] = ..., toward: _Optional[int] = ..., stars: _Optional[int] = ..., age: _Optional[float] = ..., latStddev: _Optional[float] = ..., lonStddev: _Optional[float] = ..., l2dfStars: _Optional[int] = ..., posType: _Optional[int] = ..., cHashId: _Optional[int] = ..., posLevel: _Optional[int] = ...) -> None: ...

class NavReqCoverPath(_message.Message):
    __slots__ = ["UltraWave", "channelMode", "channelWidth", "edgeMode", "jobId", "jobMode", "jobVer", "knifeHeight", "pathHash", "pver", "reserved", "result", "speed", "subCmd", "toward", "toward_included_angle", "toward_mode", "zoneHashs"]
    CHANNELMODE_FIELD_NUMBER: _ClassVar[int]
    CHANNELWIDTH_FIELD_NUMBER: _ClassVar[int]
    EDGEMODE_FIELD_NUMBER: _ClassVar[int]
    JOBID_FIELD_NUMBER: _ClassVar[int]
    JOBMODE_FIELD_NUMBER: _ClassVar[int]
    JOBVER_FIELD_NUMBER: _ClassVar[int]
    KNIFEHEIGHT_FIELD_NUMBER: _ClassVar[int]
    PATHHASH_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SPEED_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TOWARD_FIELD_NUMBER: _ClassVar[int]
    TOWARD_INCLUDED_ANGLE_FIELD_NUMBER: _ClassVar[int]
    TOWARD_MODE_FIELD_NUMBER: _ClassVar[int]
    ULTRAWAVE_FIELD_NUMBER: _ClassVar[int]
    UltraWave: int
    ZONEHASHS_FIELD_NUMBER: _ClassVar[int]
    channelMode: int
    channelWidth: int
    edgeMode: int
    jobId: int
    jobMode: int
    jobVer: int
    knifeHeight: int
    pathHash: int
    pver: int
    reserved: str
    result: int
    speed: float
    subCmd: int
    toward: int
    toward_included_angle: int
    toward_mode: int
    zoneHashs: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, pver: _Optional[int] = ..., jobId: _Optional[int] = ..., jobVer: _Optional[int] = ..., jobMode: _Optional[int] = ..., subCmd: _Optional[int] = ..., edgeMode: _Optional[int] = ..., knifeHeight: _Optional[int] = ..., channelWidth: _Optional[int] = ..., UltraWave: _Optional[int] = ..., channelMode: _Optional[int] = ..., toward: _Optional[int] = ..., speed: _Optional[float] = ..., zoneHashs: _Optional[_Iterable[int]] = ..., pathHash: _Optional[int] = ..., reserved: _Optional[str] = ..., result: _Optional[int] = ..., toward_mode: _Optional[int] = ..., toward_included_angle: _Optional[int] = ...) -> None: ...

class NavResFrame(_message.Message):
    __slots__ = ["frameid"]
    FRAMEID_FIELD_NUMBER: _ClassVar[int]
    frameid: int
    def __init__(self, frameid: _Optional[int] = ...) -> None: ...

class NavStartJob(_message.Message):
    __slots__ = ["UltraWave", "channelMode", "channelWidth", "jobId", "jobMode", "jobVer", "knifeHeight", "rainTactics", "speed"]
    CHANNELMODE_FIELD_NUMBER: _ClassVar[int]
    CHANNELWIDTH_FIELD_NUMBER: _ClassVar[int]
    JOBID_FIELD_NUMBER: _ClassVar[int]
    JOBMODE_FIELD_NUMBER: _ClassVar[int]
    JOBVER_FIELD_NUMBER: _ClassVar[int]
    KNIFEHEIGHT_FIELD_NUMBER: _ClassVar[int]
    RAINTACTICS_FIELD_NUMBER: _ClassVar[int]
    SPEED_FIELD_NUMBER: _ClassVar[int]
    ULTRAWAVE_FIELD_NUMBER: _ClassVar[int]
    UltraWave: int
    channelMode: int
    channelWidth: int
    jobId: int
    jobMode: int
    jobVer: int
    knifeHeight: int
    rainTactics: int
    speed: float
    def __init__(self, jobId: _Optional[int] = ..., jobVer: _Optional[int] = ..., jobMode: _Optional[int] = ..., rainTactics: _Optional[int] = ..., knifeHeight: _Optional[int] = ..., speed: _Optional[float] = ..., channelWidth: _Optional[int] = ..., UltraWave: _Optional[int] = ..., channelMode: _Optional[int] = ...) -> None: ...

class NavSysHashOverview(_message.Message):
    __slots__ = ["commonhashOverview", "pathHashOverview"]
    COMMONHASHOVERVIEW_FIELD_NUMBER: _ClassVar[int]
    PATHHASHOVERVIEW_FIELD_NUMBER: _ClassVar[int]
    commonhashOverview: int
    pathHashOverview: int
    def __init__(self, commonhashOverview: _Optional[int] = ..., pathHashOverview: _Optional[int] = ...) -> None: ...

class NavTaskBreakPoint(_message.Message):
    __slots__ = ["action", "flag", "toward", "x", "y", "zoneHash"]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    FLAG_FIELD_NUMBER: _ClassVar[int]
    TOWARD_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    ZONEHASH_FIELD_NUMBER: _ClassVar[int]
    action: int
    flag: int
    toward: int
    x: float
    y: float
    zoneHash: int
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., toward: _Optional[int] = ..., flag: _Optional[int] = ..., action: _Optional[int] = ..., zoneHash: _Optional[int] = ...) -> None: ...

class NavTaskCtrl(_message.Message):
    __slots__ = ["action", "reserved", "result", "type"]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    action: int
    reserved: str
    result: int
    type: int
    def __init__(self, type: _Optional[int] = ..., action: _Optional[int] = ..., result: _Optional[int] = ..., reserved: _Optional[str] = ...) -> None: ...

class NavTaskCtrlAck(_message.Message):
    __slots__ = ["action", "nav_state", "reserved", "result", "type"]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    NAV_STATE_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    action: int
    nav_state: int
    reserved: str
    result: int
    type: int
    def __init__(self, type: _Optional[int] = ..., action: _Optional[int] = ..., result: _Optional[int] = ..., nav_state: _Optional[int] = ..., reserved: _Optional[str] = ...) -> None: ...

class NavTaskIdRw(_message.Message):
    __slots__ = ["pver", "reserved", "result", "subCmd", "taskId", "taskName"]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TASKID_FIELD_NUMBER: _ClassVar[int]
    TASKNAME_FIELD_NUMBER: _ClassVar[int]
    pver: int
    reserved: str
    result: int
    subCmd: int
    taskId: str
    taskName: str
    def __init__(self, pver: _Optional[int] = ..., subCmd: _Optional[int] = ..., taskName: _Optional[str] = ..., taskId: _Optional[str] = ..., result: _Optional[int] = ..., reserved: _Optional[str] = ...) -> None: ...

class NavTaskInfo(_message.Message):
    __slots__ = ["allFrame", "area", "currentFrame", "dc", "pathlen", "time"]
    ALLFRAME_FIELD_NUMBER: _ClassVar[int]
    AREA_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DC_FIELD_NUMBER: _ClassVar[int]
    PATHLEN_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    allFrame: int
    area: int
    currentFrame: int
    dc: _containers.RepeatedCompositeFieldContainer[_common_pb2.CommDataCouple]
    pathlen: int
    time: int
    def __init__(self, area: _Optional[int] = ..., time: _Optional[int] = ..., allFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., pathlen: _Optional[int] = ..., dc: _Optional[_Iterable[_Union[_common_pb2.CommDataCouple, _Mapping]]] = ...) -> None: ...

class NavTaskProgress(_message.Message):
    __slots__ = ["taskProgress"]
    TASKPROGRESS_FIELD_NUMBER: _ClassVar[int]
    taskProgress: int
    def __init__(self, taskProgress: _Optional[int] = ...) -> None: ...

class NavUnableTimeSet(_message.Message):
    __slots__ = ["deviceId", "reserved", "result", "subCmd", "unableEndTime", "unableStartTime"]
    DEVICEID_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    UNABLEENDTIME_FIELD_NUMBER: _ClassVar[int]
    UNABLESTARTTIME_FIELD_NUMBER: _ClassVar[int]
    deviceId: str
    reserved: str
    result: int
    subCmd: int
    unableEndTime: str
    unableStartTime: str
    def __init__(self, subCmd: _Optional[int] = ..., deviceId: _Optional[str] = ..., unableStartTime: _Optional[str] = ..., unableEndTime: _Optional[str] = ..., result: _Optional[int] = ..., reserved: _Optional[str] = ...) -> None: ...

class NavUploadZigZagResult(_message.Message):
    __slots__ = ["area", "channelMode", "channelModeId", "currentFrame", "currentHash", "currentZone", "currentZonePathId", "currentZonePathNum", "dataCouple", "dataHash", "dataLen", "jobId", "jobVer", "pver", "reserved", "result", "subCmd", "time", "totalFrame", "totalZoneNum"]
    AREA_FIELD_NUMBER: _ClassVar[int]
    CHANNELMODEID_FIELD_NUMBER: _ClassVar[int]
    CHANNELMODE_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    CURRENTHASH_FIELD_NUMBER: _ClassVar[int]
    CURRENTZONEPATHID_FIELD_NUMBER: _ClassVar[int]
    CURRENTZONEPATHNUM_FIELD_NUMBER: _ClassVar[int]
    CURRENTZONE_FIELD_NUMBER: _ClassVar[int]
    DATACOUPLE_FIELD_NUMBER: _ClassVar[int]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    DATALEN_FIELD_NUMBER: _ClassVar[int]
    JOBID_FIELD_NUMBER: _ClassVar[int]
    JOBVER_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    TOTALFRAME_FIELD_NUMBER: _ClassVar[int]
    TOTALZONENUM_FIELD_NUMBER: _ClassVar[int]
    area: int
    channelMode: int
    channelModeId: int
    currentFrame: int
    currentHash: int
    currentZone: int
    currentZonePathId: int
    currentZonePathNum: int
    dataCouple: _containers.RepeatedCompositeFieldContainer[_common_pb2.CommDataCouple]
    dataHash: int
    dataLen: int
    jobId: int
    jobVer: int
    pver: int
    reserved: str
    result: int
    subCmd: int
    time: int
    totalFrame: int
    totalZoneNum: int
    def __init__(self, pver: _Optional[int] = ..., jobId: _Optional[int] = ..., jobVer: _Optional[int] = ..., result: _Optional[int] = ..., area: _Optional[int] = ..., time: _Optional[int] = ..., totalZoneNum: _Optional[int] = ..., currentZonePathNum: _Optional[int] = ..., currentZonePathId: _Optional[int] = ..., currentZone: _Optional[int] = ..., currentHash: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., channelMode: _Optional[int] = ..., channelModeId: _Optional[int] = ..., dataHash: _Optional[int] = ..., dataLen: _Optional[int] = ..., reserved: _Optional[str] = ..., dataCouple: _Optional[_Iterable[_Union[_common_pb2.CommDataCouple, _Mapping]]] = ..., subCmd: _Optional[int] = ...) -> None: ...

class NavUploadZigZagResultAck(_message.Message):
    __slots__ = ["currentFrame", "currentHash", "currentZone", "dataHash", "pver", "reserved", "subCmd", "totalFrame"]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    CURRENTHASH_FIELD_NUMBER: _ClassVar[int]
    CURRENTZONE_FIELD_NUMBER: _ClassVar[int]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TOTALFRAME_FIELD_NUMBER: _ClassVar[int]
    currentFrame: int
    currentHash: int
    currentZone: int
    dataHash: int
    pver: int
    reserved: str
    subCmd: int
    totalFrame: int
    def __init__(self, pver: _Optional[int] = ..., currentZone: _Optional[int] = ..., currentHash: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., dataHash: _Optional[int] = ..., reserved: _Optional[str] = ..., subCmd: _Optional[int] = ...) -> None: ...

class SimulationCmdData(_message.Message):
    __slots__ = ["param_id", "param_value", "subCmd"]
    PARAM_ID_FIELD_NUMBER: _ClassVar[int]
    PARAM_VALUE_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    param_id: int
    param_value: _containers.RepeatedScalarFieldContainer[int]
    subCmd: int
    def __init__(self, subCmd: _Optional[int] = ..., param_id: _Optional[int] = ..., param_value: _Optional[_Iterable[int]] = ...) -> None: ...

class SvgMessageAckT(_message.Message):
    __slots__ = ["current_frame", "data_hash", "paternal_hash_a", "pver", "result", "sub_cmd", "svg_message", "total_frame", "type"]
    CURRENT_FRAME_FIELD_NUMBER: _ClassVar[int]
    DATA_HASH_FIELD_NUMBER: _ClassVar[int]
    PATERNAL_HASH_A_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SUB_CMD_FIELD_NUMBER: _ClassVar[int]
    SVG_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FRAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    current_frame: int
    data_hash: int
    paternal_hash_a: int
    pver: int
    result: int
    sub_cmd: int
    svg_message: svg_message_t
    total_frame: int
    type: int
    def __init__(self, pver: _Optional[int] = ..., sub_cmd: _Optional[int] = ..., total_frame: _Optional[int] = ..., current_frame: _Optional[int] = ..., data_hash: _Optional[int] = ..., paternal_hash_a: _Optional[int] = ..., type: _Optional[int] = ..., result: _Optional[int] = ..., svg_message: _Optional[_Union[svg_message_t, _Mapping]] = ...) -> None: ...

class WorkReportCmdData(_message.Message):
    __slots__ = ["getInfoNum", "subCmd"]
    GETINFONUM_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    getInfoNum: int
    subCmd: int
    def __init__(self, subCmd: _Optional[int] = ..., getInfoNum: _Optional[int] = ...) -> None: ...

class WorkReportInfoAck(_message.Message):
    __slots__ = ["current_ack_num", "end_work_time", "height_of_knife", "interrupt_flag", "start_work_time", "total_ack_num", "work_ares", "work_progress", "work_result", "work_time_used", "work_type"]
    CURRENT_ACK_NUM_FIELD_NUMBER: _ClassVar[int]
    END_WORK_TIME_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_OF_KNIFE_FIELD_NUMBER: _ClassVar[int]
    INTERRUPT_FLAG_FIELD_NUMBER: _ClassVar[int]
    START_WORK_TIME_FIELD_NUMBER: _ClassVar[int]
    TOTAL_ACK_NUM_FIELD_NUMBER: _ClassVar[int]
    WORK_ARES_FIELD_NUMBER: _ClassVar[int]
    WORK_PROGRESS_FIELD_NUMBER: _ClassVar[int]
    WORK_RESULT_FIELD_NUMBER: _ClassVar[int]
    WORK_TIME_USED_FIELD_NUMBER: _ClassVar[int]
    WORK_TYPE_FIELD_NUMBER: _ClassVar[int]
    current_ack_num: int
    end_work_time: int
    height_of_knife: int
    interrupt_flag: bool
    start_work_time: int
    total_ack_num: int
    work_ares: float
    work_progress: int
    work_result: int
    work_time_used: int
    work_type: int
    def __init__(self, interrupt_flag: bool = ..., start_work_time: _Optional[int] = ..., end_work_time: _Optional[int] = ..., work_time_used: _Optional[int] = ..., work_ares: _Optional[float] = ..., work_progress: _Optional[int] = ..., height_of_knife: _Optional[int] = ..., work_type: _Optional[int] = ..., work_result: _Optional[int] = ..., total_ack_num: _Optional[int] = ..., current_ack_num: _Optional[int] = ...) -> None: ...

class WorkReportUpdateAck(_message.Message):
    __slots__ = ["info_num", "update_flag"]
    INFO_NUM_FIELD_NUMBER: _ClassVar[int]
    UPDATE_FLAG_FIELD_NUMBER: _ClassVar[int]
    info_num: int
    update_flag: bool
    def __init__(self, update_flag: bool = ..., info_num: _Optional[int] = ...) -> None: ...

class WorkReportUpdateCmd(_message.Message):
    __slots__ = ["subCmd"]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    subCmd: int
    def __init__(self, subCmd: _Optional[int] = ...) -> None: ...

class app_request_cover_paths_t(_message.Message):
    __slots__ = ["currentFrame", "dataHash", "hash_list", "pver", "reserved", "subCmd", "totalFrame", "transaction_id"]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    HASH_LIST_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TOTALFRAME_FIELD_NUMBER: _ClassVar[int]
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    currentFrame: int
    dataHash: int
    hash_list: _containers.RepeatedScalarFieldContainer[int]
    pver: int
    reserved: _containers.RepeatedScalarFieldContainer[int]
    subCmd: int
    totalFrame: int
    transaction_id: int
    def __init__(self, pver: _Optional[int] = ..., subCmd: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., dataHash: _Optional[int] = ..., transaction_id: _Optional[int] = ..., reserved: _Optional[_Iterable[int]] = ..., hash_list: _Optional[_Iterable[int]] = ...) -> None: ...

class chargePileType(_message.Message):
    __slots__ = ["toward", "x", "y"]
    TOWARD_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    toward: int
    x: float
    y: float
    def __init__(self, toward: _Optional[int] = ..., x: _Optional[float] = ..., y: _Optional[float] = ...) -> None: ...

class costmap_t(_message.Message):
    __slots__ = ["center_x", "center_y", "costmap", "height", "res", "width", "yaw"]
    CENTER_X_FIELD_NUMBER: _ClassVar[int]
    CENTER_Y_FIELD_NUMBER: _ClassVar[int]
    COSTMAP_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    RES_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    YAW_FIELD_NUMBER: _ClassVar[int]
    center_x: float
    center_y: float
    costmap: _containers.RepeatedScalarFieldContainer[int]
    height: int
    res: float
    width: int
    yaw: float
    def __init__(self, width: _Optional[int] = ..., height: _Optional[int] = ..., center_x: _Optional[float] = ..., center_y: _Optional[float] = ..., yaw: _Optional[float] = ..., res: _Optional[float] = ..., costmap: _Optional[_Iterable[int]] = ...) -> None: ...

class cover_path_packet_t(_message.Message):
    __slots__ = ["dataCouple", "path_cur", "path_hash", "path_total", "path_type", "zone_hash"]
    DATACOUPLE_FIELD_NUMBER: _ClassVar[int]
    PATH_CUR_FIELD_NUMBER: _ClassVar[int]
    PATH_HASH_FIELD_NUMBER: _ClassVar[int]
    PATH_TOTAL_FIELD_NUMBER: _ClassVar[int]
    PATH_TYPE_FIELD_NUMBER: _ClassVar[int]
    ZONE_HASH_FIELD_NUMBER: _ClassVar[int]
    dataCouple: _containers.RepeatedCompositeFieldContainer[_common_pb2.CommDataCouple]
    path_cur: int
    path_hash: int
    path_total: int
    path_type: int
    zone_hash: int
    def __init__(self, path_hash: _Optional[int] = ..., path_type: _Optional[int] = ..., path_total: _Optional[int] = ..., path_cur: _Optional[int] = ..., zone_hash: _Optional[int] = ..., dataCouple: _Optional[_Iterable[_Union[_common_pb2.CommDataCouple, _Mapping]]] = ...) -> None: ...

class cover_path_upload_t(_message.Message):
    __slots__ = ["area", "currentFrame", "dataHash", "dataLen", "path_packets", "pver", "reserved", "result", "subCmd", "time", "totalFrame", "total_path_num", "transaction_id", "vaild_path_num"]
    AREA_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    DATALEN_FIELD_NUMBER: _ClassVar[int]
    PATH_PACKETS_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    TOTALFRAME_FIELD_NUMBER: _ClassVar[int]
    TOTAL_PATH_NUM_FIELD_NUMBER: _ClassVar[int]
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    VAILD_PATH_NUM_FIELD_NUMBER: _ClassVar[int]
    area: int
    currentFrame: int
    dataHash: int
    dataLen: int
    path_packets: _containers.RepeatedCompositeFieldContainer[cover_path_packet_t]
    pver: int
    reserved: _containers.RepeatedScalarFieldContainer[int]
    result: int
    subCmd: int
    time: int
    totalFrame: int
    total_path_num: int
    transaction_id: int
    vaild_path_num: int
    def __init__(self, pver: _Optional[int] = ..., result: _Optional[int] = ..., subCmd: _Optional[int] = ..., area: _Optional[int] = ..., time: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., total_path_num: _Optional[int] = ..., vaild_path_num: _Optional[int] = ..., dataHash: _Optional[int] = ..., transaction_id: _Optional[int] = ..., reserved: _Optional[_Iterable[int]] = ..., dataLen: _Optional[int] = ..., path_packets: _Optional[_Iterable[_Union[cover_path_packet_t, _Mapping]]] = ...) -> None: ...

class nav_get_all_plan_task(_message.Message):
    __slots__ = ["tasks"]
    TASKS_FIELD_NUMBER: _ClassVar[int]
    tasks: _containers.RepeatedCompositeFieldContainer[plan_task_name_id_t]
    def __init__(self, tasks: _Optional[_Iterable[_Union[plan_task_name_id_t, _Mapping]]] = ...) -> None: ...

class nav_plan_task_execute(_message.Message):
    __slots__ = ["id", "name", "result", "subCmd"]
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    result: int
    subCmd: int
    def __init__(self, subCmd: _Optional[int] = ..., id: _Optional[str] = ..., name: _Optional[str] = ..., result: _Optional[int] = ...) -> None: ...

class nav_sys_param_msg(_message.Message):
    __slots__ = ["context", "id", "rw"]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    RW_FIELD_NUMBER: _ClassVar[int]
    context: int
    id: int
    rw: int
    def __init__(self, rw: _Optional[int] = ..., id: _Optional[int] = ..., context: _Optional[int] = ...) -> None: ...

class plan_task_name_id_t(_message.Message):
    __slots__ = ["id", "name"]
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ...) -> None: ...

class svg_message_t(_message.Message):
    __slots__ = ["base_height_m", "base_height_pix", "base_width_m", "base_width_pix", "data_count", "hide_svg", "name_count", "rotate", "scale", "svg_file_data", "svg_file_name", "x_move", "y_move"]
    BASE_HEIGHT_M_FIELD_NUMBER: _ClassVar[int]
    BASE_HEIGHT_PIX_FIELD_NUMBER: _ClassVar[int]
    BASE_WIDTH_M_FIELD_NUMBER: _ClassVar[int]
    BASE_WIDTH_PIX_FIELD_NUMBER: _ClassVar[int]
    DATA_COUNT_FIELD_NUMBER: _ClassVar[int]
    HIDE_SVG_FIELD_NUMBER: _ClassVar[int]
    NAME_COUNT_FIELD_NUMBER: _ClassVar[int]
    ROTATE_FIELD_NUMBER: _ClassVar[int]
    SCALE_FIELD_NUMBER: _ClassVar[int]
    SVG_FILE_DATA_FIELD_NUMBER: _ClassVar[int]
    SVG_FILE_NAME_FIELD_NUMBER: _ClassVar[int]
    X_MOVE_FIELD_NUMBER: _ClassVar[int]
    Y_MOVE_FIELD_NUMBER: _ClassVar[int]
    base_height_m: float
    base_height_pix: int
    base_width_m: float
    base_width_pix: int
    data_count: int
    hide_svg: bool
    name_count: int
    rotate: float
    scale: float
    svg_file_data: str
    svg_file_name: str
    x_move: float
    y_move: float
    def __init__(self, x_move: _Optional[float] = ..., y_move: _Optional[float] = ..., scale: _Optional[float] = ..., rotate: _Optional[float] = ..., base_width_m: _Optional[float] = ..., base_width_pix: _Optional[int] = ..., base_height_m: _Optional[float] = ..., base_height_pix: _Optional[int] = ..., data_count: _Optional[int] = ..., hide_svg: bool = ..., name_count: _Optional[int] = ..., svg_file_name: _Optional[str] = ..., svg_file_data: _Optional[str] = ...) -> None: ...

class vision_ctrl_msg(_message.Message):
    __slots__ = ["cmd", "type"]
    CMD_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    cmd: int
    type: int
    def __init__(self, type: _Optional[int] = ..., cmd: _Optional[int] = ...) -> None: ...

class zone_start_precent_t(_message.Message):
    __slots__ = ["dataHash", "index", "x", "y"]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    dataHash: int
    index: int
    x: float
    y: float
    def __init__(self, dataHash: _Optional[int] = ..., x: _Optional[float] = ..., y: _Optional[float] = ..., index: _Optional[int] = ...) -> None: ...
