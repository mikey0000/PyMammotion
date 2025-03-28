from abc import abstractmethod

from pymammotion.bluetooth.model.atomic_integer import AtomicInteger
from pymammotion.proto import MsgCmdType, MsgDevice
from pymammotion.utility.device_type import DeviceType


class AbstractMessage:
    seqs = AtomicInteger(0)
    user_account: int = 1

    @abstractmethod
    def get_device_name(self) -> str:
        """Get device name."""

    def get_device_product_key(self) -> str:
        """Get device name."""

    def get_msg_device(self, msg_type: MsgCmdType, msg_device: MsgDevice) -> MsgDevice:
        """Changes the rcver name if it's not a luba1."""
        if (
            not DeviceType.is_luba1(self.get_device_name(), self.get_device_product_key())
            and msg_type == MsgCmdType.NAV
        ):
            return MsgDevice.DEV_NAVIGATION
        return msg_device
