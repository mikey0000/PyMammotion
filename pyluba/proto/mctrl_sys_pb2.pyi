from pyluba.proto import dev_net_pb2 as _dev_net_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor
ERASE: Operation
OFF_PART_DEV_INFO: OffPartId
OFF_PART_DL_IMG: OffPartId
OFF_PART_FLASHDB: OffPartId
OFF_PART_MAX: OffPartId
OFF_PART_NAKEDB: OffPartId
OFF_PART_NAKEDB_BACK: OffPartId
OFF_PART_UPDINFO: OffPartId
OFF_PART_UPDINFO_BACK: OffPartId
OFF_PART_UPD_APP_IMG: OffPartId
OFF_PART_UPD_BMS_IMG: OffPartId
OFF_PART_UPD_TMP_IMG: OffPartId
READ: Operation
RIT_CONNECT: RptInfoType
RIT_DEV_LOCAL: RptInfoType
RIT_DEV_STA: RptInfoType
RIT_FW_INFO: RptInfoType
RIT_MAINTAIN: RptInfoType
RIT_RTK: RptInfoType
RIT_VIO: RptInfoType
RIT_VISION_POINT: RptInfoType
RIT_VISION_STATISTIC: RptInfoType
RIT_WORK: RptInfoType
WRITE: Operation

class CollectorStatus(_message.Message):
    __slots__ = ["collector_installation_status"]
    COLLECTOR_INSTALLATION_STATUS_FIELD_NUMBER: _ClassVar[int]
    collector_installation_status: int
    def __init__(self, collector_installation_status: _Optional[int] = ...) -> None: ...

class DeviceProductTypeInfo(_message.Message):
    __slots__ = ["main_product_type", "result", "sub_product_type"]
    MAIN_PRODUCT_TYPE_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SUB_PRODUCT_TYPE_FIELD_NUMBER: _ClassVar[int]
    main_product_type: str
    result: int
    sub_product_type: str
    def __init__(self, result: _Optional[int] = ..., main_product_type: _Optional[str] = ..., sub_product_type: _Optional[str] = ...) -> None: ...

class LoraCfgReq(_message.Message):
    __slots__ = ["cfg", "op_"]
    CFG_FIELD_NUMBER: _ClassVar[int]
    OP__FIELD_NUMBER: _ClassVar[int]
    cfg: str
    op_: int
    def __init__(self, op_: _Optional[int] = ..., cfg: _Optional[str] = ...) -> None: ...

class LoraCfgRsp(_message.Message):
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

class MCtrlSimulationCmdData(_message.Message):
    __slots__ = ["paramId", "paramValue", "subCmd"]
    PARAMID_FIELD_NUMBER: _ClassVar[int]
    PARAMVALUE_FIELD_NUMBER: _ClassVar[int]
    SUBCMD_FIELD_NUMBER: _ClassVar[int]
    paramId: int
    paramValue: _containers.RepeatedScalarFieldContainer[int]
    subCmd: int
    def __init__(self, subCmd: _Optional[int] = ..., paramId: _Optional[int] = ..., paramValue: _Optional[_Iterable[int]] = ...) -> None: ...

