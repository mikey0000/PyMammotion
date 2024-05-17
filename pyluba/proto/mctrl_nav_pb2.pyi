from pyluba.proto import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AppRequestCoverPaths(_message.Message):
    __slots__ = ["currentFrame", "dataHash", "hashList", "pver", "reserved", "subCmd", "totalFrame", "transactionId"]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    HASHLIST_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TOTALFRAME_FIELD_NUMBER: _ClassVar[int]
    TRANSACTIONID_FIELD_NUMBER: _ClassVar[int]
    currentFrame: int
    dataHash: int
    hashList: _containers.RepeatedScalarFieldContainer[int]
    pver: int
    reserved: _containers.RepeatedScalarFieldContainer[int]
    subCmd: int
    totalFrame: int
    transactionId: int
    def __init__(self, pver: _Optional[int] = ..., subCmd: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., dataHash: _Optional[int] = ..., transactionId: _Optional[int] = ..., reserved: _Optional[_Iterable[int]] = ..., hashList: _Optional[_Iterable[int]] = ...) -> None: ...

class CoverPathPacket(_message.Message):
    __slots__ = ["dataCouple", "pathCur", "pathHash", "pathTotal", "pathType", "zoneHash"]
    DATACOUPLE_FIELD_NUMBER: _ClassVar[int]
    PATHCUR_FIELD_NUMBER: _ClassVar[int]
    PATHHASH_FIELD_NUMBER: _ClassVar[int]
    PATHTOTAL_FIELD_NUMBER: _ClassVar[int]
    PATHTYPE_FIELD_NUMBER: _ClassVar[int]
    ZONEHASH_FIELD_NUMBER: _ClassVar[int]
    dataCouple: _containers.RepeatedCompositeFieldContainer[_common_pb2.CommDataCouple]
    pathCur: int
    pathHash: int
    pathTotal: int
    pathType: int
    zoneHash: int
    def __init__(self, pathHash: _Optional[int] = ..., pathType: _Optional[int] = ..., pathTotal: _Optional[int] = ..., pathCur: _Optional[int] = ..., zoneHash: _Optional[int] = ..., dataCouple: _Optional[_Iterable[_Union[_common_pb2.CommDataCouple, _Mapping]]] = ...) -> None: ...

class CoverPathUpload(_message.Message):
    __slots__ = ["area", "currentFrame", "dataHash", "dataLen", "pathPackets", "pver", "reserved", "result", "subCmd", "time", "totalFrame", "totalPathNum", "transactionId", "validPathNum"]
    AREA_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    DATALEN_FIELD_NUMBER: _ClassVar[int]
    PATHPACKETS_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    TOTALFRAME_FIELD_NUMBER: _ClassVar[int]
    TOTALPATHNUM_FIELD_NUMBER: _ClassVar[int]
    TRANSACTIONID_FIELD_NUMBER: _ClassVar[int]
    VALIDPATHNUM_FIELD_NUMBER: _ClassVar[int]
    area: int
    currentFrame: int
    dataHash: int
    dataLen: int
    pathPackets: _containers.RepeatedCompositeFieldContainer[CoverPathPacket]
    pver: int
    reserved: _containers.RepeatedScalarFieldContainer[int]
    result: int
    subCmd: int
    time: int
    totalFrame: int
    totalPathNum: int
    transactionId: int
    validPathNum: int
    def __init__(self, pver: _Optional[int] = ..., result: _Optional[int] = ..., subCmd: _Optional[int] = ..., area: _Optional[int] = ..., time: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., totalPathNum: _Optional[int] = ..., validPathNum: _Optional[int] = ..., dataHash: _Optional[int] = ..., transactionId: _Optional[int] = ..., reserved: _Optional[_Iterable[int]] = ..., dataLen: _Optional[int] = ..., pathPackets: _Optional[_Iterable[_Union[CoverPathPacket, _Mapping]]] = ...) -> None: ...

