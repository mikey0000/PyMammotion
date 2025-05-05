from abc import abstractmethod
import asyncio
import logging
from typing import Any

import betterproto

from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.model import RegionData
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.raw_data import RawMowerData
from pymammotion.data.state_manager import StateManager
from pymammotion.proto import LubaMsg, NavGetCommDataAck, NavGetHashListAck, NavPlanJobSet, SvgMessageAckT
from pymammotion.utility.device_type import DeviceType

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

    def __init__(self, state_manager: StateManager, cloud_device: Device) -> None:
        """Initialize MammotionBaseDevice."""
        self.loop = asyncio.get_event_loop()
        self._state_manager = state_manager
        self._raw_data = dict()
        self._raw_mower_data: RawMowerData = RawMowerData()
        self._notify_future: asyncio.Future[bytes] | None = None
        self._cloud_device = cloud_device

    async def datahash_response(self, hash_ack: NavGetHashListAck) -> None:
        """Handle datahash responses for root level hashs."""
        current_frame = hash_ack.current_frame

        missing_frames = self.mower.map.missing_root_hash_frame(hash_ack)
        if len(missing_frames) == 0:
            if len(self.mower.map.missing_hashlist(0)) > 0:
                data_hash = self.mower.map.missing_hashlist(hash_ack.sub_cmd).pop()
                await self.queue_command("synchronize_hash_data", hash_num=data_hash)
            return

        if current_frame != missing_frames[0] - 1:
            current_frame = missing_frames[0] - 1
        await self.queue_command("get_hash_response", total_frame=hash_ack.total_frame, current_frame=current_frame)

    async def commdata_response(self, common_data: NavGetCommDataAck | SvgMessageAckT) -> None:
        """Handle common data responses."""
        total_frame = common_data.total_frame
        current_frame = common_data.current_frame

        missing_frames = self.mower.map.missing_frame(common_data)
        if len(missing_frames) == 0:
            # get next in hash ack list

            data_hash = (
                self.mower.map.missing_hashlist(common_data.sub_cmd).pop()
                if len(self.mower.map.missing_hashlist(common_data.sub_cmd)) > 0
                else None
            )
            if data_hash is None:
                return

            await self.queue_command("synchronize_hash_data", hash_num=data_hash)
        else:
            if current_frame != missing_frames[0] - 1:
                current_frame = missing_frames[0] - 1

            region_data = RegionData()
            region_data.hash = common_data.data_hash if isinstance(common_data, SvgMessageAckT) else common_data.hash
            region_data.action = common_data.action if isinstance(common_data, NavGetCommDataAck) else None
            region_data.type = common_data.type
            region_data.sub_cmd = common_data.sub_cmd
            region_data.total_frame = total_frame
            region_data.current_frame = current_frame
            await self.queue_command("get_regional_data", regional_data=region_data)

    async def plan_callback(self, plan: NavPlanJobSet) -> None:
        if plan.plan_index < plan.total_plan_num - 1:
            index = plan.plan_index + 1
            await self.queue_command("read_plan", sub_cmd=2, plan_index=index)

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

        self._raw_mower_data.update_raw(self._raw_data)

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
        return self._state_manager.get_device()

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
        await self.queue_command("allpowerfull_rw", rw_id=5, context=1, rw=1)
        await self.async_read_settings()

    async def start_map_sync(self) -> None:
        """Start sync of map data."""

        self.mower.map.update_hash_lists(self.mower.map.hashlist)

        await self.queue_command("send_todev_ble_sync", sync_type=3)

        if self._cloud_device and len(self.mower.map.area_name) == 0 and not DeviceType.is_luba1(self.mower.name):
            await self.queue_command("get_area_name_list", device_id=self._cloud_device.iotId)

        if len(self.mower.map.plan) == 0 or list(self.mower.map.plan.values())[0].total_plan_num != len(
            self.mower.map.plan
        ):
            await self.queue_command("read_plan", sub_cmd=2, plan_index=0)

        for hash, frame in list(self.mower.map.area.items()):
            missing_frames = self.mower.map.find_missing_frames(frame)
            if len(missing_frames) > 0:
                del self.mower.map.area[hash]

        for hash, frame in list(self.mower.map.path.items()):
            missing_frames = self.mower.map.find_missing_frames(frame)
            if len(missing_frames) > 0:
                del self.mower.map.path[hash]

        for hash, frame in list(self.mower.map.obstacle.items()):
            missing_frames = self.mower.map.find_missing_frames(frame)
            if len(missing_frames) > 0:
                del self.mower.map.obstacle[hash]

        # don't know why but total frame on svg is wrong
        # for hash, frame in self.mower.map.svg.items():
        #     missing_frames = self.mower.map.find_missing_frames(frame)
        #     if len(missing_frames) > 0:
        #         del self.mower.map.svg[hash]

        if len(self.mower.map.root_hash_lists) == 0 or len(self.mower.map.missing_hashlist()) > 0:
            await self.queue_command("get_all_boundary_hash_list", sub_cmd=0)

        # sub_cmd 3 is job hashes??
        # sub_cmd 4 is dump location (yuka)
        # jobs list
        #
        # await self.queue_command("get_all_boundary_hash_list", sub_cmd=3)

    async def async_read_settings(self) -> None:
        """Read settings from device."""
        await self.queue_command("allpowerfull_rw", rw_id=3, context=1, rw=0)
        await self.queue_command("allpowerfull_rw", rw_id=4, context=1, rw=0)
        await self.queue_command("allpowerfull_rw", rw_id=6, context=1, rw=0)
        # traversal mode
        await self.queue_command("allpowerfull_rw", rw_id=7, context=1, rw=0)

        await self.queue_command("read_and_set_sidelight", is_sidelight=True, operate=1)

        await self.queue_command("read_and_set_rtk_pairing_code", op=1, cfg="")

    async def async_get_errors(self) -> None:
        """Error codes."""
        await self.queue_command("allpowerfull_rw", rw_id=5, rw=1, context=2)
        await self.queue_command("allpowerfull_rw", rw_id=5, rw=1, context=3)

    async def command(self, key: str, **kwargs):
        """Send a command to the device."""
        return await self.queue_command(key, **kwargs)

    @property
    def state_manager(self):
        return self._state_manager
