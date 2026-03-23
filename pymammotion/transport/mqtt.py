"""MQTTTransport — concrete Transport wrapping aiomqtt for Mammotion direct MQTT."""

from __future__ import annotations

import asyncio
import base64
import contextlib
from dataclasses import dataclass
import json
import logging
import ssl
from typing import TYPE_CHECKING

import aiomqtt

from pymammotion.transport.base import AuthError, Transport, TransportAvailability, TransportError, TransportType

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MQTTTransportConfig:
    """Frozen configuration for an MQTTTransport instance."""

    host: str
    client_id: str
    username: str
    password: str
    port: int = 1883
    use_ssl: bool = False
    keepalive: int = 60


class MQTTTransport(Transport):
    """Concrete Transport wrapping aiomqtt for Mammotion direct MQTT.

    A persistent receive loop task is started on connect() and cancelled on
    disconnect().  Incoming messages are forwarded to the on_message callback
    set by the broker layer.
    """

    on_message: Callable[[bytes], Awaitable[None]] | None = None
    on_device_message: Callable[[str, bytes], Awaitable[None]] | None = None

    def __init__(self, config: MQTTTransportConfig) -> None:
        """Initialise the transport with the supplied configuration."""
        self._config = config
        self._client: aiomqtt.Client | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._availability: TransportAvailability = TransportAvailability.DISCONNECTED
        self._topics: list[str] = []
        self._publish_topic: str | None = None
        # (product_key, device_name) → iot_id, used for per-device message routing
        self._device_to_iot: dict[tuple[str, str], str] = {}

    # ------------------------------------------------------------------
    # Public topic management
    # ------------------------------------------------------------------

    def add_topic(self, topic: str) -> None:
        """Register a topic to subscribe to on next (or current) connect."""
        if topic not in self._topics:
            self._topics.append(topic)

    def register_device(self, product_key: str, device_name: str, iot_id: str) -> None:
        """Map a (product_key, device_name) pair to an iot_id for message routing."""
        self._device_to_iot[(product_key, device_name)] = iot_id

    def set_publish_topic(self, topic: str) -> None:
        """Set the topic used for outgoing command publishes."""
        self._publish_topic = topic

    # ------------------------------------------------------------------
    # Transport ABC
    # ------------------------------------------------------------------

    @property
    def transport_type(self) -> TransportType:
        """Return the transport type for this implementation."""
        return TransportType.CLOUD_MAMMOTION

    @property
    def is_connected(self) -> bool:
        """True when the receive-loop task is running and not done."""
        return (
            self._availability is TransportAvailability.CONNECTED and self._task is not None and not self._task.done()
        )

    @property
    def availability(self) -> TransportAvailability:
        """Current availability state of this transport."""
        return self._availability

    async def connect(self) -> None:
        """Start the MQTT receive loop task.

        Raises TransportError if already connected or if starting the task
        fails immediately.
        """
        if self.is_connected:
            _logger.debug("MQTTTransport.connect() called while already connected — ignoring")
            return

        self._stop_event.clear()
        self._availability = TransportAvailability.CONNECTING
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run())

    async def disconnect(self) -> None:
        """Signal the receive loop to stop and wait for it to finish."""
        self._stop_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._availability = TransportAvailability.DISCONNECTED
        self._client = None

    async def send(self, payload: bytes) -> None:
        """Publish payload to the configured publish topic.

        Raises TransportError if the transport is not connected or no publish topic is set.
        """
        if not self.is_connected or self._client is None:
            msg = "MQTTTransport is not connected; cannot send payload"
            raise TransportError(msg)
        if self._publish_topic is None:
            msg = "No publish topic configured"
            raise TransportError(msg)
        await self._client.publish(self._publish_topic, payload)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Run the main connection loop, reconnecting with exponential backoff."""
        backoff = 1
        tls_context: ssl.SSLContext | None = None
        if self._config.use_ssl:
            tls_context = ssl.create_default_context()

        while not self._stop_event.is_set():
            try:
                async with aiomqtt.Client(
                    hostname=self._config.host,
                    port=self._config.port,
                    username=self._config.username,
                    password=self._config.password,
                    identifier=self._config.client_id,
                    keepalive=self._config.keepalive,
                    tls_context=tls_context,
                    protocol=aiomqtt.ProtocolVersion.V311,
                    clean_session=True,
                ) as client:
                    self._client = client
                    backoff = 1
                    self._availability = TransportAvailability.CONNECTED

                    for topic in self._topics:
                        await client.subscribe(topic)

                    async for message in client.messages:
                        if self._stop_event.is_set():
                            break
                        await self._dispatch(str(message.topic), bytes(message.payload))

            except aiomqtt.MqttCodeError as exc:
                rc = exc.rc
                if rc in (4, 5):
                    _logger.error(
                        "MQTT connection refused (rc=%s): %s — stopping reconnect (check credentials/token)",
                        rc,
                        exc,
                    )
                    self._stop_event.set()
                    raise AuthError(str(exc)) from exc
                _logger.warning("MQTT error (rc=%s): %s — retry in %ds", rc, exc, backoff)
            except aiomqtt.MqttError as exc:
                _logger.warning("MQTT disconnected: %s — retry in %ds", exc, backoff)
            except asyncio.CancelledError:
                break
            finally:
                self._client = None
                if self._availability is TransportAvailability.CONNECTED:
                    self._availability = TransportAvailability.DISCONNECTED

            if not self._stop_event.is_set():
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    break
                backoff = min(backoff * 2, 120)

    async def _dispatch(self, topic: str, raw: bytes) -> None:
        """Route an incoming message to the appropriate callback.

        If ``on_device_message`` is set, the topic is parsed to derive the
        iot_id, the JSON envelope is unwrapped, and the raw protobuf bytes
        are forwarded together with the iot_id.

        Falls back to the plain ``on_message`` callback (raw bytes, no routing)
        when ``on_device_message`` is not set.
        """
        if self.on_device_message is not None:
            # Extract (product_key, device_name) from topic: /sys/<pk>/<dn>/...
            parts = topic.split("/")
            if len(parts) >= 4:
                pk, dn = parts[2], parts[3]
                iot_id = self._device_to_iot.get((pk, dn))
                if iot_id:
                    decoded = self._unwrap_envelope(topic, raw)
                    if decoded is not None:
                        await self.on_device_message(iot_id, decoded)
                        return
            _logger.debug("MQTTTransport: could not route message on topic %s", topic)
            return

        if self.on_message is not None:
            await self.on_message(raw)

    @staticmethod
    def _unwrap_envelope(topic: str, raw: bytes) -> bytes | None:
        """Extract the base64-encoded protobuf payload from a Mammotion MQTT envelope.

        Handles two shapes::

            # Mammotion direct-MQTT event shape
            {"params": {"content": "<base64>"}}

            # Mammotion thing/event shape (nested under value)
            {"params": {"value": {"content": "<base64>"}}}
        """
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            _logger.debug("MQTTTransport: non-JSON payload on topic %s, skipping", topic)
            return None

        params = parsed.get("params", {})

        # Shape 1: params.value.content
        try:
            content: str | None = params["value"]["content"]
            if content:
                return base64.b64decode(content)
        except (KeyError, TypeError):
            pass

        # Shape 2: params.content
        try:
            content = params["content"]
            if content:
                return base64.b64decode(content)
        except (KeyError, TypeError):
            pass

        _logger.debug("MQTTTransport: no base64 content found on topic %s", topic)
        return None