class MctlNav(_message.Message):
    __slots__ = ["app_request_cover_paths_t", "bidire_reqconver_path", "bidire_taskid", "cover_path_upload_t", "simulation_cmd", "toapp_bp", "toapp_bstate", "toapp_chgpileto", "toapp_get_commondata_ack", "toapp_gethash_ack", "toapp_lat_up", "toapp_opt_border_info", "toapp_opt_line_up", "toapp_opt_obs_info", "toapp_pos_up", "toapp_task_info", "toapp_work_report_ack", "toapp_work_report_update_ack", "toapp_work_report_upload", "toapp_zigzag", "todev_cancel_draw_cmd", "todev_cancel_suscmd", "todev_chl_line", "todev_chl_line_data", "todev_chl_line_end", "todev_draw_border", "todev_draw_border_end", "todev_draw_obs", "todev_draw_obs_end", "todev_edgecmd", "todev_get_commondata", "todev_gethash", "todev_lat_up_ack", "todev_mow_task", "todev_one_touch_leave_pile", "todev_opt_border_info_ack", "todev_opt_line_up_ack", "todev_opt_obs_info_ack", "todev_planjob_set", "todev_rechgcmd", "todev_reset_chg_pile", "todev_save_task", "todev_sustask", "todev_task_info_ack", "todev_taskctrl", "todev_unable_time_set", "todev_work_report_cmd", "todev_work_report_update_cmd", "todev_zigzag_ack"]
    APP_REQUEST_COVER_PATHS_T_FIELD_NUMBER: _ClassVar[int]
    BIDIRE_REQCONVER_PATH_FIELD_NUMBER: _ClassVar[int]
    BIDIRE_TASKID_FIELD_NUMBER: _ClassVar[int]
    COVER_PATH_UPLOAD_T_FIELD_NUMBER: _ClassVar[int]
    SIMULATION_CMD_FIELD_NUMBER: _ClassVar[int]
    TOAPP_BP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_BSTATE_FIELD_NUMBER: _ClassVar[int]
    TOAPP_CHGPILETO_FIELD_NUMBER: _ClassVar[int]
    TOAPP_GETHASH_ACK_FIELD_NUMBER: _ClassVar[int]
    TOAPP_GET_COMMONDATA_ACK_FIELD_NUMBER: _ClassVar[int]
    TOAPP_LAT_UP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_OPT_BORDER_INFO_FIELD_NUMBER: _ClassVar[int]
    TOAPP_OPT_LINE_UP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_OPT_OBS_INFO_FIELD_NUMBER: _ClassVar[int]
    TOAPP_POS_UP_FIELD_NUMBER: _ClassVar[int]
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
    TODEV_TASKCTRL_FIELD_NUMBER: _ClassVar[int]
    TODEV_TASK_INFO_ACK_FIELD_NUMBER: _ClassVar[int]
    TODEV_UNABLE_TIME_SET_FIELD_NUMBER: _ClassVar[int]
    TODEV_WORK_REPORT_CMD_FIELD_NUMBER: _ClassVar[int]
    TODEV_WORK_REPORT_UPDATE_CMD_FIELD_NUMBER: _ClassVar[int]
    TODEV_ZIGZAG_ACK_FIELD_NUMBER: _ClassVar[int]
    app_request_cover_paths_t: AppRequestCoverPaths
    bidire_reqconver_path: NavReqCoverPath
    bidire_taskid: NavTaskIdRw
    cover_path_upload_t: CoverPathUpload
    simulation_cmd: SimulationCmdData
    toapp_bp: NavTaskBreakPoint
    toapp_bstate: NavBorderState
    toapp_chgpileto: chargePileType
    toapp_get_commondata_ack: NavGetCommDataAck
    toapp_gethash_ack: NavGetHashListAck
    toapp_lat_up: NavLatLonUp
    toapp_opt_border_info: NavOptiBorderInfo
    toapp_opt_line_up: NavOptLineUp
    toapp_opt_obs_info: NavOptObsInfo
    toapp_pos_up: NavPosUp
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
    todev_task_info_ack: NavResFrame
    todev_taskctrl: NavTaskCtrl
    todev_unable_time_set: NavUnableTimeSet
    todev_work_report_cmd: WorkReportCmdData
    todev_work_report_update_cmd: WorkReportUpdateCmd
    todev_zigzag_ack: NavUploadZigZagResultAck
    def __init__(self, toapp_lat_up: _Optional[_Union[NavLatLonUp, _Mapping]] = ..., toapp_pos_up: _Optional[_Union[NavPosUp, _Mapping]] = ..., todev_chl_line_data: _Optional[_Union[NavCHlLineData, _Mapping]] = ..., toapp_task_info: _Optional[_Union[NavTaskInfo, _Mapping]] = ..., toapp_opt_line_up: _Optional[_Union[NavOptLineUp, _Mapping]] = ..., toapp_opt_border_info: _Optional[_Union[NavOptiBorderInfo, _Mapping]] = ..., toapp_opt_obs_info: _Optional[_Union[NavOptObsInfo, _Mapping]] = ..., todev_task_info_ack: _Optional[_Union[NavResFrame, _Mapping]] = ..., todev_opt_border_info_ack: _Optional[_Union[NavResFrame, _Mapping]] = ..., todev_opt_obs_info_ack: _Optional[_Union[NavResFrame, _Mapping]] = ..., todev_opt_line_up_ack: _Optional[_Union[NavResFrame, _Mapping]] = ..., toapp_chgpileto: _Optional[_Union[chargePileType, _Mapping]] = ..., todev_sustask: _Optional[int] = ..., todev_rechgcmd: _Optional[int] = ..., todev_edgecmd: _Optional[int] = ..., todev_draw_border: _Optional[int] = ..., todev_draw_border_end: _Optional[int] = ..., todev_draw_obs: _Optional[int] = ..., todev_draw_obs_end: _Optional[int] = ..., todev_chl_line: _Optional[int] = ..., todev_chl_line_end: _Optional[int] = ..., todev_save_task: _Optional[int] = ..., todev_cancel_suscmd: _Optional[int] = ..., todev_reset_chg_pile: _Optional[int] = ..., todev_cancel_draw_cmd: _Optional[int] = ..., todev_one_touch_leave_pile: _Optional[int] = ..., todev_mow_task: _Optional[_Union[NavStartJob, _Mapping]] = ..., toapp_bstate: _Optional[_Union[NavBorderState, _Mapping]] = ..., todev_lat_up_ack: _Optional[int] = ..., todev_gethash: _Optional[_Union[NavGetHashList, _Mapping]] = ..., toapp_gethash_ack: _Optional[_Union[NavGetHashListAck, _Mapping]] = ..., todev_get_commondata: _Optional[_Union[NavGetCommData, _Mapping]] = ..., toapp_get_commondata_ack: _Optional[_Union[NavGetCommDataAck, _Mapping]] = ..., bidire_reqconver_path: _Optional[_Union[NavReqCoverPath, _Mapping]] = ..., toapp_zigzag: _Optional[_Union[NavUploadZigZagResult, _Mapping]] = ..., todev_zigzag_ack: _Optional[_Union[NavUploadZigZagResultAck, _Mapping]] = ..., todev_taskctrl: _Optional[_Union[NavTaskCtrl, _Mapping]] = ..., bidire_taskid: _Optional[_Union[NavTaskIdRw, _Mapping]] = ..., toapp_bp: _Optional[_Union[NavTaskBreakPoint, _Mapping]] = ..., todev_planjob_set: _Optional[_Union[NavPlanJobSet, _Mapping]] = ..., todev_unable_time_set: _Optional[_Union[NavUnableTimeSet, _Mapping]] = ..., simulation_cmd: _Optional[_Union[SimulationCmdData, _Mapping]] = ..., todev_work_report_update_cmd: _Optional[_Union[WorkReportUpdateCmd, _Mapping]] = ..., toapp_work_report_update_ack: _Optional[_Union[WorkReportUpdateAck, _Mapping]] = ..., todev_work_report_cmd: _Optional[_Union[WorkReportCmdData, _Mapping]] = ..., toapp_work_report_ack: _Optional[_Union[WorkReportInfoAck, _Mapping]] = ..., toapp_work_report_upload: _Optional[_Union[WorkReportInfoAck, _Mapping]] = ..., app_request_cover_paths_t: _Optional[_Union[AppRequestCoverPaths, _Mapping]] = ..., cover_path_upload_t: _Optional[_Union[CoverPathUpload, _Mapping]] = ...) -> None: ...

