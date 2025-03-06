# === sendOrderMsg_Media ===
from abc import ABC

from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.proto import LubaMsg, MsgAttr, MsgCmdType, MsgDevice, MulLanguage


class MessageMedia(AbstractMessage, ABC):
    def send_order_msg_media(self, mul):
        luba_msg = LubaMsg.LubaMsg(
            msgtype=MsgCmdType.MUL,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=self.get_msg_device(MsgCmdType.MUL, MsgDevice.SOC_MODULE_MULTIMEDIA),
            msgattr=MsgAttr.REQ,
            seqs=1,
            version=1,
            subtype=1,
            mul=mul,
        )

        return luba_msg.SerializeToString()

    def set_car_volume(self, volume: int):
        return self.send_order_msg_media(LubaMsg.SocMul(set_audio=LubaMsg.MulSetAudio(at_switch=volume)))

    def set_car_voice_language(self, language_type: MulLanguage | str | None):
        return self.send_order_msg_media(LubaMsg.SocMul(set_audio=LubaMsg.MulSetAudio(au_language=language_type)))

    def set_car_wiper(self, round_num: int):
        return self.send_order_msg_media(LubaMsg.SocMul(set_wiper=LubaMsg.MulSetWiper(round=round_num)))
