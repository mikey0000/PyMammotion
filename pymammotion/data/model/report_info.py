from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

import betterproto2
from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.data.model.enums import (
    BladeState,
    MnetLinkType,
    PositionMode,
    RTKStatus,
    RtkSwitchMode,
    SensorCheckState,
    SimCardStatus,
)

if TYPE_CHECKING:
    from pymammotion.proto import ReportInfoData


class NetUsedType(StrEnum):
    """Active network interface type reported by the device."""

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
    """Network connectivity details reported by the device."""

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
    """Installation status of the grass-clippings collector attachment."""

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
    """Physical lock/security state of the mower."""

    lock_state: int = 0


@dataclass
class VioSurvivalInfo(DataClassORJSONMixin):
    """Visual-inertial odometry survival distance since last reliable fix."""

    vio_survival_distance: float = 0.0


@dataclass
class FpvInfo(DataClassORJSONMixin):
    """fpv_flag: 0: no fpv, 1: fpv ok, 2: fpv error"""

    fpv_flag: int = 0
    wifi_available: int = 0
    mobile_net_available: int = 0


@dataclass
class DeviceData(DataClassORJSONMixin):
    """Core device telemetry: system status, battery, sensors, and connectivity."""

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
    # Lifetime counters sourced from thing/properties deviceOtherInfo JSON
    mileage: int = 0  # lifetime distance travelled, metres
    work_time_sec: int = 0  # lifetime working time, seconds (thing/properties wt_sec)

    # ------------------------------------------------------------------
    # sensor_status bit-field accessors
    # See docs/sensor_status.md for the full bit layout.
    # ------------------------------------------------------------------

    @property
    def bumper_state(self) -> SensorCheckState:
        """Bumper/collision-bar state (sensor_status bits 0-2)."""
        raw = self.sensor_status & 0x7
        return SensorCheckState(min(raw, int(SensorCheckState.ERROR)))

    @property
    def blade_state(self) -> BladeState:
        """Blade/cutter-disc state (sensor_status bits 9-11)."""
        raw = (self.sensor_status >> 9) & 0x7
        return BladeState.ON if raw else BladeState.OFF

    @property
    def ult_left(self) -> SensorCheckState:
        """Left ultrasonic sensor state (sensor_status bits 12-14)."""
        raw = (self.sensor_status >> 12) & 0x7
        return SensorCheckState(min(raw, int(SensorCheckState.ERROR)))

    @property
    def ult_left_front(self) -> SensorCheckState:
        """Left-front ultrasonic sensor state (sensor_status bits 15-17)."""
        raw = (self.sensor_status >> 15) & 0x7
        return SensorCheckState(min(raw, int(SensorCheckState.ERROR)))

    @property
    def ult_right_front(self) -> SensorCheckState:
        """Right-front ultrasonic sensor state (sensor_status bits 18-20)."""
        raw = (self.sensor_status >> 18) & 0x7
        return SensorCheckState(min(raw, int(SensorCheckState.ERROR)))

    @property
    def ult_right(self) -> SensorCheckState:
        """Right ultrasonic sensor state (sensor_status bits 21-23)."""
        raw = (self.sensor_status >> 21) & 0x7
        return SensorCheckState(min(raw, int(SensorCheckState.ERROR)))

    # ------------------------------------------------------------------
    # vslam_status bit-field accessors
    #
    # Packed 32-bit field: the APK splits it into three named sub-bytes at
    # MACarDataManager.java:10561-10575 (byte 0 / ``raw & 0xFF`` is unused
    # in the APK we have).  Value-space notes per property below.
    # ------------------------------------------------------------------

    @property
    def fuse_status(self) -> int:
        """Fuse-status sub-byte (vslam_status bits 8-15).

        Stored as ``CarStatusBean.fuseStatus`` in the APK.  Observed values
        0-5 in the APK code — does **not** share the 0-3 scheme used by
        ``VioState``.  No named enum constants in the APK.
        """
        return (self.vslam_status >> 8) & 0xFF

    @property
    def vision_distance(self) -> int:
        """Vision Distance sub-byte (vslam_status bits 16-23).

        Displayed in the app as "Vision Distance" — rendered as ``"(N)"``
        next to the vision state on the RTK status screen
        (``RTKStatusFragment.java:1181-1183`` via ``tvRtkVisionDis``).
        Stored as ``CarStatusBean.dis`` in the APK; no enum — raw integer.
        """
        return (self.vslam_status >> 16) & 0xFF

    @property
    def vision_state(self) -> int:
        """Vision / VSLAM-state sub-byte (vslam_status bits 24-31).

        Stored as ``CarStatusBean.visionState`` in the APK.  No observed
        comparisons in the APK code; value space unverified.  Consumers
        that need named values should compare against the ``VioState``
        enum cautiously (unconfirmed whether it uses the same 0-3 scheme).
        """
        return (self.vslam_status >> 24) & 0xFF


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
    """Unpacked RTK signal quality fields decoded from the packed ``dis_status`` integer."""

    pos_status: int = 0
    precision: int = 0
    device_signal: int = 0
    l1: int = 0
    l2: int = 0
    connection_to_ref: int = 0
    rtk_signal: int = 0