class NavBorderDataGet(_message.Message):
    __slots__ = ["borderLen", "currentFrame", "jobId"]
    BORDERLEN_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    JOBID_FIELD_NUMBER: _ClassVar[int]
    borderLen: int
    currentFrame: int
    jobId: int
    def __init__(self, currentFrame: _Optional[int] = ..., borderLen: _Optional[int] = ..., jobId: _Optional[int] = ...) -> None: ...

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
    def __init__(self, channelLineLen: _Optional[int] = ..., currentFrame: _Optional[int] = ..., endJobRI: _Optional[int] = ..., startJobRI: _Optional[int] = ...) -> None: ...

class NavCHlLineDataAck(_message.Message):
    __slots__ = ["currentFrame", "endJobRI", "startJobRI"]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    ENDJOBRI_FIELD_NUMBER: _ClassVar[int]
    STARTJOBRI_FIELD_NUMBER: _ClassVar[int]
    currentFrame: int
    endJobRI: int
    startJobRI: int
    def __init__(self, currentFrame: _Optional[int] = ..., endJobRI: _Optional[int] = ..., startJobRI: _Optional[int] = ...) -> None: ...

class NavGetCommData(_message.Message):
    __slots__ = ["Hash", "action", "currentFrame", "dataHash", "paternalHashA", "paternalHashB", "pver", "reserved", "subCmd", "totalFrame", "type"]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    Hash: int
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
    paternalHashA: int
    paternalHashB: int
    pver: int
    reserved: str
    subCmd: int
    totalFrame: int
    type: int
    def __init__(self, pver: _Optional[int] = ..., subCmd: _Optional[int] = ..., action: _Optional[int] = ..., type: _Optional[int] = ..., Hash: _Optional[int] = ..., paternalHashA: _Optional[int] = ..., paternalHashB: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., dataHash: _Optional[int] = ..., reserved: _Optional[str] = ...) -> None: ...

