# This is an automatically generated file, please do not change
# gen by protobuf_to_pydantic[v0.2.6.2](https://github.com/so1n/protobuf_to_pydantic)
# Protobuf Version: 5.26.1 
# Pydantic Version: 2.6.2 
from .dev_net_p2p import MnetInfo
from enum import IntEnum
from google.protobuf.message import Message  # type: ignore
from protobuf_to_pydantic.customer_validator import check_one_of
from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator
import typing

class Operation(IntEnum):
    WRITE = 0
    READ = 1
    ERASE = 2


class OffPartId(IntEnum):
    OFF_PART_DL_IMG = 0
    OFF_PART_UPDINFO_BACK = 1
    OFF_PART_UPDINFO = 2
    OFF_PART_NAKEDB = 3
    OFF_PART_FLASHDB = 4
    OFF_PART_UPD_APP_IMG = 5
    OFF_PART_UPD_BMS_IMG = 6
    OFF_PART_UPD_TMP_IMG = 7
    OFF_PART_DEV_INFO = 8
    OFF_PART_NAKEDB_BACK = 9
    OFF_PART_MAX = 10

class SysBatUp(BaseModel):
    batVal: int = Field(default=0) 

class SysWorkState(BaseModel):
    deviceState: int = Field(default=0) 
    chargeState: int = Field(default=0) 
    cmHash: int = Field(default=0) 
    pathHash: int = Field(default=0) 

class SysSetTimeZone(BaseModel):
    timeStamp: int = Field(default=0) 
    timeArea: int = Field(default=0) 

class SysSetDateTime(BaseModel):
    year: int = Field(default=0) 
    month: int = Field(default=0) 
    date: int = Field(default=0) 
    week: int = Field(default=0) 
    hours: int = Field(default=0) 
    minutes: int = Field(default=0) 
    seconds: int = Field(default=0) 
    timezone: int = Field(default=0) 
    daylight: int = Field(default=0) 

class SysJobPlan(BaseModel):
    jobId: int = Field(default=0) 
    jobMode: int = Field(default=0) 
    rainTactics: int = Field(default=0) 
    knifeHeight: int = Field(default=0) 

class SysDevErrCode(BaseModel):
    errorCode: int = Field(default=0) 

class SysJobPlanTime(BaseModel):
    planId: int = Field(default=0) 
    startJobTime: int = Field(default=0) 
    endJobTime: int = Field(default=0) 
    timeInDay: int = Field(default=0) 
    jobPlanMode: int = Field(default=0) 
    jobPlanEnable: int = Field(default=0) 
    jobPlan: SysJobPlan = Field() 
    weekDay: typing.List[int] = Field(default_factory=list) 
    timeInWeekDay: int = Field(default=0) 
    everyday: int = Field(default=0) 

class SysMowInfo(BaseModel):
    deviceState: int = Field(default=0) 
    batVal: int = Field(default=0) 
    knifeHeight: int = Field(default=0) 
    rTKstatus: int = Field(default=0) 
    rTKstars: int = Field(default=0) 

class SysCommCmd(BaseModel):
    rw: int = Field(default=0) 
    id: int = Field(default=0) 
    context: int = Field(default=0) 

class SysBorder(BaseModel):
    borderval: int = Field(default=0) 

class SysPlanJobStatus(BaseModel):
    planjobStatus: int = Field(default=0) 

class SysUploadFileProgress(BaseModel):
    bizId: str = Field(default="") 
    result: int = Field(default=0) 
    progress: int = Field(default=0) 

class SysDelJobPlan(BaseModel):
    deviceId: str = Field(default="") 
    planId: str = Field(default="") 

class SysKnifeControl(BaseModel):
    knifeStatus: int = Field(default=0) 
    knifeHeight: int = Field(default=0) 

class SysResetSystemStatus(BaseModel):
    resetStaus: int = Field(default=0) 

class systemRapidStateTunnel_msg(BaseModel):
    rapid_state_data: typing.List[int] = Field(default_factory=list) 