@dataclass
class RTKData(DataClassORJSONMixin):
    """RTK positioning data including fix status, satellite counts, and correction info."""

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

    @property
    def positioning_mode(self) -> PositionMode:
        """Decode pos_level into a PositionMode (FIX/SINGLE/FLOAT/NONE).

        pos_level 0 = best fix (FIX), increasing values indicate degrading solution.
        Source: MACarDataManager.java posLevel extraction + PositionMode mapping.
        """
        try:
            return PositionMode(self.pos_level)
        except ValueError:
            return PositionMode.UNKNOWN

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
    """Raw position and heading data from a single location report entry."""

    real_pos_x: int = 0
    real_pos_y: int = 0
    real_toward: int = 0
    pos_type: int = 0
    bol_hash: int = 0


@dataclass
class BladeUsed(DataClassORJSONMixin):
    """Blade usage time and warning threshold for maintenance tracking."""

    blade_used_time: int = 0
    blade_used_warn_time: int = 0


@dataclass
class Maintain(DataClassORJSONMixin):
    """Maintenance counters: blade hours, mileage, work time, and battery cycles."""

    blade_used_time: BladeUsed = field(default_factory=BladeUsed)
    mileage: int = 0
    work_time: int = 0
    bat_cycles: int = 0


@dataclass
class VisionInfo(DataClassORJSONMixin):
    """Visual-inertial odometry state reported by the vision subsystem."""

    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0
    vio_state: int = 0
    brightness: int = 0
    detect_feature_num: int = 0
    track_feature_num: int = 0


@dataclass
class HeadingState(DataClassORJSONMixin):
    """Current heading/compass state reported during navigation."""

    heading_state: int = 0


@dataclass
class WorkData(DataClassORJSONMixin):
    """Active mowing session metrics: path, progress, area, and breakpoint info."""

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
class BaseScore(DataClassORJSONMixin):
    """Quality scores reported by the RTK base station."""

    base_score: int = 0
    base_leve: int = 0
    base_moved: int = 0
    base_moving: int = 0


@dataclass
class BasestationInfo(DataClassORJSONMixin):
    """RTK base-station status, firmware version, and correction channel details."""

    # Fields from RptBasestationInfo (via toapp_report_data subscription)
    ver_major: int = 0
    ver_minor: int = 0
    ver_patch: int = 0
    ver_build: int = 0
    basestation_status: int = 0
    connect_status_since_poweron: int = 0
    # Fields from response_basestation_info_t (via LubaMsg.base.to_app)
    sats_num: int = 0
    rtk_status: int = 0
    rtk_channel: int = 0
    rtk_switch: int = 0
    wifi_rssi: int = 0
    lora_channel: int = 0
    mqtt_rtk_status: int = 0
    app_connect_type: int = 0
    score_info: BaseScore = field(default_factory=BaseScore)

    @property
    def fix_status(self) -> RTKStatus:
        """RTK fix status of the base station."""
        return RTKStatus.from_value(self.rtk_status)

    @property
    def correction_source(self) -> RtkSwitchMode:
        """Correction source mode for the base station."""
        try:
            return RtkSwitchMode(self.rtk_switch)
        except ValueError:
            return RtkSwitchMode.LORA


