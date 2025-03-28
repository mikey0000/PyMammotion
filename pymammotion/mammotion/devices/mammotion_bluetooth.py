import asyncio
from collections.abc import Awaitable, Callable
import logging
from typing import Any, cast
from uuid import UUID

import betterproto
from bleak import BleakGATTCharacteristic, BleakGATTServiceCollection, BLEDevice
from bleak.exc import BleakDBusError
from bleak_retry_connector import (
    BLEAK_RETRY_EXCEPTIONS,
    BleakClientWithServiceCache,
    BleakNotFoundError,
    establish_connection,
)

from pymammotion.bluetooth import BleMessage
from pymammotion.data.state_manager import StateManager
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.mammotion.devices.base import MammotionBaseDevice
from pymammotion.proto import LubaMsg, has_field

DBUS_ERROR_BACKOFF_TIME = 0.25

DISCONNECT_DELAY = 10


_LOGGER = logging.getLogger(__name__)


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


def _handle_timeout(fut: asyncio.Future[None]) -> None:
    """Handle a timeout."""
    if not fut.done():
        fut.set_exception(asyncio.TimeoutError)


async def _handle_retry(fut: asyncio.Future[None], func, command: bytes) -> None:
    """Handle a retry."""
    if not fut.done():
        await func(command)