class systemTardStateTunnel_msg(BaseModel):
    tard_state_data: typing.List[int] = Field(default_factory=list) 

class systemUpdateBuf_msg(BaseModel):
    update_buf_data: typing.List[int] = Field(default_factory=list) 

class TimeCtrlLight(BaseModel):
    operate: int = Field(default=0) 
    enable: int = Field(default=0) 
    start_hour: int = Field(default=0) 
    end_hour: int = Field(default=0) 
    start_min: int = Field(default=0) 
    end_min: int = Field(default=0) 
    action: int = Field(default=0) 

class systemTmpCycleTx_msg(BaseModel):
    cycle_tx_data: typing.List[int] = Field(default_factory=list) 

class SysOffChipFlash(BaseModel):
    op: int = Field(default=0) 
    id: int = Field(default=0) 
    start_addr: int = Field(default=0) 
    offset: int = Field(default=0) 
    length: int = Field(default=0) 
    data: bytes = Field(default=b"") 
    code: int = Field(default=0) 
    msg: str = Field(default="") 

class mod_fw_info(BaseModel):
    type: int = Field(default=0) 
    identify: str = Field(default="") 
    version: str = Field(default="") 

class device_fw_info(BaseModel):
    result: int = Field(default=0) 
    version: str = Field(default="") 
    mod: typing.List[mod_fw_info] = Field(default_factory=list) 

class LoraCfgReq(BaseModel):
    op_: int = Field(default=0) 
    cfg: str = Field(default="") 

class LoraCfgRsp(BaseModel):
    result: int = Field(default=0) 
    op: int = Field(default=0) 
    cfg: str = Field(default="") 
    fac_cfg: str = Field(default="") 

class mow_to_app_info_t(BaseModel):
    type: int = Field(default=0) 
    cmd: int = Field(default=0) 
    mow_data: typing.List[int] = Field(default_factory=list) 

class DeviceProductTypeInfo(BaseModel):
    result: int = Field(default=0) 
    main_product_type: str = Field(default="") 
    sub_product_type: str = Field(default="") 

class MowToAppQCToolsInfo(BaseModel):
    type: int = Field(default=0) 
    time_of_duration: int = Field(default=0) 
    result: int = Field(default=0) 
    result_details: str = Field(default="") 

class ReportInfoCfg(BaseModel):
    act: int = Field(default=0) 
    timeout: int = Field(default=0) 
    period: int = Field(default=0) 
    no_change_period: int = Field(default=0) 
    count: int = Field(default=0) 
    sub: typing.List[int] = Field(default_factory=list) 

class RptConnectStatus(BaseModel):
    connect_type: int = Field(default=0) 
    ble_rssi: int = Field(default=0) 
    wifi_rssi: int = Field(default=0) 
    link_type: int = Field(default=0) 
    mnet_rssi: int = Field(default=0) 
    mnet_inet: int = Field(default=0) 
    used_net: int = Field(default=0) 

class CollectorStatus(BaseModel):
    collector_installation_status: int = Field(default=0) 

class VioSurvivalInfo(BaseModel):
    vio_survival_distance: float = Field(default=0.0) 

class RptDevStatus(BaseModel):
    sys_status: int = Field(default=0) 
    charge_state: int = Field(default=0) 
    battery_val: int = Field(default=0) 
    sensor_status: int = Field(default=0) 
    last_status: int = Field(default=0) 
    sys_time_stamp: int = Field(default=0) 
    vslam_status: int = Field(default=0) 
    mnet_info: MnetInfo = Field() 
    collector_status: CollectorStatus = Field() 
    vio_survival_info: VioSurvivalInfo = Field() 

class RptDevLocation(BaseModel):
    real_pos_x: int = Field(default=0) 
    real_pos_y: int = Field(default=0) 
    real_toward: int = Field(default=0) 
    pos_type: int = Field(default=0) 
    zone_hash: int = Field(default=0) 
    bol_hash: int = Field(default=0) 