class MctlSys(_message.Message):
    __slots__ = ["bidire_comm_cmd", "border", "device_product_type_info", "job_plan", "mow_to_app_info", "mow_to_app_qctools_info", "plan_job_del", "simulation_cmd", "system_rapid_state_tunnel", "system_tard_state_tunnel", "system_tmp_cycle_tx", "system_update_buf", "toapp_batinfo", "toapp_dev_fw_info", "toapp_err_code", "toapp_lora_cfg_rsp", "toapp_mow_info", "toapp_plan_status", "toapp_report_data", "toapp_ul_fprogress", "toapp_work_state", "todev_data_time", "todev_deljobplan", "todev_get_dev_fw_info", "todev_job_plan_time", "todev_knife_ctrl", "todev_lora_cfg_req", "todev_mow_info_up", "todev_off_chip_flash", "todev_report_cfg", "todev_reset_system", "todev_reset_system_status", "todev_time_ctrl_light", "todev_time_zone"]
    BIDIRE_COMM_CMD_FIELD_NUMBER: _ClassVar[int]
    BORDER_FIELD_NUMBER: _ClassVar[int]
    DEVICE_PRODUCT_TYPE_INFO_FIELD_NUMBER: _ClassVar[int]
    JOB_PLAN_FIELD_NUMBER: _ClassVar[int]
    MOW_TO_APP_INFO_FIELD_NUMBER: _ClassVar[int]
    MOW_TO_APP_QCTOOLS_INFO_FIELD_NUMBER: _ClassVar[int]
    PLAN_JOB_DEL_FIELD_NUMBER: _ClassVar[int]
    SIMULATION_CMD_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_RAPID_STATE_TUNNEL_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_TARD_STATE_TUNNEL_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_TMP_CYCLE_TX_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_UPDATE_BUF_FIELD_NUMBER: _ClassVar[int]
    TOAPP_BATINFO_FIELD_NUMBER: _ClassVar[int]
    TOAPP_DEV_FW_INFO_FIELD_NUMBER: _ClassVar[int]
    TOAPP_ERR_CODE_FIELD_NUMBER: _ClassVar[int]
    TOAPP_LORA_CFG_RSP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_MOW_INFO_FIELD_NUMBER: _ClassVar[int]
    TOAPP_PLAN_STATUS_FIELD_NUMBER: _ClassVar[int]
    TOAPP_REPORT_DATA_FIELD_NUMBER: _ClassVar[int]
    TOAPP_UL_FPROGRESS_FIELD_NUMBER: _ClassVar[int]
    TOAPP_WORK_STATE_FIELD_NUMBER: _ClassVar[int]
    TODEV_DATA_TIME_FIELD_NUMBER: _ClassVar[int]
    TODEV_DELJOBPLAN_FIELD_NUMBER: _ClassVar[int]
    TODEV_GET_DEV_FW_INFO_FIELD_NUMBER: _ClassVar[int]
    TODEV_JOB_PLAN_TIME_FIELD_NUMBER: _ClassVar[int]
    TODEV_KNIFE_CTRL_FIELD_NUMBER: _ClassVar[int]
    TODEV_LORA_CFG_REQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_MOW_INFO_UP_FIELD_NUMBER: _ClassVar[int]
    TODEV_OFF_CHIP_FLASH_FIELD_NUMBER: _ClassVar[int]
    TODEV_REPORT_CFG_FIELD_NUMBER: _ClassVar[int]
    TODEV_RESET_SYSTEM_FIELD_NUMBER: _ClassVar[int]
    TODEV_RESET_SYSTEM_STATUS_FIELD_NUMBER: _ClassVar[int]
    TODEV_TIME_CTRL_LIGHT_FIELD_NUMBER: _ClassVar[int]
    TODEV_TIME_ZONE_FIELD_NUMBER: _ClassVar[int]
    bidire_comm_cmd: SysCommCmd
    border: SysBorder
    device_product_type_info: DeviceProductTypeInfo
    job_plan: SysJobPlan
    mow_to_app_info: mow_to_app_info_t
    mow_to_app_qctools_info: MowToAppQCToolsInfo
    plan_job_del: int
    simulation_cmd: MCtrlSimulationCmdData
    system_rapid_state_tunnel: systemRapidStateTunnel_msg
    system_tard_state_tunnel: systemTardStateTunnel_msg
    system_tmp_cycle_tx: systemTmpCycleTx_msg
    system_update_buf: systemUpdateBuf_msg
    toapp_batinfo: SysBatUp
    toapp_dev_fw_info: device_fw_info
    toapp_err_code: SysDevErrCode
    toapp_lora_cfg_rsp: LoraCfgRsp
    toapp_mow_info: SysMowInfo
    toapp_plan_status: SysPlanJobStatus
    toapp_report_data: ReportInfoData
    toapp_ul_fprogress: SysUploadFileProgress
    toapp_work_state: SysWorkState
    todev_data_time: SysSetDateTime
    todev_deljobplan: SysDelJobPlan
    todev_get_dev_fw_info: int
    todev_job_plan_time: SysJobPlanTime
    todev_knife_ctrl: SysKnifeControl
    todev_lora_cfg_req: LoraCfgReq
    todev_mow_info_up: int
    todev_off_chip_flash: SysOffChipFlash
    todev_report_cfg: ReportInfoCfg
    todev_reset_system: int
    todev_reset_system_status: SysResetSystemStatus
    todev_time_ctrl_light: TimeCtrlLight
    todev_time_zone: SysSetTimeZone
    def __init__(self, toapp_batinfo: _Optional[_Union[SysBatUp, _Mapping]] = ..., toapp_work_state: _Optional[_Union[SysWorkState, _Mapping]] = ..., todev_time_zone: _Optional[_Union[SysSetTimeZone, _Mapping]] = ..., todev_data_time: _Optional[_Union[SysSetDateTime, _Mapping]] = ..., job_plan: _Optional[_Union[SysJobPlan, _Mapping]] = ..., toapp_err_code: _Optional[_Union[SysDevErrCode, _Mapping]] = ..., todev_job_plan_time: _Optional[_Union[SysJobPlanTime, _Mapping]] = ..., toapp_mow_info: _Optional[_Union[SysMowInfo, _Mapping]] = ..., bidire_comm_cmd: _Optional[_Union[SysCommCmd, _Mapping]] = ..., plan_job_del: _Optional[int] = ..., border: _Optional[_Union[SysBorder, _Mapping]] = ..., toapp_plan_status: _Optional[_Union[SysPlanJobStatus, _Mapping]] = ..., toapp_ul_fprogress: _Optional[_Union[SysUploadFileProgress, _Mapping]] = ..., todev_deljobplan: _Optional[_Union[SysDelJobPlan, _Mapping]] = ..., todev_mow_info_up: _Optional[int] = ..., todev_knife_ctrl: _Optional[_Union[SysKnifeControl, _Mapping]] = ..., todev_reset_system: _Optional[int] = ..., todev_reset_system_status: _Optional[_Union[SysResetSystemStatus, _Mapping]] = ..., system_rapid_state_tunnel: _Optional[_Union[systemRapidStateTunnel_msg, _Mapping]] = ..., system_tard_state_tunnel: _Optional[_Union[systemTardStateTunnel_msg, _Mapping]] = ..., system_update_buf: _Optional[_Union[systemUpdateBuf_msg, _Mapping]] = ..., todev_time_ctrl_light: _Optional[_Union[TimeCtrlLight, _Mapping]] = ..., system_tmp_cycle_tx: _Optional[_Union[systemTmpCycleTx_msg, _Mapping]] = ..., todev_off_chip_flash: _Optional[_Union[SysOffChipFlash, _Mapping]] = ..., todev_get_dev_fw_info: _Optional[int] = ..., toapp_dev_fw_info: _Optional[_Union[device_fw_info, _Mapping]] = ..., todev_lora_cfg_req: _Optional[_Union[LoraCfgReq, _Mapping]] = ..., toapp_lora_cfg_rsp: _Optional[_Union[LoraCfgRsp, _Mapping]] = ..., mow_to_app_info: _Optional[_Union[mow_to_app_info_t, _Mapping]] = ..., device_product_type_info: _Optional[_Union[DeviceProductTypeInfo, _Mapping]] = ..., mow_to_app_qctools_info: _Optional[_Union[MowToAppQCToolsInfo, _Mapping]] = ..., todev_report_cfg: _Optional[_Union[ReportInfoCfg, _Mapping]] = ..., toapp_report_data: _Optional[_Union[ReportInfoData, _Mapping]] = ..., simulation_cmd: _Optional[_Union[MCtrlSimulationCmdData, _Mapping]] = ...) -> None: ...

