"""Device control of mammotion robots over bluetooth or MQTT."""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from functools import cache
from typing import Any

from aiohttp import ClientSession
from bleak.backends.device import BLEDevice

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.dataclass.dev_by_account_response import Device
from pymammotion.const import MAMMOTION_DOMAIN
from pymammotion.data.model.account import Credentials
from pymammotion.data.model.device import MowingDevice
from pymammotion.http.http import connect_http
from pymammotion.mammotion.devices.mammotion_bluetooth import MammotionBaseBLEDevice
from pymammotion.mammotion.devices.mammotion_cloud import MammotionBaseCloudDevice, MammotionCloud
from pymammotion.mqtt import MammotionMQTT

TIMEOUT_CLOUD_RESPONSE = 10

_LOGGER = logging.getLogger(__name__)


class ConnectionPreference(Enum):
    """Enum for connection preference."""

    EITHER = 0
    WIFI = 1
    BLUETOOTH = 2


class MammotionMixedDeviceManager:
    _ble_device: MammotionBaseBLEDevice | None = None
    _cloud_device: MammotionBaseCloudDevice | None = None
    _mowing_state: MowingDevice = MowingDevice()

    def __init__(
        self,
        name: str,
        cloud_device: Device | None = None,
        ble_device: BLEDevice | None = None,
        mqtt: MammotionCloud | None = None,
    ) -> None:
        self.name = name
        self.add_ble(ble_device)
        self.add_cloud(cloud_device, mqtt)

    def mower_state(self):
        return self._mowing_state

    def ble(self) -> MammotionBaseBLEDevice | None:
        return self._ble_device

    def cloud(self) -> MammotionBaseCloudDevice | None:
        return self._cloud_device

    def add_ble(self, ble_device: BLEDevice) -> None:
        if ble_device is not None:
            self._ble_device = MammotionBaseBLEDevice(self._mowing_state, ble_device)

    def add_cloud(self, cloud_device: Device | None = None, mqtt: MammotionCloud | None = None) -> None:
        if cloud_device is not None:
            self._cloud_device = MammotionBaseCloudDevice(
                mqtt, cloud_device=cloud_device, mowing_state=self._mowing_state
            )

    def replace_cloud(self, cloud_device: MammotionBaseCloudDevice) -> None:
        self._cloud_device = cloud_device

    def replace_ble(self, ble_device: MammotionBaseBLEDevice) -> None:
        self._ble_device = ble_device

    def has_cloud(self) -> bool:
        return self._cloud_device is not None

    def has_ble(self) -> bool:
        return self._ble_device is not None


class MammotionDevices:
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


async def create_devices(
    ble_device: BLEDevice,
    cloud_credentials: Credentials | None = None,
    preference: ConnectionPreference = ConnectionPreference.BLUETOOTH,
):
    mammotion = Mammotion(ble_device, preference)

    if cloud_credentials and preference == ConnectionPreference.EITHER or preference == ConnectionPreference.WIFI:
        cloud_client = await Mammotion.login(
            cloud_credentials.account_id or cloud_credentials.email, cloud_credentials.password
        )
        await mammotion.initiate_cloud_connection(cloud_client)

    return mammotion


