import asyncio
from asyncio import InvalidStateError
import base64
from collections import deque
from collections.abc import Awaitable, Callable
import json
import logging
import time
from typing import Any

import betterproto2
from Tea.exceptions import UnretryableException

from pymammotion import AliyunMQTT, CloudIOTGateway, MammotionMQTT
from pymammotion.aliyun.cloud_gateway import DeviceOfflineException
from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.mower_state_manager import MowerStateManager
from pymammotion.data.mqtt.event import MammotionEventMessage, ThingEventMessage
from pymammotion.data.mqtt.properties import MammotionPropertiesMessage, ThingPropertiesMessage
from pymammotion.data.mqtt.status import ThingStatusMessage
from pymammotion.event.event import DataEvent
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.mammotion.devices.base import MammotionBaseDevice
from pymammotion.proto import LubaMsg

_LOGGER = logging.getLogger(__name__)


class MammotionCloud:
    """Per account MQTT cloud."""

    def __init__(self, mqtt_client: AliyunMQTT | MammotionMQTT, cloud_client: CloudIOTGateway) -> None:
        """Initialize MammotionCloud."""
        self.cloud_client = cloud_client
        self.command_sent_time = 0
        self.loop = asyncio.get_event_loop()
        self.is_ready = False
        self.command_queue = asyncio.Queue()
        self._waiting_queue = deque()
        self.mqtt_message_event = DataEvent()
        self.mqtt_properties_event = DataEvent()
        self.mqtt_status_event = DataEvent()
        self.mqtt_device_event = DataEvent()
        self.on_ready_event = DataEvent()
        self.on_disconnected_event = DataEvent()
        self.on_connected_event = DataEvent()
        self._operation_lock = asyncio.Lock()
        self._mqtt_client = mqtt_client
        self._mqtt_client.on_connected = self.on_connected
        self._mqtt_client.on_disconnected = self.on_disconnected
        self._mqtt_client.on_message = self._on_mqtt_message
        self._mqtt_client.on_ready = self.on_ready

    async def on_ready(self) -> None:
        """Starts processing the queue and emits the ready event."""
        loop = asyncio.get_event_loop()
        loop.create_task(self.process_queue())
        await self.on_ready_event.data_event(None)

    def is_connected(self) -> bool:
        return self._mqtt_client.is_connected

    def disconnect(self) -> None:
        """Disconnect the MQTT client."""
        if self.is_connected:
            self._mqtt_client.disconnect()

    def connect_async(self) -> None:
        self._mqtt_client.connect_async()

    async def send_command(self, iot_id: str, command: bytes) -> None:
        await self._mqtt_client.send_cloud_command(iot_id, command)

    async def on_connected(self) -> None:
        """Callback for when MQTT connects."""
        await self.on_connected_event.data_event(None)

    async def on_disconnected(self) -> None:
        """Callback for when MQTT disconnects."""
        await self.on_disconnected_event.data_event(None)

    async def process_queue(self) -> None:
        while True:
            # Get the next item from the queue
            iot_id, key, command, future = await self.command_queue.get()
            try:
                # Process the command using _execute_command_locked
                result = await self._execute_command_locked(iot_id, key, command)
                # Set the result on the future
                future.set_result(result)
            except Exception as ex:
                # Set the exception on the future if something goes wrong
                try:
                    future.set_exception(ex)
                except InvalidStateError:
                    """Dead end, log an error."""
                    _LOGGER.exception("InvalidStateError while trying to bubble up exception")
            finally:
                # Mark the task as done
                self.command_queue.task_done()

    async def _execute_command_locked(self, iot_id: str, key: str, command: bytes) -> None:
        """Execute command and read response."""
        assert self._mqtt_client is not None
        self._key = key
        _LOGGER.debug("Sending command: %s", key)
        self.command_sent_time = time.time()
        await self._mqtt_client.send_cloud_command(iot_id, command)

    async def _on_mqtt_message(self, topic: str, payload: bytes, iot_id: str) -> None:
        """Handle incoming MQTT messages."""
        # _LOGGER.debug("MQTT message received on topic %s: %s, iot_id: %s", topic, payload, iot_id)
        json_str = payload.decode("utf-8")
        dict_payload = json.loads(json_str)
        await self._parse_mqtt_response(topic, dict_payload, iot_id)

    async def _parse_mqtt_response(self, topic: str, payload: dict, iot_id: str) -> None:
        """Parse and handle MQTT responses based on the topic.

        This function processes different types of MQTT messages received from various
        topics. It logs debug information and calls appropriate callback methods for
        each event type.

        Args:
            topic (str): The MQTT topic from which the message was received.
            payload (dict): The payload data of the MQTT message.

        """
        if topic.endswith("/app/down/thing/events"):
            _LOGGER.debug("Thing event received")
            event = ThingEventMessage.from_dicts(payload)
            params = event.params
            if isinstance(params, dict) or params.identifier is None:
                _LOGGER.debug("Received dict params: %s", params)
                return
            if params.identifier == "device_protobuf_msg_event" and event.method == "thing.events":
                _LOGGER.debug("Protobuf event")
                # Call the callbacks for each cloudDevice
                await self.mqtt_message_event.data_event(event)
            if event.method == "thing.events":
                await self.mqtt_device_event.data_event(event)
            if event.method == "thing.properties":
                await self.mqtt_properties_event.data_event(event)
                _LOGGER.debug(event)
        elif topic.endswith("/app/down/thing/status"):
            status = ThingStatusMessage.from_dict(payload)
            await self.mqtt_status_event.data_event(status)
        elif topic.endswith("app/down/thing/properties"):
            property_event = ThingPropertiesMessage.from_dict(payload)
            await self.mqtt_properties_event.data_event(property_event)

        if topic.endswith("/thing/event/device_protobuf_msg_event/post"):
            _LOGGER.debug("Mammotion Thing event received")
            mammotion_event = MammotionEventMessage.from_dict(payload)
            mammotion_event.params.iot_id = iot_id
            await self.mqtt_message_event.data_event(mammotion_event)
        elif topic.endswith("/thing/event/property/post"):
            _LOGGER.debug("Mammotion Property event received")
            mammotion_property_event = MammotionPropertiesMessage.from_dict(payload)
            mammotion_property_event.params.iot_id = iot_id
            await self.mqtt_properties_event.data_event(mammotion_property_event)

    def _disconnect(self) -> None:
        """Disconnect the MQTT client."""
        self._mqtt_client.disconnect()

    @property
    def waiting_queue(self) -> deque:
        return self._waiting_queue