class NavGetCommDataAck(_message.Message):
    __slots__ = ["Hash", "action", "currentFrame", "dataCouple", "dataHash", "dataLen", "paternalHashA", "paternalHashB", "pver", "reserved", "result", "subCmd", "totalFrame", "type"]
    ACTION_FIELD_NUMBER: _ClassVar[int]
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
    def __init__(self, pver: _Optional[int] = ..., subCmd: _Optional[int] = ..., result: _Optional[int] = ..., action: _Optional[int] = ..., type: _Optional[int] = ..., Hash: _Optional[int] = ..., paternalHashA: _Optional[int] = ..., paternalHashB: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., dataHash: _Optional[int] = ..., dataLen: _Optional[int] = ..., dataCouple: _Optional[_Iterable[_Union[_common_pb2.CommDataCouple, _Mapping]]] = ..., reserved: _Optional[str] = ...) -> None: ...

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
    __slots__ = ["currentFrame", "dataCouple", "dataHash", "hashLen", "pver", "reserved", "subCmd", "totalFrame"]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    DATACOUPLE_FIELD_NUMBER: _ClassVar[int]
    DATAHASH_FIELD_NUMBER: _ClassVar[int]
    HASHLEN_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TOTALFRAME_FIELD_NUMBER: _ClassVar[int]
    currentFrame: int
    dataCouple: _containers.RepeatedScalarFieldContainer[int]
    dataHash: int
    hashLen: int
    pver: int
    reserved: str
    subCmd: int
    totalFrame: int
    def __init__(self, pver: _Optional[int] = ..., subCmd: _Optional[int] = ..., totalFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., dataHash: _Optional[int] = ..., hashLen: _Optional[int] = ..., reserved: _Optional[str] = ..., dataCouple: _Optional[_Iterable[int]] = ...) -> None: ...