class MowToAppQCToolsInfo(_message.Message):
    __slots__ = ["result", "result_details", "time_of_duration", "type"]
    EXCEPT_FIELD_NUMBER: _ClassVar[int]
    RESULT_DETAILS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    TIME_OF_DURATION_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    result: int
    result_details: str
    time_of_duration: int
    type: int
    def __init__(self, type: _Optional[int] = ..., time_of_duration: _Optional[int] = ..., result: _Optional[int] = ..., result_details: _Optional[str] = ..., **kwargs) -> None: ...

class QCAppTestConditions(_message.Message):
    __slots__ = ["cond_type", "double_val", "float_val", "int_val", "string_val"]
    COND_TYPE_FIELD_NUMBER: _ClassVar[int]
    DOUBLE_VAL_FIELD_NUMBER: _ClassVar[int]
    FLOAT_VAL_FIELD_NUMBER: _ClassVar[int]
    INT_VAL_FIELD_NUMBER: _ClassVar[int]
    STRING_VAL_FIELD_NUMBER: _ClassVar[int]
    cond_type: str
    double_val: float
    float_val: float
    int_val: int
    string_val: str
    def __init__(self, cond_type: _Optional[str] = ..., int_val: _Optional[int] = ..., float_val: _Optional[float] = ..., double_val: _Optional[float] = ..., string_val: _Optional[str] = ...) -> None: ...

class QCAppTestExcept(_message.Message):
    __slots__ = ["conditions", "except_type"]
    CONDITIONS_FIELD_NUMBER: _ClassVar[int]
    EXCEPT_TYPE_FIELD_NUMBER: _ClassVar[int]
    conditions: _containers.RepeatedCompositeFieldContainer[QCAppTestConditions]
    except_type: str
    def __init__(self, except_type: _Optional[str] = ..., conditions: _Optional[_Iterable[_Union[QCAppTestConditions, _Mapping]]] = ...) -> None: ...

class ReportInfoCfg(_message.Message):
    __slots__ = ["act", "count", "no_change_period", "period", "sub", "timeout"]
    ACT_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    NO_CHANGE_PERIOD_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    SUB_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    act: int
    count: int
    no_change_period: int
    period: int
    sub: _containers.RepeatedScalarFieldContainer[RptInfoType]
    timeout: int
    def __init__(self, act: _Optional[int] = ..., timeout: _Optional[int] = ..., period: _Optional[int] = ..., no_change_period: _Optional[int] = ..., count: _Optional[int] = ..., sub: _Optional[_Iterable[_Union[RptInfoType, str]]] = ...) -> None: ...

class ReportInfoData(_message.Message):
    __slots__ = ["connect", "dev", "fw_info", "locations", "maintain", "rtk", "vio_to_app_info", "vision_point_info", "vision_statistic_info", "work"]
    CONNECT_FIELD_NUMBER: _ClassVar[int]
    DEV_FIELD_NUMBER: _ClassVar[int]
    FW_INFO_FIELD_NUMBER: _ClassVar[int]
    LOCATIONS_FIELD_NUMBER: _ClassVar[int]
    MAINTAIN_FIELD_NUMBER: _ClassVar[int]
    RTK_FIELD_NUMBER: _ClassVar[int]
    VIO_TO_APP_INFO_FIELD_NUMBER: _ClassVar[int]
    VISION_POINT_INFO_FIELD_NUMBER: _ClassVar[int]
    VISION_STATISTIC_INFO_FIELD_NUMBER: _ClassVar[int]
    WORK_FIELD_NUMBER: _ClassVar[int]
    connect: RptConnectStatus
    dev: RptDevStatus
    fw_info: device_fw_info
    locations: _containers.RepeatedCompositeFieldContainer[RptDevLocation]
    maintain: RptMaintain
    rtk: RptRtk
    vio_to_app_info: VioToAppInfoMsg
    vision_point_info: _containers.RepeatedCompositeFieldContainer[VisionPointInfoMsg]
    vision_statistic_info: VisionStatisticInfoMsg
    work: RptWork
    def __init__(self, connect: _Optional[_Union[RptConnectStatus, _Mapping]] = ..., dev: _Optional[_Union[RptDevStatus, _Mapping]] = ..., fw_info: _Optional[_Union[device_fw_info, _Mapping]] = ..., locations: _Optional[_Iterable[_Union[RptDevLocation, _Mapping]]] = ..., maintain: _Optional[_Union[RptMaintain, _Mapping]] = ..., rtk: _Optional[_Union[RptRtk, _Mapping]] = ..., vio_to_app_info: _Optional[_Union[VioToAppInfoMsg, _Mapping]] = ..., vision_point_info: _Optional[_Iterable[_Union[VisionPointInfoMsg, _Mapping]]] = ..., vision_statistic_info: _Optional[_Union[VisionStatisticInfoMsg, _Mapping]] = ..., work: _Optional[_Union[RptWork, _Mapping]] = ...) -> None: ...

