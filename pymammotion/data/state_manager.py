"""Manage state from notifications into MowingDevice."""

from collections.abc import Awaitable, Callable
from datetime import datetime
import logging
from typing import Any

import betterproto

from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.device_info import SideLight
from pymammotion.data.model.hash_list import AreaHashNameList, NavGetCommData, NavGetHashListData, SvgMessage
from pymammotion.data.mqtt.properties import ThingPropertiesMessage
from pymammotion.data.mqtt.status import ThingStatusMessage
from pymammotion.proto import (
    AppGetAllAreaHashName,
    DeviceFwInfo,
    DeviceProductTypeInfoT,
    DrvDevInfoResp,
    DrvDevInfoResult,
    LubaMsg,
    NavGetCommDataAck,
    NavGetHashListAck,
    SvgMessageAckT,
    TimeCtrlLight,
    WifiIotStatusReport,
)

logger = logging.getLogger(__name__)


class StateManager:
    """Manage state."""

    _device: MowingDevice
    last_updated_at: datetime = datetime.now()
    cloud_gethash_ack_callback: Callable[[NavGetHashListAck], Awaitable[None]] | None = None
    cloud_get_commondata_ack_callback: Callable[[NavGetCommDataAck | SvgMessageAckT], Awaitable[None]] | None = None
    cloud_on_notification_callback: Callable[[tuple[str, Any | None]], Awaitable[None]] | None = None

    # possibly don't need anymore
    cloud_queue_command_callback: Callable[[str, dict[str, Any]], Awaitable[bytes]] | None = None

    ble_gethash_ack_callback: Callable[[NavGetHashListAck], Awaitable[None]] | None = None
    ble_get_commondata_ack_callback: Callable[[NavGetCommDataAck | SvgMessageAckT], Awaitable[None]] | None = None
    ble_on_notification_callback: Callable[[tuple[str, Any | None]], Awaitable[None]] | None = None

    # possibly don't need anymore
    ble_queue_command_callback: Callable[[str, dict[str, Any]], Awaitable[bytes]] | None = None

    def __init__(self, device: MowingDevice) -> None:
        self._device = device
        self.last_updated_at = datetime.now()

    def get_device(self) -> MowingDevice:
        """Get device."""
        return self._device

    def set_device(self, device: MowingDevice) -> None:
        """Set device."""
        self._device = device

    def properties(self, thing_properties: ThingPropertiesMessage) -> None:
        # TODO update device based off thing properties
        self._device.mqtt_properties = thing_properties

    def status(self, thing_status: ThingStatusMessage) -> None:
        if not self._device.online:
            self._device.online = True
        self._device.status_properties = thing_status
        if self._device.mower_state.product_key == "":
            self._device.mower_state.product_key = thing_status.params.productKey

    @property
    def online(self) -> bool:
        return self._device.online

    @online.setter
    def online(self, value: bool) -> None:
        self._device.online = value

    async def gethash_ack_callback(self, msg: NavGetHashListAck) -> None:
        if self.cloud_gethash_ack_callback:
            await self.cloud_gethash_ack_callback(msg)
        elif self.ble_gethash_ack_callback:
            await self.ble_gethash_ack_callback(msg)

    async def on_notification_callback(self, res: tuple[str, Any | None]) -> None:
        if self.cloud_on_notification_callback:
            await self.cloud_on_notification_callback(res)
        elif self.ble_on_notification_callback:
            await self.ble_on_notification_callback(res)

    async def get_commondata_ack_callback(self, comm_data: NavGetCommDataAck | SvgMessageAckT) -> None:
        if self.cloud_get_commondata_ack_callback:
            await self.cloud_get_commondata_ack_callback(comm_data)
        elif self.ble_get_commondata_ack_callback:
            await self.ble_get_commondata_ack_callback(comm_data)

    async def notification(self, message: LubaMsg) -> None:
        """Handle protobuf notifications."""
        res = betterproto.which_one_of(message, "LubaSubMsg")
        self.last_updated_at = datetime.now()
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

    async def _update_nav_data(self, message) -> None:
        """Update nav data."""
        nav_msg = betterproto.which_one_of(message.nav, "SubNavMsg")
        match nav_msg[0]:
            case "toapp_gethash_ack":
                hashlist_ack: NavGetHashListAck = nav_msg[1]
                self._device.map.update_root_hash_list(
                    NavGetHashListData.from_dict(hashlist_ack.to_dict(casing=betterproto.Casing.SNAKE))
                )
                await self.gethash_ack_callback(nav_msg[1])
            case "toapp_get_commondata_ack":
                common_data: NavGetCommDataAck = nav_msg[1]
                updated = self._device.map.update(
                    NavGetCommData.from_dict(common_data.to_dict(casing=betterproto.Casing.SNAKE))
                )
                if updated:
                    await self.get_commondata_ack_callback(common_data)
            case "toapp_svg_msg":
                common_svg_data: SvgMessageAckT = nav_msg[1]
                updated = self._device.map.update(
                    SvgMessage.from_dict(common_svg_data.to_dict(casing=betterproto.Casing.SNAKE))
                )
                if updated:
                    await self.get_commondata_ack_callback(common_svg_data)

            case "toapp_all_hash_name":
                hash_names: AppGetAllAreaHashName = nav_msg[1]
                converted_list = [AreaHashNameList(name=item.name, hash=item.hash) for item in hash_names.hashnames]
                self._device.map.area_name = converted_list

    def _update_sys_data(self, message) -> None:
        """Update system."""
        sys_msg = betterproto.which_one_of(message.sys, "SubSysMsg")
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
                side_led: SideLight = SideLight.from_dict(ctrl_light.to_dict(casing=betterproto.Casing.SNAKE))
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
        pass

    def _update_net_data(self, message) -> None:
        net_msg = betterproto.which_one_of(message.net, "NetSubType")
        match net_msg[0]:
            case "toapp_wifi_iot_status":
                wifi_iot_status: WifiIotStatusReport = net_msg[1]
                self._device.mower_state.product_key = wifi_iot_status.productkey
            case "toapp_devinfo_resp":
                toapp_devinfo_resp: DrvDevInfoResp = net_msg[1]
                for resp in toapp_devinfo_resp.resp_ids:
                    if resp.res == DrvDevInfoResult.DRV_RESULT_SUC and resp.id == 1 and resp.type == 6:
                        self._device.mower_state.swversion = resp.info
                        self._device.device_firmwares.device_version = resp.info

    def _update_mul_data(self, message) -> None:
        pass

    def _update_ota_data(self, message) -> None:
        pass
