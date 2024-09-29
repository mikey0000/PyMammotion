from pymammotion.mammotion.commands.messages.driver import MessageDriver
from pymammotion.mammotion.commands.messages.media import MessageMedia
from pymammotion.mammotion.commands.messages.navigation import MessageNavigation
from pymammotion.mammotion.commands.messages.network import MessageNetwork
from pymammotion.mammotion.commands.messages.ota import MessageOta
from pymammotion.mammotion.commands.messages.system import MessageSystem
from pymammotion.mammotion.commands.messages.video import MessageVideo
from pymammotion.utility.movement import get_percent, transform_both_speeds


class MammotionCommand(
    MessageSystem, MessageNavigation, MessageNetwork, MessageOta, MessageVideo, MessageMedia, MessageDriver
):
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

    def move_forward(self, linear: float) -> bytes:
        """Move forward. values 0.0 1.0."""
        linear_percent = get_percent(abs(linear * 100))
        (linear_speed, angular_speed) = transform_both_speeds(90.0, 0.0, linear_percent, 0.0)
        return self.send_movement(linear_speed=linear_speed, angular_speed=angular_speed)

    def move_back(self, linear: float) -> bytes:
        """Move back. values 0.0 1.0."""
        linear_percent = get_percent(abs(linear * 100))
        (linear_speed, angular_speed) = transform_both_speeds(270.0, 0.0, linear_percent, 0.0)
        return self.send_movement(linear_speed=linear_speed, angular_speed=angular_speed)

    def move_left(self, angular: float) -> bytes:
        """Move forward. values 0.0 1.0."""
        angular_percent = get_percent(abs(angular * 100))
        (linear_speed, angular_speed) = transform_both_speeds(0.0, 0.0, 0.0, angular_percent)
        return self.send_movement(linear_speed=linear_speed, angular_speed=angular_speed)

    def move_right(self, angular: float) -> bytes:
        """Move back. values 0.0 1.0."""
        angular_percent = get_percent(abs(angular * 100))
        (linear_speed, angular_speed) = transform_both_speeds(0.0, 180.0, 0.0, angular_percent)
        return self.send_movement(linear_speed=linear_speed, angular_speed=angular_speed)
