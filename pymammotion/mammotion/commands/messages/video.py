# === sendOrderMsg_Video ===
from abc import ABC
import time

from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.proto import MUL_CAMERA_POSITION, LubaMsg, MsgAttr, MsgCmdType, MsgDevice, MulSetVideo, SocMul
from pymammotion.utility.device_type import DeviceType


class MessageVideo(AbstractMessage, ABC):
    def send_order_msg_video(self, mul: SocMul):
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.MUL,
            msgattr=MsgAttr.REQ,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=self.get_msg_device(MsgCmdType.MUL, MsgDevice.SOC_MODULE_MULTIMEDIA),
            mul=mul,
            seqs=self.seqs.increment_and_get() & 255,
            version=1,
            subtype=self.user_account,
            timestamp=round(time.time() * 1000),
        )

        return luba_msg.SerializeToString()

    def device_agora_join_channel_with_position(self, enter_state: int):
        position = (
            MUL_CAMERA_POSITION.ALL
            if DeviceType.value_of_str(self.get_device_name()).get_value() == DeviceType.LUBA_YUKA.get_value()
            else MUL_CAMERA_POSITION.LEFT
        )
        soc_mul = SocMul(set_video=MulSetVideo(position=position, vi_switch=enter_state))
        return self.send_order_msg_video(soc_mul)
