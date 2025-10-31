"""RTK device with Bluetooth LE connectivity."""

import asyncio
import logging
from typing import Any
from uuid import UUID

from bleak import BleakGATTCharacteristic, BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache

from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.bluetooth import BleMessage
from pymammotion.data.model.device import RTKDevice
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.mammotion.devices.rtk_device import MammotionRTKDevice

_LOGGER = logging.getLogger(__name__)


class MammotionRTKBLEDevice(MammotionRTKDevice):
    """RTK device with BLE connectivity - simpler than mowers, no map sync."""

    def __init__(
        self, cloud_device: Device, rtk_state: RTKDevice, device: BLEDevice, interface: int = 0, **kwargs: Any
    ) -> None:
        """Initialize MammotionRTKBLEDevice."""
        super().__init__(cloud_device, rtk_state)
        self.command_sent_time = 0
        self._disconnect_strategy = True
        self._interface = f"hci{interface}"
        self.ble_device = device
        self._client: BleakClientWithServiceCache | None = None
        self._read_char: BleakGATTCharacteristic | int | str | UUID = 0
        self._write_char: BleakGATTCharacteristic | int | str | UUID = 0
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._message: BleMessage | None = None
        self._commands: MammotionCommand = MammotionCommand(device.name or "", 1)
        self.command_queue = asyncio.Queue()
        self._expected_disconnect = False
        self._connect_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()
        self._key: str | None = None
        loop = asyncio.get_event_loop()
        loop.create_task(self.process_queue())

    def __del__(self) -> None:
        """Cleanup."""
        if self._disconnect_timer:
            self._disconnect_timer.cancel()

    @property
    def client(self) -> BleakClientWithServiceCache:
        """Return the BLE client."""
        return self._client

    def set_disconnect_strategy(self, *, disconnect: bool) -> None:
        """Set disconnect strategy."""
        self._disconnect_strategy = disconnect

    async def process_queue(self) -> None:
        """Process queued commands - simplified for RTK."""
        while True:
            key, kwargs = await self.command_queue.get()
            try:
                _LOGGER.debug("Processing RTK BLE command: %s", key)
                command_bytes = getattr(self._commands, key)(**kwargs)
                # Send command via BLE (implementation depends on BLE infrastructure)
                # For now, this is a placeholder
                _LOGGER.debug("RTK BLE command sent: %s", key)
            except Exception as ex:
                _LOGGER.exception("Error processing RTK BLE command: %s", ex)
            finally:
                self.command_queue.task_done()

    async def queue_command(self, key: str, **kwargs: Any) -> None:
        """Queue a command to the RTK device."""
        await self.command_queue.put((key, kwargs))

    async def command(self, key: str, **kwargs):
        """Send a command to the RTK device."""
        return await self.queue_command(key, **kwargs)

    async def _ble_sync(self) -> None:
        """RTK devices don't use BLE sync in the same way as mowers."""

    async def stop(self) -> None:
        """Stop everything ready for destroying."""
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()
