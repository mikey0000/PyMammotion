"""Device control of mammotion robots over bluetooth or MQTT."""

from __future__ import annotations

import asyncio
import codecs
import json
import logging
from abc import abstractmethod
from enum import Enum
from typing import Any, cast
from uuid import UUID

import betterproto
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

from pymammotion.bluetooth import BleMessage
from pymammotion.data.model import RegionData
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.mqtt.event import ThingEventMessage
from pymammotion.data.state_manager import StateManager
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.mqtt import MammotionMQTT
from pymammotion.proto.luba_msg import LubaMsg
from pymammotion.proto.mctrl_nav import NavGetCommDataAck, NavGetHashListAck


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
    thebyte = err.object[err.start: err.end]
    repl = "\\x" + hex(ord(thebyte))[2:]
    return (repl, err.end)


codecs.register_error("slashescape", slashescape)


def find_next_integer(lst: list[int], current_int: int) -> int | None:
    try:
        # Find the index of the current integer
        current_index = lst.index(current_int)

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


class ConnectionPreference(Enum):
    """Enum for connection preference."""

    EITHER = 0
    WIFI = 1
    BLUETOOTH = 2


class MammotionDevice:
    """Represents a Mammotion device."""

    _ble_device: MammotionBaseBLEDevice | None = None

    def __init__(
            self,
            ble_device: BLEDevice,
            preference: ConnectionPreference = ConnectionPreference.EITHER,
    ) -> None:
        """Initialize MammotionDevice."""
        if ble_device:
            self._ble_device = MammotionBaseBLEDevice(ble_device)
            self._preference = preference

    async def send_command(self, key: str):
        """Send a command to the device."""
        return await self._ble_device.command(key)


def has_field(message: betterproto.Message) -> bool:
    """Check if the message has any fields serialized on wire."""
    return betterproto.serialized_on_wire(message)


class MammotionBaseDevice:
    """Base class for Mammotion devices."""

    _luba_msg: MowingDevice
    _state_manager: StateManager

    def __init__(self) -> None:
        """Initialize MammotionBaseDevice."""
        self.loop = asyncio.get_event_loop()
        self._raw_data = LubaMsg().to_dict(casing=betterproto.Casing.SNAKE)
        self._luba_msg = MowingDevice()
        self._state_manager = StateManager(self._luba_msg)

        self._state_manager.gethash_ack_callback.add_subscribers(self.datahash_response)
        self._state_manager.get_commondata_ack_callback.add_subscribers(self.commdata_response)
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

            data_hash = find_next_integer(self.luba_msg.nav.toapp_gethash_ack.data_couple, common_data.hash)
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

        self._luba_msg.update_raw(self._raw_data)

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
    def luba_msg(self) -> MowingDevice:
        """Get the LubaMsg of the device."""
        return self._luba_msg

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

        await self._send_command_with_args("get_area_name_list",
                                           device_id=self.luba_msg.device.net.toapp_wifi_iot_status.devicename)
        # sub_cmd 3 is job hashes??
        # sub_cmd 4 is dump location (yuka)
        # jobs list
        # hash_list_result = await self._send_command_with_args("get_all_boundary_hash_list", sub_cmd=3)

    async def command(self, key: str, **kwargs):
        """Send a command to the device."""
        return await self._send_command_with_args(key, **kwargs)


class MammotionBaseBLEDevice(MammotionBaseDevice):
    """Base class for Mammotion BLE devices."""

    def __init__(self, device: BLEDevice, interface: int = 0, **kwargs: Any) -> None:
        """Initialize MammotionBaseBLEDevice."""
        super().__init__()
        self._ble_sync_task = None
        self._prev_notification = None
        self._interface = f"hci{interface}"
        self._device = device
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
                BleakClient,
                self._device,
                self.name,
                self._disconnected,
                max_attempts=10,
                use_services_cache=True,
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


class MammotionBaseCloudDevice(MammotionBaseDevice):
    """Base class for Mammotion Cloud devices."""

    def __init__(
            self,
            mqtt_client: MammotionMQTT,
            iot_id: str,
            device_name: str,
            nick_name: str,
            **kwargs: Any,
    ) -> None:
        """Initialize MammotionBaseCloudDevice."""
        super().__init__()
        self._mqtt_client = mqtt_client
        self.iot_id = iot_id
        self.nick_name = nick_name
        self._command_futures = {}
        self._commands: MammotionCommand = MammotionCommand(device_name)
        self.loop = asyncio.get_event_loop()

    def _on_mqtt_message(self, topic: str, payload: str) -> None:
        """Handle incoming MQTT messages."""
        _LOGGER.debug("MQTT message received on topic %s: %s", topic, payload)
        payload = json.loads(payload)
        message_id = self._extract_message_id(payload)
        if message_id and message_id in self._command_futures:
            self._parse_mqtt_response(topic=topic, payload=payload)
            future = self._command_futures.pop(message_id)
            if not future.done():
                future.set_result(payload)

    async def _send_command(self, key: str, retry: int | None = None) -> bytes | None:
        """Send command to device via MQTT and read response."""
        future = self.loop.create_future()
        command_bytes = getattr(self._commands, key)()
        message_id = self._mqtt_client.get_cloud_client().send_cloud_command(self.iot_id, command_bytes)
        if message_id != "":
            self._command_futures[message_id] = future
            try:
                return await asyncio.wait_for(future, timeout=TIMEOUT_CLOUD_RESPONSE)
            except asyncio.TimeoutError:
                _LOGGER.error("Command '%s' timed out", key)
        return None

    async def _send_command_with_args(self, key: str, **kwargs: any) -> bytes | None:
        """Send command with arguments to device via MQTT and read response."""
        future = self.loop.create_future()
        command_bytes = getattr(self._commands, key)(**kwargs)
        message_id = self._mqtt_client.get_cloud_client().send_cloud_command(self.iot_id, command_bytes)
        if message_id != "":
            self._command_futures[message_id] = future
            try:
                return await asyncio.wait_for(future, timeout=TIMEOUT_CLOUD_RESPONSE)
            except asyncio.TimeoutError:
                _LOGGER.error("Command '%s' timed out", key)
        return None

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

    def _parse_mqtt_response(self, topic: str, payload: dict) -> None:
        """Parse the MQTT response."""
        if topic.endswith("/app/down/thing/events"):
            event = ThingEventMessage(**payload)
            params = event.params
            if params.identifier == "device_protobuf_msg_event":
                self._update_raw_data(cast(bytes, params.value.content))

    async def _disconnect(self):
        """Disconnect the MQTT client."""
        self._mqtt_client.disconnect()
