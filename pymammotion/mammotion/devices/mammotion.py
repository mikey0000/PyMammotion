"""Device control of mammotion robots over bluetooth or MQTT."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from bleak import BLEDevice

from pymammotion import MammotionMQTT
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.enums import ConnectionPreference
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.camera_stream import StreamSubscriptionResponse, VideoResourceResponse
from pymammotion.http.model.http import DeviceRecord, Response
from pymammotion.mammotion.devices.mammotion_cloud import MammotionCloud
from pymammotion.mammotion.devices.mammotion_mower_ble import MammotionMowerBLEDevice
from pymammotion.mammotion.devices.managers.managers import AbstractDeviceManager
from pymammotion.mammotion.devices.mower_manager import MammotionMowerDeviceManager
from pymammotion.mammotion.devices.rtk_manager import MammotionRTKDeviceManager
from pymammotion.mqtt import AliyunMQTT
from pymammotion.utility.device_type import DeviceType

# RTK imports - imported here for type hints, full import in add_cloud_devices
if TYPE_CHECKING:
    from pymammotion.mammotion.devices.rtk_ble import MammotionRTKBLEDevice

TIMEOUT_CLOUD_RESPONSE = 10

_LOGGER = logging.getLogger(__name__)


class MammotionDeviceManager:
    """Manage devices - both mowers and RTK."""

    def __init__(self) -> None:
        self.devices: dict[str, MammotionMowerDeviceManager] = {}
        self.rtk_devices: dict[str, MammotionRTKDeviceManager] = {}

    def _should_disconnect_mqtt(self, device_for_removal: AbstractDeviceManager) -> bool:
        """Check if MQTT connection should be disconnected.

        Returns True if no other devices share the same MQTT connection.
        """
        if not device_for_removal.cloud:
            return False

        mqtt_to_check = device_for_removal.cloud.mqtt

        # Check if any mower device shares this MQTT connection
        shared_devices: set[AbstractDeviceManager] = {
            device
            for device in self.devices.values()
            if device.cloud is not None and device.cloud.mqtt == mqtt_to_check
        }

        # Also check RTK devices for shared MQTT
        shared_devices.update(
            {
                device
                for device in self.rtk_devices.values()
                if device.cloud is not None and device.cloud.mqtt == mqtt_to_check
            }
        )

        return len(shared_devices) == 0

    def add_device(self, mammotion_device: MammotionMowerDeviceManager) -> None:
        """Add a mower device."""
        exists: MammotionMowerDeviceManager | None = self.devices.get(mammotion_device.name)
        if exists is None:
            self.devices[mammotion_device.name] = mammotion_device
            return
        if mammotion_device.cloud is not None:
            exists.replace_cloud(mammotion_device.cloud)
        if mammotion_device.ble:
            exists.replace_ble(mammotion_device.ble)

    def add_rtk_device(self, rtk_device: MammotionRTKDeviceManager) -> None:
        """Add an RTK device."""

        exists: MammotionRTKDeviceManager | None = self.rtk_devices.get(rtk_device.name)
        if exists is None:
            self.rtk_devices[rtk_device.name] = rtk_device
            return
        if rtk_device.cloud:
            exists.replace_cloud(rtk_device.cloud)
        if rtk_device.ble:
            exists.replace_ble(rtk_device.ble)

    def has_device(self, mammotion_device_name: str) -> bool:
        """Check if a mower device exists."""
        if self.devices.get(mammotion_device_name, None) is not None:
            return True
        return False

    def has_rtk_device(self, rtk_device_name: str) -> bool:
        """Check if an RTK device exists."""
        if self.rtk_devices.get(rtk_device_name, None) is not None:
            return True
        return False

    def get_device(self, mammotion_device_name: str) -> MammotionMowerDeviceManager:
        """Get a mower device."""
        return self.devices[mammotion_device_name]

    def get_device_by_iot_id(self, iot_id: str) -> MammotionMowerDeviceManager | None:
        """Get a mower device by IoT ID."""
        for device in self.devices.values():
            if device.iot_id == iot_id:
                return device
        return None

    def get_rtk_device(self, rtk_device_name: str) -> MammotionRTKDeviceManager:
        """Get an RTK device."""
        return self.rtk_devices[rtk_device_name]

    async def remove_device(self, name: str) -> None:
        """Remove a mower device."""
        if self.devices.get(name):
            device_for_removal = self.devices.pop(name)
            loop = asyncio.get_running_loop()

            if device_for_removal.cloud:
                if self._should_disconnect_mqtt(device_for_removal):
                    await loop.run_in_executor(None, device_for_removal.cloud.mqtt.disconnect)
                await device_for_removal.cloud.stop()

            if device_for_removal.ble:
                await device_for_removal.ble.stop()

            del device_for_removal

    async def remove_rtk_device(self, name: str) -> None:
        """Remove an RTK device."""
        if self.rtk_devices.get(name):
            device_for_removal = self.rtk_devices.pop(name)
            loop = asyncio.get_running_loop()

            if device_for_removal.cloud:
                if self._should_disconnect_mqtt(device_for_removal):
                    await loop.run_in_executor(None, device_for_removal.cloud.mqtt.disconnect)
                await device_for_removal.cloud.stop()

            if device_for_removal.ble:
                await device_for_removal.ble.stop()

            del device_for_removal


class Mammotion:
    """Represents a Mammotion account and its devices."""

    device_manager = MammotionDeviceManager()

    _instance: Mammotion | None = None

    def __new__(cls) -> Mammotion:
        """Create a singleton."""
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize MammotionDevice."""
        self._login_lock = asyncio.Lock()
        self.mqtt_list: dict[str, MammotionCloud] = {}

    async def login_and_initiate_cloud(self, account: str, password: str, force: bool = False) -> None:
        async with self._login_lock:
            exists_aliyun: MammotionCloud | None = self.mqtt_list.get(f"{account}_aliyun")
            exists_mammotion: MammotionCloud | None = self.mqtt_list.get(f"{account}_mammotion")
            if (not exists_aliyun and not exists_mammotion) or force:
                cloud_client = await self.login(account, password)
                await self.initiate_cloud_connection(account, cloud_client)

    async def refresh_login(self, account: str) -> None:
        """Refresh login."""
        async with self._login_lock:
            exists_aliyun: MammotionCloud | None = self.mqtt_list.get(f"{account}_aliyun")
            exists_mammotion: MammotionCloud | None = self.mqtt_list.get(f"{account}_mammotion")

            if not exists_aliyun and not exists_mammotion:
                return
            mammotion_http = (
                exists_aliyun.cloud_client.mammotion_http
                if exists_aliyun
                else exists_mammotion.cloud_client.mammotion_http
            )

            await mammotion_http.refresh_login()

            if len(mammotion_http.device_records.records) != 0:
                await mammotion_http.get_mqtt_credentials()

            if exists_aliyun and exists_aliyun.is_connected():
                exists_aliyun.disconnect()
                await self.connect_iot(exists_aliyun.cloud_client)

            if exists_mammotion and exists_mammotion.is_connected():
                exists_mammotion.disconnect()

            if exists_aliyun and not exists_aliyun.is_connected():
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, exists_aliyun.connect_async)
            if exists_mammotion and not exists_mammotion.is_connected():
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, exists_mammotion.connect_async)

    @staticmethod
    def shim_cloud_devices(devices: list[DeviceRecord]) -> list[Device]:
        device_list: list[Device] = []
        for device in devices:
            device_list.append(
                Device(
                    gmt_modified=0,
                    product_name="",
                    status=0,
                    net_type="NET_WIFI",
                    is_edge_gateway=False,
                    category_name="",
                    owned=1,
                    identity_alias="UNKNOW",
                    thing_type="DEVICE",
                    identity_id=device.identity_id,
                    device_name=device.device_name,
                    product_key=device.product_key,
                    iot_id=device.iot_id,
                    bind_time=device.bind_time,
                    node_type="DEVICE",
                    category_key="LawnMower",
                )
            )

        return device_list

    async def initiate_ble_connection(self, devices: dict[str, BLEDevice], cloud_devices: list[Device]) -> None:
        """Initiate BLE connection."""
        for device in cloud_devices:
            if ble_device := devices.get(device.device_name):
                if device.device_name.startswith(("Luba-", "Yuka-")):
                    if not self.device_manager.has_device(device.device_name):
                        self.device_manager.add_device(
                            MammotionMowerDeviceManager(
                                name=device.device_name,
                                iot_id=device.iot_id,
                                cloud_device=device,
                                ble_device=ble_device,
                                preference=ConnectionPreference.BLUETOOTH,
                                cloud_client=CloudIOTGateway(MammotionHTTP()),
                            )
                        )
                    else:
                        self.device_manager.get_device(device.device_name).add_ble(ble_device)
                if device.device_name.startswith(("RTK", "RBS")):
                    if not self.device_manager.has_rtk_device(device.device_name):
                        self.device_manager.add_rtk_device(
                            MammotionRTKDeviceManager(
                                name=device.device_name,
                                iot_id=device.iot_id,
                                cloud_device=device,
                                ble_device=ble_device,
                                preference=ConnectionPreference.BLUETOOTH,
                                cloud_client=CloudIOTGateway(MammotionHTTP()),
                            )
                        )
                    else:
                        self.device_manager.get_rtk_device(device.device_name).add_ble(ble_device)

    async def initiate_cloud_connection(self, account: str, cloud_client: CloudIOTGateway) -> None:
        """Initiate cloud connection."""
        loop = asyncio.get_running_loop()

        mammotion_http = cloud_client.mammotion_http

        if mqtt := self.mqtt_list.get(f"{account}_aliyun"):
            if mqtt.is_connected():
                await loop.run_in_executor(None, mqtt.disconnect)

        if mqtt := self.mqtt_list.get(f"{account}_mammotion"):
            if mqtt.is_connected():
                await loop.run_in_executor(None, mqtt.disconnect)

        if len(cloud_client.devices_by_account_response.data.data) != 0:
            mammotion_cloud = MammotionCloud(
                AliyunMQTT(
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
            self.mqtt_list[f"{account}_aliyun"] = mammotion_cloud
            self.add_cloud_devices(mammotion_cloud)

            await loop.run_in_executor(None, self.mqtt_list[f"{account}_aliyun"].connect_async)
        if len(mammotion_http.device_records.records) != 0:
            mammotion_cloud = MammotionCloud(
                MammotionMQTT(
                    records=mammotion_http.device_records.records,
                    mammotion_http=mammotion_http,
                    mqtt_connection=mammotion_http.mqtt_credentials,
                ),
                cloud_client,
            )
            self.mqtt_list[f"{account}_mammotion"] = mammotion_cloud
            self.add_mammotion_devices(mammotion_cloud, mammotion_http.device_records.records)

            await loop.run_in_executor(None, self.mqtt_list[f"{account}_mammotion"].connect_async)

    def add_mammotion_devices(self, mqtt_client: MammotionCloud, devices: list[DeviceRecord]) -> None:
        """Add devices from mammotion cloud."""
        for device in devices:
            if device.device_name.startswith(("Luba-", "Yuka-")):
                has_device = self.device_manager.has_device(device.device_name)
                if has_device:
                    mower_device = self.device_manager.get_device(device.device_name)
                    if mower_device.cloud is None:
                        mower_device.add_cloud(mqtt=mqtt_client)
                    else:
                        mower_device.replace_mqtt(mqtt_client)

                else:
                    cloud_device_shim = Device(
                        gmt_modified=0,
                        product_name="",
                        status=0,
                        net_type="NET_WIFI",
                        is_edge_gateway=False,
                        category_name="",
                        owned=1,
                        identity_alias="UNKNOW",
                        thing_type="DEVICE",
                        identity_id=device.identity_id,
                        device_name=device.device_name,
                        product_key=device.product_key,
                        iot_id=device.iot_id,
                        bind_time=device.bind_time,
                        node_type="DEVICE",
                        category_key="LawnMower",
                    )

                    mixed_device = MammotionMowerDeviceManager(
                        name=device.device_name,
                        iot_id=device.iot_id,
                        cloud_client=mqtt_client.cloud_client,
                        cloud_device=cloud_device_shim,
                        mqtt=mqtt_client,
                        preference=ConnectionPreference.WIFI,
                    )
                    mixed_device.state.mower_state.product_key = device.product_key
                    self.device_manager.add_device(mixed_device)

    def add_cloud_devices(self, mqtt_client: MammotionCloud) -> None:
        """Add devices from cloud - both mowers and RTK."""
        from pymammotion.mammotion.devices.rtk_manager import MammotionRTKDeviceManager

        for device in mqtt_client.cloud_client.devices_by_account_response.data.data:
            # Handle mower devices (Luba, Yuka)
            if device.device_name.startswith(("Luba-", "Yuka-")):
                has_device = self.device_manager.has_device(device.device_name)
                if not has_device:
                    mixed_device = MammotionMowerDeviceManager(
                        name=device.device_name,
                        iot_id=device.iot_id,
                        cloud_client=mqtt_client.cloud_client,
                        cloud_device=device,
                        mqtt=mqtt_client,
                        preference=ConnectionPreference.WIFI,
                    )
                    mixed_device.state.mower_state.product_key = device.product_key
                    mixed_device.state.mower_state.model = (
                        device.product_name if device.product_model is None else device.product_model
                    )
                    self.device_manager.add_device(mixed_device)
                else:
                    mower_device = self.device_manager.get_device(device.device_name)
                    if mower_device.cloud is None:
                        mower_device.add_cloud(mqtt=mqtt_client)
                    else:
                        mower_device.replace_mqtt(mqtt_client)

            # Handle RTK devices
            elif device.device_name.startswith(("RTK", "RBS")):
                has_rtk_device = self.device_manager.has_rtk_device(device.device_name)
                if not has_rtk_device:
                    rtk_device = MammotionRTKDeviceManager(
                        name=device.device_name,
                        iot_id=device.iot_id,
                        cloud_client=mqtt_client.cloud_client,
                        cloud_device=device,
                        mqtt=mqtt_client,
                        preference=ConnectionPreference.WIFI,
                    )
                    self.device_manager.add_rtk_device(rtk_device)
                else:
                    rtk_device = self.device_manager.get_rtk_device(device.device_name)
                    if rtk_device.cloud is None:
                        rtk_device.add_cloud(mqtt=mqtt_client)
                    else:
                        rtk_device.replace_mqtt(mqtt_client)

    def set_disconnect_strategy(self, *, disconnect: bool) -> None:
        """Set disconnect strategy for all BLE devices (mowers and RTK)."""
        for device in self.device_manager.devices.values():
            if device.ble is not None:
                ble_device: MammotionMowerBLEDevice = device.ble
                ble_device.set_disconnect_strategy(disconnect=disconnect)

        for rtk_device in self.device_manager.rtk_devices.values():
            if rtk_device.ble is not None:
                ble_rtk_device: MammotionRTKBLEDevice = rtk_device.ble
                ble_rtk_device.set_disconnect_strategy(disconnect=disconnect)

    async def login(self, account: str, password: str) -> CloudIOTGateway:
        """Login to mammotion cloud."""
        mammotion_http = MammotionHTTP()
        await mammotion_http.login_v2(account, password)
        await mammotion_http.get_user_device_page()
        device_list = await mammotion_http.get_user_device_list()
        _LOGGER.debug("device_list: %s", device_list)
        await mammotion_http.get_mqtt_credentials()
        cloud_client = CloudIOTGateway(mammotion_http)
        await self.connect_iot(cloud_client)
        return cloud_client

    @staticmethod
    async def connect_iot(cloud_client: CloudIOTGateway) -> None:
        """Connect to aliyun cloud and fetch device info."""
        mammotion_http = cloud_client.mammotion_http
        country_code = mammotion_http.login_info.userInformation.domainAbbreviation
        if cloud_client.region_response is None:
            await cloud_client.get_region(country_code)
        await cloud_client.connect()
        await cloud_client.login_by_oauth(country_code)
        await cloud_client.aep_handle()
        await cloud_client.session_by_auth_code()
        await cloud_client.list_binding_by_account()

    async def remove_device(self, name: str) -> None:
        """Remove a mower device."""
        await self.device_manager.remove_device(name)

    async def remove_rtk_device(self, name: str) -> None:
        """Remove an RTK device."""
        await self.device_manager.remove_rtk_device(name)

    def get_device_by_name(self, name: str) -> MammotionMowerDeviceManager:
        """Get a mower device by name."""
        return self.device_manager.get_device(name)

    def get_rtk_device_by_name(self, name: str) -> MammotionRTKDeviceManager:
        """Get an RTK device by name."""
        return self.device_manager.get_rtk_device(name)

    def get_or_create_device_by_name(
        self, device: Device, mqtt_client: MammotionCloud | None, ble_device: BLEDevice | None
    ) -> MammotionMowerDeviceManager:
        """Get or create a mower device by name."""
        if self.device_manager.has_device(device.device_name):
            return self.device_manager.get_device(device.device_name)
        mow_device = MammotionMowerDeviceManager(
            name=device.device_name,
            iot_id=device.iot_id,
            cloud_client=mqtt_client.cloud_client if mqtt_client else CloudIOTGateway(MammotionHTTP()),
            mqtt=mqtt_client,
            cloud_device=device,
            ble_device=ble_device,
            preference=ConnectionPreference.WIFI if mqtt_client else ConnectionPreference.BLUETOOTH,
        )
        self.device_manager.add_device(mow_device)
        return mow_device

    async def send_command(self, name: str, key: str):
        """Send a command to the device."""
        device = self.get_device_by_name(name)
        if device:
            if device.preference is ConnectionPreference.BLUETOOTH and device.ble:
                return await device.ble.command(key)
            if device.preference is ConnectionPreference.WIFI and device.cloud:
                return await device.cloud.command(key)
            # TODO work with both with EITHER
        return None

    async def send_command_with_args(self, name: str, key: str, **kwargs: Any):
        """Send a command with args to the device."""
        device = self.get_device_by_name(name)
        if device:
            if device.preference is ConnectionPreference.BLUETOOTH and device.ble:
                return await device.ble.command(key, **kwargs)
            if device.preference is ConnectionPreference.WIFI and device.cloud:
                return await device.cloud.command(key, **kwargs)
            # TODO work with both with EITHER
        return None

    async def start_map_sync(self, name: str) -> None:
        """Start map sync."""
        device = self.get_device_by_name(name)
        if device:
            if device.preference is ConnectionPreference.BLUETOOTH and device.ble:
                return await device.ble.start_map_sync()
            if device.preference is ConnectionPreference.WIFI and device.cloud:
                return await device.cloud.start_map_sync()
            # TODO work with both with EITHER
        return None

    async def start_schedule_sync(self, name: str) -> None:
        """Start map sync."""
        device = self.get_device_by_name(name)
        if device:
            if device.preference is ConnectionPreference.BLUETOOTH and device.ble:
                return await device.ble.start_schedule_sync()
            if device.preference is ConnectionPreference.WIFI and device.cloud:
                return await device.cloud.start_schedule_sync()
            # TODO work with both with EITHER
        return None

    async def get_stream_subscription(self, name: str, iot_id: str) -> Response[StreamSubscriptionResponse] | Any:
        """Get stream subscription."""
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
        """Get video resource."""
        device = self.get_device_by_name(name)

        if DeviceType.is_mini_or_x_series(name):
            _video_resource_response = await device.mammotion_http.get_video_resource(iot_id)
            _LOGGER.debug(_video_resource_response)
            return _video_resource_response
        return None

    def mower(self, name: str) -> MowingDevice | None:
        """Get a mower device by name."""
        device = self.get_device_by_name(name)
        if device:
            return device.state
        return None
