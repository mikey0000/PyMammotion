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
    """Manager that owns and coordinates the BLE and cloud transport instances for a single mower."""

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
        """Return the BLE device instance, or None if not configured."""
        return self._ble_device

    @property
    def cloud(self) -> MammotionMowerCloudDevice | None:
        """Return the cloud device instance, or None if not configured."""
        return self._cloud_device

    def has_queued_commands(self) -> bool:
        """Return True if the active transport has pending commands in its queue."""
        if self.cloud and self.preference == ConnectionPreference.WIFI:
            return not self.cloud.mqtt.command_queue.empty()
        if self.ble:
            return not self.ble.command_queue.empty()
        return False

    def add_ble(self, ble_device: BLEDevice) -> MammotionMowerBLEDevice:
        """Create and attach a BLE device for the given BLEDevice."""
        self._ble_device = MammotionMowerBLEDevice(
            state_manager=self._state_manager, cloud_device=self._device, device=ble_device
        )
        return self._ble_device

    def add_cloud(self, mqtt: MammotionCloud) -> MammotionMowerCloudDevice:
        """Create and attach a cloud device backed by the given MQTT connection."""
        self._cloud_device = MammotionMowerCloudDevice(
            mqtt, cloud_device=self._device, state_manager=self._state_manager
        )
        return self._cloud_device

    def replace_cloud(self, cloud_device: MammotionMowerCloudDevice) -> None:
        """Replace the existing cloud device, cleaning up the old one's subscriptions first."""
        if self._cloud_device is not None:
            self._cloud_device.cleanup_subscriptions()
        self._cloud_device = cloud_device

    def remove_cloud(self) -> None:
        """Clear cloud-specific state manager callbacks and detach the cloud device."""
        self._state_manager.cloud_get_commondata_ack_callback = None
        self._state_manager.cloud_get_hashlist_ack_callback = None
        self._state_manager.cloud_get_plan_callback = None
        self._state_manager.cloud_gethash_ack_callback = None
        # Do NOT null out cloud_on_notification_callback — it is a persistent
        # event bus that external callers (e.g. HA) subscribe to.  Replacing it
        # with None would silently drop those subscriptions and they would never
        # be re-registered after a reconnect.
        self._cloud_device = None

    def replace_ble(self, ble_device: MammotionMowerBLEDevice) -> None:
        """Replace the BLE device with the provided instance."""
        self._ble_device = ble_device

    def remove_ble(self) -> None:
        """Clear BLE-specific state manager callbacks and detach the BLE device."""
        self._state_manager.ble_get_commondata_ack_callback = None
        self._state_manager.ble_get_hashlist_ack_callback = None
        self._state_manager.ble_get_plan_callback = None
        self._state_manager.ble_gethash_ack_callback = None
        # Do NOT null out ble_on_notification_callback — same reason as cloud.
        self._ble_device = None

    def replace_mqtt(self, mqtt: MammotionCloud) -> None:
        """Rebuild the cloud device using a new MQTT connection, cleaning up the old one."""
        device = self._cloud_device.device
        self._cloud_device.cleanup_subscriptions()
        self._cloud_device = MammotionMowerCloudDevice(mqtt, cloud_device=device, state_manager=self._state_manager)

    def has_cloud(self) -> bool:
        """Return True if a cloud device is currently attached."""
        return self._cloud_device is not None

    def has_ble(self) -> bool:
        """Return True if a BLE device is currently attached."""
        return self._ble_device is not None