class NavLatLonUp(_message.Message):
    __slots__ = ["lat", "lon"]
    LAT_FIELD_NUMBER: _ClassVar[int]
    LON_FIELD_NUMBER: _ClassVar[int]
    lat: float
    lon: float
    def __init__(self, lat: _Optional[float] = ..., lon: _Optional[float] = ...) -> None: ...

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
    def __init__(self, endJobRI: _Optional[int] = ..., startJobRI: _Optional[int] = ..., allFrame: _Optional[int] = ..., currentFrame: _Optional[int] = ..., channelDataLen: _Optional[int] = ..., dc: _Optional[_Iterable[_Union[_common_pb2.CommDataCouple, _Mapping]]] = ...) -> None: ...

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
    __slots__ = ["area", "deviceId", "edgeMode", "endTime", "id", "jobId", "jobName", "knifeHeight", "model", "planId", "planIndex", "pver", "requiredTime", "reserved", "result", "routeAngle", "routeModel", "routeSpacing", "speed", "startTime", "subCmd", "taskId", "taskName", "totalPlanNum", "ultrasonicBarrier", "userId", "version", "week", "workTime", "zoneHashs"]
    AREA_FIELD_NUMBER: _ClassVar[int]
    DEVICEID_FIELD_NUMBER: _ClassVar[int]
    EDGEMODE_FIELD_NUMBER: _ClassVar[int]
    ENDTIME_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    JOBID_FIELD_NUMBER: _ClassVar[int]
    JOBNAME_FIELD_NUMBER: _ClassVar[int]
    KNIFEHEIGHT_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    PLANID_FIELD_NUMBER: _ClassVar[int]
    PLANINDEX_FIELD_NUMBER: _ClassVar[int]
    PVER_FIELD_NUMBER: _ClassVar[int]
    REQUIREDTIME_FIELD_NUMBER: _ClassVar[int]
    RESERVED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ROUTEANGLE_FIELD_NUMBER: _ClassVar[int]
    ROUTEMODEL_FIELD_NUMBER: _ClassVar[int]
    ROUTESPACING_FIELD_NUMBER: _ClassVar[int]
    SPEED_FIELD_NUMBER: _ClassVar[int]
    STARTTIME_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    TASKID_FIELD_NUMBER: _ClassVar[int]
    TASKNAME_FIELD_NUMBER: _ClassVar[int]
    TOTALPLANNUM_FIELD_NUMBER: _ClassVar[int]
    ULTRASONICBARRIER_FIELD_NUMBER: _ClassVar[int]
    USERID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    WEEK_FIELD_NUMBER: _ClassVar[int]
    WORKTIME_FIELD_NUMBER: _ClassVar[int]
    ZONEHASHS_FIELD_NUMBER: _ClassVar[int]
    area: int
    deviceId: str
    edgeMode: int
    endTime: str
    id: str
    jobId: str
    jobName: str
    knifeHeight: int
    model: int
    planId: str
    planIndex: int
    pver: int
    requiredTime: int
    reserved: str
    result: int
    routeAngle: int
    routeModel: int
    routeSpacing: int
    speed: float
    startTime: str
    subCmd: int
    taskId: str
    taskName: str
    totalPlanNum: int
    ultrasonicBarrier: int
    userId: str
    version: str
    week: int
    workTime: int
    zoneHashs: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, pver: _Optional[int] = ..., subCmd: _Optional[int] = ..., area: _Optional[int] = ..., workTime: _Optional[int] = ..., version: _Optional[str] = ..., id: _Optional[str] = ..., userId: _Optional[str] = ..., deviceId: _Optional[str] = ..., planId: _Optional[str] = ..., taskId: _Optional[str] = ..., jobId: _Optional[str] = ..., startTime: _Optional[str] = ..., endTime: _Optional[str] = ..., week: _Optional[int] = ..., knifeHeight: _Optional[int] = ..., model: _Optional[int] = ..., edgeMode: _Optional[int] = ..., requiredTime: _Optional[int] = ..., routeAngle: _Optional[int] = ..., routeModel: _Optional[int] = ..., routeSpacing: _Optional[int] = ..., ultrasonicBarrier: _Optional[int] = ..., totalPlanNum: _Optional[int] = ..., planIndex: _Optional[int] = ..., result: _Optional[int] = ..., speed: _Optional[float] = ..., taskName: _Optional[str] = ..., jobName: _Optional[str] = ..., zoneHashs: _Optional[_Iterable[int]] = ..., reserved: _Optional[str] = ...) -> None: ...

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
    __slots__ = ["channelMode", "channelWidth", "edgeMode", "jobId", "jobMode", "jobVer", "knifeHeight", "pathHash", "pver", "reserved", "result", "speed", "subCmd", "toward", "ultraWave", "zoneHashs"]
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
    ULTRAWAVE_FIELD_NUMBER: _ClassVar[int]
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
    ultraWave: int
    zoneHashs: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, pver: _Optional[int] = ..., jobId: _Optional[int] = ..., jobVer: _Optional[int] = ..., jobMode: _Optional[int] = ..., subCmd: _Optional[int] = ..., edgeMode: _Optional[int] = ..., knifeHeight: _Optional[int] = ..., channelWidth: _Optional[int] = ..., ultraWave: _Optional[int] = ..., channelMode: _Optional[int] = ..., toward: _Optional[int] = ..., speed: _Optional[float] = ..., zoneHashs: _Optional[_Iterable[int]] = ..., pathHash: _Optional[int] = ..., reserved: _Optional[str] = ..., result: _Optional[int] = ...) -> None: ...

