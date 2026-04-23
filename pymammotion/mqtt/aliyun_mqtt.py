"""Aliyun IoT MQTT client for PyMammotion."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import hashlib
import hmac
from importlib.resources import files
import json
from logging import getLogger
import ssl
import time
from typing import TYPE_CHECKING

import aiomqtt

if TYPE_CHECKING:
    from pymammotion.aliyun.cloud_gateway import CloudIOTGateway

logger = getLogger(__name__)
_CA_CERT_FILE = str(files("pymammotion.resources").joinpath("ca.pem"))

_MQTT_PORT = 8883
_MQTT_KEEPALIVE = 60
_MQTT_MAX_INFLIGHT = 20
_MQTT_MAX_QUEUED = 40
_MQTT_RECONNECT_MIN_SEC = 1
_MQTT_RECONNECT_MAX_SEC = 60


class AliyunMQTT:
    """Async MQTT client for the Aliyun IoT platform.

    Handles Aliyun-specific credential format and topic structure using aiomqtt.
    Runs a persistent asyncio task that reconnects with exponential backoff on
    any connection error.
    """

    def __init__(
        self,
        region_id: str,
        product_key: str,
        device_name: str,
        device_secret: str,
        iot_token: str,
        cloud_client: CloudIOTGateway,
        client_id: str | None = None,
    ) -> None:
        self._cloud_client = cloud_client
        self._product_key = product_key
        self._device_name = device_name

        # Base client_id: "{product_key}&{device_name}" per Aliyun convention
        self._client_id_base = f"{product_key}&{device_name}" if client_id is None else client_id
        self._device_secret = device_secret
        self._mqtt_username = f"{device_name}&{product_key}"
        self._mqtt_host = f"{product_key}.iot-as-mqtt.{region_id}.aliyuncs.com"

        self.is_connected = False
        self.is_ready = False
        self.on_connected: Callable[[], Awaitable[None]] | None = None
        self.on_ready: Callable[[], Awaitable[None]] | None = None
        self.on_error: Callable[[str], Awaitable[None]] | None = None
        self.on_disconnected: Callable[[], Awaitable[None]] | None = None
        self.on_message: Callable[[str, bytes, str], Awaitable[None]] | None = None

        self._task: asyncio.Task[None] | None = None
        self._disconnect_requested = False
        self.loop = asyncio.get_running_loop()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def connect_async(self) -> None:
        """Schedule the connection loop on the event loop.

        Safe to call from any thread (including a thread-pool executor).
        Ignored if already connected or a connection task is already running.
        """
        if self.is_connected:
            logger.debug("connect_async called while already connected — ignoring")
            return
        self._disconnect_requested = False
        self.loop.call_soon_threadsafe(self._start_task)

    def disconnect(self) -> None:
        """Stop the connection loop and disconnect."""
        self._disconnect_requested = True
        if self._task is not None:
            self.loop.call_soon_threadsafe(self._task.cancel)

    @property
    def iot_token(self) -> str:
        """Return the current Aliyun IoT token from the cloud gateway session, or an empty string if unavailable."""
        if authcode_response := self._cloud_client.session_by_authcode_response.data:
            return authcode_response.iotToken
        return ""

    async def send_cloud_command(self, iot_id: str, command: bytes) -> str:
        """Send a command via the Aliyun cloud gateway."""
        return await self._cloud_client.send_cloud_command(iot_id, command)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_task(self) -> None:
        if self._task is None or self._task.done():
            self._task = self.loop.create_task(self._run())

    def _build_credentials(self) -> tuple[str, str]:
        """Return (client_id, password) stamped with the current timestamp."""
        timestamp = str(int(time.time()))
        client_id = f"{self._client_id_base}|securemode=2,signmethod=hmacsha1,ext=1,_ss=1,timestamp={timestamp}|"
        sign_content = (
            f"clientId{self._client_id_base}"
            f"deviceName{self._device_name}"
            f"productKey{self._product_key}"
            f"timestamp{timestamp}"
        )
        password = hmac.new(self._device_secret.encode("utf-8"), sign_content.encode("utf-8"), hashlib.sha1).hexdigest()
        return client_id, password

    def _subscription_topics(self) -> list[str]:
        base = f"/sys/{self._product_key}/{self._device_name}"
        return [
            f"{base}/app/down/account/bind_reply",
            f"{base}/app/down/thing/event/property/post_reply",
            f"{base}/app/down/thing/wifi/status/notify",
            f"{base}/app/down/thing/wifi/connect/event/notify",
            f"{base}/app/down/_thing/event/notify",
            f"{base}/app/down/thing/events",
            f"{base}/app/down/thing/status",
            f"{base}/app/down/thing/properties",
            f"{base}/app/down/thing/model/down_raw",
        ]

    # ------------------------------------------------------------------
    # Connection loop
    # ------------------------------------------------------------------

    @staticmethod
    async def get_ssl_context() -> ssl.SSLContext:
        loop = asyncio.get_running_loop()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.options |= ssl.OP_IGNORE_UNEXPECTED_EOF
        # Offload the blocking disk I/O to a separate thread
        loop.run_in_executor(None, context.load_verify_locations, _CA_CERT_FILE)
        return context

    async def _run(self) -> None:
        """Main connection loop — reconnects with exponential backoff."""
        backoff = _MQTT_RECONNECT_MIN_SEC
        _tls_context = await self.get_ssl_context()

        while not self._disconnect_requested:
            client_id, password = self._build_credentials()
            try:
                async with aiomqtt.Client(
                    hostname=self._mqtt_host,
                    port=_MQTT_PORT,
                    username=self._mqtt_username,
                    password=password,
                    identifier=client_id,
                    keepalive=_MQTT_KEEPALIVE,
                    tls_context=_tls_context,
                    protocol=aiomqtt.ProtocolVersion.V311,
                    max_inflight_messages=_MQTT_MAX_INFLIGHT,
                    max_queued_incoming_messages=_MQTT_MAX_QUEUED,
                ) as client:
                    backoff = _MQTT_RECONNECT_MIN_SEC  # reset on successful connect

                    for topic in self._subscription_topics():
                        await client.subscribe(topic, qos=1)

                    await client.publish(
                        f"/sys/{self._product_key}/{self._device_name}/app/up/account/bind",
                        json.dumps(
                            {
                                "id": "msgid1",
                                "version": "1.0",
                                "request": {"clientId": self._mqtt_username},
                                "params": {"iotToken": self.iot_token},
                            }
                        ),
                        qos=1,
                    )

                    self.is_connected = True
                    if self.on_connected is not None:
                        await self.on_connected()

                    self.is_ready = True
                    if self.on_ready is not None:
                        await self.on_ready()

                    async for message in client.messages:
                        if self._disconnect_requested:
                            break  # type: ignore[unreachable]
                        await self._dispatch(str(message.topic), message.payload)

            except aiomqtt.MqttCodeError as exc:
                rc = exc.rc
                if rc in (4, 5):
                    logger.error(
                        "MQTT connection refused (rc=%s): %s — stopping reconnect (check credentials/token)",
                        rc,
                        exc,
                    )
                    self._disconnect_requested = True
                    if self.on_error is not None:
                        await self.on_error(str(exc))
                else:
                    logger.warning("MQTT error (rc=%s): %s — retry in %ds", rc, exc, backoff)
            except aiomqtt.MqttError as exc:
                logger.warning("MQTT disconnected: %s — retry in %ds", exc, backoff)
            except asyncio.CancelledError:
                break
            finally:
                if self.is_connected or self.is_ready:
                    self.is_connected = False
                    self.is_ready = False
                    if self.on_disconnected is not None:
                        await self.on_disconnected()

            if not self._disconnect_requested:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MQTT_RECONNECT_MAX_SEC)

    async def _dispatch(self, topic: str, payload: bytes | bytearray | str | float | None) -> None:
        """Parse and route an incoming MQTT message."""
        logger.debug("Message on topic %s", topic)
        if isinstance(payload, (bytes, bytearray)):
            raw = bytes(payload)
        elif isinstance(payload, str):
            raw = payload.encode("utf-8")
        else:
            logger.warning("Unexpected payload type %s on topic %s, ignoring", type(payload), topic)
            return

        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Non-JSON payload on topic %s, ignoring", topic)
            return

        iot_id: str = parsed.get("params", {}).get("iotId", "")
        if iot_id and self.on_message is not None:
            await self.on_message(topic, raw, iot_id)
