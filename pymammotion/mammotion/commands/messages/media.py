# === sendOrderMsg_Media ===
from abc import ABC

from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.proto import (
    MUL_LANGUAGE,
    MUL_SEX,
    GetHeadlamp,
    LampCtrlSta,
    LampManualCtrlSta,
    LubaMsg,
    MsgAttr,
    MsgCmdType,
    MsgDevice,
    MulSetAudio,
    MulSetWiper,
    SetHeadlamp,
    SocMul,
)


class MessageMedia(AbstractMessage, ABC):
    def send_order_msg_media(self, mul):
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.MUL,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=self.get_msg_device(MsgCmdType.MUL, MsgDevice.SOC_MODULE_MULTIMEDIA),
            msgattr=MsgAttr.REQ,
            seqs=self.seqs.increment_and_get() & 255,
            version=1,
            subtype=self.user_account,
            mul=mul,
        )

        return luba_msg.SerializeToString()

    def set_car_volume(self, volume: int):
        """Set the car volume. 0 - 100"""
        return self.send_order_msg_media(SocMul(set_audio=MulSetAudio(at_switch=volume)))

    def set_car_voice_language(self, language_type: MUL_LANGUAGE | str | None):
        return self.send_order_msg_media(SocMul(set_audio=MulSetAudio(au_language=language_type)))

    def set_car_volume_sex(self, sex: MUL_SEX):
        return self.send_order_msg_media(SocMul(set_audio=MulSetAudio(sex=sex)))

    def set_car_wiper(self, round_num: int):
        """Set mower wiper."""
        # 2
        return self.send_order_msg_media(SocMul(set_wiper=MulSetWiper(round=round_num)))

    def get_car_light(self, ids: int):
        """Get mower light settings.
        1126 for manual
        1123 for night time settings
        """
        return self.send_order_msg_media(SocMul(get_lamp=GetHeadlamp(get_ids=ids)))

    def set_car_light(self, on_off: bool = False):
        """Set mower light.

        set whether light is on during the night during mowing
        auto night on true, id=1121, power_ctrl=1
        auto night off false, id=1121, power_ctrl=1
        """

        ctrl_state = LampCtrlSta.power_ctrl_on if on_off else LampCtrlSta.power_off
        return self.send_order_msg_media(
            SocMul(
                set_lamp=SetHeadlamp(
                    set_ids=1121, lamp_power_ctrl=1, lamp_ctrl=ctrl_state, ctrl_lamp_bright=False, lamp_bright=0
                )
            )
        )

    def set_car_manual_light(self, manual_ctrl: bool = False):
        """Set mower light.

        set whether light is on manually
        manual on: true, id=1125, power_ctrl=2
        manual off: false, id=1127, power_ctrl=2
        """
        ids = 1125 if manual_ctrl else 1127
        manual_light_ctrl = LampManualCtrlSta.manual_power_off if manual_ctrl else LampManualCtrlSta.manual_power_on
        return self.send_order_msg_media(
            SocMul(set_lamp=SetHeadlamp(set_ids=ids, lamp_power_ctrl=2, lamp_manual_ctrl=manual_light_ctrl))
        )