class NavResFrame(_message.Message):
    __slots__ = ["frameid"]
    FRAMEID_FIELD_NUMBER: _ClassVar[int]
    frameid: int
    def __init__(self, frameid: _Optional[int] = ...) -> None: ...

class NavStartJob(_message.Message):
    __slots__ = ["channelMode", "channelWidth", "jobId", "jobMode", "jobVer", "knifeHeight", "rainTactics", "speed", "ultraWave"]
    CHANNELMODE_FIELD_NUMBER: _ClassVar[int]
    CHANNELWIDTH_FIELD_NUMBER: _ClassVar[int]
    JOBID_FIELD_NUMBER: _ClassVar[int]
    JOBMODE_FIELD_NUMBER: _ClassVar[int]
    JOBVER_FIELD_NUMBER: _ClassVar[int]
    KNIFEHEIGHT_FIELD_NUMBER: _ClassVar[int]
    RAINTACTICS_FIELD_NUMBER: _ClassVar[int]
    SPEED_FIELD_NUMBER: _ClassVar[int]
    ULTRAWAVE_FIELD_NUMBER: _ClassVar[int]
    channelMode: int
    channelWidth: int
    jobId: int
    jobMode: int
    jobVer: int
    knifeHeight: int
    rainTactics: int
    speed: float
    ultraWave: int
    def __init__(self, jobId: _Optional[int] = ..., jobVer: _Optional[int] = ..., jobMode: _Optional[int] = ..., rainTactics: _Optional[int] = ..., knifeHeight: _Optional[int] = ..., speed: _Optional[float] = ..., channelWidth: _Optional[int] = ..., ultraWave: _Optional[int] = ..., channelMode: _Optional[int] = ...) -> None: ...

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
    reserved: int
    result: int
    type: int
    def __init__(self, type: _Optional[int] = ..., action: _Optional[int] = ..., result: _Optional[int] = ..., reserved: _Optional[int] = ...) -> None: ...

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
    def __init__(self, allFrame: _Optional[int] = ..., area: _Optional[int] = ..., time: _Optional[int] = ..., currentFrame: _Optional[int] = ..., pathlen: _Optional[int] = ..., dc: _Optional[_Iterable[_Union[_common_pb2.CommDataCouple, _Mapping]]] = ...) -> None: ...

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
    __slots__ = ["paramId", "paramValue", "subCmd"]
    PARAMID_FIELD_NUMBER: _ClassVar[int]
    PARAMVALUE_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    paramId: int
    paramValue: _containers.RepeatedScalarFieldContainer[int]
    subCmd: int
    def __init__(self, subCmd: _Optional[int] = ..., paramId: _Optional[int] = ..., paramValue: _Optional[_Iterable[int]] = ...) -> None: ...

