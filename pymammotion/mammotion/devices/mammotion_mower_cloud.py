"""Mower device with cloud MQTT connectivity."""

import logging

from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.mower_state_manager import MowerStateManager
from pymammotion.mammotion.devices.mammotion_cloud import MammotionBaseCloudDevice, MammotionCloud
from pymammotion.mammotion.devices.mower_device import MammotionMowerDevice

_LOGGER = logging.getLogger(__name__)


class MammotionMowerCloudDevice(MammotionBaseCloudDevice, MammotionMowerDevice):
    """Mower device with cloud connectivity and map synchronization."""

    def __init__(self, mqtt: MammotionCloud, cloud_device: Device, state_manager: MowerStateManager) -> None:
        """Initialize MammotionMowerCloudDevice.

        Uses multiple inheritance to combine:
        - MammotionBaseCloudDevice: MQTT communication
        - MammotionMowerDevice: Map sync callbacks
        """
        # Initialize base cloud device (which also initializes MammotionBaseDevice)
        super().__init__(mqtt, cloud_device, state_manager)
        # Initialize mower device callbacks (but skip base device init as it's already done)
        # We manually set the callbacks that MammotionMowerDevice would set
        self._state_manager.cloud_gethash_ack_callback = self.datahash_response
        self._state_manager.cloud_get_commondata_ack_callback = self.commdata_response
        self._state_manager.cloud_get_plan_callback = self.plan_callback

    def __del__(self) -> None:
        """Cleanup subscriptions and callbacks."""
        # Clean up mower-specific callbacks
        if hasattr(self, "_state_manager"):
            self._state_manager.cloud_gethash_ack_callback = None
            self._state_manager.cloud_get_commondata_ack_callback = None
            self._state_manager.cloud_get_plan_callback = None
        # Call parent cleanup
        super().__del__()
