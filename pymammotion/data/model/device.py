"""MowingDevice class to wrap around the betterproto dataclasses."""

from dataclasses import dataclass, field
from typing import Optional

import betterproto
from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.data.model import HashList, RapidState
from pymammotion.data.model.device_info import MowerInfo
from pymammotion.data.model.location import Location
from pymammotion.data.model.report_info import ReportData
from pymammotion.data.mqtt.properties import ThingPropertiesMessage
from pymammotion.http.model.http import ErrorInfo
from pymammotion.proto.mctrl_sys import (
    MowToAppInfoT,
    ReportInfoData,
    SystemRapidStateTunnelMsg,
    SystemUpdateBufMsg,
)
from pymammotion.utility.constant import WorkMode
from pymammotion.utility.conversions import parse_double
from pymammotion.utility.map import CoordinateConverter


@dataclass
class MowingDevice(DataClassORJSONMixin):
    """Wraps the betterproto dataclasses, so we can bypass the groups for keeping all data."""

    mower_state: MowerInfo = field(default_factory=MowerInfo)
    mqtt_properties: ThingPropertiesMessage | None = None
    map: HashList = field(default_factory=HashList)
    location: Location = field(default_factory=Location)
    mowing_state: RapidState = field(default_factory=RapidState)
    report_data: ReportData = field(default_factory=ReportData)
    err_code_list: list = field(default_factory=list)
    err_code_list_time: Optional[list] = field(default_factory=list)
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
                self.location.orientation = location.real_toward / 10000
                self.location.device = coordinate_converter.enu_to_lla(
                    parse_double(location.real_pos_y, 4.0), parse_double(location.real_pos_x, 4.0)
                )
                if location.zone_hash:
                    self.location.work_zone = (
                        location.zone_hash if self.report_data.dev.sys_status == WorkMode.MODE_WORKING else 0
                    )

        self.report_data.update(toapp_report_data.to_dict(casing=betterproto.Casing.SNAKE))

    def run_state_update(self, rapid_state: SystemRapidStateTunnelMsg) -> None:
        coordinate_converter = CoordinateConverter(self.location.RTK.latitude, self.location.RTK.longitude)
        self.mowing_state = RapidState().from_raw(rapid_state.rapid_state_data)
        self.location.position_type = self.mowing_state.pos_type
        self.location.orientation = self.mowing_state.toward / 10000
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