class WorkReportCmdData(_message.Message):
    __slots__ = ["getInfoNum", "subCmd"]
    GETINFONUM_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    getInfoNum: int
    subCmd: int
    def __init__(self, subCmd: _Optional[int] = ..., getInfoNum: _Optional[int] = ...) -> None: ...

class WorkReportInfoAck(_message.Message):
    __slots__ = ["currentAckNum", "endWorkTime", "heightOfKnife", "interruptFlag", "startWorkTime", "totalAckNum", "workAres", "workProgress", "workResult", "workTimeUsed", "workType"]
    CURRENTACKNUM_FIELD_NUMBER: _ClassVar[int]
    ENDWORKTIME_FIELD_NUMBER: _ClassVar[int]
    HEIGHTOFKNIFE_FIELD_NUMBER: _ClassVar[int]
    INTERRUPTFLAG_FIELD_NUMBER: _ClassVar[int]
    STARTWORKTIME_FIELD_NUMBER: _ClassVar[int]
    TOTALACKNUM_FIELD_NUMBER: _ClassVar[int]
    WORKARES_FIELD_NUMBER: _ClassVar[int]
    WORKPROGRESS_FIELD_NUMBER: _ClassVar[int]
    WORKRESULT_FIELD_NUMBER: _ClassVar[int]
    WORKTIMEUSED_FIELD_NUMBER: _ClassVar[int]
    WORKTYPE_FIELD_NUMBER: _ClassVar[int]
    currentAckNum: int
    endWorkTime: int
    heightOfKnife: int
    interruptFlag: bool
    startWorkTime: int
    totalAckNum: int
    workAres: float
    workProgress: int
    workResult: int
    workTimeUsed: int
    workType: int
    def __init__(self, currentAckNum: _Optional[int] = ..., endWorkTime: _Optional[int] = ..., heightOfKnife: _Optional[int] = ..., interruptFlag: bool = ..., startWorkTime: _Optional[int] = ..., totalAckNum: _Optional[int] = ..., workAres: _Optional[float] = ..., workProgress: _Optional[int] = ..., workResult: _Optional[int] = ..., workTimeUsed: _Optional[int] = ..., workType: _Optional[int] = ...) -> None: ...

class WorkReportUpdateAck(_message.Message):
    __slots__ = ["infoNum", "updateFlag"]
    INFONUM_FIELD_NUMBER: _ClassVar[int]
    UPDATEFLAG_FIELD_NUMBER: _ClassVar[int]
    infoNum: int
    updateFlag: bool
    def __init__(self, infoNum: _Optional[int] = ..., updateFlag: bool = ...) -> None: ...

class WorkReportUpdateCmd(_message.Message):
    __slots__ = ["subCmd"]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    subCmd: int
    def __init__(self, subCmd: _Optional[int] = ...) -> None: ...

class chargePileType(_message.Message):
    __slots__ = ["toward", "x", "y"]
    TOWARD_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    toward: int
    x: float
    y: float
    def __init__(self, toward: _Optional[int] = ..., x: _Optional[float] = ..., y: _Optional[float] = ...) -> None: ...
