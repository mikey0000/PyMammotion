"""Device control of mammotion robots over bluetooth or MQTT."""

from __future__ import annotations

import queue
import threading
import asyncio
import base64
import codecs
import json
import logging
from abc import abstractmethod
from collections import deque
from enum import Enum
from functools import cache
from typing import Any, Callable, Optional, cast, Awaitable
from uuid import UUID

import betterproto
from aiohttp import ClientSession
from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.backends.service import BleakGATTCharacteristic, BleakGATTServiceCollection
from bleak.exc import BleakDBusError
from bleak_retry_connector import (
    BLEAK_RETRY_EXCEPTIONS,
    BleakClientWithServiceCache,
    BleakNotFoundError,
    establish_connection,
)

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.dataclass.dev_by_account_response import Device
from pymammotion.bluetooth import BleMessage
from pymammotion.const import MAMMOTION_DOMAIN
from pymammotion.data.model import RegionData
from pymammotion.data.model.account import Credentials
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.mqtt.event import ThingEventMessage
from pymammotion.data.state_manager import StateManager
from pymammotion.http.http import connect_http
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.mqtt import MammotionMQTT
from pymammotion.mqtt.mammotion_future import MammotionFuture
from pymammotion.proto.luba_msg import LubaMsg
from pymammotion.proto.mctrl_nav import NavGetCommDataAck, NavGetHashListAck
from pymammotion.utility.rocker_util import RockerControlUtil


class CharacteristicMissingError(Exception):
    """Raised when a characteristic is missing."""


def _sb_uuid(comms_type: str = "service") -> UUID | str:
    """Return Mammotion UUID.

    Args:
        comms_type (str): The type of communication (tx, rx, or service).

    Returns:
        UUID | str: The UUID for the specified communication type or an error message.

    """
    _uuid = {"tx": "ff01", "rx": "ff02", "service": "2A05"}

    if comms_type in _uuid:
        return UUID(f"0000{_uuid[comms_type]}-0000-1000-8000-00805f9b34fb")

    return "Incorrect type, choose between: tx, rx or service"


READ_CHAR_UUID = _sb_uuid(comms_type="rx")
WRITE_CHAR_UUID = _sb_uuid(comms_type="tx")

DBUS_ERROR_BACKOFF_TIME = 0.25

DISCONNECT_DELAY = 10

TIMEOUT_CLOUD_RESPONSE = 10

_LOGGER = logging.getLogger(__name__)


def slashescape(err):
    """Escape a slash character."""
    # print err, dir(err), err.start, err.end, err.object[:err.start]
    thebyte = err.object[err.start : err.end]
    repl = "\\x" + hex(ord(thebyte))[2:]
    return (repl, err.end)


codecs.register_error("slashescape", slashescape)


def find_next_integer(lst: list[int], current_hash: float) -> int | None:
    try:
        # Find the index of the current integer
        current_index = lst.index(current_hash)

        # Check if there is a next integer in the list
        if current_index + 1 < len(lst):
            return lst[current_index + 1]
        else:
            return None  # Or raise an exception or handle it in some other way
    except ValueError:
        # Handle the case where current_int is not in the list
        return None  # Or raise an exception or handle it in some other way


def _handle_timeout(fut: asyncio.Future[None]) -> None:
    """Handle a timeout."""
    if not fut.done():
        fut.set_exception(asyncio.TimeoutError)


async def _handle_retry(fut: asyncio.Future[None], func, command: bytes) -> None:
    """Handle a retry."""
    if not fut.done():
        await func(command)


async def _handle_retry_cloud(self, fut: asyncio.Future[None], func, iot_id: str, command: bytes) -> None:
    """Handle a retry."""

    if not fut.done():
        self._operation_lock.release()
        await self.loop.run_in_executor(None, func, iot_id, command)


class ConnectionPreference(Enum):
    """Enum for connection preference."""

    EITHER = 0
    WIFI = 1
    BLUETOOTH = 2

class MammotionMixedDeviceManager:
    _ble_device: MammotionBaseBLEDevice | None = None
    _cloud_device: MammotionBaseCloudDevice | None = None
    _mowing_state: MowingDevice = MowingDevice()

    def __init__(self, name: str, cloud_device: Device | None = None,
                 ble_device: BLEDevice | None = None, mqtt: MammotionMQTT | None = None) -> None:
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

    def add_cloud(self, cloud_device: Device | None = None, mqtt: MammotionMQTT | None = None) -> None:
        if cloud_device is not None:
            self._cloud_device = MammotionBaseCloudDevice(
                mqtt_client=mqtt,
                cloud_device=cloud_device,
                mowing_state=self._mowing_state)

    def replace_cloud(self, cloud_device:MammotionBaseCloudDevice) -> None:
        self._cloud_device = cloud_device

    def replace_ble(self, ble_device:MammotionBaseBLEDevice) -> None:
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

