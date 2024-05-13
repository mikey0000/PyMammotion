# This is an automatically generated file, please do not change
# gen by protobuf_to_pydantic[v0.2.6.2](https://github.com/so1n/protobuf_to_pydantic)
# Protobuf Version: 5.26.1 
# Pydantic Version: 2.6.2 
from .common_p2p import CommDataCouple
from google.protobuf.message import Message  # type: ignore
from protobuf_to_pydantic.customer_validator import check_one_of
from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator
import typing


class NavLatLonUp(BaseModel):
    lat: float = Field(default=0.0) 
    lon: float = Field(default=0.0) 

class NavBorderState(BaseModel):
    bdstate: int = Field(default=0) 

class NavPosUp(BaseModel):
    x: float = Field(default=0.0) 
    y: float = Field(default=0.0) 
    status: int = Field(default=0) 
    toward: int = Field(default=0) 
    stars: int = Field(default=0) 
    age: float = Field(default=0.0) 
    latStddev: float = Field(default=0.0) 
    lonStddev: float = Field(default=0.0) 
    l2dfStars: int = Field(default=0) 
    posType: int = Field(default=0) 
    cHashId: int = Field(default=0) 
    posLevel: int = Field(default=0) 

class NavBorderDataGetAck(BaseModel):
    jobId: int = Field(default=0) 
    currentFrame: int = Field(default=0) 

class NavObstiBorderDataGet(BaseModel):
    obstacleIndex: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    obstaclesLen: int = Field(default=0) 

class NavObstiBorderDataGetAck(BaseModel):
    obstacleIndex: int = Field(default=0) 
    currentFrame: int = Field(default=0) 

class NavCHlLineData(BaseModel):
    channelLineLen: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    endJobRI: int = Field(default=0) 
    startJobRI: int = Field(default=0) 

class NavCHlLineDataAck(BaseModel):
    currentFrame: int = Field(default=0) 
    endJobRI: int = Field(default=0) 
    startJobRI: int = Field(default=0) 

class NavBorderDataGet(BaseModel):
    currentFrame: int = Field(default=0) 
    borderLen: int = Field(default=0) 
    jobId: int = Field(default=0) 

class NavTaskInfo(BaseModel):
    allFrame: int = Field(default=0) 
    area: int = Field(default=0) 
    time: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    pathlen: int = Field(default=0) 
    dc: typing.List[CommDataCouple] = Field(default_factory=list) 

class NavOptLineUp(BaseModel):
    endJobRI: int = Field(default=0) 
    startJobRI: int = Field(default=0) 
    allFrame: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    channelDataLen: int = Field(default=0) 
    dc: typing.List[CommDataCouple] = Field(default_factory=list) 

class NavOptiBorderInfo(BaseModel):
    jobId: int = Field(default=0) 
    allFrame: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    borderDataLen: int = Field(default=0) 
    dc: typing.List[CommDataCouple] = Field(default_factory=list) 

class NavOptObsInfo(BaseModel):
    obstacleId: int = Field(default=0) 
    allFrame: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    obstacleDataLen: int = Field(default=0) 
    dc: typing.List[CommDataCouple] = Field(default_factory=list) 

class NavStartJob(BaseModel):
    jobId: int = Field(default=0) 
    jobVer: int = Field(default=0) 
    jobMode: int = Field(default=0) 
    rainTactics: int = Field(default=0) 
    knifeHeight: int = Field(default=0) 
    speed: float = Field(default=0.0) 
    channelWidth: int = Field(default=0) 
    ultraWave: int = Field(default=0) 
    channelMode: int = Field(default=0) 

class NavGetHashList(BaseModel):
    pver: int = Field(default=0) 
    subCmd: int = Field(default=0) 
    totalFrame: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    dataHash: int = Field(default=0) 
    reserved: str = Field(default="") 

class NavGetHashListAck(BaseModel):
    pver: int = Field(default=0) 
    subCmd: int = Field(default=0) 
    totalFrame: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    dataHash: int = Field(default=0) 
    hashLen: int = Field(default=0) 
    reserved: str = Field(default="") 
    dataCouple: typing.List[int] = Field(default_factory=list) 

