from __future__ import annotations

import asyncio
import codecs
import logging
from abc import abstractmethod
from enum import Enum
from typing import Any
from uuid import UUID

import betterproto
from bleak.backends.device import BLEDevice
from bleak.backends.service import BleakGATTCharacteristic, BleakGATTServiceCollection
from bleak.exc import BleakDBusError
from bleak_retry_connector import (
    BLEAK_RETRY_EXCEPTIONS,
    BleakClientWithServiceCache,
    BleakNotFoundError,
    establish_connection,
)
from google.protobuf import json_format

from pyluba.bluetooth import BleMessage
from pyluba.bluetooth.const import (
    UUID_NOTIFICATION_CHARACTERISTIC,
    UUID_WRITE_CHARACTERISTIC,
)

from pyluba.mammotion.commands.mammotion_command import MammotionCommand
from pyluba.proto import (
    luba_msg_pb2,
)
from pyluba.proto.dev_net import DevNet
from pyluba.proto.luba_msg import LubaMsg
from pyluba.proto.luba_mul import SocMul
from pyluba.proto.mctrl_ota import MctlOta
from pyluba.proto.mctrl_sys import MctlSys


class CharacteristicMissingError(Exception):
    """Raised when a characteristic is missing."""


def _sb_uuid(comms_type: str = "service") -> UUID | str:
    """Return Mammotion UUID."""

    _uuid = {"tx": "ff01", "rx": "ff02", "service": "2A05"}

    if comms_type in _uuid:
        return UUID(f"0000{_uuid[comms_type]}-0000-1000-8000-00805f9b34fb")

    return "Incorrect type, choose between: tx, rx or service"


READ_CHAR_UUID = _sb_uuid(comms_type="rx")
WRITE_CHAR_UUID = _sb_uuid(comms_type="tx")

DBUS_ERROR_BACKOFF_TIME = 0.25

DISCONNECT_DELAY = 10

_LOGGER = logging.getLogger(__name__)


def slashescape(err):
    """Codecs error handler. err is UnicodeDecode instance. return
    a tuple with a replacement for the unencodable part of the input
    and a position where encoding should continue
    """
    # print err, dir(err), err.start, err.end, err.object[:err.start]
    thebyte = err.object[err.start: err.end]
    repl = "\\x" + hex(ord(thebyte))[2:]
    return (repl, err.end)


codecs.register_error("slashescape", slashescape)


def _handle_timeout(fut: asyncio.Future[None]) -> None:
    """Handle a timeout."""
    if not fut.done():
        fut.set_exception(asyncio.TimeoutError)


class ConnectionPreference(Enum):
    EITHER = 0
    WIFI = 1
    BLUETOOTH = 2


class MammotionDevice:
    _ble_device: MammotionBaseBLEDevice | None = None

    def __init__(self, ble_device: BLEDevice, preference: ConnectionPreference = ConnectionPreference.EITHER) -> None:
        if ble_device:
            self._ble_device = MammotionBaseBLEDevice(ble_device)
            self._preference = preference

    async def send_command(self, key: str):
        return await self._ble_device.command(key)


def has_field(message: betterproto.Message) -> bool:
    return betterproto.serialized_on_wire(message)