class RptMaintain(BaseModel):
    mileage: int = Field(default=0) 
    work_time: int = Field(default=0) 
    bat_cycles: int = Field(default=0) 

class RptLora(BaseModel):
    pair_code_scan: int = Field(default=0) 
    pair_code_channel: int = Field(default=0) 
    pair_code_locid: int = Field(default=0) 
    pair_code_netid: int = Field(default=0) 
    lora_connection_status: int = Field(default=0) 

class RptRtk(BaseModel):
    status: int = Field(default=0) 
    pos_level: int = Field(default=0) 
    gps_stars: int = Field(default=0) 
    age: int = Field(default=0) 
    lat_std: int = Field(default=0) 
    lon_std: int = Field(default=0) 
    l2_stars: int = Field(default=0) 
    dis_status: int = Field(default=0) 
    top4_total_mean: int = Field(default=0) 
    co_view_stars: int = Field(default=0) 
    reset: int = Field(default=0) 
    lora_info: RptLora = Field() 

class VioToAppInfoMsg(BaseModel):
    x: float = Field(default=0.0) 
    y: float = Field(default=0.0) 
    heading: float = Field(default=0.0) 
    vio_state: int = Field(default=0) 
    brightness: int = Field(default=0) 
    detect_feature_num: int = Field(default=0) 
    track_feature_num: int = Field(default=0) 

class VisionPointMsg(BaseModel):
    x: float = Field(default=0.0) 
    y: float = Field(default=0.0) 
    z: float = Field(default=0.0) 

class VisionPointInfoMsg(BaseModel):
    label: int = Field(default=0) 
    num: int = Field(default=0) 
    vision_point: typing.List[VisionPointMsg] = Field(default_factory=list) 

class VisionStatisticMsg(BaseModel):
    mean: float = Field(default=0.0) 
    var: float = Field(default=0.0) 

class VisionStatisticInfoMsg(BaseModel):
    timestamp: float = Field(default=0.0) 
    num: int = Field(default=0) 
    vision_statistics: typing.List[VisionStatisticMsg] = Field(default_factory=list) 

class RptWork(BaseModel):
    plan: int = Field(default=0) 
    path_hash: int = Field(default=0) 
    progress: int = Field(default=0) 
    area: int = Field(default=0) 
    bp_info: int = Field(default=0) 
    bp_hash: int = Field(default=0) 
    bp_pos_x: int = Field(default=0) 
    bp_pos_y: int = Field(default=0) 
    real_path_num: int = Field(default=0) 
    path_pos_x: int = Field(default=0) 
    path_pos_y: int = Field(default=0) 
    ub_zone_hash: int = Field(default=0) 
    ub_path_hash: int = Field(default=0) 
    init_cfg_hash: int = Field(default=0) 
    ub_ecode_hash: int = Field(default=0) 
    nav_run_mode: int = Field(default=0) 
    test_mode_status: int = Field(default=0) 
    man_run_speed: int = Field(default=0) 
    nav_edit_status: int = Field(default=0) 
    knife_height: int = Field(default=0) 

class ReportInfoData(BaseModel):
    connect: RptConnectStatus = Field() 
    dev: RptDevStatus = Field() 
    fw_info: device_fw_info = Field() 
    locations: typing.List[RptDevLocation] = Field(default_factory=list) 
    maintain: RptMaintain = Field() 
    rtk: RptRtk = Field() 
    vio_to_app_info: VioToAppInfoMsg = Field() 
    vision_point_info: typing.List[VisionPointInfoMsg] = Field(default_factory=list) 
    vision_statistic_info: VisionStatisticInfoMsg = Field() 
    work: RptWork = Field() 

class MCtrlSimulationCmdData(BaseModel):
    subCmd: int = Field(default=0) 
    paramId: int = Field(default=0) 
    paramValue: typing.List[int] = Field(default_factory=list) 