async def create_devices(ble_device: BLEDevice,
    cloud_credentials: Credentials | None = None,
    preference: ConnectionPreference = ConnectionPreference.BLUETOOTH):
    cloud_client = await Mammotion.login(cloud_credentials.account_id or cloud_credentials.email, cloud_credentials.password)
    mammotion = Mammotion(ble_device, preference)

    if cloud_credentials:
        await mammotion.initiate_cloud_connection(cloud_client)

    return mammotion


@cache
class Mammotion(object):
    """Represents a Mammotion device."""

    devices = MammotionDevices()
    cloud_client: CloudIOTGateway | None = None
    mqtt: MammotionMQTT | None = None



    def __init__(
        self,
            ble_device: BLEDevice,
            preference: ConnectionPreference = ConnectionPreference.BLUETOOTH
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
        self.mqtt = MammotionMQTT(region_id=cloud_client._region.data.regionId,
                                        product_key=cloud_client._aep_response.data.productKey,
                                        device_name=cloud_client._aep_response.data.deviceName,
                                        device_secret=cloud_client._aep_response.data.deviceSecret,
                                        iot_token=cloud_client._session_by_authcode_response.data.iotToken,
                                        client_id=cloud_client._client_id)

        self.mqtt._cloud_client = cloud_client
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.mqtt.connect_async)

        for device in cloud_client.listing_dev_by_account_response.data.data:
            if device.deviceName.startswith(("Luba-", "Yuka-")):
                self.devices.add_device(MammotionMixedDeviceManager(name=device.deviceName, cloud_device=device, mqtt=self.mqtt))

    def set_disconnect_strategy(self, disconnect: bool):
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
            await loop.run_in_executor(None, cloud_client.get_region, country_code, mammotion_http.login_info.authorization_code)
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

    async def send_command_with_args(self,name: str, key: str, **kwargs: any):
        """Send a command with args to the device."""
        device = self.get_device_by_name(name)
        if device:
            if self._preference is ConnectionPreference.BLUETOOTH:
                return await device.ble().command(key, **kwargs)
            if self._preference is ConnectionPreference.WIFI:
                return await device.cloud().command(key, **kwargs)
            # TODO work with both with EITHER

    async def start_sync(self,name:str, retry: int):
        device = self.get_device_by_name(name)
        if device:
            if self._preference is ConnectionPreference.BLUETOOTH:
                return await device.ble().start_sync(retry)
            if self._preference is ConnectionPreference.WIFI:
                return await device.cloud().start_sync(retry)
            # TODO work with both with EITHER

    async def start_map_sync(self, name:str):
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

def has_field(message: betterproto.Message) -> bool:
    """Check if the message has any fields serialized on wire."""
    return betterproto.serialized_on_wire(message)