class MammotionBaseDevice:

    def __init__(self) -> None:
        self.loop = asyncio.get_event_loop()
        self._raw_data = LubaMsg().to_dict(casing=betterproto.Casing.SNAKE)
        self._luba_msg = LubaMsg()
        self._notify_future: asyncio.Future[bytes] | None = None

    def _update_raw_data(self, data: bytes) -> None:
        """Update raw and model data from notifications."""
        # proto_luba = luba_msg_pb2.LubaMsg()
        # proto_luba.ParseFromString(data)
        tmp_msg = LubaMsg.FromString(data)
        res = betterproto.which_one_of(tmp_msg, "LubaSubMsg")
        match res[0]:
            case 'nav':
                nav_sub_msg = betterproto.which_one_of(
                    tmp_msg.nav, 'SubNavMsg')
                nav = self._raw_data.get('nav')
                if nav is None:
                    self._raw_data['nav'] = {}
                if isinstance(nav_sub_msg[1], int):
                    self._raw_data['net'][nav_sub_msg[0]] = nav_sub_msg[1]
                else:
                    self._raw_data['nav'][nav_sub_msg[0]] = nav_sub_msg[1].to_dict(
                        casing=betterproto.Casing.SNAKE)
            case 'sys':
                sys_sub_msg = betterproto.which_one_of(
                    tmp_msg.sys, 'SubSysMsg')
                sys = self._raw_data.get('sys')
                if sys is None:
                    self._raw_data['sys'] = {}
                self._raw_data['sys'][sys_sub_msg[0]] = sys_sub_msg[1].to_dict(
                    casing=betterproto.Casing.SNAKE)
            case 'driver':
                drv_sub_msg = betterproto.which_one_of(
                    tmp_msg.driver, 'SubDrvMsg')
                drv = self._raw_data.get('driver')
                if drv is None:
                    self._raw_data['driver'] = {}
                self._raw_data['driver'][drv_sub_msg[0]] = drv_sub_msg[1].to_dict(
                    casing=betterproto.Casing.SNAKE)
            case 'net':
                net_sub_msg = betterproto.which_one_of(
                    tmp_msg.net, 'NetSubType')
                net = self._raw_data.get('net')
                if net is None:
                    self._raw_data['net'] = {}
                if isinstance(net_sub_msg[1], int):
                    self._raw_data['net'][net_sub_msg[0]] = net_sub_msg[1]
                else:
                    self._raw_data['net'][net_sub_msg[0]] = net_sub_msg[1].to_dict(
                        casing=betterproto.Casing.SNAKE)
            case 'mul':
                mul_sub_msg = betterproto.which_one_of(tmp_msg.mul, 'SubMul')
                mul = self._raw_data.get('mul')
                if mul is None:
                    self._raw_data['mul'] = {}
                self._raw_data['mul'][mul_sub_msg[0]] = mul_sub_msg[1].to_dict(
                    casing=betterproto.Casing.SNAKE)
            case 'ota':
                ota_sub_msg = betterproto.which_one_of(
                    tmp_msg.ota, 'SubOtaMsg')
                ota = self._raw_data.get('ota')
                if ota is None:
                    self._raw_data['ota'] = {}
                self._raw_data['ota'][ota_sub_msg[0]] = ota_sub_msg[1].to_dict(
                    casing=betterproto.Casing.SNAKE)

        self._luba_msg = LubaMsg().from_dict(self._raw_data)

    @property
    def raw_data(self) -> dict[str, Any]:
        return self._raw_data

    @property
    def luba_msg(self) -> LubaMsg:
        return self._luba_msg

    @abstractmethod
    async def _send_command(self, key: str, retry: int | None = None) -> bytes | None:
        """Send command to device and read response."""

    @abstractmethod
    async def _send_command_with_args(self, key: str, **kwargs: dict[str, Any]) -> bytes | None:
        """Send command to device and read response."""

    async def start_sync(self, retry: int):
        await self._send_command("get_device_base_info", retry)
        cfg = await self._send_command("get_report_cfg", retry)
        # cfg_proto = luba_msg_pb2.LubaMsg()
        # cfg_proto.ParseFromString(cfg)
        # print(json_format.MessageToDict(cfg_proto))

        plan = await self._send_command_with_args("read_plan", **{'id': 2})
        # plan_proto = luba_msg_pb2.LubaMsg()
        # plan_proto.ParseFromString(plan)
        # print(json_format.MessageToDict(plan_proto))

        RW = await self._send_command_with_args("allpowerfull_rw", **{'id': 5, 'context': 1, 'rw': 1})
        # RW_proto = luba_msg_pb2.LubaMsg()
        # RW_proto.ParseFromString(RW)
        # print(json_format.MessageToDict(RW_proto))

    async def command(self, key: str, **kwargs):
        return await self._send_command_with_args(key, **kwargs)


