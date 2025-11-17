"""Mower device with Bluetooth LE connectivity."""

import logging
from typing import Any

from bleak import BLEDevice

from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.mower_state_manager import MowerStateManager
from pymammotion.mammotion.devices.mammotion_bluetooth import MammotionBaseBLEDevice
from pymammotion.mammotion.devices.mower_device import MammotionMowerDevice

_LOGGER = logging.getLogger(__name__)


class MammotionMowerBLEDevice(MammotionBaseBLEDevice, MammotionMowerDevice):
    """Mower device with BLE connectivity and map synchronization."""

    def __init__(
        self,
        state_manager: MowerStateManager,
        cloud_device: Device,
        device: BLEDevice,
        interface: int = 0,
        **kwargs: Any,
    ) -> None:
        """Initialize MammotionMowerBLEDevice.

        Uses multiple inheritance to combine:
        - MammotionBaseBLEDevice: BLE communication
        - MammotionMowerDevice: Map sync callbacks
        """
        # Initialize base BLE device (which also initializes MammotionBaseDevice)
        MammotionBaseBLEDevice.__init__(self, state_manager, cloud_device, device, interface, **kwargs)
        # Set up mower-specific BLE callbacks
        self._state_manager.ble_gethash_ack_callback = self.datahash_response
        self._state_manager.ble_get_commondata_ack_callback = self.commdata_response
        self._state_manager.ble_get_plan_callback = self.plan_callback

    def __del__(self) -> None:
        """Cleanup subscriptions and callbacks."""
        # Clean up mower-specific callbacks
        if hasattr(self, "_state_manager"):
            self._state_manager.ble_gethash_ack_callback = None
            self._state_manager.ble_get_commondata_ack_callback = None
            self._state_manager.ble_get_plan_callback = None
        # Call parent cleanup
        super().__del__()