class NavGetCommData(BaseModel):
    pver: int = Field(default=0) 
    subCmd: int = Field(default=0) 
    action: int = Field(default=0) 
    type: int = Field(default=0) 
    Hash: int = Field(default=0) 
    paternalHashA: float = Field(default=0.0) 
    paternalHashB: float = Field(default=0.0) 
    totalFrame: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    dataHash: float = Field(default=0.0) 
    reserved: str = Field(default="") 

class NavGetCommDataAck(BaseModel):
    pver: int = Field(default=0) 
    subCmd: int = Field(default=0) 
    result: int = Field(default=0) 
    action: int = Field(default=0) 
    type: int = Field(default=0) 
    Hash: float = Field(default=0.0) 
    paternalHashA: float = Field(default=0.0) 
    paternalHashB: float = Field(default=0.0) 
    totalFrame: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    dataHash: int = Field(default=0) 
    dataLen: int = Field(default=0) 
    dataCouple: typing.List[CommDataCouple] = Field(default_factory=list) 
    reserved: str = Field(default="") 

class NavReqCoverPath(BaseModel):
    pver: int = Field(default=0) 
    jobId: int = Field(default=0) 
    jobVer: int = Field(default=0) 
    jobMode: int = Field(default=0) 
    subCmd: int = Field(default=0) 
    edgeMode: int = Field(default=0) 
    knifeHeight: int = Field(default=0) 
    channelWidth: int = Field(default=0) 
    ultraWave: int = Field(default=0) 
    channelMode: int = Field(default=0) 
    toward: int = Field(default=0) 
    speed: float = Field(default=0.0) 
    zoneHashs: typing.List[int] = Field(default_factory=list) 
    pathHash: int = Field(default=0) 
    reserved: str = Field(default="") 
    result: int = Field(default=0) 

class NavUploadZigZagResult(BaseModel):
    pver: int = Field(default=0) 
    jobId: int = Field(default=0) 
    jobVer: int = Field(default=0) 
    result: int = Field(default=0) 
    area: int = Field(default=0) 
    time: int = Field(default=0) 
    totalZoneNum: int = Field(default=0) 
    currentZonePathNum: int = Field(default=0) 
    currentZonePathId: int = Field(default=0) 
    currentZone: int = Field(default=0) 
    currentHash: int = Field(default=0) 
    totalFrame: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    channelMode: int = Field(default=0) 
    channelModeId: int = Field(default=0) 
    dataHash: int = Field(default=0) 
    dataLen: int = Field(default=0) 
    reserved: str = Field(default="") 
    dataCouple: typing.List[CommDataCouple] = Field(default_factory=list) 
    subCmd: int = Field(default=0) 

class NavUploadZigZagResultAck(BaseModel):
    pver: int = Field(default=0) 
    currentZone: int = Field(default=0) 
    currentHash: int = Field(default=0) 
    totalFrame: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    dataHash: int = Field(default=0) 
    reserved: str = Field(default="") 
    subCmd: int = Field(default=0) 

class NavTaskCtrl(BaseModel):
    type: int = Field(default=0) 
    action: int = Field(default=0) 
    result: int = Field(default=0) 
    reserved: int = Field(default=0) 

class NavTaskIdRw(BaseModel):
    pver: int = Field(default=0) 
    subCmd: int = Field(default=0) 
    taskName: str = Field(default="") 
    taskId: str = Field(default="") 
    result: int = Field(default=0) 
    reserved: str = Field(default="") 

class NavSysHashOverview(BaseModel):
    commonhashOverview: int = Field(default=0) 
    pathHashOverview: int = Field(default=0) 

class NavTaskBreakPoint(BaseModel):
    x: float = Field(default=0.0) 
    y: float = Field(default=0.0) 
    toward: int = Field(default=0) 
    flag: int = Field(default=0) 
    action: int = Field(default=0) 
    zoneHash: int = Field(default=0) 

