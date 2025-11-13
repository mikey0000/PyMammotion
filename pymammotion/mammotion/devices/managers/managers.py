from abc import ABC, abstractmethod

from bleak import BLEDevice

from pymammotion import CloudIOTGateway
from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.model.device import MowingDevice, RTKDevice
from pymammotion.data.model.enums import ConnectionPreference
from pymammotion.mammotion.devices.mammotion_bluetooth import MammotionBaseBLEDevice
from pymammotion.mammotion.devices.mammotion_cloud import MammotionBaseCloudDevice, MammotionCloud


class AbstractDeviceManager(ABC):
    """Abstract base class for device managers."""

    def __init__(
        self,
        name: str,
        iot_id: str,
        cloud_client: CloudIOTGateway,
        cloud_device: Device,
        preference: ConnectionPreference = ConnectionPreference.BLUETOOTH,
    ) -> None:
        self.name = name
        self.iot_id = iot_id
        self.cloud_client = cloud_client
        self._device: Device = cloud_device
        self.mammotion_http = cloud_client.mammotion_http
        self.preference = preference

    @property
    @abstractmethod
    def state(self) -> MowingDevice | RTKDevice:
        """Return the state of the device."""

    @state.setter
    @abstractmethod
    def state(self, value: MowingDevice | RTKDevice) -> None:
        """Set the device state."""

    @property
    @abstractmethod
    def ble(self) -> MammotionBaseBLEDevice | None:
        """Return BLE device interface."""

    @property
    @abstractmethod
    def cloud(self) -> MammotionBaseCloudDevice | None:
        """Return cloud device interface."""

    @abstractmethod
    def has_queued_commands(self) -> bool:
        """Check if there are queued commands."""

    @abstractmethod
    def add_ble(self, ble_device: BLEDevice) -> MammotionBaseBLEDevice:
        """Add BLE device."""

    @abstractmethod
    def add_cloud(self, mqtt: MammotionCloud) -> MammotionBaseCloudDevice:
        """Add cloud device."""

    @abstractmethod
    def replace_cloud(self, cloud_device: MammotionBaseCloudDevice) -> None:
        """Replace cloud device."""

    @abstractmethod
    def remove_cloud(self) -> None:
        """Remove cloud device."""

    @abstractmethod
    def replace_ble(self, ble_device: MammotionBaseBLEDevice) -> None:
        """Replace BLE device."""

    @abstractmethod
    def remove_ble(self) -> None:
        """Remove BLE device."""

    @abstractmethod
    def replace_mqtt(self, mqtt: MammotionCloud) -> None:
        """Replace MQTT connection."""
