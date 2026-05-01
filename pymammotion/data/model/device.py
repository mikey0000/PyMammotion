"""Device model hierarchy: Device base + MowerDevice (and future PoolCleanerDevice)."""

from dataclasses import dataclass, field
import math
from typing import Any

from mashumaro.mixins.orjson import DataClassORJSONMixin
import orjson

from pymammotion.data.model import HashList, RapidState
from pymammotion.data.model.device_info import DeviceFirmwares, DeviceNonWorkingHours, MowerInfo
from pymammotion.data.model.device_limits import DeviceLimits
from pymammotion.data.model.enums import TaskAreaStatus
from pymammotion.data.model.errors import DeviceErrors
from pymammotion.data.model.events import Events
from pymammotion.data.model.location import Location
from pymammotion.data.model.pool_state import PoolMap, PoolState
from pymammotion.data.model.report_info import BaseScore, ReportData, WorkSessionResult
from pymammotion.data.model.work import CurrentTaskSettings
from pymammotion.data.mqtt.event import ThingEventMessage
from pymammotion.data.mqtt.properties import ThingPropertiesMessage
from pymammotion.data.mqtt.status import ThingStatusMessage
from pymammotion.http.model.http import CheckDeviceVersion
from pymammotion.proto import DeviceFwInfo, MowToAppInfoT, ReportInfoData, SystemTardStateTunnelMsg, SystemUpdateBufMsg
from pymammotion.utility.conversions import parse_double
from pymammotion.utility.device_config import DeviceConfig
from pymammotion.utility.map import CoordinateConverter

_device_config = DeviceConfig()


@dataclass
class Device(DataClassORJSONMixin):
    """Base class for any Mammotion device (lawn mower, pool cleaner, RTK, …).

    Holds only the fields that are truly universal — identity, online flag,
    OTA check, and MQTT envelopes. Device-class-specific state lives on
    subclasses (``MowerDevice``, ``PoolCleanerDevice``, …).
    """

    name: str = ""
    online: bool = True
    enabled: bool = True
    update_check: CheckDeviceVersion = field(default_factory=CheckDeviceVersion)
    mqtt_properties: ThingPropertiesMessage | None = None
    status_properties: ThingStatusMessage | None = None
    device_event: ThingEventMessage | None = None