class NavPlanJobSet(BaseModel):
    pver: int = Field(default=0) 
    subCmd: int = Field(default=0) 
    area: int = Field(default=0) 
    workTime: int = Field(default=0) 
    version: str = Field(default="") 
    id: str = Field(default="") 
    userId: str = Field(default="") 
    deviceId: str = Field(default="") 
    planId: str = Field(default="") 
    taskId: str = Field(default="") 
    jobId: str = Field(default="") 
    startTime: str = Field(default="") 
    endTime: str = Field(default="") 
    week: int = Field(default=0) 
    knifeHeight: int = Field(default=0) 
    model: int = Field(default=0) 
    edgeMode: int = Field(default=0) 
    requiredTime: int = Field(default=0) 
    routeAngle: int = Field(default=0) 
    routeModel: int = Field(default=0) 
    routeSpacing: int = Field(default=0) 
    ultrasonicBarrier: int = Field(default=0) 
    totalPlanNum: int = Field(default=0) 
    planIndex: int = Field(default=0) 
    result: int = Field(default=0) 
    speed: float = Field(default=0.0) 
    taskName: str = Field(default="") 
    jobName: str = Field(default="") 
    zoneHashs: typing.List[int] = Field(default_factory=list) 
    reserved: str = Field(default="") 

class NavResFrame(BaseModel):
    frameid: int = Field(default=0) 

class NavTaskProgress(BaseModel):
    taskProgress: int = Field(default=0) 

class NavUnableTimeSet(BaseModel):
    subCmd: int = Field(default=0) 
    deviceId: str = Field(default="") 
    unableStartTime: str = Field(default="") 
    unableEndTime: str = Field(default="") 
    result: int = Field(default=0) 
    reserved: str = Field(default="") 

class SimulationCmdData(BaseModel):
    subCmd: int = Field(default=0) 
    paramId: int = Field(default=0) 
    paramValue: typing.List[int] = Field(default_factory=list) 

class WorkReportCmdData(BaseModel):
    subCmd: int = Field(default=0) 
    getInfoNum: int = Field(default=0) 

class WorkReportInfoAck(BaseModel):
    currentAckNum: int = Field(default=0) 
    endWorkTime: int = Field(default=0) 
    heightOfKnife: int = Field(default=0) 
    interruptFlag: bool = Field(default=False) 
    startWorkTime: int = Field(default=0) 
    totalAckNum: int = Field(default=0) 
    workAres: float = Field(default=0.0) 
    workProgress: int = Field(default=0) 
    workResult: int = Field(default=0) 
    workTimeUsed: int = Field(default=0) 
    workType: int = Field(default=0) 

class WorkReportUpdateAck(BaseModel):
    infoNum: int = Field(default=0) 
    updateFlag: bool = Field(default=False) 

class WorkReportUpdateCmd(BaseModel):
    subCmd: int = Field(default=0) 

class chargePileType(BaseModel):
    toward: int = Field(default=0) 
    x: float = Field(default=0.0) 
    y: float = Field(default=0.0) 

class AppRequestCoverPaths(BaseModel):
    pver: int = Field(default=0) 
    subCmd: int = Field(default=0) 
    totalFrame: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    dataHash: float = Field(default=0.0) 
    transactionId: int = Field(default=0) 
    reserved: typing.List[int] = Field(default_factory=list) 
    hashList: typing.List[int] = Field(default_factory=list) 

class CoverPathPacket(BaseModel):
    pathHash: float = Field(default=0.0) 
    pathType: int = Field(default=0) 
    pathTotal: int = Field(default=0) 
    pathCur: int = Field(default=0) 
    zoneHash: float = Field(default=0.0) 
    dataCouple: typing.List[CommDataCouple] = Field(default_factory=list) 

class CoverPathUpload(BaseModel):
    pver: int = Field(default=0) 
    result: int = Field(default=0) 
    subCmd: int = Field(default=0) 
    area: int = Field(default=0) 
    time: int = Field(default=0) 
    totalFrame: int = Field(default=0) 
    currentFrame: int = Field(default=0) 
    totalPathNum: int = Field(default=0) 
    validPathNum: int = Field(default=0) 
    dataHash: float = Field(default=0.0) 
    transactionId: int = Field(default=0) 
    reserved: typing.List[int] = Field(default_factory=list) 
    dataLen: int = Field(default=0) 
    pathPackets: typing.List[CoverPathPacket] = Field(default_factory=list) 