class MammotionBaseBLEDevice(MammotionBaseDevice):

    def __init__(self, device: BLEDevice, interface: int = 0, **kwargs: Any) -> None:
        super().__init__()
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
        self._device = device

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
                _LOGGER.error(
                    "%s: device not found, no longer in range, or poor RSSI: %s",
                    self.name,
                    self.rssi,
                    exc_info=True,
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
                _LOGGER.debug(
                    "%s: communication failed with:", self.name, exc_info=True
                )
        raise RuntimeError("Unreachable")

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
                _LOGGER.error(
                    "%s: device not found, no longer in range, or poor RSSI: %s",
                    self.name,
                    self.rssi,
                    exc_info=True,
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
                _LOGGER.debug(
                    "%s: communication failed with:", self.name, exc_info=True
                )
        # raise RuntimeError("Unreachable")

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
                BleakClientWithServiceCache,
                self._device,
                self.name,
                self._disconnected,
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
            _LOGGER.debug(
                "%s: RSSI: %s; Disconnecting due to error: %s", self.name, self.rssi, ex
            )
            await self._execute_forced_disconnect()
            raise

    async def _notification_handler(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle notification responses."""
        _LOGGER.debug("%s: Received notification: %s", self.name, data)
        result = self._message.parseNotification(data)
        if result == 0:
            data = await self._message.parseBlufiNotifyData(True)
            self._update_raw_data(data)
            self._message.clearNotification()
        else:
            return
        new_msg = LubaMsg().parse(data)
        if betterproto.serialized_on_wire(new_msg.net):
            if new_msg.net.todev_ble_sync != 0 or has_field(new_msg.net.toapp_wifi_iot_status):
                # TODO occasionally respond with ble sync
                return

        if self._notify_future and not self._notify_future.done():
            self._notify_future.set_result(data)
            return

    async def _start_notify(self) -> None:
        """Start notification."""
        _LOGGER.debug("%s: Subscribe to notifications; RSSI: %s",
                      self.name, self.rssi)
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

        timeout = 5
        timeout_handle = self.loop.call_at(
            self.loop.time() + timeout, _handle_timeout, self._notify_future
        )
        timeout_expired = False
        try:
            notify_msg = await self._notify_future
        except asyncio.TimeoutError:
            timeout_expired = True
            raise
        finally:
            if not timeout_expired:
                timeout_handle.cancel()
            self._notify_future = None

        _LOGGER.debug("%s: Notification received: %s",
                      self.name, notify_msg.hex())
        return notify_msg

    def get_address(self) -> str:
        """Return address of device."""
        return self._device.address

    def _resolve_characteristics(self, services: BleakGATTServiceCollection) -> None:
        """Resolve characteristics."""
        self._read_char = services.get_characteristic(READ_CHAR_UUID)
        if not self._read_char:
            raise CharacteristicMissingError(READ_CHAR_UUID)
        self._write_char = services.get_characteristic(WRITE_CHAR_UUID)
        if not self._write_char:
            raise CharacteristicMissingError(WRITE_CHAR_UUID)

    def _reset_disconnect_timer(self):
        """Reset disconnect timer."""
        self._cancel_disconnect_timer()
        self._expected_disconnect = False
        self._disconnect_timer = self.loop.call_later(
            DISCONNECT_DELAY, self._disconnect_from_timer
        )

    def _disconnected(self, client: BleakClientWithServiceCache) -> None:
        """Disconnected callback."""
        if self._expected_disconnect:
            _LOGGER.debug(
                "%s: Disconnected from device; RSSI: %s", self.name, self.rssi
            )
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
        self._timed_disconnect_task = asyncio.create_task(
            self._execute_timed_disconnect()
        )

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