@dataclass
class MowerDevice(Device):
    """Lawn-mowing robot (Luba, Yuka, RTK rovers).

    Wraps the betterproto dataclasses so we can bypass the oneof groups and
    keep everything in one place.
    """

    mower_state: MowerInfo = field(default_factory=MowerInfo)
    map: HashList = field(default_factory=HashList)
    work: CurrentTaskSettings = field(default_factory=CurrentTaskSettings)
    location: Location = field(default_factory=Location)
    mowing_state: RapidState = field(default_factory=RapidState)
    report_data: ReportData = field(default_factory=ReportData)
    device_firmwares: DeviceFirmwares = field(default_factory=DeviceFirmwares)
    errors: DeviceErrors = field(default_factory=DeviceErrors)
    non_work_hours: DeviceNonWorkingHours = field(default_factory=DeviceNonWorkingHours)
    events: Events = field(default_factory=Events)
    work_session_result: WorkSessionResult = field(default_factory=WorkSessionResult)

    @property
    def device_limits(self) -> DeviceLimits:
        """Return the operating limits for this device.

        Tries (in order):
          1. sub_model_id — the most specific internal model code
          2. product_key  — per-product-family limits
          3. get_best_default — safe fallback based on device family
        """
        limits = _device_config.get_working_parameters(self.mower_state.sub_model_id)
        if limits is None:
            limits = _device_config.get_working_parameters(self.mower_state.product_key)
        if limits is None:
            limits = _device_config.get_best_default(self.mower_state.product_key)
        return limits

    def clear_version_info(self) -> None:
        """Clear all cached firmware version info so it will be re-fetched after an OTA update."""
        self.device_firmwares = DeviceFirmwares()
        self.mower_state.swversion = ""

    def buffer(self, buffer_list: SystemUpdateBufMsg) -> None:
        """Update the device based on which buffer we are reading from."""
        match buffer_list.update_buf_data[0]:
            case 1:
                # 4 speed?
                if buffer_list.update_buf_data[5] != 0:
                    self.location.RTK.latitude = parse_double(buffer_list.update_buf_data[5], 8.0)
                    self.location.RTK.longitude = parse_double(buffer_list.update_buf_data[6], 8.0)
                    # Index 13 = RTK base station heading (radians) — used to rotate device-local
                    # ENU coordinates to geographic ENU for correct map placement.
                    if len(buffer_list.update_buf_data) > 13:
                        self.location.RTK.yaw = parse_double(buffer_list.update_buf_data[13], 8.0)
                if buffer_list.update_buf_data[7] != 0:
                    # latitude Y longitude X
                    self.location.dock.longitude = parse_double(buffer_list.update_buf_data[7], 4.0)
                    self.location.dock.latitude = parse_double(buffer_list.update_buf_data[8], 4.0)
                    self.location.dock.rotation = buffer_list.update_buf_data[3]

            case 2:
                self.errors.err_code_list.clear()
                self.errors.err_code_list_time.clear()
                self.errors.err_code_list.extend(
                    [
                        buffer_list.update_buf_data[3],
                        buffer_list.update_buf_data[5],
                        buffer_list.update_buf_data[7],
                        buffer_list.update_buf_data[9],
                        buffer_list.update_buf_data[11],
                        buffer_list.update_buf_data[13],
                        buffer_list.update_buf_data[15],
                        buffer_list.update_buf_data[17],
                        buffer_list.update_buf_data[19],
                        buffer_list.update_buf_data[21],
                    ]
                )
                self.errors.err_code_list_time.extend(
                    [
                        buffer_list.update_buf_data[4],
                        buffer_list.update_buf_data[6],
                        buffer_list.update_buf_data[8],
                        buffer_list.update_buf_data[10],
                        buffer_list.update_buf_data[12],
                        buffer_list.update_buf_data[14],
                        buffer_list.update_buf_data[16],
                        buffer_list.update_buf_data[18],
                        buffer_list.update_buf_data[20],
                        buffer_list.update_buf_data[22],
                    ]
                )
            case 3:
                # Task area state event (TaskAreaStateEvent in APK / MACarDataManager).
                # Format: [3, 0, count, hash1, status1, hash2, status2, ...]
                # Pairs of (zone_hash, status) starting at index 3, step 2.
                # task_area_ids preserves the original mow order of zones.
                # Status values: see TaskAreaStatus enum.
                task_area_map: dict[int, TaskAreaStatus] = {}
                task_area_ids = []

                for i in range(3, len(buffer_list.update_buf_data), 2):
                    area_id = buffer_list.update_buf_data[i]

                    if area_id != 0:
                        status = TaskAreaStatus(int(buffer_list.update_buf_data[i + 1]))
                        if status is TaskAreaStatus.ABORTED:
                            continue
                        task_area_map[area_id] = status
                        task_area_ids.append(area_id)
                self.events.work_tasks_event.hash_area_map = task_area_map
                self.events.work_tasks_event.ids = task_area_ids

    def update_report_data(self, toapp_report_data: ReportInfoData) -> None:
        """Set report data for the mower."""

        # adjust for vision models
        if (
            (rtk := toapp_report_data.rtk)
            and (mqtt_rtk := rtk.mqtt_rtk_info)
            and self.location.RTK.latitude == 0
            and self.location.RTK.longitude == 0
        ):
            self.location.RTK.longitude = math.radians(mqtt_rtk.longitude)
            self.location.RTK.latitude = math.radians(mqtt_rtk.latitude)

        coordinate_converter = CoordinateConverter(self.location.RTK.latitude, self.location.RTK.longitude)
        for index, location in enumerate(toapp_report_data.locations):
            if index == 0:
                self.location.position_type = location.pos_type
                self.location.orientation = int(location.real_toward / 10000)
                x_dev = parse_double(location.real_pos_x, 4.0)
                y_dev = parse_double(location.real_pos_y, 4.0)
                yaw = self.location.RTK.yaw
                east_geo = math.cos(yaw) * x_dev - math.sin(yaw) * y_dev
                north_geo = math.sin(yaw) * x_dev + math.cos(yaw) * y_dev
                self.location.device = coordinate_converter.enu_to_lla(north_geo, east_geo)
                self.map.invalidate_maps(location.bol_hash)
                self.location.work_zone = location.zone_hash

        if toapp_report_data.fw_info:
            self.update_device_firmwares(toapp_report_data.fw_info)

        if (
            toapp_report_data.work
            and (toapp_report_data.work.area >> 16) == 0
            and toapp_report_data.work.ub_path_hash == 0
        ):
            self.work.zone_hashs = []
            self.events.work_tasks_event.hash_area_map = {}
            self.events.work_tasks_event.ids = []
            self.map.invalidate_breakpoint_line(0)

        if toapp_report_data.work:
            self.map.invalidate_mow_path(toapp_report_data.work.path_hash)
            self.map.invalidate_breakpoint_line(toapp_report_data.work.ub_path_hash)

        self.report_data.update(toapp_report_data)

    def run_state_update(self, tard_state: SystemTardStateTunnelMsg) -> None:
        """Set lat long, work zone of RTK and robot."""
        coordinate_converter = CoordinateConverter(self.location.RTK.latitude, self.location.RTK.longitude)
        self.mowing_state = RapidState().from_raw(tard_state.tard_state_data)
        self.location.position_type = self.mowing_state.pos_type
        self.location.orientation = int(self.mowing_state.toward)
        x_dev = parse_double(self.mowing_state.pos_x, 4.0)
        y_dev = parse_double(self.mowing_state.pos_y, 4.0)
        yaw = self.location.RTK.yaw
        east_geo = math.cos(yaw) * x_dev - math.sin(yaw) * y_dev
        north_geo = math.sin(yaw) * x_dev + math.cos(yaw) * y_dev
        self.location.device = coordinate_converter.enu_to_lla(north_geo, east_geo)
        self.location.work_zone = self.mowing_state.zone_hash

    def mow_info(self, toapp_mow_info: MowToAppInfoT) -> None:
        """Set mow info."""

    def report_missing_data(self) -> list[str]:
        """Report what data is missing for basic operation."""
        from pymammotion.device.readiness import get_readiness_checker

        checker = get_readiness_checker(self.name)
        status = checker.check(self)
        return status.missing

    def update_device_firmwares(self, fw_info: DeviceFwInfo) -> None:
        """Set firmware versions on all parts of the robot or RTK."""
        for mod in fw_info.mod:
            match mod.type:
                case 1:
                    self.device_firmwares.main_controller = mod.version
                case 3:
                    self.device_firmwares.left_motor_driver = mod.version
                case 4:
                    self.device_firmwares.right_motor_driver = mod.version
                case 5:
                    self.device_firmwares.rtk_rover_station = mod.version
                case 7:
                    self.device_firmwares.bms = mod.version
                case 8:
                    self.device_firmwares.main_controller_bt = mod.version
                case 9:
                    self.device_firmwares.left_motor_driver_bt = mod.version
                case 10:
                    self.device_firmwares.right_motor_driver_bt = mod.version
                case 11:
                    self.device_firmwares.bsp = mod.version
                case 12:
                    self.device_firmwares.middleware = mod.version
                case 14:
                    self.device_firmwares.lora_module = mod.version
                case 16:
                    self.device_firmwares.lte_module = mod.version
                case 17:
                    self.device_firmwares.lidar = mod.version
                case 101:
                    # RTK main board
                    self.device_firmwares.main_controller = mod.version
                case 102:
                    self.device_firmwares.rtk_version = mod.version
                case 103:
                    self.device_firmwares.lora_version = mod.version
                case 201:
                    self.device_firmwares.left_motor_driver = mod.version
                    self.device_firmwares.right_motor_driver = mod.version
                case 202:
                    self.device_firmwares.left_motor_driver_bt = mod.version
                    self.device_firmwares.right_motor_driver_bt = mod.version
                case 203:
                    self.device_firmwares.cutter_driver = mod.version
                case 204:
                    self.device_firmwares.cutter_driver_bt = mod.version


