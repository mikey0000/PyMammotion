from dataclasses import dataclass
from typing import Annotated

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias


@dataclass
class FirmwareInfo(DataClassORJSONMixin):
    t: str
    c: str
    v: str


@dataclass
class DeviceVersionInfo(DataClassORJSONMixin):
    dev_ver: Annotated[str, Alias("devVer")]
    whole: int
    fw_info: Annotated[list[FirmwareInfo], Alias("fwInfo")]

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class Coordinate(DataClassORJSONMixin):
    lon: float
    lat: float


@dataclass
class InternalNavigation(DataClassORJSONMixin):
    nav: Annotated[str, Alias("NAV")]
    pau: Annotated[str, Alias("Pau")]
    r_pau: Annotated[str, Alias("rPau")]
    mcu: Annotated[str, Alias("MCU")]
    app: Annotated[str, Alias("APP")]
    w_slp: Annotated[str, Alias("wSlp")]
    i_slp: Annotated[str, Alias("iSlp")]

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class BandwidthTraffic(DataClassORJSONMixin):
    iot: Annotated[str, Alias("IoT")]
    roi: Annotated[str, Alias("RoI")]
    fpv: Annotated[str, Alias("FPV")]
    inav: InternalNavigation

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class TrafficPeriod(DataClassORJSONMixin):
    r: str
    t: str
    s: str


@dataclass
class TrafficData(DataClassORJSONMixin):
    upt: str
    hour: Annotated[dict[str, TrafficPeriod], Alias("Hour")]
    day: Annotated[dict[str, TrafficPeriod], Alias("Day")]
    mon: Annotated[dict[str, TrafficPeriod], Alias("Mon")]

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class NetworkInfo(DataClassORJSONMixin):
    ssid: str
    ip: str
    wifi_sta_mac: str
    wifi_rssi: int
    wifi_available: int
    bt_mac: str
    mnet_model: str
    imei: str
    fw_ver: str
    sim: str
    imsi: str
    iccid: str
    sim_source: str
    mnet_rssi: int
    signal: int
    mnet_link: int
    mnet_option: str
    mnet_ip: str
    mnet_reg: str
    mnet_rsrp: str
    mnet_snr: str
    mnet_enable: int
    apn_num: int
    apn_info: str
    apn_cid: int
    used_net: int
    hub_reset: int
    mnet_dis: int
    airplane_times: int
    lsusb_num: int
    b_tra: Annotated[BandwidthTraffic, Alias("bTra")]
    bw_tra: Annotated[BandwidthTraffic, Alias("bwTra")]
    mnet_rx: str
    mnet_tx: str
    m_tra: Annotated[TrafficData, Alias("mTra")]
    mnet_uniot: int
    mnet_un_getiot: int
    ssh_flag: str
    mileage: str
    work_time: str
    wt_sec: int
    bat_cycles: str


