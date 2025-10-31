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
from pymammotion.http.model.http import MQTTConnection, Response

logger = logging.getLogger(__name__)


class MammotionMQTT:
    def __init__(
        self, mqtt_connection: MQTTConnection, mammotion_http: MammotionHTTP, product_key: str, device_name: str
    ) -> None:
        self.on_connected: Callable[[], Awaitable[None]] | None = None
        self.on_ready: Callable[[], Awaitable[None]] | None = None
        self.on_error: Callable[[str], Awaitable[None]] | None = None
        self.on_disconnected: Callable[[], Awaitable[None]] | None = None
        self.on_message: Callable[[str, str, str], Awaitable[None]] | None = None
        self.loop = asyncio.get_running_loop()
        self.mammotion_http = mammotion_http
        self.mqtt_connection = mqtt_connection
        self.client = self.build(mqtt_connection)

        self.device_name = device_name
        self.product_key = product_key

        # wire callbacks from the service object if present
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        # client.on_subscribe = getattr(mqtt_service_obj, "on_subscribe", None)
        # client.on_publish = getattr(mqtt_service_obj, "on_publish", None)

    def __del__(self) -> None:
        if self.client.is_connected():
            self.unsubscribe_all(self.product_key, self.device_name)
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
        json_payload = json.loads(message.payload)

        iot_id = json_payload.get("params", {}).get("iotId", "")
        if iot_id != "" and self.on_message is not None:
            future = asyncio.run_coroutine_threadsafe(
                self.on_message(message.topic, str(message.payload), iot_id), self.loop
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
        if self.on_connected is not None:
            self.subscribe_all(self.product_key, self.device_name)
            future = asyncio.run_coroutine_threadsafe(self.on_connected(), self.loop)
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
            self.unsubscribe_all(self.product_key, self.device_name)
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
        res: Response[dict] = await self.mammotion_http.mqtt_invoke(str(command), "", iot_id)

        return str(res.data["result"])
