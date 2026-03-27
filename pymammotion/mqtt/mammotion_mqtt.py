"""Direct (non-Aliyun-gateway) MQTT client for PyMammotion."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import json
import logging
import ssl
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import aiomqtt

from pymammotion.aliyun.exceptions import (
    CheckSessionException,
    DeviceOfflineException,
    FailedRequestException,
    GatewayTimeoutException,
    SetupException,
)
from pymammotion.http.model.http import DeviceRecord, MQTTConnection, UnauthorizedException
from pymammotion.utility.datatype_converter import DatatypeConverter

if TYPE_CHECKING:
    from pymammotion.http.http import MammotionHTTP

logger = logging.getLogger(__name__)


class MammotionMQTT:
    """Direct MQTT client using JWT credentials (bypasses Aliyun cloud gateway).

    Runs a persistent asyncio task that subscribes to all device topics and
    reconnects automatically on error.
    """

    def __init__(
        self,
        mqtt_connection: MQTTConnection,
        records: list[DeviceRecord],
        mammotion_http: MammotionHTTP | None = None,
    ) -> None:
        self.on_connected: Callable[[], Awaitable[None]] | None = None
        self.on_ready: Callable[[], Awaitable[None]] | None = None
        self.on_error: Callable[[str], Awaitable[None]] | None = None
        self.on_disconnected: Callable[[], Awaitable[None]] | None = None
        self.on_message: Callable[[str, bytes, str], Awaitable[None]] | None = None

        self.is_connected = False
        self.is_ready = False
        self.records = records

        self._mammotion_http = mammotion_http
        self._converter = DatatypeConverter()
        self._connection = mqtt_connection
        self._task: asyncio.Task[None] | None = None
        self._disconnect_requested = False
        self.loop = asyncio.get_running_loop()

        host = mqtt_connection.host
        parsed = urlparse(host if "://" in host else "tcp://" + host)
        self._use_ssl = parsed.scheme in ("mqtts", "ssl")
        self._hostname = parsed.hostname or host
        self._port = parsed.port or (8883 if self._use_ssl else 1883)

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
        """Stop the connection loop."""
        self._disconnect_requested = True
        if self._task is not None:
            self.loop.call_soon_threadsafe(self._task.cancel)

    def update_credentials(self, mqtt_connection: MQTTConnection) -> None:
        """Replace MQTT credentials so the next connect attempt uses fresh ones."""
        self._connection = mqtt_connection
        logger.debug("MammotionMQTT credentials updated")

    async def send_cloud_command(self, iot_id: str, command: bytes) -> str:
        """Send a command via the Mammotion HTTP API (mqtt_invoke)."""
        logger.debug("Sending cloud command to %s", iot_id)
        if self._mammotion_http is None:
            raise NotImplementedError("No MammotionHTTP instance provided; cannot send cloud commands.")
        res = await self._mammotion_http.mqtt_invoke(self._converter.printBase64Binary(command), "", iot_id)
        if res.code == 401:
            raise UnauthorizedException(res.msg)
        if res.code == 22000:
            raise FailedRequestException(iot_id)
        if res.code == 20056:
            logger.debug("Gateway timeout.")
            raise GatewayTimeoutException(res.code, iot_id)
        if res.code == 29003:
            raise SetupException(res.code, iot_id)
        if res.code == 6205:
            raise DeviceOfflineException(res.code, iot_id)
        if res.code in (6205, 50104, 460):
            logger.debug("token expired, must re-login.")
            raise CheckSessionException(res.data)
        if res.code != 0:
            raise Exception(f"Error sending cloud command: {res.msg}, {iot_id}")
        return str(res.data.get("result") if res.data is not None else "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_task(self) -> None:
        if self._task is None or self._task.done():
            self._task = self.loop.create_task(self._run())

    def _topics_for(self, product_key: str, device_name: str) -> list[str]:
        return [
            f"/sys/{product_key}/{device_name}/app/down/thing/status",
            f"/sys/{product_key}/{device_name}/thing/event/+/post",
            f"/sys/proto/{product_key}/{device_name}/thing/event/+/post",
        ]

    # ------------------------------------------------------------------
    # Connection loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Main connection loop — reconnects with exponential backoff."""
        backoff = 1
        tls_context: ssl.SSLContext | None = None
        if self._use_ssl:
            tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        while not self._disconnect_requested:
            try:
                async with aiomqtt.Client(
                    hostname=self._hostname,
                    port=self._port,
                    username=self._connection.username,
                    password=self._connection.jwt,
                    identifier=self._connection.client_id,
                    keepalive=60,
                    tls_context=tls_context,
                    protocol=aiomqtt.ProtocolVersion.V311,
                    clean_session=True,
                ) as client:
                    backoff = 1

                    for record in self.records:
                        for topic in self._topics_for(record.product_key, record.device_name):
                            await client.subscribe(topic)

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
                backoff = min(backoff * 2, 120)

    async def _dispatch(self, topic: str, payload: Any) -> None:
        """Enrich payload with iot_id derived from topic and route to handler."""
        logger.debug("Message on topic %s", topic)
        if isinstance(payload, (bytes, bytearray)):
            raw = bytes(payload)
        elif isinstance(payload, str):
            raw = payload.encode("utf-8")
        else:
            logger.warning("Unexpected payload type on topic %s, ignoring", topic)
            return

        iot_id: str | None = None
        topic_parts = topic.split("/")
        if len(topic_parts) >= 4:
            product_key = topic_parts[2]
            device_name = topic_parts[3]
            for record in self.records:
                if record.product_key == product_key and record.device_name == device_name:
                    iot_id = record.iot_id
                    try:
                        enriched = json.loads(raw)
                        enriched["iot_id"] = iot_id
                        enriched["product_key"] = product_key
                        enriched["device_name"] = device_name
                        raw = json.dumps(enriched).encode("utf-8")
                    except (json.JSONDecodeError, ValueError):
                        logger.warning("Non-JSON payload on topic %s, ignoring", topic)
                    break

        if iot_id and self.on_message is not None:
            logger.debug("Message sent from topic %s, %s iot_id=%s", topic, raw, iot_id)
            await self.on_message(topic, raw, iot_id)