class MammotionBaseCloudDevice(MammotionBaseDevice):
    """Base class for Mammotion Cloud devices."""

    def __init__(self, mqtt: MammotionCloud, cloud_device: Device, state_manager: MowerStateManager) -> None:
        """Initialize MammotionBaseCloudDevice."""
        super().__init__(state_manager, cloud_device)
        self.stopped = False
        self.on_ready_callback: Callable[[], Awaitable[None]] | None = None
        self.loop = asyncio.get_event_loop()
        self._mqtt = mqtt
        self.iot_id = cloud_device.iot_id
        self.device = cloud_device
        self._command_futures = {}
        self._commands: MammotionCommand = MammotionCommand(
            cloud_device.device_name,
            int(mqtt.cloud_client.mammotion_http.response.data.userInformation.userAccount),
        )
        self.currentID = ""
        self._mqtt.mqtt_message_event.add_subscribers(self._parse_message_for_device)
        self._mqtt.mqtt_properties_event.add_subscribers(self._parse_message_properties_for_device)
        self._mqtt.mqtt_status_event.add_subscribers(self._parse_message_status_for_device)
        self._mqtt.mqtt_device_event.add_subscribers(self._parse_device_event_for_device)
        self._mqtt.on_ready_event.add_subscribers(self.on_ready)
        self._mqtt.on_disconnected_event.add_subscribers(self.on_disconnect)
        self._mqtt.on_connected_event.add_subscribers(self.on_connect)
        self.set_queue_callback(self.queue_command)

    def __del__(self) -> None:
        """Cleanup subscriptions."""
        self._mqtt.on_ready_event.remove_subscribers(self.on_ready)
        self._mqtt.on_disconnected_event.remove_subscribers(self.on_disconnect)
        self._mqtt.on_connected_event.remove_subscribers(self.on_connect)
        self._mqtt.mqtt_message_event.remove_subscribers(self._parse_message_for_device)
        self._mqtt.mqtt_properties_event.remove_subscribers(self._parse_message_properties_for_device)
        self._mqtt.mqtt_status_event.remove_subscribers(self._parse_message_status_for_device)
        self._mqtt.mqtt_device_event.remove_subscribers(self._parse_device_event_for_device)
        self._state_manager.cloud_queue_command_callback.remove_subscribers(self.queue_command)

    @property
    def command_sent_time(self) -> float:
        return self._mqtt.command_sent_time

    def set_notification_callback(self, func: Callable[[tuple[str, Any | None]], Awaitable[None]]) -> None:
        self._state_manager.cloud_on_notification_callback.add_subscribers(func)

    def set_queue_callback(self, func: Callable[[str, dict[str, Any]], Awaitable[None]]) -> None:
        self._state_manager.cloud_queue_command_callback.add_subscribers(func)

    async def on_ready(self) -> None:
        """Callback for when MQTT is subscribed to events."""
        if self.stopped:
            return
        try:
            if self.on_ready_callback:
                await self.on_ready_callback()
        except (DeviceOfflineException, UnretryableException):
            _LOGGER.debug("Device is offline")

    async def on_disconnect(self) -> None:
        self._mqtt.disconnect()

    async def on_connect(self) -> None:
        """On connect callback"""

    async def stop(self) -> None:
        """Stop all tasks and disconnect."""
        # self._mqtt._mqtt_client.unsubscribe()
        self.stopped = True

    async def start(self) -> None:
        """Start the device connection."""
        self.stopped = False
        if not self.mqtt.is_connected():
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.mqtt.connect_async)
        # else:
        #     self.mqtt._mqtt_client.thing_on_thing_enable(None)

    async def _ble_sync(self) -> None:
        pass

    async def queue_command(self, key: str, **kwargs: Any) -> None:
        # Create a future to hold the result
        _LOGGER.debug("Queueing command: %s", key)
        future = asyncio.Future()
        # Put the command in the queue as a tuple (key, command, future)
        command_bytes = getattr(self._commands, key)(**kwargs)
        await self._mqtt.command_queue.put((self.iot_id, key, command_bytes, future))
        # Wait for the future to be resolved
        try:
            await future
            return
        except asyncio.CancelledError:
            """Try again once."""
            future = asyncio.Future()
            await self._mqtt.command_queue.put((self.iot_id, key, command_bytes, future))

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

    @staticmethod
    def dequeue_by_iot_id(queue, iot_id):
        for item in queue:
            if item.iot_id == iot_id:
                queue.remove(item)
                return item
        return None

    async def _parse_message_properties_for_device(self, event: ThingPropertiesMessage) -> None:
        if event.params.iot_id != self.iot_id:
            return
        await self.state_manager.properties(event)

    async def _parse_message_status_for_device(self, status: ThingStatusMessage) -> None:
        if status.params.iot_id != self.iot_id:
            return
        await self.state_manager.status(status)

    async def _parse_device_event_for_device(self, status: ThingStatusMessage) -> None:
        """Process device event if it matches the device's IoT ID."""
        if status.params.iot_id != self.iot_id:
            return
        await self.state_manager.device_event(status)

    async def _parse_message_for_device(self, event: ThingEventMessage) -> None:
        """Parses a message received from a device and updates internal state.

        This function processes an incoming `ThingEventMessage`, checks if the message
        is intended for this device, decodes the binary data, and updates raw data. It
        then attempts to parse the binary data into a `LubaMsg`. If parsing fails, it
        logs the exception. The function also handles setting the device product key if
        not already set and processes specific sub-messages based on their types.

        Args:
            event (ThingEventMessage): The event message received from the device.

        """
        params = event.params
        new_msg = LubaMsg()
        if event.params.iot_id != self.iot_id:
            return
        binary_data = base64.b64decode(params.value.content)
        try:
            self._update_raw_data(binary_data)
            new_msg = LubaMsg().parse(binary_data)
        except (KeyError, ValueError, IndexError, UnicodeDecodeError):
            _LOGGER.exception("Error parsing message %s", binary_data)

        if (
            self._commands.get_device_product_key() == ""
            and self._commands.get_device_name() == event.params.device_name
        ):
            self._commands.set_device_product_key(event.params.product_key)

        res = betterproto2.which_one_of(new_msg, "LubaSubMsg")
        if res[0] == "net":
            if new_msg.net.todev_ble_sync != 0 or new_msg.net.toapp_wifi_iot_status is not None:
                return

        await self._state_manager.notification(new_msg)

    @property
    def mqtt(self):
        return self._mqtt
