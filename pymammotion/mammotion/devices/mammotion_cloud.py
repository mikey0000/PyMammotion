import asyncio
import base64
import json
import logging
from asyncio import TimerHandle
from collections import deque
from typing import Any, Awaitable, Callable, Optional, cast

import betterproto

from pymammotion import CloudIOTGateway, MammotionMQTT
from pymammotion.aliyun.cloud_gateway import DeviceOfflineException, SetupException
from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.mqtt.event import ThingEventMessage
from pymammotion.event.event import DataEvent
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.mammotion.devices.base import MammotionBaseDevice
from pymammotion.mqtt.mammotion_future import MammotionFuture
from pymammotion.proto import has_field
from pymammotion.proto.luba_msg import LubaMsg

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
        self.on_ready_event = DataEvent()
        self.on_disconnected_event = DataEvent()
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
                future.set_exception(ex)
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
            notify_msg = b""

        _LOGGER.debug("%s: Message received", iot_id)

        return notify_msg

    async def _on_mqtt_message(self, topic: str, payload: str, iot_id: str) -> None:
        """Handle incoming MQTT messages."""
        _LOGGER.debug("MQTT message received on topic %s: %s, iot_id: %s", topic, payload, iot_id)

        json_str = json.dumps(payload)
        payload = json.loads(json_str)

        await self._handle_mqtt_message(topic, payload)

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
                _LOGGER.debug(event)

    async def _handle_mqtt_message(self, topic: str, payload: dict) -> None:
        """Async handler for incoming MQTT messages."""
        await self._parse_mqtt_response(topic=topic, payload=payload)

    def _disconnect(self) -> None:
        """Disconnect the MQTT client."""
        self._mqtt_client.disconnect()

    @property
    def waiting_queue(self):
        return self._waiting_queue


class MammotionBaseCloudDevice(MammotionBaseDevice):
    """Base class for Mammotion Cloud devices."""

    def __init__(self, mqtt: MammotionCloud, cloud_device: Device, mowing_state: MowingDevice) -> None:
        """Initialize MammotionBaseCloudDevice."""
        super().__init__(mowing_state, cloud_device)
        self._ble_sync_task: TimerHandle | None = None
        self.stopped = False
        self.on_ready_callback: Optional[Callable[[], Awaitable[None]]] = None
        self.loop = asyncio.get_event_loop()
        self._mqtt = mqtt
        self.iot_id = cloud_device.iotId
        self.device = cloud_device
        self._mower = mowing_state
        self._command_futures = {}
        self._commands: MammotionCommand = MammotionCommand(cloud_device.deviceName)
        self.currentID = ""
        self._mqtt.mqtt_message_event.add_subscribers(self._parse_message_for_device)
        self._mqtt.on_ready_event.add_subscribers(self.on_ready)
        self._mqtt.on_disconnected_event.add_subscribers(self.on_disconnect)
        self.set_queue_callback(self.queue_command)

        if self._mqtt.is_ready:
            self.run_periodic_sync_task()

    async def on_ready(self) -> None:
        """Callback for when MQTT is subscribed to events."""
        if self.stopped:
            return
        try:
            await self._ble_sync()
            if self._ble_sync_task is None or self._ble_sync_task.cancelled():
                await self.run_periodic_sync_task()
            if self.on_ready_callback:
                await self.on_ready_callback()
        except DeviceOfflineException:
            await self.stop()
        except SetupException:
            await self.stop()

    async def on_disconnect(self) -> None:
        if self._ble_sync_task:
            self._ble_sync_task.cancel()
        loop = asyncio.get_event_loop()
        self._mqtt.disconnect()
        await loop.run_in_executor(None, self._mqtt.cloud_client.sign_out)

    async def stop(self) -> None:
        """Stop all tasks and disconnect."""
        if self._ble_sync_task:
            self._ble_sync_task.cancel()
        self._mqtt.on_ready_event.remove_subscribers(self.on_ready)
        self.stopped = True

    async def _ble_sync(self) -> None:
        command_bytes = self._commands.send_todev_ble_sync(3)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._mqtt.send_command, self.iot_id, command_bytes)

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
        return await future

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

    async def _parse_message_for_device(self, event: ThingEventMessage) -> None:
        params = event.params
        if event.params.iotId != self.iot_id:
            return
        binary_data = base64.b64decode(params.value.content)
        self._update_raw_data(binary_data)
        new_msg = LubaMsg().parse(binary_data)

        if (
            self._commands.get_device_product_key() == ""
            and self._commands.get_device_name() == event.params.deviceName
        ):
            self._commands.set_device_product_key(event.params.productKey)

        if betterproto.serialized_on_wire(new_msg.net):
            if new_msg.net.todev_ble_sync != 0 or has_field(new_msg.net.toapp_wifi_iot_status):
                return

        if len(self._mqtt.waiting_queue) > 0:
            fut: MammotionFuture = self.dequeue_by_iot_id(self._mqtt.waiting_queue, self.iot_id)
            if fut is None:
                return
            while fut.fut.cancelled() and len(self._mqtt.waiting_queue) > 0:
                fut: MammotionFuture = self.dequeue_by_iot_id(self._mqtt.waiting_queue, self.iot_id)
            if not fut.fut.cancelled():
                fut.resolve(cast(bytes, binary_data))
        await self._state_manager.notification(new_msg)

    @property
    def mqtt(self):
        return self._mqtt