class MctlSys(BaseModel):
    _one_of_dict = {"MctlSys.subSysMsg": {"fields": {"bidire_comm_cmd", "border", "device_product_type_info", "job_plan", "mow_to_app_info", "mow_to_app_qctools_info", "plan_job_del", "simulation_cmd", "system_rapid_state_tunnel", "system_tard_state_tunnel", "system_tmp_cycle_tx", "system_update_buf", "toapp_batinfo", "toapp_dev_fw_info", "toapp_err_code", "toapp_lora_cfg_rsp", "toapp_mow_info", "toapp_plan_status", "toapp_report_data", "toapp_ul_fprogress", "toapp_work_state", "todev_data_time", "todev_deljobplan", "todev_get_dev_fw_info", "todev_job_plan_time", "todev_knife_ctrl", "todev_lora_cfg_req", "todev_mow_info_up", "todev_off_chip_flash", "todev_report_cfg", "todev_reset_system", "todev_reset_system_status", "todev_time_ctrl_light", "todev_time_zone"}}}
    one_of_validator = model_validator(mode="before")(check_one_of)
    toapp_batinfo: SysBatUp = Field() 
    toapp_work_state: SysWorkState = Field() 
    todev_time_zone: SysSetTimeZone = Field() 
    todev_data_time: SysSetDateTime = Field() 
    job_plan: SysJobPlan = Field() 
    toapp_err_code: SysDevErrCode = Field() 
    todev_job_plan_time: SysJobPlanTime = Field() 
    toapp_mow_info: SysMowInfo = Field() 
    bidire_comm_cmd: SysCommCmd = Field() 
    plan_job_del: int = Field(default=0) 
    border: SysBorder = Field() 
    toapp_plan_status: SysPlanJobStatus = Field() 
    toapp_ul_fprogress: SysUploadFileProgress = Field() 
    todev_deljobplan: SysDelJobPlan = Field() 
    todev_mow_info_up: int = Field(default=0) 
    todev_knife_ctrl: SysKnifeControl = Field() 
    todev_reset_system: int = Field(default=0) 
    todev_reset_system_status: SysResetSystemStatus = Field() 
    system_rapid_state_tunnel: systemRapidStateTunnel_msg = Field() 
    system_tard_state_tunnel: systemTardStateTunnel_msg = Field() 
    system_update_buf: systemUpdateBuf_msg = Field() 
    todev_time_ctrl_light: TimeCtrlLight = Field() 
    system_tmp_cycle_tx: systemTmpCycleTx_msg = Field() 
    todev_off_chip_flash: SysOffChipFlash = Field() 
    todev_get_dev_fw_info: int = Field(default=0) 
    toapp_dev_fw_info: device_fw_info = Field() 
    todev_lora_cfg_req: LoraCfgReq = Field() 
    toapp_lora_cfg_rsp: LoraCfgRsp = Field() 
    mow_to_app_info: mow_to_app_info_t = Field() 
    device_product_type_info: DeviceProductTypeInfo = Field() 
    mow_to_app_qctools_info: MowToAppQCToolsInfo = Field() 
    todev_report_cfg: ReportInfoCfg = Field() 
    toapp_report_data: ReportInfoData = Field() 
    simulation_cmd: MCtrlSimulationCmdData = Field() 

class SysBoardType(BaseModel):
    boardType: int = Field(default=0) 

class SysSwVersion(BaseModel):
    boardType: int = Field(default=0) 
    versionLen: int = Field(default=0) 

class SysOptiLineAck(BaseModel):
    currentFrame: int = Field(default=0) 
    responesCmd: int = Field(default=0) 

class SysErrorCode(BaseModel):
    codeNo: int = Field(default=0) 

class QCAppTestConditions(BaseModel):
    cond_type: str = Field(default="") 
    int_val: int = Field(default=0) 
    float_val: float = Field(default=0.0) 
    double_val: float = Field(default=0.0) 
    string_val: str = Field(default="") 

class QCAppTestExcept(BaseModel):
    except_type: str = Field(default="") 
    conditions: typing.List[QCAppTestConditions] = Field(default_factory=list) 