class RptConnectStatus(_message.Message):
    __slots__ = ["ble_rssi", "connect_type", "link_type", "mnet_inet", "mnet_rssi", "used_net", "wifi_rssi"]
    BLE_RSSI_FIELD_NUMBER: _ClassVar[int]
    CONNECT_TYPE_FIELD_NUMBER: _ClassVar[int]
    LINK_TYPE_FIELD_NUMBER: _ClassVar[int]
    MNET_INET_FIELD_NUMBER: _ClassVar[int]
    MNET_RSSI_FIELD_NUMBER: _ClassVar[int]
    USED_NET_FIELD_NUMBER: _ClassVar[int]
    WIFI_RSSI_FIELD_NUMBER: _ClassVar[int]
    ble_rssi: int
    connect_type: int
    link_type: int
    mnet_inet: int
    mnet_rssi: int
    used_net: int
    wifi_rssi: int
    def __init__(self, connect_type: _Optional[int] = ..., ble_rssi: _Optional[int] = ..., wifi_rssi: _Optional[int] = ..., link_type: _Optional[int] = ..., mnet_rssi: _Optional[int] = ..., mnet_inet: _Optional[int] = ..., used_net: _Optional[int] = ...) -> None: ...

class RptDevLocation(_message.Message):
    __slots__ = ["bol_hash", "pos_type", "real_pos_x", "real_pos_y", "real_toward", "zone_hash"]
    BOL_HASH_FIELD_NUMBER: _ClassVar[int]
    POS_TYPE_FIELD_NUMBER: _ClassVar[int]
    REAL_POS_X_FIELD_NUMBER: _ClassVar[int]
    REAL_POS_Y_FIELD_NUMBER: _ClassVar[int]
    REAL_TOWARD_FIELD_NUMBER: _ClassVar[int]
    ZONE_HASH_FIELD_NUMBER: _ClassVar[int]
    bol_hash: int
    pos_type: int
    real_pos_x: int
    real_pos_y: int
    real_toward: int
    zone_hash: int
    def __init__(self, real_pos_x: _Optional[int] = ..., real_pos_y: _Optional[int] = ..., real_toward: _Optional[int] = ..., pos_type: _Optional[int] = ..., zone_hash: _Optional[int] = ..., bol_hash: _Optional[int] = ...) -> None: ...

class RptDevStatus(_message.Message):
    __slots__ = ["battery_val", "charge_state", "collector_status", "last_status", "mnet_info", "sensor_status", "sys_status", "sys_time_stamp", "vio_survival_info", "vslam_status"]
    BATTERY_VAL_FIELD_NUMBER: _ClassVar[int]
    CHARGE_STATE_FIELD_NUMBER: _ClassVar[int]
    COLLECTOR_STATUS_FIELD_NUMBER: _ClassVar[int]
    LAST_STATUS_FIELD_NUMBER: _ClassVar[int]
    MNET_INFO_FIELD_NUMBER: _ClassVar[int]
    SENSOR_STATUS_FIELD_NUMBER: _ClassVar[int]
    SYS_STATUS_FIELD_NUMBER: _ClassVar[int]
    SYS_TIME_STAMP_FIELD_NUMBER: _ClassVar[int]
    VIO_SURVIVAL_INFO_FIELD_NUMBER: _ClassVar[int]
    VSLAM_STATUS_FIELD_NUMBER: _ClassVar[int]
    battery_val: int
    charge_state: int
    collector_status: CollectorStatus
    last_status: int
    mnet_info: _dev_net_pb2.MnetInfo
    sensor_status: int
    sys_status: int
    sys_time_stamp: int
    vio_survival_info: VioSurvivalInfo
    vslam_status: int
    def __init__(self, sys_status: _Optional[int] = ..., charge_state: _Optional[int] = ..., battery_val: _Optional[int] = ..., sensor_status: _Optional[int] = ..., last_status: _Optional[int] = ..., sys_time_stamp: _Optional[int] = ..., vslam_status: _Optional[int] = ..., mnet_info: _Optional[_Union[_dev_net_pb2.MnetInfo, _Mapping]] = ..., collector_status: _Optional[_Union[CollectorStatus, _Mapping]] = ..., vio_survival_info: _Optional[_Union[VioSurvivalInfo, _Mapping]] = ...) -> None: ...

class RptLora(_message.Message):
    __slots__ = ["lora_connection_status", "pair_code_channel", "pair_code_locid", "pair_code_netid", "pair_code_scan"]
    LORA_CONNECTION_STATUS_FIELD_NUMBER: _ClassVar[int]
    PAIR_CODE_CHANNEL_FIELD_NUMBER: _ClassVar[int]
    PAIR_CODE_LOCID_FIELD_NUMBER: _ClassVar[int]
    PAIR_CODE_NETID_FIELD_NUMBER: _ClassVar[int]
    PAIR_CODE_SCAN_FIELD_NUMBER: _ClassVar[int]
    lora_connection_status: int
    pair_code_channel: int
    pair_code_locid: int
    pair_code_netid: int
    pair_code_scan: int
    def __init__(self, pair_code_scan: _Optional[int] = ..., pair_code_channel: _Optional[int] = ..., pair_code_locid: _Optional[int] = ..., pair_code_netid: _Optional[int] = ..., lora_connection_status: _Optional[int] = ...) -> None: ...