@dataclass
class PoolCleanerDevice(Device):
    """Swimming-pool cleaning robot (Spino, Spino-S1/E1/SP).

    Carries only the state the Mammotion Android app actually surfaces in
    its pool-cleaner fragments + settings screens (see ``pool_state.py``
    for the field-by-field rationale). Internal-only proto fields (pump
    status, RSSI, wheel state, …) are intentionally omitted until they
    show up in the UI or there is a concrete consumer for them.
    """

    iot_id: str = ""
    pool_state: PoolState = field(default_factory=PoolState)
    pool_map: PoolMap = field(default_factory=PoolMap)
    device_firmwares: DeviceFirmwares = field(default_factory=DeviceFirmwares)
    errors: DeviceErrors = field(default_factory=DeviceErrors)


@dataclass
class RTKBaseStationDevice(Device):
    """RTK base station (RTK, RBS03A0/A1/A2, RTKNB).

    All devices share one MQTT connection per account (Aliyun or Mammotion
    MQTT); messages are routed by ``iot_id``.  This model holds state from
    messages that carry the RTK device's own ``iot_id``.  The mower-side
    relay data (satellite count, fix status, LoRa channel) arrives in
    messages with the *mower's* ``iot_id`` via ``base.to_app`` and is stored
    on ``MowerDevice.report_data.basestation_info`` — not here.

    Fields populated from LubaMsg protobuf (``iot_id``-routed):

    - ``basestation_status``: from ``sys.toapp_report_data`` →
      ``rpt_basestation_info.basestation_status``.
    - ``connect_status_since_poweron``: connectivity uptime, same source.
    - ``device_version``: from ``sys.toapp_dev_fw_info`` or thing/properties.
    - ``wifi_mac``: from ``net.toapp_networkinfo_rsp``.
    - ``product_key``: from ``net.toapp_wifi_iot_status``.

    Fields populated from ``base.to_app`` (``ResponseBasestationInfoT``):

    - ``sats_num``: number of satellites in view.
    - ``rtk_status``: RTK fix quality.
    - ``app_connect_type``: connection type (BLE/Wi-Fi/MQTT).
    - ``lora_scan``, ``lora_channel``, ``lora_locid``, ``lora_netid``: LoRa radio config.
    - ``mqtt_rtk_status``, ``rtk_channel``, ``rtk_switch``: additional RTK state.
    - ``lowpower_status``: low-power mode flag.
    - ``ble_rssi``: BLE signal strength.
    - ``score_info``: RTK quality scores (``BaseScore``).
    - ``wifi_rssi``: dBm (also updated via thing/properties ``networkInfo``).

    Fields populated from thing/properties JSON pushes:

    - ``lat``, ``lon``: radians, from ``coordinate`` property.
    - ``wifi_rssi``: dBm, from ``networkInfo`` property.
    - ``wifi_sta_mac``, ``bt_mac``: MAC addresses from ``networkInfo``.
    - ``device_version`` + ``device_firmwares``: from ``deviceVersionInfo`` blob
      (main firmware version plus per-module versions keyed by component type).
    - ``lora_version``: from ``loraGeneralConfig`` property (also populated from
      HTTP API ``fetch_rtk_lora_info``).

    Fields populated from ``net.toapp_networkinfo_rsp`` protobuf:

    - ``wifi_ssid``, ``wifi_mac``, ``wifi_rssi``, ``ip``, ``mask``, ``gateway``.
    """

    iot_id: str = ""
    basestation_status: int = 0
    connect_status_since_poweron: int = 0
    device_version: str = ""
    product_key: str = ""
    # base.to_app (ResponseBasestationInfoT) sourced
    sats_num: int = 0
    rtk_status: int = 0
    app_connect_type: int = 0
    lora_scan: int = 0
    lora_channel: int = 0
    lora_locid: int = 0
    lora_netid: int = 0
    mqtt_rtk_status: int = 0
    rtk_channel: int = 0
    rtk_switch: int = 0
    lowpower_status: int = 0
    ble_rssi: int = 0
    score_info: BaseScore | None = None
    # thing/properties sourced
    lat: float = 0.0
    lon: float = 0.0
    wifi_rssi: int = 0
    wifi_mac: str = ""
    bt_mac: str = ""
    lora_version: str = ""
    device_firmwares: DeviceFirmwares = field(default_factory=DeviceFirmwares)
    # net.toapp_networkinfo_rsp sourced
    wifi_ssid: str = ""
    ip: int = 0
    mask: int = 0
    gateway: int = 0