class MammotionBaseDevice:
    """Base class for Mammotion devices."""

    _mower: MowingDevice
    _state_manager: StateManager

    def __init__(self, device: MowingDevice) -> None:
        """Initialize MammotionBaseDevice."""
        self.loop = asyncio.get_event_loop()
        self._raw_data = LubaMsg().to_dict(casing=betterproto.Casing.SNAKE)
        self._mower = device
        self._state_manager = StateManager(self._mower)
        self._state_manager.gethash_ack_callback = self.datahash_response
        self._state_manager.get_commondata_ack_callback = self.commdata_response
        self._notify_future: asyncio.Future[bytes] | None = None

    async def datahash_response(self, hash_ack: NavGetHashListAck):
        """Handle datahash responses."""
        result_hash = 0
        while hash_ack.data_couple[0] != result_hash:
            data = await self._send_command_with_args("synchronize_hash_data", hash_num=hash_ack.data_couple[0])
            msg = LubaMsg().parse(data)
            if betterproto.serialized_on_wire(msg.nav.toapp_get_commondata_ack):
                result_hash = msg.nav.toapp_get_commondata_ack.hash

    async def commdata_response(self, common_data: NavGetCommDataAck):
        """Handle common data responses."""
        total_frame = common_data.total_frame
        current_frame = common_data.current_frame

        if total_frame == current_frame:
            # get next in hash ack list

            data_hash = find_next_integer(self._mower.nav.toapp_gethash_ack.data_couple, common_data.hash)
            if data_hash is None:
                return
            result_hash = 0
            while data_hash != result_hash:
                data = await self._send_command_with_args("synchronize_hash_data", hash_num=data_hash)
                msg = LubaMsg().parse(data)
                if betterproto.serialized_on_wire(msg.nav.toapp_get_commondata_ack):
                    result_hash = msg.nav.toapp_get_commondata_ack.hash
        else:
            # check if we have the data already first
            region_data = RegionData()
            region_data.hash = common_data.hash
            region_data.action = common_data.action
            region_data.type = common_data.type
            region_data.total_frame = total_frame
            region_data.current_frame = current_frame
            await self._send_command_with_args("get_regional_data", regional_data=region_data)

    def _update_raw_data(self, data: bytes) -> None:
        """Update raw and model data from notifications."""
        tmp_msg = LubaMsg().parse(data)
        res = betterproto.which_one_of(tmp_msg, "LubaSubMsg")
        match res[0]:
            case "nav":
                self._update_nav_data(tmp_msg)
            case "sys":
                self._update_sys_data(tmp_msg)
            case "driver":
                self._update_driver_data(tmp_msg)
            case "net":
                self._update_net_data(tmp_msg)
            case "mul":
                self._update_mul_data(tmp_msg)
            case "ota":
                self._update_ota_data(tmp_msg)

        self._mower.update_raw(self._raw_data)

    def _update_nav_data(self, tmp_msg):
        """Update navigation data."""
        nav_sub_msg = betterproto.which_one_of(tmp_msg.nav, "SubNavMsg")
        if nav_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", nav_sub_msg[0])
            return
        nav = self._raw_data.get("nav", {})
        if isinstance(nav_sub_msg[1], int):
            nav[nav_sub_msg[0]] = nav_sub_msg[1]
        else:
            nav[nav_sub_msg[0]] = nav_sub_msg[1].to_dict(casing=betterproto.Casing.SNAKE)
        self._raw_data["nav"] = nav

    def _update_sys_data(self, tmp_msg):
        """Update system data."""
        sys_sub_msg = betterproto.which_one_of(tmp_msg.sys, "SubSysMsg")
        if sys_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", sys_sub_msg[0])
            return
        sys = self._raw_data.get("sys", {})
        sys[sys_sub_msg[0]] = sys_sub_msg[1].to_dict(casing=betterproto.Casing.SNAKE)
        self._raw_data["sys"] = sys

    def _update_driver_data(self, tmp_msg):
        """Update driver data."""
        drv_sub_msg = betterproto.which_one_of(tmp_msg.driver, "SubDrvMsg")
        if drv_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", drv_sub_msg[0])
            return
        drv = self._raw_data.get("driver", {})
        drv[drv_sub_msg[0]] = drv_sub_msg[1].to_dict(casing=betterproto.Casing.SNAKE)
        self._raw_data["driver"] = drv

    def _update_net_data(self, tmp_msg):
        """Update network data."""
        net_sub_msg = betterproto.which_one_of(tmp_msg.net, "NetSubType")
        if net_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", net_sub_msg[0])
            return
        net = self._raw_data.get("net", {})
        if isinstance(net_sub_msg[1], int):
            net[net_sub_msg[0]] = net_sub_msg[1]
        else:
            net[net_sub_msg[0]] = net_sub_msg[1].to_dict(casing=betterproto.Casing.SNAKE)
        self._raw_data["net"] = net

    def _update_mul_data(self, tmp_msg):
        """Update mul data."""
        mul_sub_msg = betterproto.which_one_of(tmp_msg.mul, "SubMul")
        if mul_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", mul_sub_msg[0])
            return
        mul = self._raw_data.get("mul", {})
        mul[mul_sub_msg[0]] = mul_sub_msg[1].to_dict(casing=betterproto.Casing.SNAKE)
        self._raw_data["mul"] = mul

    def _update_ota_data(self, tmp_msg):
        """Update OTA data."""
        ota_sub_msg = betterproto.which_one_of(tmp_msg.ota, "SubOtaMsg")
        if ota_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", ota_sub_msg[0])
            return
        ota = self._raw_data.get("ota", {})
        ota[ota_sub_msg[0]] = ota_sub_msg[1].to_dict(casing=betterproto.Casing.SNAKE)
        self._raw_data["ota"] = ota

    @property
    def raw_data(self) -> dict[str, Any]:
        """Get the raw data of the device."""
        return self._raw_data

    @property
    def mower(self) -> MowingDevice:
        """Get the LubaMsg of the device."""
        return self._mower

    @abstractmethod
    async def _send_command(self, key: str, retry: int | None = None) -> bytes | None:
        """Send command to device and read response."""

    @abstractmethod
    async def _send_command_with_args(self, key: str, **kwargs: any) -> bytes | None:
        """Send command to device and read response."""

    @abstractmethod
    async def _ble_sync(self):
        """Send ble sync command every 3 seconds or sooner."""

    async def start_sync(self, retry: int):
        """Start synchronization with the device."""
        await self._send_command("get_device_base_info", retry)
        await self._send_command("get_report_cfg", retry)
        """RTK and dock location."""
        await self._send_command_with_args("allpowerfull_rw", id=5, rw=1, context=1)
        """Error codes."""
        await self._send_command_with_args("allpowerfull_rw", id=5, rw=1, context=2)
        await self._send_command_with_args("allpowerfull_rw", id=5, rw=1, context=3)

    async def start_map_sync(self):
        """Start sync of map data."""
        await self._send_command_with_args("read_plan", sub_cmd=2, plan_index=0)

        await self._send_command_with_args("get_all_boundary_hash_list", sub_cmd=0)

        await self._send_command_with_args("get_hash_response", total_frame=1, current_frame=1)

        await self._send_command_with_args(
            "get_area_name_list", device_id=self._mower.device.net.toapp_wifi_iot_status.devicename
        )

        # sub_cmd 3 is job hashes??
        # sub_cmd 4 is dump location (yuka)
        # jobs list
        # hash_list_result = await self._send_command_with_args("get_all_boundary_hash_list", sub_cmd=3)

    async def move_forward(self):
        linear_speed = 1.0
        angular_speed = 0.0
        transfrom3 = RockerControlUtil.getInstance().transfrom3(90, 1000)
        transform4 = RockerControlUtil.getInstance().transfrom3(0, 0)

        if transfrom3 is not None and len(transfrom3) > 0:
            linear_speed = transfrom3[0] * 10
            angular_speed = int(transform4[1] * 4.5)
        await self._send_command_with_args("send_movement", linear_speed=linear_speed, angular_speed=angular_speed)

    async def move_stop(self):
        linear_speed = 0.0
        angular_speed = 0.0
        transfrom3 = RockerControlUtil.getInstance().transfrom3(0, 0)
        transform4 = RockerControlUtil.getInstance().transfrom3(0, 0)

        if transfrom3 is not None and len(transfrom3) > 0:
            linear_speed = transfrom3[0] * 10
            angular_speed = int(transform4[1] * 4.5)
        await self._send_command_with_args("send_movement", linear_speed=linear_speed, angular_speed=angular_speed)

    async def command(self, key: str, **kwargs):
        """Send a command to the device."""
        return await self._send_command_with_args(key, **kwargs)