class RptMaintain(_message.Message):
    __slots__ = ["bat_cycles", "mileage", "work_time"]
    BAT_CYCLES_FIELD_NUMBER: _ClassVar[int]
    MILEAGE_FIELD_NUMBER: _ClassVar[int]
    WORK_TIME_FIELD_NUMBER: _ClassVar[int]
    bat_cycles: int
    mileage: int
    work_time: int
    def __init__(self, mileage: _Optional[int] = ..., work_time: _Optional[int] = ..., bat_cycles: _Optional[int] = ...) -> None: ...

class RptRtk(_message.Message):
    __slots__ = ["age", "co_view_stars", "dis_status", "gps_stars", "l2_stars", "lat_std", "lon_std", "lora_info", "pos_level", "reset", "status", "top4_total_mean"]
    AGE_FIELD_NUMBER: _ClassVar[int]
    CO_VIEW_STARS_FIELD_NUMBER: _ClassVar[int]
    DIS_STATUS_FIELD_NUMBER: _ClassVar[int]
    GPS_STARS_FIELD_NUMBER: _ClassVar[int]
    L2_STARS_FIELD_NUMBER: _ClassVar[int]
    LAT_STD_FIELD_NUMBER: _ClassVar[int]
    LON_STD_FIELD_NUMBER: _ClassVar[int]
    LORA_INFO_FIELD_NUMBER: _ClassVar[int]
    POS_LEVEL_FIELD_NUMBER: _ClassVar[int]
    RESET_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    TOP4_TOTAL_MEAN_FIELD_NUMBER: _ClassVar[int]
    age: int
    co_view_stars: int
    dis_status: int
    gps_stars: int
    l2_stars: int
    lat_std: int
    lon_std: int
    lora_info: RptLora
    pos_level: int
    reset: int
    status: int
    top4_total_mean: int
    def __init__(self, status: _Optional[int] = ..., pos_level: _Optional[int] = ..., gps_stars: _Optional[int] = ..., age: _Optional[int] = ..., lat_std: _Optional[int] = ..., lon_std: _Optional[int] = ..., l2_stars: _Optional[int] = ..., dis_status: _Optional[int] = ..., top4_total_mean: _Optional[int] = ..., co_view_stars: _Optional[int] = ..., reset: _Optional[int] = ..., lora_info: _Optional[_Union[RptLora, _Mapping]] = ...) -> None: ...

class RptWork(_message.Message):
    __slots__ = ["area", "bp_hash", "bp_info", "bp_pos_x", "bp_pos_y", "init_cfg_hash", "knife_height", "man_run_speed", "nav_edit_status", "nav_run_mode", "path_hash", "path_pos_x", "path_pos_y", "plan", "progress", "real_path_num", "test_mode_status", "ub_ecode_hash", "ub_path_hash", "ub_zone_hash"]
    AREA_FIELD_NUMBER: _ClassVar[int]
    BP_HASH_FIELD_NUMBER: _ClassVar[int]
    BP_INFO_FIELD_NUMBER: _ClassVar[int]
    BP_POS_X_FIELD_NUMBER: _ClassVar[int]
    BP_POS_Y_FIELD_NUMBER: _ClassVar[int]
    INIT_CFG_HASH_FIELD_NUMBER: _ClassVar[int]
    KNIFE_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    MAN_RUN_SPEED_FIELD_NUMBER: _ClassVar[int]
    NAV_EDIT_STATUS_FIELD_NUMBER: _ClassVar[int]
    NAV_RUN_MODE_FIELD_NUMBER: _ClassVar[int]
    PATH_HASH_FIELD_NUMBER: _ClassVar[int]
    PATH_POS_X_FIELD_NUMBER: _ClassVar[int]
    PATH_POS_Y_FIELD_NUMBER: _ClassVar[int]
    PLAN_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    REAL_PATH_NUM_FIELD_NUMBER: _ClassVar[int]
    TEST_MODE_STATUS_FIELD_NUMBER: _ClassVar[int]
    UB_ECODE_HASH_FIELD_NUMBER: _ClassVar[int]
    UB_PATH_HASH_FIELD_NUMBER: _ClassVar[int]
    UB_ZONE_HASH_FIELD_NUMBER: _ClassVar[int]
    area: int
    bp_hash: int
    bp_info: int
    bp_pos_x: int
    bp_pos_y: int
    init_cfg_hash: int
    knife_height: int
    man_run_speed: int
    nav_edit_status: int
    nav_run_mode: int
    path_hash: int
    path_pos_x: int
    path_pos_y: int
    plan: int
    progress: int
    real_path_num: int
    test_mode_status: int
    ub_ecode_hash: int
    ub_path_hash: int
    ub_zone_hash: int
    def __init__(self, plan: _Optional[int] = ..., path_hash: _Optional[int] = ..., progress: _Optional[int] = ..., area: _Optional[int] = ..., bp_info: _Optional[int] = ..., bp_hash: _Optional[int] = ..., bp_pos_x: _Optional[int] = ..., bp_pos_y: _Optional[int] = ..., real_path_num: _Optional[int] = ..., path_pos_x: _Optional[int] = ..., path_pos_y: _Optional[int] = ..., ub_zone_hash: _Optional[int] = ..., ub_path_hash: _Optional[int] = ..., init_cfg_hash: _Optional[int] = ..., ub_ecode_hash: _Optional[int] = ..., nav_run_mode: _Optional[int] = ..., test_mode_status: _Optional[int] = ..., man_run_speed: _Optional[int] = ..., nav_edit_status: _Optional[int] = ..., knife_height: _Optional[int] = ...) -> None: ...

class SysBatUp(_message.Message):
    __slots__ = ["batVal"]
    BATVAL_FIELD_NUMBER: _ClassVar[int]
    batVal: int
    def __init__(self, batVal: _Optional[int] = ...) -> None: ...

