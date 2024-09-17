import asyncio
import logging
from abc import abstractmethod
from typing import Any, Awaitable, Callable

import betterproto

from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.model import RegionData
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.state_manager import StateManager
from pymammotion.proto import has_field
from pymammotion.proto.luba_msg import LubaMsg
from pymammotion.proto.mctrl_nav import NavGetCommDataAck, NavGetHashListAck
from pymammotion.utility.movement import get_percent, transform_both_speeds

_LOGGER = logging.getLogger(__name__)


def find_next_integer(lst: list[int], current_hash: int) -> int | None:
    try:
        # Find the index of the current integer
        current_index = lst.index(current_hash)

        # Check if there is a next integer in the list
        if current_index + 1 < len(lst):
            return lst[current_index + 1]
        else:
            return None  # Or raise an exception or handle it in some other way
    except ValueError:
        # Handle the case where current_int is not in the list
        return None  # Or raise an exception or handle it in some other way


class MammotionBaseDevice:
    """Base class for Mammotion devices."""

    _mower: MowingDevice
    _state_manager: StateManager
    _cloud_device: Device | None = None

    def __init__(self, device: MowingDevice, cloud_device: Device | None = None) -> None:
        """Initialize MammotionBaseDevice."""
        self.loop = asyncio.get_event_loop()
        self._raw_data = LubaMsg().to_dict(casing=betterproto.Casing.SNAKE)
        self._mower = device
        self._state_manager = StateManager(self._mower)
        self._state_manager.gethash_ack_callback = self.datahash_response
        self._state_manager.get_commondata_ack_callback = self.commdata_response
        self._notify_future: asyncio.Future[bytes] | None = None
        self._cloud_device = cloud_device

    def set_notification_callback(self, func: Callable[[], Awaitable[None]]) -> None:
        self._state_manager.on_notification_callback = func

    def set_queue_callback(self, func: Callable[[str, dict[str, Any]], Awaitable[bytes]]) -> None:
        self._state_manager.queue_command_callback = func

    async def datahash_response(self, hash_ack: NavGetHashListAck) -> None:
        """Handle datahash responses."""
        await self.queue_command("synchronize_hash_data", hash_num=hash_ack.data_couple[0])

    async def commdata_response(self, common_data: NavGetCommDataAck) -> None:
        """Handle common data responses."""
        total_frame = common_data.total_frame
        current_frame = common_data.current_frame

        missing_frames = self._mower.map.missing_frame(common_data)
        if len(missing_frames) == 0:
            # get next in hash ack list

            data_hash = find_next_integer(self._mower.nav.toapp_gethash_ack.data_couple, common_data.hash)
            if data_hash is None:
                return

            await self.queue_command("synchronize_hash_data", hash_num=data_hash)
        else:
            if current_frame != missing_frames[0] - 1:
                current_frame = missing_frames[0] - 1

            region_data = RegionData()
            region_data.hash = common_data.hash
            region_data.action = common_data.action
            region_data.type = common_data.type
            region_data.total_frame = total_frame
            region_data.current_frame = current_frame
            await self.queue_command("get_regional_data", regional_data=region_data)

    def _update_raw_data(self, data: bytes) -> None:
        """Update raw and model data from notifications."""
        tmp_msg = LubaMsg().parse(data)
        res = betterproto.which_one_of(tmp_msg, "LubaSubMsg")
        match res[0]:
            case "nav":
                self._update_nav_data(tmp_msg)
            case "sys":
                self._update_sys_data(tmp_msg)
            case "driver":
                self._update_driver_data(tmp_msg)
            case "net":
                self._update_net_data(tmp_msg)
            case "mul":
                self._update_mul_data(tmp_msg)
            case "ota":
                self._update_ota_data(tmp_msg)

        self._mower.update_raw(self._raw_data)

    def _update_nav_data(self, tmp_msg) -> None:
        """Update navigation data."""
        nav_sub_msg = betterproto.which_one_of(tmp_msg.nav, "SubNavMsg")
        if nav_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", nav_sub_msg[0])
            return
        nav = self._raw_data.get("nav", {})
        if isinstance(nav_sub_msg[1], int):
            nav[nav_sub_msg[0]] = nav_sub_msg[1]
        else:
            nav[nav_sub_msg[0]] = nav_sub_msg[1].to_dict(casing=betterproto.Casing.SNAKE)
        self._raw_data["nav"] = nav

    def _update_sys_data(self, tmp_msg) -> None:
        """Update system data."""
        sys_sub_msg = betterproto.which_one_of(tmp_msg.sys, "SubSysMsg")
        if sys_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", sys_sub_msg[0])
            return
        sys = self._raw_data.get("sys", {})
        sys[sys_sub_msg[0]] = sys_sub_msg[1].to_dict(casing=betterproto.Casing.SNAKE)
        self._raw_data["sys"] = sys

    def _update_driver_data(self, tmp_msg) -> None:
        """Update driver data."""
        drv_sub_msg = betterproto.which_one_of(tmp_msg.driver, "SubDrvMsg")
        if drv_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", drv_sub_msg[0])
            return
        drv = self._raw_data.get("driver", {})
        drv[drv_sub_msg[0]] = drv_sub_msg[1].to_dict(casing=betterproto.Casing.SNAKE)
        self._raw_data["driver"] = drv

    def _update_net_data(self, tmp_msg) -> None:
        """Update network data."""
        net_sub_msg = betterproto.which_one_of(tmp_msg.net, "NetSubType")
        if net_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", net_sub_msg[0])
            return
        net = self._raw_data.get("net", {})
        if isinstance(net_sub_msg[1], int):
            net[net_sub_msg[0]] = net_sub_msg[1]
        else:
            net[net_sub_msg[0]] = net_sub_msg[1].to_dict(casing=betterproto.Casing.SNAKE)
        self._raw_data["net"] = net

    def _update_mul_data(self, tmp_msg) -> None:
        """Update mul data."""
        mul_sub_msg = betterproto.which_one_of(tmp_msg.mul, "SubMul")
        if mul_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", mul_sub_msg[0])
            return
        mul = self._raw_data.get("mul", {})
        mul[mul_sub_msg[0]] = mul_sub_msg[1].to_dict(casing=betterproto.Casing.SNAKE)
        self._raw_data["mul"] = mul

    def _update_ota_data(self, tmp_msg) -> None:
        """Update OTA data."""
        ota_sub_msg = betterproto.which_one_of(tmp_msg.ota, "SubOtaMsg")
        if ota_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", ota_sub_msg[0])
            return
        ota = self._raw_data.get("ota", {})
        ota[ota_sub_msg[0]] = ota_sub_msg[1].to_dict(casing=betterproto.Casing.SNAKE)
        self._raw_data["ota"] = ota

    @property
    def raw_data(self) -> dict[str, Any]:
        """Get the raw data of the device."""
        return self._raw_data

    @property
    def mower(self) -> MowingDevice:
        """Get the LubaMsg of the device."""
        return self._mower

    @abstractmethod
    async def queue_command(self, key: str, **kwargs: any) -> bytes | None:
        """Queue commands to mower."""

    @abstractmethod
    async def _ble_sync(self):
        """Send ble sync command every 3 seconds or sooner."""

    @abstractmethod
    def stop(self):
        """Stop everything ready for destroying."""

    async def start_sync(self, retry: int) -> None:
        """Start synchronization with the device."""
        await self.queue_command("get_device_base_info")
        await self.queue_command("get_device_product_model")
        await self.queue_command("get_report_cfg")
        """RTK and dock location."""
        await self.queue_command("allpowerfull_rw", id=5, rw=1, context=1)

    async def start_map_sync(self) -> None:
        """Start sync of map data."""
        try:
            # work out why this crashes sometimes for better proto

            if self._cloud_device and len(self._mower.map.area_name) == 0:
                await self.queue_command("get_area_name_list", device_id=self._cloud_device.iotId)
        except Exception:
            """Do nothing for now."""

        await self.queue_command("read_plan", sub_cmd=2, plan_index=0)

        if not has_field(self.mower.nav.toapp_gethash_ack):
            await self.queue_command("get_all_boundary_hash_list", sub_cmd=0)
            await self.queue_command("get_hash_response", total_frame=1, current_frame=1)
        else:
            for data_hash in self.mower.nav.toapp_gethash_ack.data_couple:
                await self.queue_command("synchronize_hash_data", hash_num=data_hash)

        # sub_cmd 3 is job hashes??
        # sub_cmd 4 is dump location (yuka)
        # jobs list
        # hash_list_result = await self._send_command_with_args("get_all_boundary_hash_list", sub_cmd=3)

    async def async_get_errors(self) -> None:
        """Error codes."""
        await self.queue_command("allpowerfull_rw", id=5, rw=1, context=2)
        await self.queue_command("allpowerfull_rw", id=5, rw=1, context=3)

    async def move_forward(self, linear: float) -> None:
        """Move forward. values 0.0 1.0."""
        linear_percent = get_percent(abs(linear * 100))
        (linear_speed, angular_speed) = transform_both_speeds(90.0, 0.0, linear_percent, 0.0)
        await self.queue_command("send_movement", linear_speed=linear_speed, angular_speed=angular_speed)

    async def move_back(self, linear: float) -> None:
        """Move back. values 0.0 1.0."""
        linear_percent = get_percent(abs(linear * 100))
        (linear_speed, angular_speed) = transform_both_speeds(270.0, 0.0, linear_percent, 0.0)
        await self.queue_command("send_movement", linear_speed=linear_speed, angular_speed=angular_speed)

    async def move_left(self, angulur: float) -> None:
        """Move forward. values 0.0 1.0."""
        angular_percent = get_percent(abs(angulur * 100))
        (linear_speed, angular_speed) = transform_both_speeds(0.0, 0.0, 0.0, angular_percent)
        await self.queue_command("send_movement", linear_speed=linear_speed, angular_speed=angular_speed)

    async def move_right(self, angulur: float) -> None:
        """Move back. values 0.0 1.0."""
        angular_percent = get_percent(abs(angulur * 100))
        (linear_speed, angular_speed) = transform_both_speeds(0.0, 180.0, 0.0, angular_percent)
        await self.queue_command("send_movement", linear_speed=linear_speed, angular_speed=angular_speed)

    async def command(self, key: str, **kwargs):
        """Send a command to the device."""
        return await self.queue_command(key, **kwargs)