@cache
class Mammotion:
    """Represents a Mammotion account and its devices."""

    devices = MammotionDevices()
    cloud_client: CloudIOTGateway | None = None
    mqtt: MammotionCloud | None = None

    def __init__(
        self, ble_device: BLEDevice, preference: ConnectionPreference = ConnectionPreference.BLUETOOTH
    ) -> None:
        """Initialize MammotionDevice."""
        if ble_device:
            self.devices.add_device(MammotionMixedDeviceManager(name=ble_device.name, ble_device=ble_device))

        if preference:
            self._preference = preference

    async def initiate_cloud_connection(self, cloud_client: CloudIOTGateway) -> None:
        if self.mqtt is not None:
            if self.mqtt.is_connected:
                return

        self.cloud_client = cloud_client
        self.mqtt = MammotionCloud(
            MammotionMQTT(
                region_id=cloud_client.region_response.data.regionId,
                product_key=cloud_client.aep_response.data.productKey,
                device_name=cloud_client.aep_response.data.deviceName,
                device_secret=cloud_client.aep_response.data.deviceSecret,
                iot_token=cloud_client.session_by_authcode_response.data.iotToken,
                client_id=cloud_client.client_id,
                cloud_client=cloud_client,
            )
        )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.mqtt.connect_async)

        for device in cloud_client.devices_by_account_response.data.data:
            if device.deviceName.startswith(("Luba-", "Yuka-")) and self.devices.get_device(device.deviceName) is None:
                self.devices.add_device(
                    MammotionMixedDeviceManager(name=device.deviceName, cloud_device=device, mqtt=self.mqtt)
                )

    def set_disconnect_strategy(self, disconnect: bool) -> None:
        for device_name, device in self.devices.devices:
            if device.ble() is not None:
                ble_device: MammotionBaseBLEDevice = device.ble()
                ble_device.set_disconnect_strategy(disconnect)

    @staticmethod
    async def login(account: str, password: str) -> CloudIOTGateway:
        """Login to mammotion cloud."""
        cloud_client = CloudIOTGateway()
        async with ClientSession(MAMMOTION_DOMAIN) as session:
            mammotion_http = await connect_http(account, password)
            country_code = mammotion_http.login_info.userInformation.domainAbbreviation
            _LOGGER.debug("CountryCode: " + country_code)
            _LOGGER.debug("AuthCode: " + mammotion_http.login_info.authorization_code)
            loop = asyncio.get_running_loop()
            cloud_client.set_http(mammotion_http)
            await loop.run_in_executor(
                None, cloud_client.get_region, country_code, mammotion_http.login_info.authorization_code
            )
            await cloud_client.connect()
            await cloud_client.login_by_oauth(country_code, mammotion_http.login_info.authorization_code)
            await loop.run_in_executor(None, cloud_client.aep_handle)
            await loop.run_in_executor(None, cloud_client.session_by_auth_code)

            await loop.run_in_executor(None, cloud_client.list_binding_by_account)
            return cloud_client

    def get_device_by_name(self, name: str) -> MammotionMixedDeviceManager:
        return self.devices.get_device(name)

    async def send_command(self, name: str, key: str):
        """Send a command to the device."""
        device = self.get_device_by_name(name)
        if device:
            if self._preference is ConnectionPreference.BLUETOOTH:
                return await device.ble().command(key)
            if self._preference is ConnectionPreference.WIFI:
                return await device.cloud().command(key)
            # TODO work with both with EITHER

    async def send_command_with_args(self, name: str, key: str, **kwargs: Any):
        """Send a command with args to the device."""
        device = self.get_device_by_name(name)
        if device:
            if self._preference is ConnectionPreference.BLUETOOTH:
                return await device.ble().command(key, **kwargs)
            if self._preference is ConnectionPreference.WIFI:
                return await device.cloud().command(key, **kwargs)
            # TODO work with both with EITHER

    async def start_sync(self, name: str, retry: int):
        device = self.get_device_by_name(name)
        if device:
            if self._preference is ConnectionPreference.BLUETOOTH:
                return await device.ble().start_sync(retry)
            if self._preference is ConnectionPreference.WIFI:
                return await device.cloud().start_sync(retry)
            # TODO work with both with EITHER

    async def start_map_sync(self, name: str):
        device = self.get_device_by_name(name)
        if device:
            if self._preference is ConnectionPreference.BLUETOOTH:
                return await device.ble().start_map_sync()
            if self._preference is ConnectionPreference.WIFI:
                return await device.cloud().start_map_sync()
            # TODO work with both with EITHER

    def mower(self, name: str):
        device = self.get_device_by_name(name)
        if device:
            return device.mower_state()