class SysBoardType(_message.Message):
    __slots__ = ["boardType"]
    BOARDTYPE_FIELD_NUMBER: _ClassVar[int]
    boardType: int
    def __init__(self, boardType: _Optional[int] = ...) -> None: ...

class SysBorder(_message.Message):
    __slots__ = ["borderval"]
    BORDERVAL_FIELD_NUMBER: _ClassVar[int]
    borderval: int
    def __init__(self, borderval: _Optional[int] = ...) -> None: ...

class SysCommCmd(_message.Message):
    __slots__ = ["context", "id", "rw"]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    RW_FIELD_NUMBER: _ClassVar[int]
    context: int
    id: int
    rw: int
    def __init__(self, rw: _Optional[int] = ..., id: _Optional[int] = ..., context: _Optional[int] = ...) -> None: ...

class SysDelJobPlan(_message.Message):
    __slots__ = ["deviceId", "planId"]
    DEVICEID_FIELD_NUMBER: _ClassVar[int]
    PLANID_FIELD_NUMBER: _ClassVar[int]
    deviceId: str
    planId: str
    def __init__(self, deviceId: _Optional[str] = ..., planId: _Optional[str] = ...) -> None: ...

class SysDevErrCode(_message.Message):
    __slots__ = ["errorCode"]
    ERRORCODE_FIELD_NUMBER: _ClassVar[int]
    errorCode: int
    def __init__(self, errorCode: _Optional[int] = ...) -> None: ...

class SysErrorCode(_message.Message):
    __slots__ = ["codeNo"]
    CODENO_FIELD_NUMBER: _ClassVar[int]
    codeNo: int
    def __init__(self, codeNo: _Optional[int] = ...) -> None: ...

class SysJobPlan(_message.Message):
    __slots__ = ["jobId", "jobMode", "knifeHeight", "rainTactics"]
    JOBID_FIELD_NUMBER: _ClassVar[int]
    JOBMODE_FIELD_NUMBER: _ClassVar[int]
    KNIFEHEIGHT_FIELD_NUMBER: _ClassVar[int]
    RAINTACTICS_FIELD_NUMBER: _ClassVar[int]
    jobId: int
    jobMode: int
    knifeHeight: int
    rainTactics: int
    def __init__(self, jobId: _Optional[int] = ..., jobMode: _Optional[int] = ..., rainTactics: _Optional[int] = ..., knifeHeight: _Optional[int] = ...) -> None: ...

class SysJobPlanTime(_message.Message):
    __slots__ = ["endJobTime", "everyday", "jobPlan", "jobPlanEnable", "jobPlanMode", "planId", "startJobTime", "timeInDay", "timeInWeekDay", "weekDay"]
    ENDJOBTIME_FIELD_NUMBER: _ClassVar[int]
    EVERYDAY_FIELD_NUMBER: _ClassVar[int]
    JOBPLANENABLE_FIELD_NUMBER: _ClassVar[int]
    JOBPLANMODE_FIELD_NUMBER: _ClassVar[int]
    JOBPLAN_FIELD_NUMBER: _ClassVar[int]
    PLANID_FIELD_NUMBER: _ClassVar[int]
    STARTJOBTIME_FIELD_NUMBER: _ClassVar[int]
    TIMEINDAY_FIELD_NUMBER: _ClassVar[int]
    TIMEINWEEKDAY_FIELD_NUMBER: _ClassVar[int]
    WEEKDAY_FIELD_NUMBER: _ClassVar[int]
    endJobTime: int
    everyday: int
    jobPlan: SysJobPlan
    jobPlanEnable: int
    jobPlanMode: int
    planId: int
    startJobTime: int
    timeInDay: int
    timeInWeekDay: int
    weekDay: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, planId: _Optional[int] = ..., startJobTime: _Optional[int] = ..., endJobTime: _Optional[int] = ..., timeInDay: _Optional[int] = ..., jobPlanMode: _Optional[int] = ..., jobPlanEnable: _Optional[int] = ..., jobPlan: _Optional[_Union[SysJobPlan, _Mapping]] = ..., weekDay: _Optional[_Iterable[int]] = ..., timeInWeekDay: _Optional[int] = ..., everyday: _Optional[int] = ...) -> None: ...

class SysKnifeControl(_message.Message):
    __slots__ = ["knifeHeight", "knifeStatus"]
    KNIFEHEIGHT_FIELD_NUMBER: _ClassVar[int]
    KNIFESTATUS_FIELD_NUMBER: _ClassVar[int]
    knifeHeight: int
    knifeStatus: int
    def __init__(self, knifeStatus: _Optional[int] = ..., knifeHeight: _Optional[int] = ...) -> None: ...

class SysMowInfo(_message.Message):
    __slots__ = ["batVal", "deviceState", "knifeHeight", "rTKstars", "rTKstatus"]
    BATVAL_FIELD_NUMBER: _ClassVar[int]
    DEVICESTATE_FIELD_NUMBER: _ClassVar[int]
    KNIFEHEIGHT_FIELD_NUMBER: _ClassVar[int]
    RTKSTARS_FIELD_NUMBER: _ClassVar[int]
    RTKSTATUS_FIELD_NUMBER: _ClassVar[int]
    batVal: int
    deviceState: int
    knifeHeight: int
    rTKstars: int
    rTKstatus: int
    def __init__(self, deviceState: _Optional[int] = ..., batVal: _Optional[int] = ..., knifeHeight: _Optional[int] = ..., rTKstatus: _Optional[int] = ..., rTKstars: _Optional[int] = ...) -> None: ...

