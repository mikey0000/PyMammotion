from __future__ import annotations

from bleak import BLEDevice

from pymammotion import CloudIOTGateway
from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.enums import ConnectionPreference
from pymammotion.data.mower_state_manager import MowerStateManager
from pymammotion.mammotion.devices.mammotion_cloud import MammotionCloud
from pymammotion.mammotion.devices.mammotion_mower_ble import MammotionMowerBLEDevice
from pymammotion.mammotion.devices.mammotion_mower_cloud import MammotionMowerCloudDevice
from pymammotion.mammotion.devices.managers.managers import AbstractDeviceManager


class MammotionMowerDeviceManager(AbstractDeviceManager):
    def __init__(
        self,
        name: str,
        iot_id: str,
        cloud_client: CloudIOTGateway,
        cloud_device: Device,
        ble_device: BLEDevice | None = None,
        mqtt: MammotionCloud | None = None,
        preference: ConnectionPreference = ConnectionPreference.BLUETOOTH,
    ) -> None:
        super().__init__(name, iot_id, cloud_client, cloud_device, preference)
        self._ble_device: MammotionMowerBLEDevice | None = None
        self._cloud_device: MammotionMowerCloudDevice | None = None

        self._state_manager = MowerStateManager(MowingDevice())
        self._state_manager.get_device().name = name
        self.add_ble(ble_device) if ble_device else None
        self.add_cloud(mqtt) if mqtt else None

    @property
    def state_manager(self) -> MowerStateManager:
        """Return the state manager."""
        return self._state_manager

    @property
    def state(self) -> MowingDevice:
        """Return the state of the device."""
        return self._state_manager.get_device()

    @state.setter
    def state(self, value: MowingDevice) -> None:
        self._state_manager.set_device(value)

    @property
    def ble(self) -> MammotionMowerBLEDevice | None:
        return self._ble_device

    @property
    def cloud(self) -> MammotionMowerCloudDevice | None:
        return self._cloud_device

    def has_queued_commands(self) -> bool:
        if self.cloud and self.preference == ConnectionPreference.WIFI:
            return not self.cloud.mqtt.command_queue.empty()
        elif self.ble:
            return not self.ble.command_queue.empty()
        return False

    def add_ble(self, ble_device: BLEDevice) -> MammotionMowerBLEDevice:
        self._ble_device = MammotionMowerBLEDevice(
            state_manager=self._state_manager, cloud_device=self._device, device=ble_device
        )
        return self._ble_device

    def add_cloud(self, mqtt: MammotionCloud) -> MammotionMowerCloudDevice:
        self._cloud_device = MammotionMowerCloudDevice(
            mqtt, cloud_device=self._device, state_manager=self._state_manager
        )
        return self._cloud_device

    def replace_cloud(self, cloud_device: MammotionMowerCloudDevice) -> None:
        self._cloud_device = cloud_device

    def remove_cloud(self) -> None:
        self._state_manager.cloud_get_commondata_ack_callback = None
        self._state_manager.cloud_get_hashlist_ack_callback = None
        self._state_manager.cloud_get_plan_callback = None
        self._state_manager.cloud_on_notification_callback = None
        self._state_manager.cloud_gethash_ack_callback = None
        self._cloud_device = None

    def replace_ble(self, ble_device: MammotionMowerBLEDevice) -> None:
        self._ble_device = ble_device

    def remove_ble(self) -> None:
        self._state_manager.ble_get_commondata_ack_callback = None
        self._state_manager.ble_get_hashlist_ack_callback = None
        self._state_manager.ble_get_plan_callback = None
        self._state_manager.ble_on_notification_callback = None
        self._state_manager.ble_gethash_ack_callback = None
        self._ble_device = None

    def replace_mqtt(self, mqtt: MammotionCloud) -> None:
        device = self._cloud_device.device
        self._cloud_device = MammotionMowerCloudDevice(mqtt, cloud_device=device, state_manager=self._state_manager)

    def has_cloud(self) -> bool:
        return self._cloud_device is not None

    def has_ble(self) -> bool:
        return self._ble_device is not None
