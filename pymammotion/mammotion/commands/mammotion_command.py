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