class SysOffChipFlash(_message.Message):
    __slots__ = ["code", "data", "id", "length", "msg", "offset", "op", "start_addr"]
    CODE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    LENGTH_FIELD_NUMBER: _ClassVar[int]
    MSG_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    OP_FIELD_NUMBER: _ClassVar[int]
    START_ADDR_FIELD_NUMBER: _ClassVar[int]
    code: int
    data: bytes
    id: int
    length: int
    msg: str
    offset: int
    op: int
    start_addr: int
    def __init__(self, op: _Optional[int] = ..., id: _Optional[int] = ..., start_addr: _Optional[int] = ..., offset: _Optional[int] = ..., length: _Optional[int] = ..., data: _Optional[bytes] = ..., code: _Optional[int] = ..., msg: _Optional[str] = ...) -> None: ...

class SysOptiLineAck(_message.Message):
    __slots__ = ["currentFrame", "responesCmd"]
    CURRENTFRAME_FIELD_NUMBER: _ClassVar[int]
    RESPONESCMD_FIELD_NUMBER: _ClassVar[int]
    currentFrame: int
    responesCmd: int
    def __init__(self, currentFrame: _Optional[int] = ..., responesCmd: _Optional[int] = ...) -> None: ...

class SysPlanJobStatus(_message.Message):
    __slots__ = ["planjobStatus"]
    PLANJOBSTATUS_FIELD_NUMBER: _ClassVar[int]
    planjobStatus: int
    def __init__(self, planjobStatus: _Optional[int] = ...) -> None: ...

class SysResetSystemStatus(_message.Message):
    __slots__ = ["resetStaus"]
    RESETSTAUS_FIELD_NUMBER: _ClassVar[int]
    resetStaus: int
    def __init__(self, resetStaus: _Optional[int] = ...) -> None: ...

class SysSetDateTime(_message.Message):
    __slots__ = ["date", "daylight", "hours", "minutes", "month", "seconds", "timezone", "week", "year"]
    DATE_FIELD_NUMBER: _ClassVar[int]
    DAYLIGHT_FIELD_NUMBER: _ClassVar[int]
    HOURS_FIELD_NUMBER: _ClassVar[int]
    MINUTES_FIELD_NUMBER: _ClassVar[int]
    MONTH_FIELD_NUMBER: _ClassVar[int]
    SECONDS_FIELD_NUMBER: _ClassVar[int]
    TIMEZONE_FIELD_NUMBER: _ClassVar[int]
    WEEK_FIELD_NUMBER: _ClassVar[int]
    YEAR_FIELD_NUMBER: _ClassVar[int]
    date: int
    daylight: int
    hours: int
    minutes: int
    month: int
    seconds: int
    timezone: int
    week: int
    year: int
    def __init__(self, year: _Optional[int] = ..., month: _Optional[int] = ..., date: _Optional[int] = ..., week: _Optional[int] = ..., hours: _Optional[int] = ..., minutes: _Optional[int] = ..., seconds: _Optional[int] = ..., timezone: _Optional[int] = ..., daylight: _Optional[int] = ...) -> None: ...

class SysSetTimeZone(_message.Message):
    __slots__ = ["timeArea", "timeStamp"]
    TIMEAREA_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    timeArea: int
    timeStamp: int
    def __init__(self, timeStamp: _Optional[int] = ..., timeArea: _Optional[int] = ...) -> None: ...

class SysSwVersion(_message.Message):
    __slots__ = ["boardType", "versionLen"]
    BOARDTYPE_FIELD_NUMBER: _ClassVar[int]
    VERSIONLEN_FIELD_NUMBER: _ClassVar[int]
    boardType: int
    versionLen: int
    def __init__(self, boardType: _Optional[int] = ..., versionLen: _Optional[int] = ...) -> None: ...

class SysUploadFileProgress(_message.Message):
    __slots__ = ["bizId", "progress", "result"]
    BIZID_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    bizId: str
    progress: int
    result: int
    def __init__(self, bizId: _Optional[str] = ..., result: _Optional[int] = ..., progress: _Optional[int] = ...) -> None: ...

class SysWorkState(_message.Message):
    __slots__ = ["chargeState", "cmHash", "deviceState", "pathHash"]
    CHARGESTATE_FIELD_NUMBER: _ClassVar[int]
    CMHASH_FIELD_NUMBER: _ClassVar[int]
    DEVICESTATE_FIELD_NUMBER: _ClassVar[int]
    PATHHASH_FIELD_NUMBER: _ClassVar[int]
    chargeState: int
    cmHash: int
    deviceState: int
    pathHash: int
    def __init__(self, deviceState: _Optional[int] = ..., chargeState: _Optional[int] = ..., cmHash: _Optional[int] = ..., pathHash: _Optional[int] = ...) -> None: ...

class TimeCtrlLight(_message.Message):
    __slots__ = ["action", "enable", "end_hour", "end_min", "operate", "start_hour", "start_min"]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    ENABLE_FIELD_NUMBER: _ClassVar[int]
    END_HOUR_FIELD_NUMBER: _ClassVar[int]
    END_MIN_FIELD_NUMBER: _ClassVar[int]
    OPERATE_FIELD_NUMBER: _ClassVar[int]
    START_HOUR_FIELD_NUMBER: _ClassVar[int]
    START_MIN_FIELD_NUMBER: _ClassVar[int]
    action: int
    enable: int
    end_hour: int
    end_min: int
    operate: int
    start_hour: int
    start_min: int
    def __init__(self, operate: _Optional[int] = ..., enable: _Optional[int] = ..., start_hour: _Optional[int] = ..., end_hour: _Optional[int] = ..., start_min: _Optional[int] = ..., end_min: _Optional[int] = ..., action: _Optional[int] = ...) -> None: ...

