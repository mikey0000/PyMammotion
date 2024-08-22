from pymammotion.mammotion.commands.messages.driver import MessageDriver
from pymammotion.mammotion.commands.messages.navigation import MessageNavigation
from pymammotion.mammotion.commands.messages.network import MessageNetwork
from pymammotion.mammotion.commands.messages.ota import MessageOta
from pymammotion.mammotion.commands.messages.system import MessageSystem
from pymammotion.mammotion.commands.messages.video import MessageVideo
from pymammotion.proto import dev_net_pb2, luba_msg_pb2


class MammotionCommand(MessageSystem, MessageNavigation, MessageNetwork, MessageOta, MessageVideo, MessageDriver):
    """MQTT commands for Luba."""

    def __init__(self, device_name: str) -> None:
        self._device_name = device_name
        self._product_key = ""

    def get_device_name(self) -> str:
        """Get device name."""
        return self._device_name

    def get_device_product_key(self) -> str:
        return self._product_key

    def set_device_product_key(self, product_key: str) -> None:
        self._product_key = product_key

    """BLE commands for Luba."""

    def send_todev_ble_sync(self, sync_type: int) -> bytes:
        commEsp = dev_net_pb2.DevNet(todev_ble_sync=sync_type)

        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_ESP
        lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.msgattr = luba_msg_pb2.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.net.CopyFrom(commEsp)
        return lubaMsg.SerializeToString()