class MammotionBaseBLEDevice(MammotionBaseDevice):
    """Base class for Mammotion BLE devices."""

    def __init__(self, state_manager: StateManager, device: BLEDevice, interface: int = 0, **kwargs: Any) -> None:
        """Initialize MammotionBaseBLEDevice."""
        super().__init__(state_manager)
        self._disconnect_strategy = True
        self._ble_sync_task = None
        self._prev_notification = None
        self._interface = f"hci{interface}"
        self.ble_device = device
        self._client: BleakClientWithServiceCache | None = None
        self._read_char: BleakGATTCharacteristic | int | str | UUID = 0
        self._write_char: BleakGATTCharacteristic | int | str | UUID = 0
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._message: BleMessage | None = None
        self._commands: MammotionCommand = MammotionCommand(device.name, 1)
        self.command_queue = asyncio.Queue()
        self._expected_disconnect = False
        self._connect_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()
        self._key: str | None = None
        self.set_queue_callback(self.queue_command)
        self._state_manager.ble_gethash_ack_callback = self.datahash_response
        self._state_manager.ble_get_commondata_ack_callback = self.commdata_response
        loop = asyncio.get_event_loop()
        loop.create_task(self.process_queue())

    def set_notification_callback(self, func: Callable[[tuple[str, Any | None]], Awaitable[None]]) -> None:
        self._state_manager.ble_on_notification_callback = func

    def set_queue_callback(self, func: Callable[[str, dict[str, Any]], Awaitable[bytes]]) -> None:
        self._state_manager.ble_queue_command_callback = func

    def update_device(self, device: BLEDevice) -> None:
        """Update the BLE device."""
        self.ble_device = device

    async def _ble_sync(self) -> None:
        if self._client is not None and self._client.is_connected:
            _LOGGER.debug("BLE SYNC")
            command_bytes = self._commands.send_todev_ble_sync(2)
            await self._message.post_custom_data_bytes(command_bytes)

    async def run_periodic_sync_task(self) -> None:
        """Send ble sync to robot."""
        try:
            await self._ble_sync()
        finally:
            self.schedule_ble_sync()

    def schedule_ble_sync(self) -> None:
        """Periodically sync to keep connection alive."""
        if self._client is not None and self._client.is_connected:
            self._ble_sync_task = self.loop.call_later(
                130, lambda: asyncio.ensure_future(self.run_periodic_sync_task())
            )

    async def stop(self) -> None:
        """Stop all tasks and disconnect."""
        if self._ble_sync_task:
            self._ble_sync_task.cancel()
        if self._client is not None:
            await self._client.disconnect()

    async def queue_command(self, key: str, **kwargs: Any) -> bytes | None:
        # Create a future to hold the result
        _LOGGER.debug("Queueing command: %s", key)
        future = asyncio.Future()
        # Put the command in the queue as a tuple (key, command, future)
        command_bytes = getattr(self._commands, key)(**kwargs)
        await self.command_queue.put((key, command_bytes, future))
        # Wait for the future to be resolved
        return await future
        # return await self._send_command_with_args(key, **kwargs)

    async def process_queue(self) -> None:
        while True:
            # Get the next item from the queue
            key, command, future = await self.command_queue.get()
            try:
                # Process the command using _execute_command_locked
                result = await self._send_command_locked(key, command)
                # Set the result on the future
                future.set_result(result)
            except Exception as ex:
                # Set the exception on the future if something goes wrong
                future.set_exception(ex)
            finally:
                # Mark the task as done
                self.command_queue.task_done()

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
        return

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
        return

    @property
    def name(self) -> str:
        """Return device name."""
        return f"{self.ble_device.name} ({self.ble_device.address})"

    @property
    def rssi(self) -> int:
        """Return RSSI of device."""
        try:
            return cast(self.mower.sys.toapp_report_data.connect.ble_rssi, int)
        finally:
            return 0

    async def _ensure_connected(self) -> None:
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
                self.ble_device,
                self.name,
                self._disconnected,
                max_attempts=10,
                ble_device_callback=lambda: self.ble_device,
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
            await self._ble_sync()
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
        if self._message is None:
            return
        result = self._message.parseNotification(data)
        if result == 0:
            data = await self._message.parseBlufiNotifyData(True)
            try:
                self._update_raw_data(data)
            except (KeyError, ValueError, IndexError, UnicodeDecodeError):
                _LOGGER.exception("Error parsing message %s", data)
                data = b""
            finally:
                self._message.clear_notification()

            _LOGGER.debug("%s: Received notification: %s", self.name, data)
        else:
            return
        new_msg = LubaMsg().parse(data)
        if betterproto.serialized_on_wire(new_msg.net):
            if new_msg.net.todev_ble_sync != 0 or has_field(new_msg.net.toapp_wifi_iot_status):
                if has_field(new_msg.net.toapp_wifi_iot_status) and self._commands.get_device_product_key() == "":
                    self._commands.set_device_product_key(new_msg.net.toapp_wifi_iot_status.productkey)

                return

        await self._state_manager.notification(new_msg)
        # may or may not be correct, some work could be done here to correctly match responses
        if self._notify_future and not self._notify_future.done():
            self._notify_future.set_result(data)

        if self._execute_timed_disconnect is None:
            await self._execute_forced_disconnect()

        self._reset_disconnect_timer()

    async def _start_notify(self) -> None:
        """Start notification."""
        _LOGGER.debug("%s: Subscribe to notifications; RSSI: %s", self.name, self.rssi)
        await self._client.start_notify(self._read_char, self._notification_handler)

    async def _execute_command_locked(self, key: str, command: bytes) -> bytes:
        """Execute command and read response."""
        assert self._client is not None
        self._notify_future = self.loop.create_future()
        self._key = key
        _LOGGER.debug("%s: Sending command: %s", self.name, key)
        await self._message.post_custom_data_bytes(command)

        timeout = 2
        timeout_handle = self.loop.call_at(self.loop.time() + timeout, _handle_timeout, self._notify_future)
        timeout_expired = False
        try:
            notify_msg = await self._notify_future
        except asyncio.TimeoutError:
            timeout_expired = True
            notify_msg = b""
        finally:
            if not timeout_expired:
                timeout_handle.cancel()
            self._notify_future = None

        _LOGGER.debug("%s: Notification received: %s", self.name, notify_msg.hex())
        return notify_msg

    def get_address(self) -> str:
        """Return address of device."""
        return self.ble_device.address

    def _resolve_characteristics(self, services: BleakGATTServiceCollection) -> None:
        """Resolve characteristics."""
        self._read_char = services.get_characteristic(READ_CHAR_UUID)
        if not self._read_char:
            _LOGGER.error(CharacteristicMissingError(READ_CHAR_UUID))
        self._write_char = services.get_characteristic(WRITE_CHAR_UUID)
        if not self._write_char:
            _LOGGER.error(CharacteristicMissingError(WRITE_CHAR_UUID))

    def _reset_disconnect_timer(self) -> None:
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
        self._client = None

    def _disconnect_from_timer(self) -> None:
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

    def _cancel_disconnect_timer(self) -> None:
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

    def set_disconnect_strategy(self, disconnect: bool) -> None:
        self._disconnect_strategy = disconnect
