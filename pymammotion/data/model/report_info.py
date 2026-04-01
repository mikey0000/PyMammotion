from dataclasses import dataclass, field
from enum import StrEnum

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.data.model.enums import MnetLinkType, RtkSwitchMode, SimCardStatus


class NetUsedType(StrEnum):
    NONE = "NONE"
    WIFI = "WIFI"
    MNET = "MNET"


@dataclass
class NetSpeed(DataClassORJSONMixin):
    """Upload/download throughput reported by the device."""

    download: int = 0  # bytes/sec
    upload: int = 0  # bytes/sec


@dataclass
class ConnectData(DataClassORJSONMixin):
    connect_type: int = 0
    ble_rssi: int = 0
    wifi_rssi: int = 0
    link_type: int = 0
    mnet_rssi: int = 0
    mnet_inet: int = 0
    used_net: str = "NONE"
    # Cloud / WiFi connection state (rpt_connect_status)
    iot_con_status: int = 0  # IotConnectionStatus: 0=offline, 1=online, 2=reset
    wifi_con_status: int = 0  # WiFi connection status code
    wifi_is_available: int = 0  # 1 if WiFi interface is available
    dev_net_speed: NetSpeed = field(default_factory=NetSpeed)


#    mnet_cfg:


@dataclass
class CollectorStatus(DataClassORJSONMixin):
    collector_installation_status: int = 0


@dataclass
class CellularInetStatus(DataClassORJSONMixin):
    """Internet connectivity state of the cellular module (proto mnet_inet_status)."""

    connect: bool = False
    ip: int = 0  # assigned IP address as uint32 (use socket.inet_ntoa to format)
    mask: int = 0  # subnet mask as uint32
    gateway: int = 0  # gateway IP as uint32


@dataclass
class MnetInfo(DataClassORJSONMixin):
    """Cellular module information (proto MnetInfo — all 10 fields).

    sim / link_type are stored as their proto enum name strings
    (e.g. "SIM_OK", "MNET_LINK_4G") — use SimCardStatus / MnetLinkType enums
    to interpret the integer equivalent.
    """

    model: str = ""
    revision: str = ""
    imei: str = ""
    # Fields missing from the original model:
    sim: str = "SIM_NONE"  # SimCardStatus enum name
    imsi: str = ""  # SIM IMSI number
    link_type: str = "MNET_LINK_NONE"  # MnetLinkType enum name
    rssi: int = 0  # 4G signal strength (dBm, negative)
    inet: CellularInetStatus = field(default_factory=CellularInetStatus)
    iccid: str = ""  # SIM ICCID
    operator: str = ""  # Carrier name e.g. "Vodafone"

    @property
    def sim_status(self) -> SimCardStatus:
        """Return sim card state as a typed enum."""
        try:
            return SimCardStatus[self.sim]
        except KeyError:
            return SimCardStatus.SIM_NONE

    @property
    def cellular_link_type(self) -> MnetLinkType:
        """Return network generation as a typed enum."""
        try:
            return MnetLinkType[
                self.link_type.replace("MNET_LINK_", "LINK_") if self.link_type != "MNET_LINK_NONE" else "NONE"
            ]
        except KeyError:
            return MnetLinkType.NONE

    @property
    def is_connected(self) -> bool:
        """True if the cellular module has an active internet connection."""
        return self.inet.connect


@dataclass
class LockStateT(DataClassORJSONMixin):
    lock_state: int = 0


@dataclass
class VioSurvivalInfo(DataClassORJSONMixin):
    vio_survival_distance: float = 0.0


@dataclass
class FpvInfo(DataClassORJSONMixin):
    """fpv_flag: 0: no fpv, 1: fpv ok, 2: fpv error"""

    fpv_flag: int = 0
    wifi_available: int = 0
    mobile_net_available: int = 0


@dataclass
class DeviceData(DataClassORJSONMixin):
    sys_status: int = 0
    charge_state: int = 0
    battery_val: int = 0
    sensor_status: int = 0
    last_status: int = 0
    sys_time_stamp: str = ""
    vslam_status: int = 0
    mnet_info: MnetInfo = field(default_factory=MnetInfo)
    vio_survival_info: VioSurvivalInfo = field(default_factory=VioSurvivalInfo)
    collector_status: CollectorStatus = field(default_factory=CollectorStatus)
    fpv_info: FpvInfo | None = None
    lock_state: LockStateT = field(default_factory=LockStateT)
    # Hardware self-check bitmask (rpt_dev_status.self_check_status)
    self_check_status: int = 0


@dataclass
class LoraInfo(DataClassORJSONMixin):
    """LoRa base-station pairing state (proto rpt_lora).

    pair_code_channel: LoRa channel number
    pair_code_locid:   location ID for the paired base
    pair_code_netid:   network ID
    lora_connection_status: 0=disconnected, >0=connected
    """

    pair_code_scan: int = 0
    pair_code_channel: int = 0
    pair_code_locid: int = 0
    pair_code_netid: int = 0
    lora_connection_status: int = 0

    @property
    def is_connected(self) -> bool:
        """Return True if the LoRa base station connection status indicates an active link."""
        return self.lora_connection_status > 0


