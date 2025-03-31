"""MowingDevice class to wrap around the betterproto dataclasses."""

from dataclasses import dataclass, field

import betterproto
from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.data.model import HashList, RapidState
from pymammotion.data.model.device_info import DeviceFirmwares, MowerInfo
from pymammotion.data.model.location import Location
from pymammotion.data.model.report_info import ReportData
from pymammotion.data.mqtt.properties import ThingPropertiesMessage
from pymammotion.data.mqtt.status import ThingStatusMessage
from pymammotion.http.model.http import ErrorInfo
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
    mower_state: MowerInfo = field(default_factory=MowerInfo)
    mqtt_properties: ThingPropertiesMessage | None = None
    status_properties: ThingStatusMessage | None = None
    map: HashList = field(default_factory=HashList)
    location: Location = field(default_factory=Location)
    mowing_state: RapidState = field(default_factory=RapidState)
    report_data: ReportData = field(default_factory=ReportData)
    device_firmwares: DeviceFirmwares = field(default_factory=DeviceFirmwares)
    err_code_list: list = field(default_factory=list)
    err_code_list_time: list | None = field(default_factory=list)
    error_codes: dict[str, ErrorInfo] = field(default_factory=dict)

    def buffer(self, buffer_list: SystemUpdateBufMsg) -> None:
        """Update the device based on which buffer we are reading from."""
        match buffer_list.update_buf_data[0]:
            case 1:
                # 4 speed
                self.location.RTK.latitude = parse_double(buffer_list.update_buf_data[5], 8.0)
                self.location.RTK.longitude = parse_double(buffer_list.update_buf_data[6], 8.0)
                self.location.dock.latitude = parse_double(buffer_list.update_buf_data[7], 4.0)
                self.location.dock.longitude = parse_double(buffer_list.update_buf_data[8], 4.0)
                self.location.dock.rotation = buffer_list.update_buf_data[3] + 180
            case 2:
                self.err_code_list.clear()
                self.err_code_list_time.clear()
                self.err_code_list.extend(
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
                self.err_code_list_time.extend(
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

    def update_report_data(self, toapp_report_data: ReportInfoData) -> None:
        coordinate_converter = CoordinateConverter(self.location.RTK.latitude, self.location.RTK.longitude)
        for index, location in enumerate(toapp_report_data.locations):
            if index == 0 and location.real_pos_y != 0:
                self.location.position_type = location.pos_type
                self.location.orientation = int(location.real_toward / 10000)
                self.location.device = coordinate_converter.enu_to_lla(
                    parse_double(location.real_pos_y, 4.0), parse_double(location.real_pos_x, 4.0)
                )
                if location.zone_hash:
                    self.location.work_zone = (
                        location.zone_hash if self.report_data.dev.sys_status == WorkMode.MODE_WORKING else 0
                    )

        if toapp_report_data.fw_info:
            self.update_device_firmwares(toapp_report_data.fw_info)

        self.report_data.update(toapp_report_data.to_dict(casing=betterproto.Casing.SNAKE))

    def run_state_update(self, rapid_state: SystemRapidStateTunnelMsg) -> None:
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
        pass

    def report_missing_data(self) -> None:
        """Report missing data so we can refetch it."""

    def update_device_firmwares(self, fw_info: DeviceFwInfo) -> None:
        """Sets firmware versions on all parts of the robot or RTK."""
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
