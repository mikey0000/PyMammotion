"""Device control of mammotion robots over bluetooth or MQTT."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak.backends.device import BLEDevice

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.enums import ConnectionPreference
from pymammotion.data.state_manager import StateManager
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.camera_stream import StreamSubscriptionResponse, VideoResourceResponse
from pymammotion.http.model.http import Response
from pymammotion.mammotion.devices.mammotion_bluetooth import MammotionBaseBLEDevice
from pymammotion.mammotion.devices.mammotion_cloud import MammotionBaseCloudDevice, MammotionCloud
from pymammotion.mqtt import MammotionMQTT
from pymammotion.utility.device_type import DeviceType

TIMEOUT_CLOUD_RESPONSE = 10

_LOGGER = logging.getLogger(__name__)


class MammotionMixedDeviceManager:
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
        self._ble_device: MammotionBaseBLEDevice | None = None
        self._cloud_device: MammotionBaseCloudDevice | None = None
        self.name = name
        self.iot_id = iot_id
        self.cloud_client = cloud_client
        self._state_manager = StateManager(MowingDevice())
        self._state_manager.get_device().name = name
        self._device: Device = cloud_device
        self.add_ble(ble_device)
        self.add_cloud(mqtt)
        self.mammotion_http = cloud_client.mammotion_http
        self.preference = preference
        self._state_manager.preference = preference

    @property
    def state_manager(self) -> StateManager:
        """Return the state manager."""
        return self._state_manager

    @property
    def state(self):
        """Return the state of the device."""
        return self._state_manager.get_device()

    @state.setter
    def state(self, value: MowingDevice) -> None:
        self._state_manager.set_device(value)

    def ble(self) -> MammotionBaseBLEDevice | None:
        return self._ble_device

    def cloud(self) -> MammotionBaseCloudDevice | None:
        return self._cloud_device

    def has_queued_commands(self) -> bool:
        if self.has_cloud() and self.preference == ConnectionPreference.WIFI:
            return not self.cloud().mqtt.command_queue.empty()
        else:
            return not self.ble().command_queue.empty()

    def add_ble(self, ble_device: BLEDevice) -> None:
        if ble_device is not None:
            self._ble_device = MammotionBaseBLEDevice(
                state_manager=self._state_manager, cloud_device=self._device, device=ble_device
            )

    def add_cloud(self, mqtt: MammotionCloud) -> None:
        self._cloud_device = MammotionBaseCloudDevice(
            mqtt, cloud_device=self._device, state_manager=self._state_manager
        )

    def replace_cloud(self, cloud_device: MammotionBaseCloudDevice) -> None:
        self._cloud_device = cloud_device

    def remove_cloud(self) -> None:
        self._state_manager.cloud_get_commondata_ack_callback = None
        self._state_manager.cloud_get_hashlist_ack_callback = None
        self._state_manager.cloud_get_plan_callback = None
        self._state_manager.cloud_on_notification_callback = None
        self._state_manager.cloud_gethash_ack_callback = None
        self._cloud_device = None

    def replace_ble(self, ble_device: MammotionBaseBLEDevice) -> None:
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
        self._cloud_device = MammotionBaseCloudDevice(mqtt, cloud_device=device, state_manager=self._state_manager)

    def has_cloud(self) -> bool:
        return self._cloud_device is not None

    def has_ble(self) -> bool:
        return self._ble_device is not None


class MammotionDeviceManager:
    devices: dict[str, MammotionMixedDeviceManager] = {}

    def add_device(self, mammotion_device: MammotionMixedDeviceManager) -> None:
        exists: MammotionMixedDeviceManager | None = self.devices.get(mammotion_device.name)
        if exists is None:
            self.devices[mammotion_device.name] = mammotion_device
            return
        if mammotion_device.has_cloud():
            exists.replace_cloud(mammotion_device.cloud())
        if mammotion_device.has_ble():
            exists.replace_ble(mammotion_device.ble())

    def get_device(self, mammotion_device_name: str) -> MammotionMixedDeviceManager:
        return self.devices.get(mammotion_device_name)

    async def remove_device(self, name: str) -> None:
        if self.devices.get(name):
            device_for_removal = self.devices.pop(name)
            loop = asyncio.get_running_loop()
            if device_for_removal.has_cloud():
                should_disconnect = {
                    device
                    for key, device in self.devices.items()
                    if device.cloud() is not None and device.cloud().mqtt == device_for_removal.cloud().mqtt
                }
                if len(should_disconnect) == 0:
                    await loop.run_in_executor(None, device_for_removal.cloud().mqtt.disconnect)
                await device_for_removal.cloud().stop()
            if device_for_removal.has_ble():
                await device_for_removal.ble().stop()

            del device_for_removal


class Mammotion:
    """Represents a Mammotion account and its devices."""

    device_manager = MammotionDeviceManager()
    mqtt_list: dict[str, MammotionCloud] = dict()

    _instance: Mammotion | None = None

    def __new__(cls, *args: Any, **kwargs: Any):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize MammotionDevice."""
        self._login_lock = asyncio.Lock()

    async def login_and_initiate_cloud(self, account, password, force: bool = False) -> None:
        async with self._login_lock:
            exists: MammotionCloud | None = self.mqtt_list.get(account)
            if not exists or force:
                cloud_client = await self.login(account, password)
                await self.initiate_cloud_connection(account, cloud_client)

    async def refresh_login(self, account: str, password: str | None = None) -> None:
        async with self._login_lock:
            exists: MammotionCloud | None = self.mqtt_list.get(account)
            if not exists:
                return
            mammotion_http = exists.cloud_client.mammotion_http
            await mammotion_http.refresh_login(account, password)
            await self.connect_iot(exists.cloud_client)

            if not exists.is_connected():
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, exists.connect_async)

    async def initiate_cloud_connection(self, account: str, cloud_client: CloudIOTGateway) -> None:
        loop = asyncio.get_running_loop()
        if mqtt := self.mqtt_list.get(account):
            if mqtt.is_connected():
                await loop.run_in_executor(None, mqtt.disconnect)

        mammotion_cloud = MammotionCloud(
            MammotionMQTT(
                region_id=cloud_client.region_response.data.regionId,
                product_key=cloud_client.aep_response.data.productKey,
                device_name=cloud_client.aep_response.data.deviceName,
                device_secret=cloud_client.aep_response.data.deviceSecret,
                iot_token=cloud_client.session_by_authcode_response.data.iotToken,
                client_id=cloud_client.client_id,
                cloud_client=cloud_client,
            ),
            cloud_client,
        )
        self.mqtt_list[account] = mammotion_cloud
        self.add_cloud_devices(mammotion_cloud)

        await loop.run_in_executor(None, self.mqtt_list[account].connect_async)

    def add_cloud_devices(self, mqtt_client: MammotionCloud) -> None:
        for device in mqtt_client.cloud_client.devices_by_account_response.data.data:
            mower_device = self.device_manager.get_device(device.deviceName)
            if device.deviceName.startswith(("Luba-", "Yuka-")) and mower_device is None:
                mixed_device = MammotionMixedDeviceManager(
                    name=device.deviceName,
                    iot_id=device.iotId,
                    cloud_client=mqtt_client.cloud_client,
                    cloud_device=device,
                    mqtt=mqtt_client,
                    preference=ConnectionPreference.WIFI,
                )
                mixed_device.state.mower_state.product_key = device.productKey
                mixed_device.state.mower_state.model = (
                    device.productName if device.productModel is None else device.productModel
                )
                self.device_manager.add_device(mixed_device)
            elif device.deviceName.startswith(("Luba-", "Yuka-")) and mower_device:
                if mower_device.cloud() is None:
                    mower_device.add_cloud(mqtt=mqtt_client)
                else:
                    mower_device.replace_mqtt(mqtt_client)

    def set_disconnect_strategy(self, disconnect: bool) -> None:
        for device_name, device in self.device_manager.devices.items():
            if device.ble() is not None:
                ble_device: MammotionBaseBLEDevice = device.ble()
                ble_device.set_disconnect_strategy(disconnect)

    async def login(self, account: str, password: str) -> CloudIOTGateway:
        """Login to mammotion cloud."""
        mammotion_http = MammotionHTTP()
        cloud_client = CloudIOTGateway(mammotion_http)
        await mammotion_http.login(account, password)
        await self.connect_iot(cloud_client)
        return cloud_client

    @staticmethod
    async def connect_iot(cloud_client: CloudIOTGateway) -> None:
        mammotion_http = cloud_client.mammotion_http
        country_code = mammotion_http.login_info.userInformation.domainAbbreviation
        await cloud_client.get_region(country_code)
        await cloud_client.connect()
        await cloud_client.login_by_oauth(country_code)
        await cloud_client.aep_handle()
        await cloud_client.session_by_auth_code()
        await cloud_client.list_binding_by_account()

    async def remove_device(self, name: str) -> None:
        await self.device_manager.remove_device(name)

    def get_device_by_name(self, name: str) -> MammotionMixedDeviceManager:
        return self.device_manager.get_device(name)

    def get_or_create_device_by_name(self, device: Device, mqtt_client: MammotionCloud) -> MammotionMixedDeviceManager:
        if mow_device := self.device_manager.get_device(device.deviceName):
            return mow_device
        mow_device = MammotionMixedDeviceManager(
            name=device.deviceName,
            iot_id=device.iotId,
            cloud_client=mqtt_client.cloud_client,
            mqtt=mqtt_client,
            cloud_device=device,
            ble_device=None,
        )
        self.device_manager.add_device(mow_device)
        return mow_device

    async def send_command(self, name: str, key: str):
        """Send a command to the device."""
        device = self.get_device_by_name(name)
        if device:
            if device.preference is ConnectionPreference.BLUETOOTH and device.has_ble():
                return await device.ble().command(key)
            if device.preference is ConnectionPreference.WIFI:
                return await device.cloud().command(key)
            # TODO work with both with EITHER
        return None

    async def send_command_with_args(self, name: str, key: str, **kwargs: Any):
        """Send a command with args to the device."""
        device = self.get_device_by_name(name)
        if device:
            if device.preference is ConnectionPreference.BLUETOOTH and device.has_ble():
                return await device.ble().command(key, **kwargs)
            if device.preference is ConnectionPreference.WIFI:
                return await device.cloud().command(key, **kwargs)
            # TODO work with both with EITHER
        return None

    async def start_sync(self, name: str, retry: int):
        device = self.get_device_by_name(name)
        if device:
            if device.preference is ConnectionPreference.BLUETOOTH and device.has_ble():
                return await device.ble().start_sync(retry)
            if device.preference is ConnectionPreference.WIFI:
                return await device.cloud().start_sync(retry)
            # TODO work with both with EITHER
        return None

    async def start_map_sync(self, name: str):
        device = self.get_device_by_name(name)
        if device:
            if device.preference is ConnectionPreference.BLUETOOTH and device.has_ble():
                return await device.ble().start_map_sync()
            if device.preference is ConnectionPreference.WIFI:
                return await device.cloud().start_map_sync()
            # TODO work with both with EITHER
        return None

    async def get_stream_subscription(self, name: str, iot_id: str) -> Response[StreamSubscriptionResponse] | Any:
        device = self.get_device_by_name(name)
        if DeviceType.is_mini_or_x_series(name):
            _stream_response = await device.mammotion_http.get_stream_subscription_mini_or_x_series(
                iot_id, DeviceType.is_yuka(name) and not DeviceType.is_yuka_mini(name)
            )
            _LOGGER.debug(_stream_response)
            return _stream_response
        else:
            _stream_response = await device.mammotion_http.get_stream_subscription(iot_id)
            _LOGGER.debug(_stream_response)
            return _stream_response

    async def get_video_resource(self, name: str, iot_id: str) -> Response[VideoResourceResponse] | None:
        device = self.get_device_by_name(name)

        if DeviceType.is_mini_or_x_series(name):
            _video_resource_response = await device.mammotion_http.get_video_resource(iot_id)
            _LOGGER.debug(_video_resource_response)
            return _video_resource_response
        return None

    def mower(self, name: str) -> MowingDevice | None:
        device = self.get_device_by_name(name)
        if device:
            return device.state
        return None
