"""RTK Device Manager - manages RTK devices with cloud and BLE connectivity."""

from typing import override

from bleak import BLEDevice

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.model.device import RTKDevice
from pymammotion.data.model.enums import ConnectionPreference
from pymammotion.mammotion.devices.mammotion_cloud import MammotionCloud
from pymammotion.mammotion.devices.managers.managers import AbstractDeviceManager
from pymammotion.mammotion.devices.rtk_ble import MammotionRTKBLEDevice
from pymammotion.mammotion.devices.rtk_cloud import MammotionRTKCloudDevice


class MammotionRTKDeviceManager(AbstractDeviceManager):
    """Manages an RTK device with both cloud and BLE connectivity options."""

    def __init__(
        self,
        name: str,
        iot_id: str,
        cloud_client: CloudIOTGateway,
        cloud_device: Device,
        ble_device: BLEDevice | None = None,
        mqtt: MammotionCloud | None = None,
        preference: ConnectionPreference = ConnectionPreference.WIFI,
    ) -> None:
        """Initialize RTK device manager."""
        super().__init__(name, iot_id, cloud_client, cloud_device, preference)
        # Store as generic interfaces to satisfy AbstractDeviceManager contract
        self._ble_device: MammotionRTKBLEDevice | None = None
        self._cloud_device: MammotionRTKCloudDevice | None = None
        self.name = name
        self.iot_id = iot_id
        self.cloud_client = cloud_client
        self._device: Device = cloud_device
        self.mammotion_http = cloud_client.mammotion_http
        self.preference = preference

        # Initialize RTK state
        self._rtk_state = RTKDevice(
            name=name,
            iot_id=iot_id,
            product_key=cloud_device.product_key,
        )

        # Add connection types if provided
        if ble_device:
            self.add_ble(ble_device)
        if mqtt:
            self.add_cloud(mqtt)

    @property
    def state(self) -> RTKDevice:
        """Return the RTK device state."""
        return self._rtk_state

    @state.setter
    def state(self, value: RTKDevice) -> None:
        """Set the RTK device state."""
        self._rtk_state = value

    @property
    def ble(self) -> MammotionRTKBLEDevice | None:
        """Return BLE device interface."""
        return self._ble_device

    @property
    def cloud(self) -> MammotionRTKCloudDevice | None:
        """Return cloud device interface."""
        return self._cloud_device

    def has_queued_commands(self) -> bool:
        """Check if there are queued commands."""
        if self.cloud and self.preference == ConnectionPreference.WIFI:
            return not self.cloud.mqtt.command_queue.empty()
        elif self.ble:
            return not self.ble.command_queue.empty()
        return False

    def add_ble(self, ble_device: BLEDevice) -> MammotionRTKBLEDevice:
        """Add BLE device."""
        self._ble_device = MammotionRTKBLEDevice(
            cloud_device=self._device, rtk_state=self._rtk_state, device=ble_device
        )
        return self._ble_device

    @override
    def add_cloud(self, mqtt: MammotionCloud) -> MammotionRTKCloudDevice:
        """Add cloud device."""
        self._cloud_device = MammotionRTKCloudDevice(mqtt, cloud_device=self._device, rtk_state=self._rtk_state)
        return self._cloud_device

    def replace_cloud(self, cloud_device: MammotionRTKCloudDevice) -> None:
        """Replace cloud device."""
        self._cloud_device = cloud_device

    def remove_cloud(self) -> None:
        """Remove cloud device."""
        self._cloud_device = None

    def replace_ble(self, ble_device: MammotionRTKBLEDevice) -> None:
        """Replace BLE device."""
        self._ble_device = ble_device

    def remove_ble(self) -> None:
        """Remove BLE device."""
        self._ble_device = None

    def replace_mqtt(self, mqtt: MammotionCloud) -> None:
        """Replace MQTT connection."""
        if cloud_device := self._cloud_device:
            self._cloud_device = MammotionRTKCloudDevice(
                mqtt, cloud_device=cloud_device.device, rtk_state=self._rtk_state
            )

    def has_cloud(self) -> bool:
        """Check if cloud connection is available."""
        return self._cloud_device is not None

    def has_ble(self) -> bool:
        """Check if BLE connection is available."""
        return self._ble_device is not None
