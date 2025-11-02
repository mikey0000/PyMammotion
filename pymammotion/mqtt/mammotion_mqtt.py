import asyncio
from collections.abc import Awaitable, Callable
import json
import logging
import ssl
from typing import Any
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

from pymammotion import MammotionHTTP
from pymammotion.http.model.http import DeviceRecord, MQTTConnection, Response, UnauthorizedException
from pymammotion.utility.datatype_converter import DatatypeConverter

logger = logging.getLogger(__name__)


class MammotionMQTT:
    """Mammotion MQTT Client."""

    converter = DatatypeConverter()

    def __init__(
        self, mqtt_connection: MQTTConnection, mammotion_http: MammotionHTTP, records: list[DeviceRecord]
    ) -> None:
        self.on_connected: Callable[[], Awaitable[None]] | None = None
        self.on_ready: Callable[[], Awaitable[None]] | None = None
        self.on_error: Callable[[str], Awaitable[None]] | None = None
        self.on_disconnected: Callable[[], Awaitable[None]] | None = None
        self.on_message: Callable[[str, bytes, str], Awaitable[None]] | None = None
        self.loop = asyncio.get_running_loop()
        self.mammotion_http = mammotion_http
        self.mqtt_connection = mqtt_connection
        self.client = self.build(mqtt_connection)

        self.records = records

        # wire callbacks from the service object if present
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        # client.on_subscribe = getattr(mqtt_service_obj, "on_subscribe", None)
        # client.on_publish = getattr(mqtt_service_obj, "on_publish", None)

    def __del__(self) -> None:
        if self.client.is_connected():
            for record in self.records:
                self.unsubscribe_all(record.product_key, record.device_name)
            self.client.disconnect()

    def connect_async(self) -> None:
        """Connect async to MQTT Server."""
        if not self.client.is_connected():
            logger.info("Connecting...")
            self.client.connect_async(host=self.client.host, port=self.client.port, keepalive=self.client.keepalive)
            self.client.loop_start()

    def disconnect(self) -> None:
        """Disconnect from MQTT Server."""
        logger.info("Disconnecting...")
        self.client.disconnect()

    @staticmethod
    def build(mqtt_connection: MQTTConnection, keepalive: int = 60, timeout: int = 30) -> mqtt.Client:
        """get_jwt_response: object with attributes .client_id, .username, .jwt (password), .host (e.g. 'mqtts://broker:8883' or 'broker:1883' or 'broker').
        mqtt_service_obj: object that exposes callback methods (on_connect, on_message, on_disconnect, etc.)
        Returns: (client, connected_bool, rc)
        """
        host = mqtt_connection.host
        # Ensure urlparse can parse plain hosts
        parsed = urlparse(host if "://" in host else "tcp://" + host)
        scheme = parsed.scheme
        hostname = parsed.hostname
        port = parsed.port

        # decide TLS/ssl and default port
        use_ssl = scheme in ("mqtts", "ssl")
        if port is None:
            port = 8883 if use_ssl else 1883

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=mqtt_connection.client_id,
            clean_session=True,
            protocol=mqtt.MQTTv311,
        )

        client.username_pw_set(mqtt_connection.username, mqtt_connection.jwt)

        if use_ssl:
            # use system default CA certs; adjust tls_set() params if custom CA/client certs required
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            client.tls_insecure_set(False)

        # automatic reconnect backoff
        client.reconnect_delay_set(min_delay=1, max_delay=120)

        # connect (synchronous connect attempt) and start background loop
        if hostname:
            client.host = hostname
            client.port = port
            client.keepalive = keepalive

        return client

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        """Is called when message is received."""
        logger.debug("Message on topic %s", message.topic)
        logger.debug(message)

        if self.on_message is not None:
            iot_id = None
            # Parse the topic path to get product_key and device_name
            topic_parts = message.topic.split("/")
            if len(topic_parts) >= 4:
                product_key = topic_parts[2]
                device_name = topic_parts[3]

                # Filter records to find matching device
                filtered_records = [
                    record
                    for record in self.records
                    if record.product_key == product_key and record.device_name == device_name
                ]

                if filtered_records:
                    iot_id = filtered_records[0].iot_id
                    payload = json.loads(message.payload.decode("utf-8"))
                    payload["iot_id"] = iot_id
                    payload["product_key"] = product_key
                    payload["device_name"] = device_name
                    message.payload = json.dumps(payload).encode("utf-8")

            if iot_id:
                future = asyncio.run_coroutine_threadsafe(
                    self.on_message(message.topic, message.payload, iot_id), self.loop
                )
                asyncio.wrap_future(future, loop=self.loop)

    def _on_connect(
        self,
        _client: mqtt.Client,
        user_data: Any,
        session_flag: mqtt.ConnectFlags,
        rc: ReasonCode,
        properties: Properties | None,
    ) -> None:
        """Handle connection event and execute callback if set."""
        self.is_connected = True
        for record in self.records:
            self.subscribe_all(record.product_key, record.device_name)
        if self.on_connected is not None:
            future = asyncio.run_coroutine_threadsafe(self.on_connected(), self.loop)
            asyncio.wrap_future(future, loop=self.loop)

        if self.on_ready:
            self.is_ready = True
            future = asyncio.run_coroutine_threadsafe(self.on_ready(), self.loop)
            asyncio.wrap_future(future, loop=self.loop)

        logger.debug("on_connect, session_flag:%s, rc:%s", session_flag, rc)

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        user_data: Any | None,
        disconnect_flags: mqtt.DisconnectFlags,
        rc: ReasonCode,
        properties: Properties | None,
        **kwargs: Any,
    ) -> None:
        """Handle disconnection event and execute callback if set."""
        self.is_connected = False
        if self.on_disconnected is not None:
            for record in self.records:
                self.unsubscribe_all(record.product_key, record.device_name)
            future = asyncio.run_coroutine_threadsafe(self.on_disconnected(), self.loop)
            asyncio.wrap_future(future, loop=self.loop)

        logger.debug("on_disconnect, rc:%s", rc)

    def subscribe_all(self, product_key: str, device_name: str) -> None:
        """Subscribe to all topics for the given device."""

        # "/sys/" + this.$productKey + "/" + this.$deviceName + "/thing/event/+/post"
        # "/sys/proto/" + this.$productKey + "/" + this.$deviceName + "/thing/event/+/post"
        # "/sys/" + this.$productKey + "/" + this.$deviceName + "/app/down/thing/status"
        self.client.subscribe(f"/sys/{product_key}/{device_name}/app/down/thing/status")
        self.client.subscribe(f"/sys/{product_key}/{device_name}/thing/event/+/post")
        self.client.subscribe(f"/sys/proto/{product_key}/{device_name}/thing/event/+/post")

    def unsubscribe_all(self, product_key: str, device_name: str) -> None:
        """Unsubscribe from all topics for the given device."""
        self.client.unsubscribe(f"/sys/{product_key}/{device_name}/app/down/thing/status")
        self.client.unsubscribe(f"/sys/{product_key}/{device_name}/thing/event/+/post")
        self.client.unsubscribe(f"/sys/proto/{product_key}/{device_name}/thing/event/+/post")

    async def send_cloud_command(self, iot_id: str, command: bytes) -> str:
        """Send command to cloud."""
        res: Response[dict] = await self.mammotion_http.mqtt_invoke(
            self.converter.printBase64Binary(command), "", iot_id
        )

        logger.debug("send_cloud_command: %s", res)

        if res.code == 500:
            return res.msg

        if res.code == 401:
            raise UnauthorizedException(res.msg)

        return str(res.data["result"])