class MammotionBaseBLEDevice(MammotionBaseDevice):
    """Base class for Mammotion BLE devices."""

    def __init__(self, mowing_state: MowingDevice, device: BLEDevice, interface: int = 0, **kwargs: Any) -> None:
        """Initialize MammotionBaseBLEDevice."""
        super().__init__(mowing_state)
        self._disconnect_strategy = True
        self._ble_sync_task = None
        self._prev_notification = None
        self._interface = f"hci{interface}"
        self._device = device
        self._mower = mowing_state
        self._client: BleakClientWithServiceCache | None = None
        self._read_char: BleakGATTCharacteristic | None = None
        self._write_char: BleakGATTCharacteristic | None = None
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._message: BleMessage | None = None
        self._commands: MammotionCommand = MammotionCommand(device.name)
        self._expected_disconnect = False
        self._connect_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()
        self._key: str | None = None

    def update_device(self, device: BLEDevice) -> None:
        """Update the BLE device."""
        self._device = device

    async def _ble_sync(self):
        command_bytes = self._commands.send_todev_ble_sync(2)
        await self._message.post_custom_data_bytes(command_bytes)

    async def run_periodic_sync_task(self) -> None:
        """Send ble sync to robot."""
        try:
            await self._ble_sync()
        finally:
            self.schedule_ble_sync()

    def schedule_ble_sync(self):
        """Periodically sync to keep connection alive."""
        if self._client is not None and self._client.is_connected:
            self._ble_sync_task = self.loop.call_later(
                130, lambda: asyncio.ensure_future(self.run_periodic_sync_task())
            )

    async def _send_command_with_args(self, key: str, **kwargs) -> bytes | None:
        """Send command to device and read response."""
        if self._operation_lock.locked():
            _LOGGER.debug(
                "%s: Operation already in progress, waiting for it to complete; RSSI: %s",
                self.name,
                self.rssi,
            )
        async with self._operation_lock:
            try:
                command_bytes = getattr(self._commands, key)(**kwargs)
                return await self._send_command_locked(key, command_bytes)
            except BleakNotFoundError:
                _LOGGER.exception(
                    "%s: device not found, no longer in range, or poor RSSI: %s",
                    self.name,
                    self.rssi,
                )
                raise
            except CharacteristicMissingError as ex:
                _LOGGER.debug(
                    "%s: characteristic missing: %s; RSSI: %s",
                    self.name,
                    ex,
                    self.rssi,
                    exc_info=True,
                )
            except BLEAK_RETRY_EXCEPTIONS:
                _LOGGER.debug("%s: communication failed with:", self.name, exc_info=True)

    async def _send_command(self, key: str, retry: int | None = None) -> bytes | None:
        """Send command to device and read response."""
        if self._operation_lock.locked():
            _LOGGER.debug(
                "%s: Operation already in progress, waiting for it to complete; RSSI: %s",
                self.name,
                self.rssi,
            )
        async with self._operation_lock:
            try:
                command_bytes = getattr(self._commands, key)()
                return await self._send_command_locked(key, command_bytes)
            except BleakNotFoundError:
                _LOGGER.exception(
                    "%s: device not found, no longer in range, or poor RSSI: %s",
                    self.name,
                    self.rssi,
                )
                raise
            except CharacteristicMissingError as ex:
                _LOGGER.debug(
                    "%s: characteristic missing: %s; RSSI: %s",
                    self.name,
                    ex,
                    self.rssi,
                    exc_info=True,
                )
            except BLEAK_RETRY_EXCEPTIONS:
                _LOGGER.debug("%s: communication failed with:", self.name, exc_info=True)

    @property
    def name(self) -> str:
        """Return device name."""
        return f"{self._device.name} ({self._device.address})"

    @property
    def rssi(self) -> int:
        """Return RSSI of device."""
        try:
            return self._mower.device.sys.toapp_report_data.connect.ble_rssi
        finally:
            return 0

    async def _ensure_connected(self):
        """Ensure connection to device is established."""
        if self._connect_lock.locked():
            _LOGGER.debug(
                "%s: Connection already in progress, waiting for it to complete; RSSI: %s",
                self.name,
                self.rssi,
            )
        if self._client and self._client.is_connected:
            _LOGGER.debug(
                "%s: Already connected before obtaining lock, resetting timer; RSSI: %s",
                self.name,
                self.rssi,
            )
            self._reset_disconnect_timer()
            return
        async with self._connect_lock:
            # Check again while holding the lock
            if self._client and self._client.is_connected:
                _LOGGER.debug(
                    "%s: Already connected after obtaining lock, resetting timer; RSSI: %s",
                    self.name,
                    self.rssi,
                )
                self._reset_disconnect_timer()
                return
            _LOGGER.debug("%s: Connecting; RSSI: %s", self.name, self.rssi)
            client: BleakClientWithServiceCache = await establish_connection(
                BleakClientWithServiceCache,
                self._device,
                self.name,
                self._disconnected,
                max_attempts=10,
                ble_device_callback=lambda: self._device,
            )
            _LOGGER.debug("%s: Connected; RSSI: %s", self.name, self.rssi)
            self._client = client
            self._message = BleMessage(client)

            try:
                self._resolve_characteristics(client.services)
            except CharacteristicMissingError as ex:
                _LOGGER.debug(
                    "%s: characteristic missing, clearing cache: %s; RSSI: %s",
                    self.name,
                    ex,
                    self.rssi,
                    exc_info=True,
                )
                await client.clear_cache()
                self._cancel_disconnect_timer()
                await self._execute_disconnect_with_lock()
                raise

            _LOGGER.debug(
                "%s: Starting notify and disconnect timer; RSSI: %s",
                self.name,
                self.rssi,
            )
            self._reset_disconnect_timer()
            await self._start_notify()
            command_bytes = self._commands.send_todev_ble_sync(2)
            await self._message.post_custom_data_bytes(command_bytes)
            self.schedule_ble_sync()

    async def _send_command_locked(self, key: str, command: bytes) -> bytes:
        """Send command to device and read response."""
        await self._ensure_connected()
        try:
            return await self._execute_command_locked(key, command)
        except BleakDBusError as ex:
            # Disconnect so we can reset state and try again
            await asyncio.sleep(DBUS_ERROR_BACKOFF_TIME)
            _LOGGER.debug(
                "%s: RSSI: %s; Backing off %ss; Disconnecting due to error: %s",
                self.name,
                self.rssi,
                DBUS_ERROR_BACKOFF_TIME,
                ex,
            )
            await self._execute_forced_disconnect()
            raise
        except BLEAK_RETRY_EXCEPTIONS as ex:
            # Disconnect so we can reset state and try again
            _LOGGER.debug("%s: RSSI: %s; Disconnecting due to error: %s", self.name, self.rssi, ex)
            await self._execute_forced_disconnect()
            raise

    async def _notification_handler(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle notification responses."""
        result = self._message.parseNotification(data)
        if result == 0:
            data = await self._message.parseBlufiNotifyData(True)
            self._update_raw_data(data)
            self._message.clearNotification()
            _LOGGER.debug("%s: Received notification: %s", self.name, data)
        else:
            return
        new_msg = LubaMsg().parse(data)
        if betterproto.serialized_on_wire(new_msg.net):
            if new_msg.net.todev_ble_sync != 0 or has_field(new_msg.net.toapp_wifi_iot_status):
                if has_field(new_msg.net.toapp_wifi_iot_status) and self._commands.get_device_product_key() == "":
                    self._commands.set_device_product_key(new_msg.net.toapp_wifi_iot_status.productkey)

                return

        # may or may not be correct, some work could be done here to correctly match responses
        if self._notify_future and not self._notify_future.done():
            self._notify_future.set_result(data)

        self._reset_disconnect_timer()
        await self._state_manager.notification(new_msg)

    async def _start_notify(self) -> None:
        """Start notification."""
        _LOGGER.debug("%s: Subscribe to notifications; RSSI: %s", self.name, self.rssi)
        await self._client.start_notify(self._read_char, self._notification_handler)

    async def _execute_command_locked(self, key: str, command: bytes) -> bytes:
        """Execute command and read response."""
        assert self._client is not None
        assert self._read_char is not None
        assert self._write_char is not None
        self._notify_future = self.loop.create_future()
        self._key = key
        _LOGGER.debug("%s: Sending command: %s", self.name, key)
        await self._message.post_custom_data_bytes(command)

        retry_handle = self.loop.call_at(
            self.loop.time() + 2,
            lambda: asyncio.ensure_future(
                _handle_retry(self._notify_future, self._message.post_custom_data_bytes, command)
            ),
        )
        timeout = 5
        timeout_handle = self.loop.call_at(self.loop.time() + timeout, _handle_timeout, self._notify_future)
        timeout_expired = False
        try:
            notify_msg = await self._notify_future
        except asyncio.TimeoutError:
            timeout_expired = True
            raise
        finally:
            if not timeout_expired:
                timeout_handle.cancel()
                retry_handle.cancel()
            self._notify_future = None

        _LOGGER.debug("%s: Notification received: %s", self.name, notify_msg.hex())
        return notify_msg

    def get_address(self) -> str:
        """Return address of device."""
        return self._device.address

    def _resolve_characteristics(self, services: BleakGATTServiceCollection) -> None:
        """Resolve characteristics."""
        self._read_char = services.get_characteristic(READ_CHAR_UUID)
        if not self._read_char:
            self._read_char = READ_CHAR_UUID
            _LOGGER.error(CharacteristicMissingError(READ_CHAR_UUID))
        self._write_char = services.get_characteristic(WRITE_CHAR_UUID)
        if not self._write_char:
            self._write_char = WRITE_CHAR_UUID
            _LOGGER.error(CharacteristicMissingError(WRITE_CHAR_UUID))

    def _reset_disconnect_timer(self):
        """Reset disconnect timer."""
        self._cancel_disconnect_timer()
        self._expected_disconnect = False
        self._disconnect_timer = self.loop.call_later(DISCONNECT_DELAY, self._disconnect_from_timer)

    def _disconnected(self, client: BleakClientWithServiceCache) -> None:
        """Disconnected callback."""
        if self._expected_disconnect:
            _LOGGER.debug("%s: Disconnected from device; RSSI: %s", self.name, self.rssi)
            return
        _LOGGER.warning(
            "%s: Device unexpectedly disconnected; RSSI: %s",
            self.name,
            self.rssi,
        )
        self._cancel_disconnect_timer()

    def _disconnect_from_timer(self):
        """Disconnect from device."""
        if self._operation_lock.locked() and self._client.is_connected:
            _LOGGER.debug(
                "%s: Operation in progress, resetting disconnect timer; RSSI: %s",
                self.name,
                self.rssi,
            )
            self._reset_disconnect_timer()
            return
        self._cancel_disconnect_timer()
        self._timed_disconnect_task = asyncio.create_task(self._execute_timed_disconnect())

    def _cancel_disconnect_timer(self):
        """Cancel disconnect timer."""
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
            self._disconnect_timer = None

    async def _execute_forced_disconnect(self) -> None:
        """Execute forced disconnection."""
        self._cancel_disconnect_timer()
        _LOGGER.debug(
            "%s: Executing forced disconnect",
            self.name,
        )
        await self._execute_disconnect()

    async def _execute_timed_disconnect(self) -> None:
        """Execute timed disconnection."""
        if not self._disconnect_strategy:
            return
        _LOGGER.debug(
            "%s: Executing timed disconnect after timeout of %s",
            self.name,
            DISCONNECT_DELAY,
        )
        await self._execute_disconnect()

    async def _execute_disconnect(self) -> None:
        """Execute disconnection."""
        _LOGGER.debug("%s: Executing disconnect", self.name)
        async with self._connect_lock:
            await self._execute_disconnect_with_lock()

    async def _execute_disconnect_with_lock(self) -> None:
        """Execute disconnection while holding the lock."""
        assert self._connect_lock.locked(), "Lock not held"
        _LOGGER.debug("%s: Executing disconnect with lock", self.name)
        if self._disconnect_timer:  # If the timer was reset, don't disconnect
            _LOGGER.debug("%s: Skipping disconnect as timer reset", self.name)
            return
        client = self._client
        self._expected_disconnect = True

        if not client:
            _LOGGER.debug("%s: Already disconnected", self.name)
            return
        _LOGGER.debug("%s: Disconnecting", self.name)
        try:
            """We reset what command the robot last heard before disconnecting."""
            if client is not None and client.is_connected:
                command_bytes = self._commands.send_todev_ble_sync(2)
                await self._message.post_custom_data_bytes(command_bytes)
                await client.stop_notify(self._read_char)
                await client.disconnect()
        except BLEAK_RETRY_EXCEPTIONS as ex:
            _LOGGER.warning(
                "%s: Error disconnecting: %s; RSSI: %s",
                self.name,
                ex,
                self.rssi,
            )
        else:
            _LOGGER.debug("%s: Disconnect completed successfully", self.name)
        self._client = None

    async def _disconnect(self) -> bool:
        if self._client is not None:
            return await self._client.disconnect()

    def set_disconnect_strategy(self, disconnect):
        self._disconnect_strategy = disconnect


class MammotionBaseCloudDevice(MammotionBaseDevice):
    """Base class for Mammotion Cloud devices."""

    def __init__(
        self,
        mqtt_client: MammotionMQTT,
        cloud_device: Device,
        mowing_state: MowingDevice
    ) -> None:
        """Initialize MammotionBaseCloudDevice."""
        super().__init__(mowing_state)
        self._ble_sync_task = None
        self.is_ready = False
        self._mqtt_client = mqtt_client
        self.iot_id = cloud_device.iotId
        self.device = cloud_device
        self._mower = mowing_state
        self._command_futures = {}
        self._commands: MammotionCommand = MammotionCommand(cloud_device.deviceName)
        self.currentID = ""
        self.on_ready_callback: Optional[Callable[[], Awaitable[None]]] = None
        self._waiting_queue = deque()
        self._operation_lock = threading.Lock()

        self._mqtt_client.on_connected = self.on_connected
        self._mqtt_client.on_disconnected = self.on_disconnected
        self._mqtt_client.on_message = self._on_mqtt_message
        self._mqtt_client.on_ready = self.on_ready
        if self._mqtt_client.is_connected:
            self._ble_sync()
            self.run_periodic_sync_task()

        # temporary for testing only
        # self._start_sync_task = self.loop.call_later(30, lambda: asyncio.ensure_future(self.start_sync(0)))

    async def on_ready(self):
        """Callback for when MQTT is subscribed to events."""
        if self.on_ready_callback:
            self.on_ready_callback()

        await self._ble_sync()
        await self.run_periodic_sync_task()

    async def on_connected(self):
        """Callback for when MQTT connects."""


    async def on_disconnected(self):
        """Callback for when MQTT disconnects."""

    async def _ble_sync(self):
        command_bytes = self._commands.send_todev_ble_sync(3)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._mqtt_client.get_cloud_client().send_cloud_command, self.iot_id, command_bytes)


    async def run_periodic_sync_task(self) -> None:
        """Send ble sync to robot."""
        try:
            await self._ble_sync()
        finally:
            self.schedule_ble_sync()

    def schedule_ble_sync(self):
        """Periodically sync to keep connection alive."""
        if self._mqtt_client is not None and self._mqtt_client.is_connected:
            self._ble_sync_task = self.loop.call_later(
                160, lambda: asyncio.ensure_future(self.run_periodic_sync_task())
            )

    async def _on_mqtt_message(self, topic: str, payload: str, iot_id: str) -> None:
        """Handle incoming MQTT messages."""
        _LOGGER.debug("MQTT message received on topic %s: %s, iot_id: %s", topic, payload, iot_id)

        json_str = json.dumps(payload)
        payload = json.loads(json_str)

        await self._handle_mqtt_message(topic, payload)

    async def _send_command(self, key: str, retry: int | None = None) -> bytes | None:
        """Send command to device via MQTT and read response."""
        if self._operation_lock.locked():
            _LOGGER.debug(
                "%s: Operation already in progress, waiting for it to complete;",
                self.device.nickName
            )
        with self._operation_lock:
            try:
                command_bytes = getattr(self._commands, key)()
                return await self._send_command_locked(key, command_bytes)
            except Exception as ex:
                _LOGGER.exception("%s: error in sending command -  %s", self.device.nickName, ex)
                raise

    async def _send_command_locked(self, key: str, command: bytes) -> bytes:
        """Send command to device and read response."""
        try:
            return await self._execute_command_locked(key, command)
        except Exception as ex:
            # Disconnect so we can reset state and try again
            await asyncio.sleep(DBUS_ERROR_BACKOFF_TIME)
            _LOGGER.debug(
                "%s: error in _send_command_locked: %s",
                self.device.nickName,
                ex,
            )
            raise

    async def _execute_command_locked(self, key: str, command: bytes) -> bytes:
        """Execute command and read response."""
        assert self._mqtt_client is not None
        self._key = key
        _LOGGER.debug("%s: Sending command: %s", self.device.nickName, key)
        await self.loop.run_in_executor(None, self._mqtt_client.get_cloud_client().send_cloud_command, self.iot_id, command)
        future = MammotionFuture()
        self._waiting_queue.append(future)
        timeout = 20
        try:
            notify_msg = await future.async_get(timeout)
        except asyncio.TimeoutError:
            raise

        _LOGGER.debug("%s: Message received", self.device.nickName)

        return notify_msg

    async def _send_command_with_args(self, key: str, **kwargs: any) -> bytes | None:
        """Send command with arguments to device via MQTT and read response."""
        if self._operation_lock.locked():
            _LOGGER.debug(
                "%s: Operation already in progress, waiting for it to complete;",
                self.device.nickName
            )
        with self._operation_lock:
            try:
                command_bytes = getattr(self._commands, key)(**kwargs)
                return await self._send_command_locked(key, command_bytes)
            except Exception as ex:
                _LOGGER.exception("%s: error in sending command -  %s", self.device.nickName, ex)
                raise

    def _extract_message_id(self, payload: dict) -> str:
        """Extract the message ID from the payload."""
        return payload.get("id", "")

    def _extract_encoded_message(self, payload: dict) -> str:
        """Extract the encoded message from the payload."""
        try:
            content = payload.get("data", {}).get("data", {}).get("params", {}).get("content", "")
            return str(content)
        except AttributeError:
            _LOGGER.error("Error extracting encoded message. Payload: %s", payload)
            return ""

    async def _parse_mqtt_response(self, topic: str, payload: dict) -> None:
        """Parse the MQTT response."""
        if topic.endswith("/app/down/thing/events"):
            _LOGGER.debug("Thing event received")
            event = ThingEventMessage.from_dicts(payload)
            params = event.params
            if params.identifier == "device_protobuf_msg_event":
                _LOGGER.debug("Protobuf event")
                binary_data = base64.b64decode(params.value.get("content", ""))
                self._update_raw_data(cast(bytes, binary_data))
                new_msg = LubaMsg().parse(cast(bytes, binary_data))

                if self._commands.get_device_product_key() == "" and self._commands.get_device_name() == event.params.deviceName:
                    self._commands.set_device_product_key(event.params.productKey)

                if betterproto.serialized_on_wire(new_msg.net):
                    if new_msg.net.todev_ble_sync != 0 or has_field(new_msg.net.toapp_wifi_iot_status):
                        return


                if len(self._waiting_queue) > 0:
                    fut: MammotionFuture = self._waiting_queue.popleft()
                    while fut.fut.cancelled():
                        fut: MammotionFuture = self._waiting_queue.popleft()
                    fut.resolve(cast(bytes, binary_data))
                await self._state_manager.notification(new_msg)

    async def _handle_mqtt_message(self, topic: str, payload: dict) -> None:
        """Async handler for incoming MQTT messages."""
        await self._parse_mqtt_response(topic=topic, payload=payload)

    def _disconnect(self):
        """Disconnect the MQTT client."""
        self._mqtt_client.disconnect()


