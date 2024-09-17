"""Manage state from notifications into MowingDevice."""

from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

import betterproto

from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.hash_list import AreaHashNameList
from pymammotion.proto.luba_msg import LubaMsg
from pymammotion.proto.mctrl_nav import AppGetAllAreaHashName, NavGetCommDataAck, NavGetHashListAck
from pymammotion.utility.constant import WorkMode


class StateManager:
    """Manage state."""

    _device: MowingDevice
    last_updated_at: datetime = datetime.now()

    def __init__(self, device: MowingDevice) -> None:
        self._device = device
        self.gethash_ack_callback: Optional[Callable[[NavGetHashListAck], Awaitable[None]]] = None
        self.get_commondata_ack_callback: Optional[Callable[[NavGetCommDataAck], Awaitable[None]]] = None
        self.on_notification_callback: Optional[Callable[[], Awaitable[None]]] = None
        self.queue_command_callback: Optional[Callable[[str, dict[str, Any]], Awaitable[bytes]]] = None
        self.last_updated_at = datetime.now()

    def get_device(self) -> MowingDevice:
        """Get device."""
        return self._device

    def set_device(self, device: MowingDevice) -> None:
        """Set device."""
        self._device = device

    async def notification(self, message: LubaMsg) -> None:
        """Handle protobuf notifications."""
        res = betterproto.which_one_of(message, "LubaSubMsg")
        self.last_updated_at = datetime.now()

        match res[0]:
            case "nav":
                await self._update_nav_data(message)
            case "sys":
                await self._update_sys_data(message)
            case "driver":
                self._update_driver_data(message)
            case "net":
                self._update_net_data(message)
            case "mul":
                self._update_mul_data(message)
            case "ota":
                self._update_ota_data(message)

        if self.on_notification_callback:
            await self.on_notification_callback()

    async def _update_nav_data(self, message) -> None:
        """Update nav data."""
        nav_msg = betterproto.which_one_of(message.nav, "SubNavMsg")
        match nav_msg[0]:
            case "toapp_gethash_ack":
                hashlist_ack: NavGetHashListAck = nav_msg[1]
                self._device.map.set_hashlist(hashlist_ack.data_couple)
                await self.gethash_ack_callback(nav_msg[1])
            case "toapp_get_commondata_ack":
                common_data: NavGetCommDataAck = nav_msg[1]
                updated = self._device.map.update(common_data)
                if updated:
                    await self.get_commondata_ack_callback(common_data)
            case "toapp_all_hash_name":
                hash_names: AppGetAllAreaHashName = nav_msg[1]
                converted_list = [AreaHashNameList(name=item.name, hash=item.hash) for item in hash_names.hashnames]
                self._device.map.area_name = converted_list

    async def _update_sys_data(self, message) -> None:
        """Update system."""
        sys_msg = betterproto.which_one_of(message.sys, "SubSysMsg")
        match sys_msg[0]:
            case "system_update_buf":
                self._device.buffer(sys_msg[1])
            case "toapp_report_data":
                self._device.update_report_data(sys_msg[1])
                if self.queue_command_callback:
                    if self._device.sys.toapp_report_data.dev.sys_status != WorkMode.MODE_WORKING:
                        await self.queue_command_callback("get_report_cfg_stop")
            case "mow_to_app_info":
                self._device.mow_info(sys_msg[1])
            case "system_tard_state_tunnel":
                self._device.run_state_update(sys_msg[1])

    def _update_driver_data(self, message) -> None:
        pass

    def _update_net_data(self, message) -> None:
        pass

    def _update_mul_data(self, message) -> None:
        pass

    def _update_ota_data(self, message) -> None:
        pass