@dataclass
class CutterWorkModeInfo(DataClassORJSONMixin):
    """Current cutter/blade operating mode and RPM."""

    current_cutter_mode: int = 0
    current_cutter_rpm: int = 0


@dataclass
class VisionPointMsg(DataClassORJSONMixin):
    """A single 3-D point detected by the vision system."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class VisionPointInfo(DataClassORJSONMixin):
    """Labelled cluster of vision-detected 3-D points from the camera subsystem."""

    label: int = 0
    num: int = 0
    vision_point: list[VisionPointMsg] = field(default_factory=list)


@dataclass
class VisionStatisticMsg(DataClassORJSONMixin):
    """Mean and variance statistics for a single vision measurement category."""

    mean: float = 0.0
    var: float = 0.0


@dataclass
class VisionStatisticInfo(DataClassORJSONMixin):
    """Timestamped collection of vision measurement statistics from the camera subsystem."""

    timestamp: float = 0.0
    num: int = 0
    vision_statistics: list[VisionStatisticMsg] = field(default_factory=list)


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
    """Aggregated device report data updated from incoming ``ReportInfoData`` protobuf messages."""

    connect: ConnectData = field(default_factory=ConnectData)
    dev: DeviceData = field(default_factory=DeviceData)
    maintenance: Maintain = field(default_factory=Maintain)
    vision_info: VisionInfo = field(default_factory=VisionInfo)
    rtk: RTKData = field(default_factory=RTKData)
    locations: list[LocationData] = field(default_factory=list)
    work: WorkData = field(default_factory=WorkData)
    basestation_info: BasestationInfo = field(default_factory=BasestationInfo)
    cutter_work_mode_info: CutterWorkModeInfo = field(default_factory=CutterWorkModeInfo)
    vision_point_info: list[VisionPointInfo] = field(default_factory=list)
    vision_statistic_info: VisionStatisticInfo = field(default_factory=VisionStatisticInfo)

    def update(self, data: ReportInfoData) -> None:
        """Update only the fields present in the proto message, leaving absent fields unchanged."""
        if data.connect is not None:
            self.connect = ConnectData.from_dict(data.connect.to_dict(casing=betterproto2.Casing.SNAKE))
        if data.dev is not None:
            self.dev = DeviceData.from_dict(data.dev.to_dict(casing=betterproto2.Casing.SNAKE))
        if data.rtk is not None:
            self.rtk = RTKData.from_dict(data.rtk.to_dict(casing=betterproto2.Casing.SNAKE))
        if data.maintain is not None:
            self.maintenance = Maintain.from_dict(data.maintain.to_dict(casing=betterproto2.Casing.SNAKE))
        if data.vio_to_app_info is not None:
            self.vision_info = VisionInfo.from_dict(data.vio_to_app_info.to_dict(casing=betterproto2.Casing.SNAKE))
        if data.locations:
            self.locations = [
                LocationData.from_dict(loc.to_dict(casing=betterproto2.Casing.SNAKE)) for loc in data.locations
            ]
        if data.work is not None:
            self.work = WorkData.from_dict(data.work.to_dict(casing=betterproto2.Casing.SNAKE))
        if data.basestation_info is not None:
            self.basestation_info = BasestationInfo.from_dict(
                data.basestation_info.to_dict(casing=betterproto2.Casing.SNAKE)
            )
        if data.cutter_work_mode_info is not None:
            self.cutter_work_mode_info = CutterWorkModeInfo.from_dict(
                data.cutter_work_mode_info.to_dict(casing=betterproto2.Casing.SNAKE)
            )
        if data.vision_point_info:
            self.vision_point_info = [
                VisionPointInfo.from_dict(vpi.to_dict(casing=betterproto2.Casing.SNAKE))
                for vpi in data.vision_point_info
            ]
        if data.vision_statistic_info is not None:
            self.vision_statistic_info = VisionStatisticInfo.from_dict(
                data.vision_statistic_info.to_dict(casing=betterproto2.Casing.SNAKE)
            )
