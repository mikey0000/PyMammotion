import asyncio
from asyncio import InvalidStateError, TimerHandle
import base64
from collections import deque
from collections.abc import Awaitable, Callable
import json
import logging
from typing import Any, cast

import betterproto
from Tea.exceptions import UnretryableException

from pymammotion import CloudIOTGateway, MammotionMQTT
from pymammotion.aliyun.cloud_gateway import CheckSessionException, DeviceOfflineException, SetupException
from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.mqtt.event import ThingEventMessage
from pymammotion.data.mqtt.properties import ThingPropertiesMessage
from pymammotion.data.mqtt.status import ThingStatusMessage
from pymammotion.data.state_manager import StateManager
from pymammotion.event.event import DataEvent
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.mammotion.devices.base import MammotionBaseDevice
from pymammotion.mqtt.mammotion_future import MammotionFuture
from pymammotion.proto import LubaMsg, has_field

_LOGGER = logging.getLogger(__name__)


class MammotionCloud:
    """Per account MQTT cloud."""

    def __init__(self, mqtt_client: MammotionMQTT, cloud_client: CloudIOTGateway) -> None:
        self.cloud_client = cloud_client
        self.loop = asyncio.get_event_loop()
        self.is_ready = False
        self.command_queue = asyncio.Queue()
        self._waiting_queue = deque()
        self.mqtt_message_event = DataEvent()
        self.mqtt_properties_event = DataEvent()
        self.mqtt_status_event = DataEvent()
        self.on_ready_event = DataEvent()
        self.on_disconnected_event = DataEvent()
        self.on_connected_event = DataEvent()
        self._operation_lock = asyncio.Lock()
        self._mqtt_client = mqtt_client
        self._mqtt_client.on_connected = self.on_connected
        self._mqtt_client.on_disconnected = self.on_disconnected
        self._mqtt_client.on_message = self._on_mqtt_message
        self._mqtt_client.on_ready = self.on_ready

        # temporary for testing only
        # self._start_sync_task = self.loop.call_later(30, lambda: asyncio.ensure_future(self.start_sync(0)))

    async def on_ready(self) -> None:
        loop = asyncio.get_event_loop()
        loop.create_task(self.process_queue())
        await self.on_ready_event.data_event(None)

    def is_connected(self) -> bool:
        return self._mqtt_client.is_connected

    def disconnect(self) -> None:
        self._mqtt_client.disconnect()

    def connect_async(self) -> None:
        self._mqtt_client.connect_async()

    def send_command(self, iot_id: str, command: bytes) -> None:
        self._mqtt_client.get_cloud_client().send_cloud_command(iot_id, command)

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

    async def _execute_command_locked(self, iot_id: str, key: str, command: bytes) -> bytes:
        """Execute command and read response."""
        assert self._mqtt_client is not None
        self._key = key
        _LOGGER.debug("Sending command: %s", key)

        await self.loop.run_in_executor(None, self._mqtt_client.get_cloud_client().send_cloud_command, iot_id, command)
        future = MammotionFuture(iot_id)
        self._waiting_queue.append(future)
        timeout = 5
        try:
            notify_msg = await future.async_get(timeout)
        except asyncio.TimeoutError:
            _LOGGER.debug("command_locked TimeoutError")
            notify_msg = b""

        _LOGGER.debug("%s: Message received", iot_id)

        return notify_msg

    async def _on_mqtt_message(self, topic: str, payload: str, iot_id: str) -> None:
        """Handle incoming MQTT messages."""
        _LOGGER.debug("MQTT message received on topic %s: %s, iot_id: %s", topic, payload, iot_id)

        json_str = json.dumps(payload)
        payload = json.loads(json_str)

        await self._parse_mqtt_response(topic, payload)

    async def _parse_mqtt_response(self, topic: str, payload: dict) -> None:
        """Parse the MQTT response."""
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
            if event.method == "thing.properties":
                await self.mqtt_properties_event.data_event(event)
                _LOGGER.debug(event)
        elif topic.endswith("/app/down/thing/status"):
            status = ThingStatusMessage.from_dict(payload)
            await self.mqtt_status_event.data_event(status)

    def _disconnect(self) -> None:
        """Disconnect the MQTT client."""
        self._mqtt_client.disconnect()

    @property
    def waiting_queue(self):
        return self._waiting_queue


