# === sendOrderMsg_Video ===
from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.proto import luba_msg_pb2, luba_mul_pb2
from pymammotion.utility.device_type import DeviceType


class MessageVideo(AbstractMessage):
    async def send_order_msg_video(self, mul):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MSG_CMD_TYPE_MUL,
            sender=luba_msg_pb2.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.SOC_MODULE_MULTIMEDIA,
            mul=mul,
        )

        return luba_msg.SerializeToString()

    def device_agora_join_channel_with_position(self, enter_state: int):
        position = (
            luba_mul_pb2.MUL_CAMERA_POSITION.ALL
            if DeviceType.is_yuka(self.get_device_name())
            else luba_mul_pb2.MUL_CAMERA_POSITION.LEFT
        )
        mctl_sys = luba_mul_pb2.SocMul(set_video=luba_mul_pb2.MulSetVideo(position=position, vi_switch=enter_state))
        return self.send_order_msg_video(mctl_sys)