@dataclass
class DeviceOtherInfo(DataClassORJSONMixin):
    soc_up_time: Annotated[int, Alias("socUpTime")]
    mcu_up_time: Annotated[int, Alias("mcuUpTime")]
    soc_loads: Annotated[str, Alias("socLoads")]
    soc_mem_free: Annotated[int, Alias("socMemFree")]
    soc_mem_total: Annotated[int, Alias("socMemTotal")]
    soc_mmc_life_time: Annotated[int, Alias("socMmcLifeTime")]
    usb_dis_cnt: Annotated[int, Alias("usbDisCnt")]
    soc_pstore: Annotated[int, Alias("socPstore")]
    soc_coredump: Annotated[int, Alias("socCoredump")]
    soc_tmp: Annotated[int, Alias("socTmp")]
    mc_mcu: Annotated[str, Alias("mcMcu")]
    tilt_degree: str
    i_msg_free: Annotated[int, Alias("iMsgFree")]
    i_msg_limit: Annotated[int, Alias("iMsgLimit")]
    i_msg_raw: Annotated[int, Alias("iMsgRaw")]
    i_msg_prop: Annotated[int, Alias("iMsgprop")]
    i_msg_serv: Annotated[int, Alias("iMsgServ")]
    i_msg_info: Annotated[int, Alias("iMsgInfo")]
    i_msg_warn: Annotated[int, Alias("iMsgWarn")]
    i_msg_fault: Annotated[int, Alias("iMsgFault")]
    i_msg_ota_stage: Annotated[int, Alias("iMsgOtaStage")]
    i_msg_protobuf: Annotated[int, Alias("iMsgProtobuf")]
    i_msg_notify: Annotated[int, Alias("iMsgNotify")]
    i_msg_log_prog: Annotated[int, Alias("iMsgLogProg")]
    i_msg_biz_req: Annotated[int, Alias("iMsgBizReq")]
    i_msg_cfg_req: Annotated[int, Alias("iMsgCfgReq")]
    i_msg_voice: Annotated[int, Alias("iMsgVoice")]
    i_msg_warn_code: Annotated[int, Alias("iMsgWarnCode")]
    pb_net: Annotated[int, Alias("pbNet")]
    pb_sys: Annotated[int, Alias("pbSys")]
    pb_nav: Annotated[int, Alias("pbNav")]
    pb_local: Annotated[int, Alias("pbLocal")]
    pb_plan: Annotated[int, Alias("pbPlan")]
    pb_e_drv: Annotated[int, Alias("pbEDrv")]
    pb_e_sys: Annotated[int, Alias("pbESys")]
    pb_midware: Annotated[int, Alias("pbMidware")]
    pb_ota: Annotated[int, Alias("pbOta")]
    pb_appl: Annotated[int, Alias("pbAppl")]
    pb_mul: Annotated[int, Alias("pbMul")]
    pb_other: Annotated[int, Alias("pbOther")]
    lora_connect: Annotated[int, Alias("loraConnect")]
    base_status: Annotated[int, Alias("Basestatus")]
    mqtt_rtk_switch: int
    mqtt_rtk_channel: int
    mqtt_rtk_status: int
    mqtt_rtcm_cnt: int
    mqtt_conn_cnt: int
    mqtt_disconn_cnt: int
    mqtt_rtk_hb_flag: int
    mqtt_rtk_hb_count: int
    mqtt_start_cnt: int
    mqtt_close_cnt: int
    mqtt_rtk_ssl_fail: int
    mqtt_rtk_wifi_config: int
    nrtk_svc_prov: int
    nrtk_svc_err: int
    base_stn_id: int
    rtk_status: int
    charge_status: int
    chassis_state: int
    nav: str
    ins_fusion: str
    perception: str
    vision_proxy: str
    vslam_vio: str
    iot_con_timeout: int
    iot_con: int
    iot_con_fail_max: str
    iot_con_fail_min: Annotated[str, Alias("iot_con__fail_min")]
    iot_url_count: int
    iot_url_max: str
    iot_url_min: str
    iot_cn: int
    iot_ap: int
    iot_us: int
    iot_eu: int
    task_area: float
    task_count: int
    task_hash: str
    systemio_boot_time: Annotated[str, Alias("systemioBootTime")]
    dds_no_gdc: int

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class CheckData(DataClassORJSONMixin):
    result: str
    error: Annotated[list[int], Alias("Error")]
    warn: Annotated[list[int], Alias("Warn")]
    ok: Annotated[list[int], Alias("OK")]

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class DeviceProperties(DataClassORJSONMixin):
    device_state: Annotated[int, Alias("deviceState")]
    battery_percentage: Annotated[int, Alias("batteryPercentage")]
    device_version: Annotated[str, Alias("deviceVersion")]
    knife_height: Annotated[int, Alias("knifeHeight")]
    lora_general_config: Annotated[str, Alias("loraGeneralConfig")]
    ext_mod: Annotated[str, Alias("extMod")]
    int_mod: Annotated[str, Alias("intMod")]
    iot_state: Annotated[int, Alias("iotState")]
    iot_msg_total: Annotated[int, Alias("iotMsgTotal")]
    iot_msg_hz: Annotated[int, Alias("iotMsgHz")]
    lt_mr_mod: Annotated[str, Alias("ltMrMod")]
    rt_mr_mod: Annotated[str, Alias("rtMrMod")]
    bms_hardware_version: Annotated[str, Alias("bmsHardwareVersion")]
    stm32_h7_version: Annotated[str, Alias("stm32H7Version")]
    left_motor_version: Annotated[str, Alias("leftMotorVersion")]
    right_motor_version: Annotated[str, Alias("rightMotorVersion")]
    rtk_version: Annotated[str, Alias("rtkVersion")]
    bms_version: Annotated[str, Alias("bmsVersion")]
    mc_boot_version: Annotated[str, Alias("mcBootVersion")]
    left_motor_boot_version: Annotated[str, Alias("leftMotorBootVersion")]
    right_motor_boot_version: Annotated[str, Alias("rightMotorBootVersion")]

    # Nested JSON objects
    device_version_info: Annotated[DeviceVersionInfo, Alias("deviceVersionInfo")]
    coordinate: Coordinate
    device_other_info: Annotated[DeviceOtherInfo, Alias("deviceOtherInfo")]
    network_info: Annotated[NetworkInfo, Alias("networkInfo")]
    check_data: Annotated[CheckData, Alias("checkData")]
    iot_id: str = ""

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True
        # Custom deserializer for nested JSON strings
        serialization_strategy = {
            DeviceVersionInfo: {
                "deserialize": lambda x: DeviceVersionInfo.from_json(x) if isinstance(x, str) else x,
                "serialize": lambda x: x.to_json() if hasattr(x, "to_json") else x,
            },
            Coordinate: {
                "deserialize": lambda x: Coordinate.from_json(x) if isinstance(x, str) else x,
                "serialize": lambda x: x.to_json() if hasattr(x, "to_json") else x,
            },
            DeviceOtherInfo: {
                "deserialize": lambda x: DeviceOtherInfo.from_json(x) if isinstance(x, str) else x,
                "serialize": lambda x: x.to_json() if hasattr(x, "to_json") else x,
            },
            NetworkInfo: {
                "deserialize": lambda x: NetworkInfo.from_json(x) if isinstance(x, str) else x,
                "serialize": lambda x: x.to_json() if hasattr(x, "to_json") else x,
            },
            CheckData: {
                "deserialize": lambda x: CheckData.from_json(x) if isinstance(x, str) else x,
                "serialize": lambda x: x.to_json() if hasattr(x, "to_json") else x,
            },
        }
