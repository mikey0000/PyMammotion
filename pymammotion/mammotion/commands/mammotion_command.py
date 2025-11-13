from pymammotion.mammotion.commands.messages.driver import MessageDriver
from pymammotion.mammotion.commands.messages.media import MessageMedia
from pymammotion.mammotion.commands.messages.navigation import MessageNavigation
from pymammotion.mammotion.commands.messages.network import MessageNetwork
from pymammotion.mammotion.commands.messages.ota import MessageOta
from pymammotion.mammotion.commands.messages.system import MessageSystem
from pymammotion.mammotion.commands.messages.video import MessageVideo
from pymammotion.utility.device_type import DeviceType
from pymammotion.utility.movement import get_percent, transform_both_speeds


class MammotionCommand(
    MessageSystem, MessageNavigation, MessageNetwork, MessageOta, MessageVideo, MessageMedia, MessageDriver
):
    """MQTT commands for Luba."""

    def __init__(self, device_name: str, user_account: int) -> None:
        self._device_name = device_name
        self._product_key = ""
        self.user_account = user_account

    def get_device_name(self) -> str:
        """Get device name."""
        return self._device_name

    def read_write_device(self, rw_id: int, context: int, rw: int):
        if (
            rw_id == 6 or rw_id == 3 or rw_id == 7 or rw_id == 8 or rw_id == 10 or rw_id == 11
        ) and DeviceType.is_luba_pro(self.get_device_name()):
            return self.allpowerfull_rw_adapter_x3(rw_id, context, rw)
        return self.allpowerfull_rw(rw_id, context, rw)

    def traverse_mode(self, context: int) -> bytes:
        """Sets the traversal mode back to charger."""
        # setReChargeMode
        # 0 direct
        # 1 follow the perimeter
        return self.read_write_device(7, context, 1)

    def turning_mode(self, context: int) -> bytes:
        """Sets the traversal mode back to charger."""
        # setTurnAroundMode
        # 0 zero turn
        # 1 multipoint turn
        return self.read_write_device(6, context, 1)

    def get_error_code(self) -> bytes:
        return self.read_write_device(5, 2, 1)

    def get_error_timestamp(self) -> bytes:
        return self.read_write_device(5, 3, 1)

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
        (linear_speed, angular_speed) = transform_both_speeds(0.0, 180.0, 0.0, angular_percent)
        return self.send_movement(linear_speed=linear_speed, angular_speed=angular_speed)

    def move_right(self, angular: float) -> bytes:
        """Move back. values 0.0 1.0."""
        angular_percent = get_percent(abs(angular * 100))
        (linear_speed, angular_speed) = transform_both_speeds(0.0, 0.0, 0.0, angular_percent)
        return self.send_movement(linear_speed=linear_speed, angular_speed=angular_speed)