@dataclass
class MqttRtkInfo(DataClassORJSONMixin):
    """RTK correction channel config received from device (proto mqtt_rtk_connect).

    rtk_switch: RtkSwitchMode — which correction source is active
    rtk_channel: LoRa channel (when rtk_switch=LORA)
    rtk_base_num: base station identifier string
    latitude/longitude: base station coordinates (0,0 = not known; -1,-1 = no GGA)
    nrtk_map_convert_status: NRTK map conversion quality
    """

    rtk_switch: str = "RTK_USED_LORA"  # RtkSwitchMode enum name from proto
    rtk_channel: int = 0
    rtk_base_num: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    nrtk_map_convert_status: int = 0
    nrtk_net_mode: int = 0

    @property
    def switch_mode(self) -> RtkSwitchMode:
        """Return correction channel as a typed enum."""
        mapping = {
            "RTK_USED_LORA": RtkSwitchMode.LORA,
            "RTK_USED_INTERNET": RtkSwitchMode.INTERNET,
            "RTK_USED_NRTK": RtkSwitchMode.NRTK,
        }
        return mapping.get(self.rtk_switch, RtkSwitchMode.LORA)

    @property
    def is_receive_gga(self) -> bool:
        """False when latitude and longitude are both -1 (no GGA data from base)."""
        return not (self.latitude == -1.0 and self.longitude == -1.0)

    @property
    def is_receive_position(self) -> bool:
        """False when latitude and longitude are both 0 (no position from base)."""
        return not (self.latitude == 0.0 and self.longitude == 0.0)


@dataclass
class RtkPositionScore(DataClassORJSONMixin):
    """RTK positioning quality scores (proto pos_score).

    rover_level / base_level: 0=poor → 5=excellent
    base_moved / base_moving: non-zero if base station has moved or is moving
    """

    rover_score: int = 0
    rover_level: int = 0
    base_score: int = 0
    base_level: int = 0
    base_moved: int = 0
    base_moving: int = 0


@dataclass
class RTKDisStatus(DataClassORJSONMixin):
    pos_status: int = 0
    precision: int = 0
    device_signal: int = 0
    l1: int = 0
    l2: int = 0
    connection_to_ref: int = 0
    rtk_signal: int = 0


@dataclass
class RTKData(DataClassORJSONMixin):
    # Core fields (existing)
    status: int = 0  # RTKFixStatus: 0=none, 1=SPP, 2=float, 4=fixed
    pos_level: int = 0
    gps_stars: int = 0  # total satellite count
    dis_status: int = 0  # packed RTK signal quality — decode with get_dis_status()
    co_view_stars: int = 0  # co-view satellite count between mower and base
    # Extended fields from rpt_rtk (new)
    age: int = 0  # age of differential correction in seconds
    lat_std: int = 0  # latitude standard deviation (scaled int)
    lon_std: int = 0  # longitude standard deviation (scaled int)
    l2_stars: int = 0  # L2-band satellite count
    top4_total_mean: int = 0  # mean signal quality of top 4 satellites
    reset: int = 0  # RTK reset count since boot
    lora_info: LoraInfo = field(default_factory=LoraInfo)
    mqtt_rtk_info: MqttRtkInfo = field(default_factory=MqttRtkInfo)
    score_info: RtkPositionScore = field(default_factory=RtkPositionScore)

    def get_dis_status(self) -> RTKDisStatus:
        """Unpack the packed dis_status integer into an RTKDisStatus with individual signal quality fields."""
        rtk_dis_status = RTKDisStatus()
        rtk_dis_status.pos_status = ((int)(self.dis_status >> 8)) & 255
        rtk_dis_status.precision = ((int)(self.dis_status >> 56)) & 255
        rtk_dis_status.device_signal = ((int)(self.dis_status >> 32)) & 255
        rtk_dis_status.l1 = ((int)(self.dis_status >> 16)) & 255
        rtk_dis_status.l2 = ((int)(self.dis_status >> 24)) & 255
        rtk_dis_status.connection_to_ref = ((int)(self.dis_status >> 48)) & 255
        rtk_dis_status.rtk_signal = ((int)(self.dis_status >> 40)) & 255
        return rtk_dis_status


@dataclass
class LocationData(DataClassORJSONMixin):
    real_pos_x: int = 0
    real_pos_y: int = 0
    real_toward: int = 0
    pos_type: int = 0
    bol_hash: int = 0


@dataclass
class BladeUsed(DataClassORJSONMixin):
    blade_used_time: int = 0
    blade_used_warn_time: int = 0


