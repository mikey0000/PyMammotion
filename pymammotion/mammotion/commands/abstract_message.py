from abc import abstractmethod

from pymammotion.bluetooth.model.atomic_integer import AtomicInteger
from pymammotion.proto import MsgCmdType, MsgDevice
from pymammotion.utility.device_type import DeviceType


class AbstractMessage:
    """Abstract base class providing sequence-counter and device-routing helpers for command builders."""

    seqs = AtomicInteger(0)
    user_account: int

    @abstractmethod
    def get_device_name(self) -> str:
        """Get device name."""

    @abstractmethod
    def get_device_product_key(self) -> str:
        """Get device name."""

    @abstractmethod
    def read_write_device(self, rw_id: int, context: int, rw: int) -> bytes:
        """Build a parameter read/write request using the carrier selected for this mower type."""

    def get_msg_device(self, msg_type: MsgCmdType, msg_device: MsgDevice) -> MsgDevice:
        """Return the receiver device, remapped for anything that is not a Luba 1."""
        if DeviceType.is_luba_pro(self.get_device_name(), self.get_device_product_key()) and msg_type == MsgCmdType.NAV:
            return MsgDevice.DEV_NAVIGATION
        return msg_device
