"""RTK device with cloud MQTT connectivity."""

import asyncio
from collections.abc import Awaitable, Callable
import logging
from typing import Any

from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.model.device import RTKDevice
from pymammotion.data.mqtt.properties import ThingPropertiesMessage
from pymammotion.data.mqtt.status import ThingStatusMessage
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.mammotion.devices.mammotion_cloud import MammotionCloud
from pymammotion.mammotion.devices.rtk_device import MammotionRTKDevice

_LOGGER = logging.getLogger(__name__)


class MammotionRTKCloudDevice(MammotionRTKDevice):
    """RTK device with cloud connectivity - simpler than mowers, no map sync."""

    def __init__(self, mqtt: MammotionCloud, cloud_device: Device, rtk_state: RTKDevice) -> None:
        """Initialize MammotionRTKCloudDevice.
        :rtype: None
        """
        super().__init__(cloud_device, rtk_state)
        self.stopped = False
        self.on_ready_callback: Callable[[], Awaitable[None]] | None = None
        self.loop = asyncio.get_event_loop()
        self._mqtt = mqtt
        self.iot_id = cloud_device.iot_id
        self.device = cloud_device
        self._commands: MammotionCommand = MammotionCommand(
            cloud_device.device_name,
            int(mqtt.cloud_client.mammotion_http.response.data.userInformation.userAccount),
        )
        # Subscribe to MQTT events for this device
        self._mqtt.mqtt_properties_event.add_subscribers(self._parse_message_properties_for_device)
        self._mqtt.mqtt_status_event.add_subscribers(self._parse_message_status_for_device)
        self._mqtt.on_ready_event.add_subscribers(self.on_ready)
        self._mqtt.on_disconnected_event.add_subscribers(self.on_disconnect)
        self._mqtt.on_connected_event.add_subscribers(self.on_connect)

    def __del__(self) -> None:
        """Cleanup subscriptions."""
        if hasattr(self, "_mqtt"):
            self._mqtt.on_ready_event.remove_subscribers(self.on_ready)
            self._mqtt.on_disconnected_event.remove_subscribers(self.on_disconnect)
            self._mqtt.on_connected_event.remove_subscribers(self.on_connect)
            self._mqtt.mqtt_properties_event.remove_subscribers(self._parse_message_properties_for_device)
            self._mqtt.mqtt_status_event.remove_subscribers(self._parse_message_status_for_device)

    @property
    def command_sent_time(self) -> float:
        return self._mqtt.command_sent_time

    @property
    def mqtt(self):
        return self._mqtt

    async def on_ready(self) -> None:
        """Callback for when MQTT is subscribed to events."""
        if self.stopped:
            return
        if self.on_ready_callback:
            await self.on_ready_callback()

    async def on_disconnect(self) -> None:
        """Callback for when MQTT disconnects."""
        self._mqtt.disconnect()

    async def on_connect(self) -> None:
        """Callback for when MQTT connects."""

    async def stop(self) -> None:
        """Stop all tasks and disconnect."""
        self.stopped = True

    async def start(self) -> None:
        """Start the device connection."""
        self.stopped = False
        if not self.mqtt.is_connected():
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.mqtt.connect_async)

    async def queue_command(self, key: str, **kwargs: Any) -> None:
        """Queue a command to the RTK device."""
        _LOGGER.debug("Queueing command: %s", key)
        future = asyncio.Future()
        command_bytes = getattr(self._commands, key)(**kwargs)
        await self._mqtt.command_queue.put((self.iot_id, key, command_bytes, future))
        try:
            return await future
        except asyncio.CancelledError:
            """Try again once."""
            future = asyncio.Future()
            await self._mqtt.command_queue.put((self.iot_id, key, command_bytes, future))

    async def _parse_message_properties_for_device(self, event: ThingPropertiesMessage) -> None:
        """Parse property messages for this RTK device."""
        if event.params.iot_id != self.iot_id:
            return
        # RTK devices have simpler properties - update as needed
        _LOGGER.debug("RTK properties update: %s", event)

    async def _parse_message_status_for_device(self, status: ThingStatusMessage) -> None:
        """Parse status messages for this RTK device."""
        if status.params.iot_id != self.iot_id:
            return
        # Update online status
        self._rtk_device.online = True
        _LOGGER.debug("RTK status update: %s", status)

    async def _ble_sync(self) -> None:
        """RTK devices don't use BLE sync in the same way as mowers."""