class MammotionBaseCloudDevice(MammotionBaseDevice):
    """Base class for Mammotion Cloud devices."""

    def __init__(self, mqtt: MammotionCloud, cloud_device: Device, state_manager: StateManager) -> None:
        """Initialize MammotionBaseCloudDevice."""
        super().__init__(state_manager, cloud_device)
        self._ble_sync_task: TimerHandle | None = None
        self.stopped = False
        self.on_ready_callback: Callable[[], Awaitable[None]] | None = None
        self.loop = asyncio.get_event_loop()
        self._mqtt = mqtt
        self.iot_id = cloud_device.iotId
        self.device = cloud_device
        self._command_futures = {}
        self._commands: MammotionCommand = MammotionCommand(
            cloud_device.deviceName,
            int(mqtt.cloud_client.mammotion_http.response.data.get("userInformation").get("userAccount")),
        )
        self.currentID = ""
        self._mqtt.mqtt_message_event.add_subscribers(self._parse_message_for_device)
        self._mqtt.mqtt_properties_event.add_subscribers(self._parse_message_properties_for_device)
        self._mqtt.mqtt_status_event.add_subscribers(self._parse_message_status_for_device)
        self._mqtt.on_ready_event.add_subscribers(self.on_ready)
        self._mqtt.on_disconnected_event.add_subscribers(self.on_disconnect)
        self._mqtt.on_connected_event.add_subscribers(self.on_connect)
        self._state_manager.cloud_gethash_ack_callback = self.datahash_response
        self._state_manager.cloud_get_commondata_ack_callback = self.commdata_response
        self.set_queue_callback(self.queue_command)

        if self._mqtt.is_ready:
            self.run_periodic_sync_task()

    def __del__(self) -> None:
        self._mqtt.on_ready_event.remove_subscribers(self.on_ready)
        self._mqtt.on_disconnected_event.remove_subscribers(self.on_disconnect)
        self._mqtt.on_connected_event.remove_subscribers(self.on_connect)
        self._mqtt.mqtt_message_event.remove_subscribers(self._parse_message_for_device)
        self._state_manager.cloud_gethash_ack_callback = None
        self._state_manager.cloud_get_commondata_ack_callback = None
        if self._ble_sync_task:
            self._ble_sync_task.cancel()

    def set_notification_callback(self, func: Callable[[tuple[str, Any | None]], Awaitable[None]]) -> None:
        self._state_manager.cloud_on_notification_callback = func

    def set_queue_callback(self, func: Callable[[str, dict[str, Any]], Awaitable[bytes]]) -> None:
        self._state_manager.cloud_queue_command_callback = func

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
        if self._ble_sync_task:
            self._ble_sync_task.cancel()
        self._mqtt.disconnect()

    async def on_connect(self) -> None:
        await self._ble_sync()
        if self._ble_sync_task is None or self._ble_sync_task.cancelled():
            await self.run_periodic_sync_task()

    async def stop(self) -> None:
        """Stop all tasks and disconnect."""
        if self._ble_sync_task:
            self._ble_sync_task.cancel()
        # self._mqtt._mqtt_client.unsubscribe()
        self.stopped = True

    async def start(self) -> None:
        await self._ble_sync()
        if self._ble_sync_task is None or self._ble_sync_task.cancelled():
            await self.run_periodic_sync_task()
        self.stopped = False
        if not self.mqtt.is_connected():
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.mqtt.connect_async)
        # else:
        #     self.mqtt._mqtt_client.thing_on_thing_enable(None)

    async def _ble_sync(self) -> None:
        command_bytes = self._commands.send_todev_ble_sync(3)
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._mqtt.send_command, self.iot_id, command_bytes)
        except (CheckSessionException, SetupException):
            self._ble_sync_task.cancel()

    async def run_periodic_sync_task(self) -> None:
        """Send ble sync to robot."""
        try:
            if not self._mqtt._operation_lock.locked() or not self.stopped:
                await self._ble_sync()
        finally:
            if not self.stopped:
                self.schedule_ble_sync()

    def schedule_ble_sync(self) -> None:
        """Periodically sync to keep connection alive."""
        if self._mqtt is not None and self._mqtt.is_connected:
            self._ble_sync_task = self.loop.call_later(
                160, lambda: asyncio.ensure_future(self.run_periodic_sync_task())
            )

    async def queue_command(self, key: str, **kwargs: Any) -> bytes:
        # Create a future to hold the result
        _LOGGER.debug("Queueing command: %s", key)
        future = asyncio.Future()
        # Put the command in the queue as a tuple (key, command, future)
        command_bytes = getattr(self._commands, key)(**kwargs)
        await self._mqtt.command_queue.put((self.iot_id, key, command_bytes, future))
        # Wait for the future to be resolved
        try:
            return await future
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
        if event.params.iotId != self.iot_id:
            return
        self.state_manager.properties(event)

    async def _parse_message_status_for_device(self, status: ThingStatusMessage) -> None:
        if status.params.iotId != self.iot_id:
            return
        self.state_manager.status(status)

    async def _parse_message_for_device(self, event: ThingEventMessage) -> None:
        _LOGGER.debug("_parse_message_for_device")
        params = event.params
        new_msg = LubaMsg()
        if event.params.iotId != self.iot_id:
            return
        binary_data = base64.b64decode(params.value.content)
        try:
            self._update_raw_data(binary_data)
            new_msg = LubaMsg().parse(binary_data)
        except (KeyError, ValueError, IndexError, UnicodeDecodeError):
            _LOGGER.exception("Error parsing message %s", binary_data)

        if (
            self._commands.get_device_product_key() == ""
            and self._commands.get_device_name() == event.params.deviceName
        ):
            self._commands.set_device_product_key(event.params.productKey)

        if betterproto.serialized_on_wire(new_msg.net):
            if new_msg.net.todev_ble_sync != 0 or has_field(new_msg.net.toapp_wifi_iot_status):
                return

        await self._state_manager.notification(new_msg)

        if len(self._mqtt.waiting_queue) > 0:
            fut: MammotionFuture = self.dequeue_by_iot_id(self._mqtt.waiting_queue, self.iot_id)
            if fut is None:
                return
            while fut is None or fut.fut.cancelled() and len(self._mqtt.waiting_queue) > 0:
                fut = self.dequeue_by_iot_id(self._mqtt.waiting_queue, self.iot_id)
            if fut is not None and not fut.fut.cancelled():
                fut.resolve(cast(bytes, binary_data))

    @property
    def mqtt(self):
        return self._mqtt