def create_device(name: str, product_key: str = "") -> "Device":
    """Construct the appropriate :class:`Device` subclass for *name*.

    Inspects the device-name prefix (and optionally *product_key*) via
    :class:`DeviceType` and returns the correct subclass:
    :class:`RTKBaseStationDevice` for RTK base stations,
    :class:`PoolCleanerDevice` for Spino variants, or :class:`MowerDevice`
    (the historical default).

    *product_key* is used as a fallback when the device name alone is not
    sufficient to identify the device family (e.g. some RTK base-station
    variants whose names don't carry the "RTK" prefix).
    """
    # Local import to avoid a circular dependency between
    # pymammotion.data.model.device and pymammotion.utility.device_type.
    from pymammotion.utility.device_type import DeviceType

    if DeviceType.is_swimming_pool(name):
        return PoolCleanerDevice(name=name)
    if DeviceType.is_rtk(name, product_key):
        return RTKBaseStationDevice(name=name)
    return MowerDevice(name=name)


# Backwards-compatible alias. The library was previously called MowingDevice
# everywhere; the rename to MowerDevice is part of the polymorphic device-model
# refactor (Phase B). External callers can keep using MowingDevice for now.
MowingDevice = MowerDevice


# Mashumaro's __init_subclass__ generates to_jsonb directly on subclasses, overwriting any
# in-class override.  Patch after class definition so orjson can handle int dict keys
# (e.g. HashList.area / path / obstacle which are dict[int, FrameList]).
def _mower_device_to_jsonb(self: "MowerDevice", **kwargs: Any) -> bytes:
    kwargs.setdefault("option", orjson.OPT_NON_STR_KEYS)
    return orjson.dumps(self.to_dict(), **kwargs)


def _mower_device_to_json(self: "MowerDevice", **kwargs: Any) -> str:
    return _mower_device_to_jsonb(self, **kwargs).decode()


MowerDevice.to_jsonb = _mower_device_to_jsonb
MowerDevice.to_json = _mower_device_to_json
