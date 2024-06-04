# === sendOrderMsg_Media ===
from pyluba.proto import luba_msg_pb2, luba_mul_pb2


class MessageMedia:
    def send_order_msg_media(self, mul):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MSG_CMD_TYPE_MUL,
            sender=luba_msg_pb2.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.SOC_MODULE_MULTIMEDIA,
            msgattr=luba_msg_pb2.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            mul=mul)

        return luba_msg.SerializeToString()

    def set_car_volume(self, volume: int):
        return self.send_order_msg_media(luba_mul_pb2.SocMul(set_audio=luba_mul_pb2.MulSetAudio(au_switch=volume)))

    def set_car_voice_language(self, language_type: int):
        return self.send_order_msg_media(luba_mul_pb2.SocMul(set_audio=luba_mul_pb2.MulSetAudio(au_language_value=language_type)))

    def set_car_wiper(self, round: int):
        return self.send_order_msg_media(luba_mul_pb2.SocMul(set_wiper=luba_mul_pb2.MulSetWiper(round=round)))
