"""Manage state from notifications into MowingDevice."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import logging
from typing import Any

import betterproto2
from shapely import Point

from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.device_info import SideLight
from pymammotion.data.model.generate_geojson import GeojsonGenerator
from pymammotion.data.model.hash_list import (
    AreaHashNameList,
    MowPath,
    NavGetCommData,
    NavGetHashListData,
    Plan,
    SvgMessage,
)
from pymammotion.data.model.location import Dock, LocationPoint
from pymammotion.data.model.work import CurrentTaskSettings
from pymammotion.data.mqtt.event import ThingEventMessage
from pymammotion.data.mqtt.properties import ThingPropertiesMessage
from pymammotion.data.mqtt.status import ThingStatusMessage
from pymammotion.event.event import DataEvent
from pymammotion.proto import (
    AppGetAllAreaHashName,
    AppGetCutterWorkMode,
    AppSetCutterWorkMode,
    CoverPathUploadT,
    DeviceFwInfo,
    DeviceProductTypeInfoT,
    DrvDevInfoResp,
    DrvDevInfoResult,
    Getlamprsp,
    GetNetworkInfoRsp,
    LubaMsg,
    NavGetCommDataAck,
    NavGetHashListAck,
    NavPlanJobSet,
    NavReqCoverPath,
    NavSysParamMsg,
    NavUnableTimeSet,
    SvgMessageAckT,
    TimeCtrlLight,
    WifiIotStatusReport,
)
from pymammotion.utility.map import CoordinateConverter

logger = logging.getLogger(__name__)


class MowerStateManager:
    """Manage state."""

    def __init__(self, device: MowingDevice) -> None:
        """Initialize state manager with a device."""
        self._device: MowingDevice = device
        self.last_updated_at = datetime.now(UTC)
        self.cloud_gethash_ack_callback: Callable[[NavGetHashListAck], Awaitable[None]] | None = None
        self.cloud_get_commondata_ack_callback: (
            Callable[[NavGetCommDataAck | SvgMessageAckT], Awaitable[None]] | None
        ) = None
        self.cloud_on_notification_callback = DataEvent()
        self.cloud_queue_command_callback = DataEvent()

        self.cloud_get_plan_callback: Callable[[NavPlanJobSet], Awaitable[None]] | None = None
        self.ble_gethash_ack_callback: Callable[[NavGetHashListAck], Awaitable[None]] | None = None
        self.ble_get_commondata_ack_callback: Callable[[NavGetCommDataAck | SvgMessageAckT], Awaitable[None]] | None = (
            None
        )
        self.ble_get_plan_callback: Callable[[NavPlanJobSet], Awaitable[None]] | None = None
        self.ble_on_notification_callback = DataEvent()
        self.ble_queue_command_callback = DataEvent()

        self.properties_callback = DataEvent()
        self.status_callback = DataEvent()
        self.device_event_callback = DataEvent()

    def get_device(self) -> MowingDevice:
        """Get device."""
        return self._device

    def set_device(self, device: MowingDevice) -> None:
        """Set device."""
        self._device = device

    async def properties(self, thing_properties: ThingPropertiesMessage) -> None:
        """Update device properties and invoke callback."""
        # TODO update device based off thing properties
        self._device.mqtt_properties = thing_properties
        await self.on_properties_callback(thing_properties)

    async def status(self, thing_status: ThingStatusMessage) -> None:
        """Update device status and invoke callback."""
        if not self._device.online:
            self._device.online = True
        self._device.status_properties = thing_status
        if self._device.mower_state.product_key == "":
            self._device.mower_state.product_key = thing_status.params.product_key
        await self.on_status_callback(thing_status)

    async def device_event(self, device_event: ThingEventMessage) -> None:
        """Sets MQTT event and calls callback."""
        self._device.mqtt_device_event = device_event
        await self.on_device_event_callback(device_event)

    @property
    def online(self) -> bool:
        """Return online status."""
        return self._device.online

    @online.setter
    def online(self, value: bool) -> None:
        """Set online status."""
        self._device.online = value

    async def gethash_ack_callback(self, msg: NavGetHashListAck) -> None:
        """Dispatch hash list acknowledgment to available callback."""
        if self.cloud_gethash_ack_callback:
            await self.cloud_gethash_ack_callback(msg)
        elif self.ble_gethash_ack_callback:
            await self.ble_gethash_ack_callback(msg)

    async def on_notification_callback(self, res: tuple[str, Any | None]) -> None:
        """Dispatch notification to available callback."""
        if self.cloud_on_notification_callback:
            await self.cloud_on_notification_callback.data_event(res)
        elif self.ble_on_notification_callback:
            await self.ble_on_notification_callback.data_event(res)

    async def on_properties_callback(self, thing_properties: ThingPropertiesMessage) -> None:
        """Call properties callback if it exists."""
        if self.properties_callback:
            await self.properties_callback.data_event(thing_properties)

    async def on_status_callback(self, thing_status: ThingStatusMessage) -> None:
        """Execute the status callback if it is set."""
        if self.status_callback:
            await self.status_callback.data_event(thing_status)

    async def on_device_event_callback(self, device_event: ThingEventMessage) -> None:
        """Executes the event callback if it is set."""
        if self.device_event_callback:
            await self.device_event_callback.data_event(device_event)

    async def get_commondata_ack_callback(self, comm_data: NavGetCommDataAck | SvgMessageAckT) -> None:
        """Asynchronously calls the appropriate callback based on available handlers."""
        if self.cloud_get_commondata_ack_callback:
            await self.cloud_get_commondata_ack_callback(comm_data)
        elif self.ble_get_commondata_ack_callback:
            await self.ble_get_commondata_ack_callback(comm_data)

    async def get_plan_callback(self, planjob: NavPlanJobSet) -> None:
        """Dispatch plan job to available callback."""
        if self.cloud_get_plan_callback:
            await self.cloud_get_plan_callback(planjob)
        elif self.ble_get_plan_callback:
            await self.ble_get_plan_callback(planjob)

    async def queue_command_callback(self, **kwargs: Any) -> None:
        """Queue command to available callback."""
        if self.cloud_queue_command_callback:
            await self.cloud_queue_command_callback.data_event(**kwargs)
        elif self.ble_queue_command_callback:
            await self.ble_queue_command_callback.data_event(**kwargs)

    async def notification(self, message: LubaMsg) -> None:
        """Handle protobuf notifications."""
        res = betterproto2.which_one_of(message, "LubaSubMsg")
        self.last_updated_at = datetime.now(UTC)
        # additional catch all if we don't get a status update
        if not self._device.online:
            self._device.online = True

        match res[0]:
            case "nav":
                await self._update_nav_data(message)
            case "sys":
                self._update_sys_data(message)
            case "driver":
                self._update_driver_data(message)
            case "net":
                self._update_net_data(message)
            case "mul":
                self._update_mul_data(message)
            case "ota":
                self._update_ota_data(message)

        await self.on_notification_callback(res)

    async def _update_nav_data(self, message: LubaMsg) -> None:
        """Update nav data."""
        nav_msg = betterproto2.which_one_of(message.nav, "SubNavMsg")
        match nav_msg[0]:
            case "toapp_gethash_ack":
                hashlist_ack: NavGetHashListAck = nav_msg[1]
                self._device.map.update_root_hash_list(
                    NavGetHashListData.from_dict(hashlist_ack.to_dict(casing=betterproto2.Casing.SNAKE))
                )
                await self.gethash_ack_callback(nav_msg[1])
            case "toapp_get_commondata_ack":
                common_data: NavGetCommDataAck = nav_msg[1]
                updated = self._device.map.update(
                    NavGetCommData.from_dict(common_data.to_dict(casing=betterproto2.Casing.SNAKE))
                )
                if updated:
                    if len(self._device.map.missing_hashlist(0)) == 0:
                        self.generate_geojson(self._device.location.RTK, self._device.location.dock)

                    await self.get_commondata_ack_callback(common_data)
            case "cover_path_upload":
                mow_path: CoverPathUploadT = nav_msg[1]
                self._device.map.update_mow_path(MowPath.from_dict(mow_path.to_dict(casing=betterproto2.Casing.SNAKE)))
                if len(self._device.map.find_missing_mow_path_frames()) == 0:
                    self.generate_mowing_geojson(self._device.location.RTK)

            case "todev_planjob_set":
                planjob: NavPlanJobSet = nav_msg[1]
                self._device.map.update_plan(Plan.from_dict(planjob.to_dict(casing=betterproto2.Casing.SNAKE)))
                await self.get_plan_callback(planjob)

            case "toapp_svg_msg":
                common_svg_data: SvgMessageAckT = nav_msg[1]
                updated = self._device.map.update(
                    SvgMessage.from_dict(common_svg_data.to_dict(casing=betterproto2.Casing.SNAKE))
                )
                if updated:
                    await self.get_commondata_ack_callback(common_svg_data)

            case "toapp_all_hash_name":
                hash_names: AppGetAllAreaHashName = nav_msg[1]
                converted_list = [AreaHashNameList(name=item.name, hash=item.hash) for item in hash_names.hashnames]
                self._device.map.area_name = converted_list

            case "bidire_reqconver_path":
                work_settings: NavReqCoverPath = nav_msg[1]

                current_task = CurrentTaskSettings.from_dict(work_settings.to_dict(casing=betterproto2.Casing.SNAKE))

                if current_task.path_hash == 0:
                    self._device.map.current_mow_path = {}

                if work_settings.sub_cmd == 0:
                    await self.queue_command_callback(key="get_all_boundary_hash_list", sub_cmd=3)

                self._device.work = current_task

            case "nav_sys_param_cmd":
                settings: NavSysParamMsg = nav_msg[1]
                match settings.id:
                    case 3:
                        self._device.mower_state.rain_detection = bool(settings.context)
                    case 6:
                        self._device.mower_state.turning_mode = settings.context
                    case 7:
                        self._device.mower_state.traversal_mode = settings.context
            case "todev_unable_time_set":
                nav_non_work_time: NavUnableTimeSet = nav_msg[1]
                self._device.non_work_hours.non_work_sub_cmd = nav_non_work_time.sub_cmd
                self._device.non_work_hours.start_time = nav_non_work_time.unable_start_time
                self._device.non_work_hours.end_time = nav_non_work_time.unable_end_time

    def _update_sys_data(self, message) -> None:
        """Update system."""
        sys_msg = betterproto2.which_one_of(message.sys, "SubSysMsg")
        match sys_msg[0]:
            case "system_update_buf":
                self._device.buffer(sys_msg[1])
            case "toapp_report_data":
                self._device.update_report_data(sys_msg[1])
            case "mow_to_app_info":
                self._device.mow_info(sys_msg[1])
            case "system_tard_state_tunnel":
                self._device.run_state_update(sys_msg[1])
            case "todev_time_ctrl_light":
                ctrl_light: TimeCtrlLight = sys_msg[1]
                side_led: SideLight = SideLight.from_dict(ctrl_light.to_dict(casing=betterproto2.Casing.SNAKE))
                self._device.mower_state.side_led = side_led
            case "device_product_type_info":
                device_product_type: DeviceProductTypeInfoT = sys_msg[1]
                if device_product_type.main_product_type != "" or device_product_type.sub_product_type != "":
                    self._device.mower_state.model_id = device_product_type.main_product_type
                    self._device.mower_state.sub_model_id = device_product_type.sub_product_type
            case "toapp_dev_fw_info":
                device_fw_info: DeviceFwInfo = sys_msg[1]
                self._device.device_firmwares.device_version = device_fw_info.version
                self._device.mower_state.swversion = device_fw_info.version

    def _update_driver_data(self, message) -> None:
        """Update driver data."""
        driver_msg = betterproto2.which_one_of(message.driver, "SubDrvMsg")
        match driver_msg[0]:
            case "current_cutter_mode":
                cutter_work_mode: AppGetCutterWorkMode = driver_msg[1]
                self._device.mower_state.cutter_mode = cutter_work_mode.current_cutter_mode
                self._device.mower_state.cutter_rpm = cutter_work_mode.current_cutter_rpm
            case "cutter_mode_ctrl_by_hand":
                cutter_work_mode_set: AppSetCutterWorkMode = driver_msg[1]
                self._device.mower_state.cutter_mode = cutter_work_mode_set.cutter_mode

    def _update_net_data(self, message) -> None:
        """Update network data."""
        net_msg = betterproto2.which_one_of(message.net, "NetSubType")
        match net_msg[0]:
            case "toapp_wifi_iot_status":
                wifi_iot_status: WifiIotStatusReport = net_msg[1]
                self._device.mower_state.product_key = wifi_iot_status.product_key
            case "toapp_devinfo_resp":
                toapp_devinfo_resp: DrvDevInfoResp = net_msg[1]
                for resp in toapp_devinfo_resp.resp_ids:
                    if resp.res == DrvDevInfoResult.DRV_RESULT_SUC and resp.id == 1 and resp.type == 6:
                        self._device.mower_state.swversion = resp.info
                        self._device.device_firmwares.device_version = resp.info
            case "toapp_networkinfo_rsp":
                get_network_info_resp: GetNetworkInfoRsp = net_msg[1]
                self._device.mower_state.wifi_mac = get_network_info_resp.wifi_mac

    def _update_mul_data(self, message) -> None:
        """Media and video states."""
        mul_msg = betterproto2.which_one_of(message.mul, "SubMul")
        match mul_msg[0]:
            case "get_lamp_rsp":
                lamp_resp: Getlamprsp = mul_msg[1]
                self._device.mower_state.lamp_info.lamp_bright = lamp_resp.lamp_bright
                if lamp_resp.get_ids in (1126, 1127):
                    self._device.mower_state.lamp_info.lamp_bright = lamp_resp.lamp_bright
                    self._device.mower_state.lamp_info.manual_light = bool(lamp_resp.lamp_manual_ctrl.value) or bool(
                        lamp_resp.lamp_bright
                    )
                if lamp_resp.get_ids == 1123:
                    self._device.mower_state.lamp_info.lamp_bright = lamp_resp.lamp_bright
                    self._device.mower_state.lamp_info.night_light = bool(lamp_resp.lamp_ctrl.value) or bool(
                        lamp_resp.lamp_bright
                    )

    def _update_ota_data(self, message) -> None:
        """Update OTA data."""

    def generate_geojson(self, rtk: LocationPoint, dock: Dock) -> Any:
        """Generate geojson from frames."""
        coordinator_converter = CoordinateConverter(rtk.latitude, rtk.longitude)
        RTK_real_loc = coordinator_converter.enu_to_lla(0, 0)

        dock_location = coordinator_converter.enu_to_lla(dock.latitude, dock.longitude)
        dock_rotation = coordinator_converter.get_transform_yaw_with_yaw(dock.rotation) + 180

        self._device.map.generated_geojson = GeojsonGenerator.generate_geojson(
            self._device.map,
            Point(RTK_real_loc.latitude, RTK_real_loc.longitude),
            Point(dock_location.latitude, dock_location.longitude),
            int(dock_rotation),
        )

        return self._device.map.generated_geojson

    def generate_mowing_geojson(self, rtk: LocationPoint) -> Any:
        """Generate geojson from frames."""
        coordinator_converter = CoordinateConverter(rtk.latitude, rtk.longitude)
        RTK_real_loc = coordinator_converter.enu_to_lla(0, 0)

        self._device.map.generated_mow_path_geojson = GeojsonGenerator.generate_mow_path_geojson(
            self._device.map,
            Point(RTK_real_loc.latitude, RTK_real_loc.longitude),
        )

        return self._device.map.generated_mow_path_geojson
