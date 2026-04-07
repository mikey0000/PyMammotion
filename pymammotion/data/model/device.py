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
from pymammotion.data.model.report_info import ReportData, WorkSessionResult
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
                self.location.device = coordinate_converter.enu_to_lla(
                    parse_double(location.real_pos_y, 4.0), parse_double(location.real_pos_x, 4.0)
                )
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
        self.location.device = coordinate_converter.enu_to_lla(
            parse_double(self.mowing_state.pos_y, 4.0), parse_double(self.mowing_state.pos_x, 4.0)
        )
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
                case 203:
                    self.device_firmwares.cutter_driver = mod.version
                case 204:
                    self.device_firmwares.cutter_driver_bt = mod.version


@dataclass
class RTKDevice(DataClassORJSONMixin):
    """Represents an RTK base-station device paired with a mower."""

    name: str
    iot_id: str
    product_key: str
    online: bool = True
    lat: float = 0.0
    lon: float = 0.0
    lora: str = ""
    wifi_rssi: int = 0
    device_version: str = ""
    lora_version: str = ""
    wifi_sta_mac: str = ""
    bt_mac: str = ""
    update_check: CheckDeviceVersion = field(default_factory=CheckDeviceVersion)


@dataclass
class PoolCleanerDevice(Device):
    """Swimming-pool cleaning robot (Spino, Spino-S1/E1/SP).

    Carries only the state the Mammotion Android app actually surfaces in
    its pool-cleaner fragments + settings screens (see ``pool_state.py``
    for the field-by-field rationale). Internal-only proto fields (pump
    status, RSSI, wheel state, …) are intentionally omitted until they
    show up in the UI or there is a concrete consumer for them.
    """

    pool_state: PoolState = field(default_factory=PoolState)
    pool_map: PoolMap = field(default_factory=PoolMap)
    device_firmwares: DeviceFirmwares = field(default_factory=DeviceFirmwares)
    errors: DeviceErrors = field(default_factory=DeviceErrors)


def create_device(name: str) -> "Device":
    """Construct the appropriate :class:`Device` subclass for *name*.

    Inspects the device-name prefix via :class:`DeviceType` and returns either
    a :class:`PoolCleanerDevice` (for Spino variants) or a :class:`MowerDevice`
    (the historical default).
    """
    # Local import to avoid a circular dependency between
    # pymammotion.data.model.device and pymammotion.utility.device_type.
    from pymammotion.utility.device_type import DeviceType

    if DeviceType.is_swimming_pool(name):
        return PoolCleanerDevice(name=name)
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


MowerDevice.to_jsonb = _mower_device_to_jsonb  # type: ignore[method-assign]
MowerDevice.to_json = _mower_device_to_json  # type: ignore[method-assign]
