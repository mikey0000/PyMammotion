"""Mower-specific device class with map synchronization callbacks."""

from abc import ABC
import logging

from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.model import RegionData
from pymammotion.data.mower_state_manager import MowerStateManager
from pymammotion.mammotion.devices.base import MammotionBaseDevice
from pymammotion.proto import NavGetCommDataAck, NavGetHashListAck, NavPlanJobSet, SvgMessageAckT
from pymammotion.utility.device_type import DeviceType

_LOGGER = logging.getLogger(__name__)


def find_next_integer(lst: list[int], current_hash: int) -> int | None:
    """Find the next integer in a list after the current hash."""
    try:
        current_index = lst.index(current_hash)
        if current_index + 1 < len(lst):
            return lst[current_index + 1]
        else:
            return None
    except ValueError:
        return None


class MammotionMowerDevice(MammotionBaseDevice, ABC):
    """Mower device with map synchronization support."""

    def __init__(self, state_manager: MowerStateManager, cloud_device: Device) -> None:
        """Initialize MammotionMowerDevice."""
        super().__init__(state_manager, cloud_device)

    async def datahash_response(self, hash_ack: NavGetHashListAck) -> None:
        """Handle datahash responses for root level hashs."""
        current_frame = hash_ack.current_frame

        missing_frames = self.mower.map.missing_root_hash_frame(hash_ack)
        if len(missing_frames) == 0:
            if len(self.mower.map.missing_hashlist(hash_ack.sub_cmd)) > 0:
                data_hash = self.mower.map.missing_hashlist(hash_ack.sub_cmd).pop(0)
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
                self.mower.map.missing_hashlist(common_data.sub_cmd).pop(0)
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
            region_data.action = common_data.action if isinstance(common_data, NavGetCommDataAck) else 0
            region_data.type = common_data.type
            region_data.sub_cmd = common_data.sub_cmd
            region_data.total_frame = total_frame
            region_data.current_frame = current_frame
            await self.queue_command("get_regional_data", regional_data=region_data)

    async def plan_callback(self, plan: NavPlanJobSet) -> None:
        """Handle plan job responses."""
        if plan.plan_index < plan.total_plan_num - 1:
            index = plan.plan_index + 1
            await self.queue_command("read_plan", sub_cmd=2, plan_index=index)

    async def start_schedule_sync(self) -> None:
        """Start sync of schedule data."""
        if len(self.mower.map.plan) == 0 or list(self.mower.map.plan.values())[0].total_plan_num != len(
            self.mower.map.plan
        ):
            await self.queue_command("read_plan", sub_cmd=2, plan_index=0)

    async def start_map_sync(self) -> None:
        """Start sync of map data."""
        if location := next((loc for loc in self.mower.report_data.locations if loc.pos_type == 5), None):
            self.mower.map.update_hash_lists(self.mower.map.hashlist, location.bol_hash)

        await self.queue_command("send_todev_ble_sync", sync_type=3)

        # TODO correctly check if area names exist for a zone.
        if self._cloud_device and len(self.mower.map.area_name) == 0 and not DeviceType.is_luba1(self.mower.name):
            await self.queue_command("get_area_name_list", device_id=self._cloud_device.iot_id)

        if len(self.mower.map.root_hash_lists) == 0 or len(self.mower.map.missing_hashlist()) > 0:
            await self.queue_command("get_all_boundary_hash_list", sub_cmd=0)

        for hash_id, frame in list(self.mower.map.area.items()):
            missing_frames = self.mower.map.find_missing_frames(frame)
            if len(missing_frames) > 0:
                del self.mower.map.area[hash_id]

        for hash_id, frame in list(self.mower.map.path.items()):
            missing_frames = self.mower.map.find_missing_frames(frame)
            if len(missing_frames) > 0:
                del self.mower.map.path[hash_id]

        for hash_id, frame in list(self.mower.map.obstacle.items()):
            missing_frames = self.mower.map.find_missing_frames(frame)
            if len(missing_frames) > 0:
                del self.mower.map.obstacle[hash_id]
