"""RTK protobuf commands."""

from abc import ABC
from logging import getLogger
import time

from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.proto import (
    AppToBaseMqttRtkT,
    BaseStation,
    LubaMsg,
    MsgAttr,
    MsgCmdType,
    MsgDevice,
    RequestBasestationInfoT,
)

logger = getLogger(__name__)


class MessageBasestation(AbstractMessage, ABC):
    def send_order_msg_basestation(self, driver) -> bytes:
        return LubaMsg(
            msgtype=MsgCmdType.BASESTATION,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=self.get_msg_device(MsgCmdType.BASESTATION, MsgDevice.DEV_MAINCTL),
            msgattr=MsgAttr.REQ,
            timestamp=round(time.time() * 1000),
            seqs=self.seqs.increment_and_get() & 255,
            version=1,
            subtype=self.user_account,
            driver=driver,
        ).SerializeToString()

    def basestation_info(self) -> bytes:
        """Build and send a request to get basestation info (request_type=1)."""
        base = BaseStation(to_dev=RequestBasestationInfoT(request_type=1))
        return self.send_order_msg_basestation(base)

    def set_base_net_rtk_switch(self, rtk_switch: int) -> bytes:
        """Set RTK switch via app_to_base_mqtt_rtk_t."""
        base = BaseStation(app_to_base_mqtt_rtk_msg=AppToBaseMqttRtkT(rtk_switch=rtk_switch))
        return self.send_order_msg_basestation(base)
