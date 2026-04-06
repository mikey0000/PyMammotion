# === sendOrderMsg_Video ===
from abc import ABC
import time

from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.proto import (
    LubaMsg,
    MsgAttr,
    MsgCmdType,
    MsgDevice,
    MulCameraPosition,
    MulSetEncode,
    MulSetVideo,
    SocMul,
)
from pymammotion.utility.device_type import DeviceType


class MessageVideo(AbstractMessage, ABC):
    def send_order_msg_video(self, mul: SocMul):
        """Serialize and return a LubaMsg multimedia video request with the given payload."""
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
        """Join or leave the Agora video channel, selecting the correct camera position for the device type."""
        position = (
            MulCameraPosition.ALL
            if DeviceType.value_of_str(self.get_device_name()).get_value() == DeviceType.LUBA_YUKA.get_value()
            else MulCameraPosition.LEFT
        )
        soc_mul = SocMul(set_video=MulSetVideo(position=position, vi_switch=enter_state))
        return self.send_order_msg_video(soc_mul)

    def refresh_fpv(self) -> bytes:
        """Refresh the FPV frame (re-enable encode stream)."""
        return self.send_order_msg_video(SocMul(req_encode=MulSetEncode(encode=True)))