class VioSurvivalInfo(_message.Message):
    __slots__ = ["vio_survival_distance"]
    VIO_SURVIVAL_DISTANCE_FIELD_NUMBER: _ClassVar[int]
    vio_survival_distance: float
    def __init__(self, vio_survival_distance: _Optional[float] = ...) -> None: ...

class VioToAppInfoMsg(_message.Message):
    __slots__ = ["brightness", "detect_feature_num", "heading", "track_feature_num", "vio_state", "x", "y"]
    BRIGHTNESS_FIELD_NUMBER: _ClassVar[int]
    DETECT_FEATURE_NUM_FIELD_NUMBER: _ClassVar[int]
    HEADING_FIELD_NUMBER: _ClassVar[int]
    TRACK_FEATURE_NUM_FIELD_NUMBER: _ClassVar[int]
    VIO_STATE_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    brightness: int
    detect_feature_num: int
    heading: float
    track_feature_num: int
    vio_state: int
    x: float
    y: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., heading: _Optional[float] = ..., vio_state: _Optional[int] = ..., brightness: _Optional[int] = ..., detect_feature_num: _Optional[int] = ..., track_feature_num: _Optional[int] = ...) -> None: ...

class VisionPointInfoMsg(_message.Message):
    __slots__ = ["label", "num", "vision_point"]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    NUM_FIELD_NUMBER: _ClassVar[int]
    VISION_POINT_FIELD_NUMBER: _ClassVar[int]
    label: int
    num: int
    vision_point: _containers.RepeatedCompositeFieldContainer[VisionPointMsg]
    def __init__(self, label: _Optional[int] = ..., num: _Optional[int] = ..., vision_point: _Optional[_Iterable[_Union[VisionPointMsg, _Mapping]]] = ...) -> None: ...

class VisionPointMsg(_message.Message):
    __slots__ = ["x", "y", "z"]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    z: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., z: _Optional[float] = ...) -> None: ...

class VisionStatisticInfoMsg(_message.Message):
    __slots__ = ["num", "timestamp", "vision_statistics"]
    NUM_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    VISION_STATISTICS_FIELD_NUMBER: _ClassVar[int]
    num: int
    timestamp: float
    vision_statistics: _containers.RepeatedCompositeFieldContainer[VisionStatisticMsg]
    def __init__(self, timestamp: _Optional[float] = ..., num: _Optional[int] = ..., vision_statistics: _Optional[_Iterable[_Union[VisionStatisticMsg, _Mapping]]] = ...) -> None: ...

class VisionStatisticMsg(_message.Message):
    __slots__ = ["mean", "var"]
    MEAN_FIELD_NUMBER: _ClassVar[int]
    VAR_FIELD_NUMBER: _ClassVar[int]
    mean: float
    var: float
    def __init__(self, mean: _Optional[float] = ..., var: _Optional[float] = ...) -> None: ...

class device_fw_info(_message.Message):
    __slots__ = ["mod", "result", "version"]
    MOD_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    mod: _containers.RepeatedCompositeFieldContainer[mod_fw_info]
    result: int
    version: str
    def __init__(self, result: _Optional[int] = ..., version: _Optional[str] = ..., mod: _Optional[_Iterable[_Union[mod_fw_info, _Mapping]]] = ...) -> None: ...

class mod_fw_info(_message.Message):
    __slots__ = ["identify", "type", "version"]
    IDENTIFY_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    identify: str
    type: int
    version: str
    def __init__(self, type: _Optional[int] = ..., identify: _Optional[str] = ..., version: _Optional[str] = ...) -> None: ...

class mow_to_app_info_t(_message.Message):
    __slots__ = ["cmd", "mow_data", "type"]
    CMD_FIELD_NUMBER: _ClassVar[int]
    MOW_DATA_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    cmd: int
    mow_data: _containers.RepeatedScalarFieldContainer[int]
    type: int
    def __init__(self, type: _Optional[int] = ..., cmd: _Optional[int] = ..., mow_data: _Optional[_Iterable[int]] = ...) -> None: ...

class systemRapidStateTunnel_msg(_message.Message):
    __slots__ = ["rapid_state_data"]
    RAPID_STATE_DATA_FIELD_NUMBER: _ClassVar[int]
    rapid_state_data: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, rapid_state_data: _Optional[_Iterable[int]] = ...) -> None: ...

class systemTardStateTunnel_msg(_message.Message):
    __slots__ = ["tard_state_data"]
    TARD_STATE_DATA_FIELD_NUMBER: _ClassVar[int]
    tard_state_data: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, tard_state_data: _Optional[_Iterable[int]] = ...) -> None: ...

class systemTmpCycleTx_msg(_message.Message):
    __slots__ = ["cycle_tx_data"]
    CYCLE_TX_DATA_FIELD_NUMBER: _ClassVar[int]
    cycle_tx_data: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, cycle_tx_data: _Optional[_Iterable[int]] = ...) -> None: ...

class systemUpdateBuf_msg(_message.Message):
    __slots__ = ["update_buf_data"]
    UPDATE_BUF_DATA_FIELD_NUMBER: _ClassVar[int]
    update_buf_data: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, update_buf_data: _Optional[_Iterable[int]] = ...) -> None: ...

class Operation(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class OffPartId(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class RptInfoType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
