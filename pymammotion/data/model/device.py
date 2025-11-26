"""MowingDevice class to wrap around the betterproto dataclasses."""

from dataclasses import dataclass, field

import betterproto2
from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.data.model import HashList, RapidState
from pymammotion.data.model.device_info import DeviceFirmwares, DeviceNonWorkingHours, MowerInfo
from pymammotion.data.model.errors import DeviceErrors
from pymammotion.data.model.events import Events
from pymammotion.data.model.location import Location
from pymammotion.data.model.report_info import ReportData
from pymammotion.data.model.work import CurrentTaskSettings
from pymammotion.data.mqtt.event import ThingEventMessage
from pymammotion.data.mqtt.properties import ThingPropertiesMessage
from pymammotion.data.mqtt.status import ThingStatusMessage
from pymammotion.http.model.http import CheckDeviceVersion
from pymammotion.proto import DeviceFwInfo, MowToAppInfoT, ReportInfoData, SystemRapidStateTunnelMsg, SystemUpdateBufMsg
from pymammotion.utility.constant import WorkMode
from pymammotion.utility.conversions import parse_double
from pymammotion.utility.map import CoordinateConverter


@dataclass
class MowingDevice(DataClassORJSONMixin):
    """Wraps the betterproto dataclasses, so we can bypass the groups for keeping all data."""

    name: str = ""
    online: bool = True
    enabled: bool = True
    update_check: CheckDeviceVersion = field(default_factory=CheckDeviceVersion)
    mower_state: MowerInfo = field(default_factory=MowerInfo)
    mqtt_properties: ThingPropertiesMessage | None = None
    status_properties: ThingStatusMessage | None = None
    device_event: ThingEventMessage | None = None
    map: HashList = field(default_factory=HashList)
    work: CurrentTaskSettings = field(default_factory=CurrentTaskSettings)
    location: Location = field(default_factory=Location)
    mowing_state: RapidState = field(default_factory=RapidState)
    report_data: ReportData = field(default_factory=ReportData)
    device_firmwares: DeviceFirmwares = field(default_factory=DeviceFirmwares)
    errors: DeviceErrors = field(default_factory=DeviceErrors)
    non_work_hours: DeviceNonWorkingHours = field(default_factory=DeviceNonWorkingHours)
    events: Events = field(default_factory=Events)

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
                # task state event
                task_area_map: dict[int, int] = {}
                task_area_ids = []

                for i in range(3, len(buffer_list.update_buf_data), 2):
                    area_id = buffer_list.update_buf_data[i]

                    if area_id != 0:
                        area_value = int(buffer_list.update_buf_data[i + 1])
                        task_area_map[area_id] = area_value
                        task_area_ids.append(area_id)
                self.events.work_tasks_event.hash_area_map = task_area_map
                self.events.work_tasks_event.ids = task_area_ids

    def update_report_data(self, toapp_report_data: ReportInfoData) -> None:
        """Set report data for the mower."""
        coordinate_converter = CoordinateConverter(self.location.RTK.latitude, self.location.RTK.longitude)
        for index, location in enumerate(toapp_report_data.locations):
            if index == 0 and location.real_pos_y != 0:
                self.location.position_type = location.pos_type
                self.location.orientation = int(location.real_toward / 10000)
                self.location.device = coordinate_converter.enu_to_lla(
                    parse_double(location.real_pos_y, 4.0), parse_double(location.real_pos_x, 4.0)
                )
                self.map.invalidate_maps(location.bol_hash)
                if location.zone_hash:
                    self.location.work_zone = (
                        location.zone_hash if self.report_data.dev.sys_status == WorkMode.MODE_WORKING else 0
                    )

        if toapp_report_data.fw_info:
            self.update_device_firmwares(toapp_report_data.fw_info)

        if (
            toapp_report_data.work
            and (toapp_report_data.work.area >> 16) == 0
            and toapp_report_data.work.path_hash == 0
        ):
            self.work.zone_hashs = []
            self.map.current_mow_path = {}
            self.map.generated_mow_path_geojson = {}

        self.report_data.update(toapp_report_data.to_dict(casing=betterproto2.Casing.SNAKE))

    def run_state_update(self, rapid_state: SystemRapidStateTunnelMsg) -> None:
        """Set lat long, work zone of RTK and robot."""
        coordinate_converter = CoordinateConverter(self.location.RTK.latitude, self.location.RTK.longitude)
        self.mowing_state = RapidState().from_raw(rapid_state.rapid_state_data)
        self.location.position_type = self.mowing_state.pos_type
        self.location.orientation = int(self.mowing_state.toward / 10000)
        self.location.device = coordinate_converter.enu_to_lla(
            parse_double(self.mowing_state.pos_y, 4.0), parse_double(self.mowing_state.pos_x, 4.0)
        )
        if self.mowing_state.zone_hash:
            self.location.work_zone = (
                self.mowing_state.zone_hash if self.report_data.dev.sys_status == WorkMode.MODE_WORKING else 0
            )

    def mow_info(self, toapp_mow_info: MowToAppInfoT) -> None:
        """Set mow info."""

    def report_missing_data(self) -> None:
        """Report missing data so we can refetch it."""

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
                case 101:
                    # RTK main board
                    self.device_firmwares.main_controller = mod.version
                case 102:
                    self.device_firmwares.rtk_version = mod.version
                case 103:
                    self.device_firmwares.lora_version = mod.version


@dataclass
class RTKDevice(DataClassORJSONMixin):
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