@dataclass
class Maintain(DataClassORJSONMixin):
    blade_used_time: BladeUsed = field(default_factory=BladeUsed)
    mileage: int = 0
    work_time: int = 0
    bat_cycles: int = 0


@dataclass
class VisionInfo(DataClassORJSONMixin):
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0
    vio_state: int = 0
    brightness: int = 0
    detect_feature_num: int = 0
    track_feature_num: int = 0


@dataclass
class HeadingState(DataClassORJSONMixin):
    heading_state: int = 0


@dataclass
class WorkData(DataClassORJSONMixin):
    path: int = 0
    path_hash: int = 0
    progress: int = 0
    area: int = 0
    """Packed field: upper 16 bits = mow completion percentage (0–100),
    lower 16 bits = area mowed in device units.  Use ``mow_percent`` to
    read the percentage and ``area_mowed`` for the raw area value."""
    bp_info: int = 0
    bp_hash: int = 0
    bp_pos_x: int = 0
    bp_pos_y: int = 0
    real_path_num: int = 0
    """Packed field encoding current mow path position.
    Use ``now_index``, ``start_index``, and ``path_direction`` to read."""
    path_pos_x: int = 0
    path_pos_y: int = 0
    ub_zone_hash: int = 0
    ub_path_hash: int = 0
    init_cfg_hash: int = 0
    ub_ecode_hash: int = 0
    nav_run_mode: int = 0
    test_mode_status: int = 0
    man_run_speed: int = 0
    nav_edit_status: int = 0
    knife_height: int = 0
    nav_heading_state: HeadingState = field(default_factory=HeadingState)
    cutter_offset: float = 0.0
    cutter_width: float = 0.0

    @property
    def mow_percent(self) -> int:
        """Mow completion percentage (0–100), packed in upper 16 bits of ``area``."""
        return self.area >> 16

    @property
    def area_mowed(self) -> int:
        """Area mowed in device units, packed in lower 16 bits of ``area``."""
        return self.area & 0xFFFF

    @property
    def now_index(self) -> int:
        """Current mow path position index (bits 8–23 of ``real_path_num``).

        This is an index into the ordered planned mow path point array.
        Points 0..now_index represent the completed portion of the path.
        """
        return (self.real_path_num & 0x00FFFF00) >> 8

    @property
    def start_index(self) -> int:
        """Start index of the current mow segment (bits 24–39 of ``real_path_num``)."""
        return (self.real_path_num & 0xFFFF000000) >> 24

    @property
    def path_direction(self) -> int:
        """Mow path traversal direction flag (bits 0–7 of ``real_path_num``)."""
        return self.real_path_num & 0xFF


@dataclass
class WorkSessionResult(DataClassORJSONMixin):
    """Completed or interrupted work session summary (proto WorkReportInfoAck).

    Sent by the device when a mow job finishes or is interrupted.
    interrupt_flag: WorkInterruptType — reason for stop (0=completed normally)
    work_ares: area covered in m² (note: proto field name has typo 'work_ares')
    start_work_time / end_work_time: Unix timestamps (int64)
    work_result: device-specific completion result code
    work_type: type of operation performed
    """

    interrupt_flag: bool = False  # True if interrupted before completion
    interrupt_type: int = 0  # WorkInterruptType value (from interrupt_flag int field)
    start_work_time: int = 0  # Unix timestamp
    end_work_time: int = 0  # Unix timestamp
    work_time_used: int = 0  # seconds spent working
    work_area: float = 0.0  # area covered in m²
    work_progress: int = 0  # progress percentage 0–100
    height_of_knife: int = 0  # blade height during the session
    work_type: int = 0
    work_result: int = 0


@dataclass
class ReportData(DataClassORJSONMixin):
    connect: ConnectData = field(default_factory=ConnectData)
    dev: DeviceData = field(default_factory=DeviceData)
    maintenance: Maintain = field(default_factory=Maintain)
    vision_info: VisionInfo = field(default_factory=VisionInfo)
    rtk: RTKData = field(default_factory=RTKData)
    locations: list[LocationData] = field(default_factory=list)
    work: WorkData = field(default_factory=WorkData)

    def update(self, data: dict) -> None:
        """Update all report fields in-place from a raw device telemetry dictionary."""
        locations = self.locations
        if data.get("locations") is not None:
            locations = [LocationData.from_dict(loc) for loc in data.get("locations", [])]

        self.connect = ConnectData.from_dict(data.get("connect", self.connect.to_dict()))
        self.dev = DeviceData.from_dict(data.get("dev", self.dev.to_dict()))
        self.rtk = RTKData.from_dict(data.get("rtk", self.rtk.to_dict()))
        self.maintenance = Maintain.from_dict(data.get("maintain", self.maintenance.to_dict()))
        self.vision_info = VisionInfo.from_dict(data.get("vio_to_app_info", VisionInfo().to_dict()))
        self.locations = locations
        self.work = WorkData.from_dict(data.get("work", self.work.to_dict()))