class MctlNav(BaseModel):
    _one_of_dict = {"MctlNav.SubNavMsg": {"fields": {"app_request_cover_paths_t", "bidire_reqconver_path", "bidire_taskid", "cover_path_upload_t", "simulation_cmd", "toapp_bp", "toapp_bstate", "toapp_chgpileto", "toapp_get_commondata_ack", "toapp_gethash_ack", "toapp_lat_up", "toapp_opt_border_info", "toapp_opt_line_up", "toapp_opt_obs_info", "toapp_pos_up", "toapp_task_info", "toapp_work_report_ack", "toapp_work_report_update_ack", "toapp_work_report_upload", "toapp_zigzag", "todev_cancel_draw_cmd", "todev_cancel_suscmd", "todev_chl_line", "todev_chl_line_data", "todev_chl_line_end", "todev_draw_border", "todev_draw_border_end", "todev_draw_obs", "todev_draw_obs_end", "todev_edgecmd", "todev_get_commondata", "todev_gethash", "todev_lat_up_ack", "todev_mow_task", "todev_one_touch_leave_pile", "todev_opt_border_info_ack", "todev_opt_line_up_ack", "todev_opt_obs_info_ack", "todev_planjob_set", "todev_rechgcmd", "todev_reset_chg_pile", "todev_save_task", "todev_sustask", "todev_task_info_ack", "todev_taskctrl", "todev_unable_time_set", "todev_work_report_cmd", "todev_work_report_update_cmd", "todev_zigzag_ack"}}}
    one_of_validator = model_validator(mode="before")(check_one_of)
    toapp_lat_up: NavLatLonUp = Field() 
    toapp_pos_up: NavPosUp = Field() 
    todev_chl_line_data: NavCHlLineData = Field() 
    toapp_task_info: NavTaskInfo = Field() 
    toapp_opt_line_up: NavOptLineUp = Field() 
    toapp_opt_border_info: NavOptiBorderInfo = Field() 
    toapp_opt_obs_info: NavOptObsInfo = Field() 
    todev_task_info_ack: NavResFrame = Field() 
    todev_opt_border_info_ack: NavResFrame = Field() 
    todev_opt_obs_info_ack: NavResFrame = Field() 
    todev_opt_line_up_ack: NavResFrame = Field() 
    toapp_chgpileto: chargePileType = Field() 
    todev_sustask: int = Field(default=0) 
    todev_rechgcmd: int = Field(default=0) 
    todev_edgecmd: int = Field(default=0) 
    todev_draw_border: int = Field(default=0) 
    todev_draw_border_end: int = Field(default=0) 
    todev_draw_obs: int = Field(default=0) 
    todev_draw_obs_end: int = Field(default=0) 
    todev_chl_line: int = Field(default=0) 
    todev_chl_line_end: int = Field(default=0) 
    todev_save_task: int = Field(default=0) 
    todev_cancel_suscmd: int = Field(default=0) 
    todev_reset_chg_pile: int = Field(default=0) 
    todev_cancel_draw_cmd: int = Field(default=0) 
    todev_one_touch_leave_pile: int = Field(default=0) 
    todev_mow_task: NavStartJob = Field() 
    toapp_bstate: NavBorderState = Field() 
    todev_lat_up_ack: int = Field(default=0) 
    todev_gethash: NavGetHashList = Field() 
    toapp_gethash_ack: NavGetHashListAck = Field() 
    todev_get_commondata: NavGetCommData = Field() 
    toapp_get_commondata_ack: NavGetCommDataAck = Field() 
    bidire_reqconver_path: NavReqCoverPath = Field() 
    toapp_zigzag: NavUploadZigZagResult = Field() 
    todev_zigzag_ack: NavUploadZigZagResultAck = Field() 
    todev_taskctrl: NavTaskCtrl = Field() 
    bidire_taskid: NavTaskIdRw = Field() 
    toapp_bp: NavTaskBreakPoint = Field() 
    todev_planjob_set: NavPlanJobSet = Field() 
    todev_unable_time_set: NavUnableTimeSet = Field() 
    simulation_cmd: SimulationCmdData = Field() 
    todev_work_report_update_cmd: WorkReportUpdateCmd = Field() 
    toapp_work_report_update_ack: WorkReportUpdateAck = Field() 
    todev_work_report_cmd: WorkReportCmdData = Field() 
    toapp_work_report_ack: WorkReportInfoAck = Field() 
    toapp_work_report_upload: WorkReportInfoAck = Field() 
    app_request_cover_paths_t: AppRequestCoverPaths = Field() 
    cover_path_upload_t: CoverPathUpload = Field() 
