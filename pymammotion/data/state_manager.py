"""Manage state from notifications into MowingDevice."""
from typing import Optional, Callable, Awaitable

import betterproto

from pymammotion.data.model.device import MowingDevice
from pymammotion.proto.luba_msg import LubaMsg
from pymammotion.proto.mctrl_nav import NavGetCommDataAck, NavGetHashListAck


class StateManager:
    """Manage state."""

    _device: MowingDevice

    def __init__(self, device: MowingDevice):
        self._device = device
        self.gethash_ack_callback: Optional[Callable[[NavGetHashListAck],Awaitable[None]]] = None
        self.get_commondata_ack_callback: Optional[Callable[[NavGetCommDataAck],Awaitable[None]]] = None

    def get_device(self) -> MowingDevice:
        """Get device."""
        return self._device

    def set_device(self, device: MowingDevice):
        """Set device."""
        self._device = device

    async def notification(self, message: LubaMsg):
        """Handle protobuf notifications."""
        res = betterproto.which_one_of(message, "LubaSubMsg")

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

    async def _update_nav_data(self, message):
        """Update nav data."""
        nav_msg = betterproto.which_one_of(message.nav, "SubNavMsg")
        match nav_msg[0]:
            case "toapp_gethash_ack":
                self._device.map.obstacle = dict()
                self._device.map.area = dict()
                self._device.map.path = dict()
                await self.gethash_ack_callback(nav_msg[1])
            case "toapp_get_commondata_ack":
                common_data: NavGetCommDataAck = nav_msg[1]
                updated = self._device.map.update(common_data)
                if updated:
                    await self.get_commondata_ack_callback(common_data)

    def _update_sys_data(self, message):
        """Update system."""
        sys_msg = betterproto.which_one_of(message.sys, "SubSysMsg")
        match sys_msg[0]:
            case "system_update_buf":
                self._device.buffer(sys_msg[1])
            case "toapp_report_data":
                self._device.update_report_data(sys_msg[1])
            case "mow_to_app_info":
                self._device.mow_info(sys_msg[1])

    def _update_driver_data(self, message):
        pass

    def _update_net_data(self, message):
        pass

    def _update_mul_data(self, message):
        pass

    def _update_ota_data(self, message):
        pass
