"""RTK device class without map synchronization callbacks."""

import asyncio
import logging
from typing import Any

from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.model.device import RTKDevice
from pymammotion.data.model.raw_data import RawMowerData

_LOGGER = logging.getLogger(__name__)


class MammotionRTKDevice:
    """RTK device without map synchronization - simpler than mowers."""

    def __init__(self, cloud_device: Device, rtk_state: RTKDevice) -> None:
        """Initialize MammotionRTKDevice."""
        self.loop = asyncio.get_event_loop()
        self._rtk_device = rtk_state
        self._raw_data = dict()
        self._raw_mower_data: RawMowerData = RawMowerData()
        self._notify_future: asyncio.Future[bytes] | None = None
        self._cloud_device = cloud_device

    @property
    def rtk(self) -> RTKDevice:
        """Get the RTK device state."""
        return self._rtk_device

    @property
    def raw_data(self) -> dict[str, Any]:
        """Get the raw data of the device."""
        return self._raw_data

    async def command(self, key: str, **kwargs: Any) -> bytes | None:
        """Send a command to the device."""
        return await self.queue_command(key, **kwargs)

    async def queue_command(self, key: str, **kwargs: Any) -> bytes | None:
        """Queue commands to RTK device - to be implemented by connection-specific subclasses."""
        raise NotImplementedError("Subclasses must implement queue_command")

    async def _ble_sync(self) -> None:
        """Send ble sync command - to be implemented by connection-specific subclasses."""
        raise NotImplementedError("Subclasses must implement _ble_sync")

    def stop(self) -> None:
        """Stop everything ready for destroying - to be implemented by connection-specific subclasses."""
        raise NotImplementedError("Subclasses must implement stop")
