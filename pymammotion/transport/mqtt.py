"""MQTTTransport — concrete Transport wrapping aiomqtt for Mammotion direct MQTT."""

from __future__ import annotations

import asyncio
import base64
import contextlib
from dataclasses import dataclass, replace
import json
import logging
import ssl
from typing import TYPE_CHECKING

import aiomqtt

from pymammotion.transport.base import AuthError, Transport, TransportAvailability, TransportError, TransportType

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.http.http import MammotionHTTP

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

    def __init__(
        self,
        config: MQTTTransportConfig,
        mammotion_http: MammotionHTTP,
        jwt_refresher: Callable[[], Awaitable[str]] | None = None,
    ) -> None:
        """Initialise the transport with the supplied configuration.

        Args:
            config: Frozen MQTT connection configuration.
            mammotion_http: HTTP client for the invoke API.
            jwt_refresher: Optional async callable that returns a fresh JWT password.
                           Called before each reconnect and on auth failure.
                           Specific to Mammotion direct-MQTT (post-2025 devices).

        """
        super().__init__()
        self._config = config
        self._http = mammotion_http
        self._jwt_refresher = jwt_refresher
        self._tls_context: ssl.SSLContext | None = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS) if config.use_ssl else None
        self._client: aiomqtt.Client | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._availability: TransportAvailability = TransportAvailability.DISCONNECTED
        self._topics: list[str] = []
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

    async def send(self, payload: bytes, iot_id: str = "") -> None:
        """Send *payload* to the device via the Mammotion HTTP invoke API.

        Args:
            payload: Raw protobuf bytes to send.
            iot_id: Mammotion IoT device identifier for the target device.

        Raises:
            TransportError: If iot_id is empty or the invoke call fails.
            AuthError: If the access token is expired (HTTP 401 or code 460).

        """
        from pymammotion.aliyun.exceptions import DeviceOfflineException, GatewayTimeoutException
        from pymammotion.http.model.http import UnauthorizedException

        if not iot_id:
            msg = "MQTTTransport.send() requires a non-empty iot_id"
            raise TransportError(msg)
        content = base64.b64encode(payload).decode()
        try:
            res = await self._http.mqtt_invoke(content, "", iot_id)
        except UnauthorizedException:
            _logger.warning("MQTTTransport.send: HTTP access token expired — refreshing and retrying")
            try:
                await self._http.refresh_login()
                res = await self._http.mqtt_invoke(content, "", iot_id)
            except Exception as refresh_exc:
                raise AuthError("Access token expired and refresh failed") from refresh_exc
        if res.code in (401, 460):
            raise AuthError(f"Access token expired (code={res.code})")
        if res.code in (6205, 50104):
            raise DeviceOfflineException(res.code, iot_id)
        if res.code == 20056:
            raise GatewayTimeoutException(res.code, iot_id)
        if res.code not in (0, 200):
            msg = f"mqtt_invoke failed: code={res.code} msg={res.msg} iot_id={iot_id}"
            raise TransportError(msg)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _notify_availability(self, state: TransportAvailability) -> None:
        """Update internal state and notify all availability listeners."""
        self._availability = state
        await self._fire_availability_listeners(state)

    async def _refresh_jwt(self) -> bool:
        """Attempt to refresh the JWT via the jwt_refresher callback.

        Returns True if credentials were refreshed, False otherwise.
        """
        if self._jwt_refresher is not None:
            try:
                new_jwt = await self._jwt_refresher()
                self._config = replace(self._config, password=new_jwt)
                _logger.debug("Mammotion MQTT JWT refreshed")
                return True
            except Exception:
                _logger.warning("JWT refresh failed", exc_info=True)
        if self.on_auth_failure is not None:
            try:
                return await self.on_auth_failure()
            except Exception:
                _logger.warning("on_auth_failure callback failed", exc_info=True)
        return False

    async def _run(self) -> None:
        """Run the main connection loop, reconnecting with exponential backoff."""
        backoff = 1
        _bad_credentials_attempts = 0
        _BAD_CREDENTIALS_MAX = 3

        while not self._stop_event.is_set():
            await self._notify_availability(TransportAvailability.CONNECTING)

            # Refresh JWT before each reconnect attempt (Mammotion MQTT only)
            if self._jwt_refresher is not None:
                try:
                    new_jwt = await self._jwt_refresher()
                    self._config = replace(self._config, password=new_jwt)
                except Exception:
                    _logger.warning("Pre-connect JWT refresh failed", exc_info=True)

            try:
                async with aiomqtt.Client(
                    hostname=self._config.host,
                    port=self._config.port,
                    username=self._config.username,
                    password=self._config.password,
                    identifier=self._config.client_id,
                    keepalive=self._config.keepalive,
                    tls_context=self._tls_context,
                    protocol=aiomqtt.ProtocolVersion.V311,
                    clean_session=True,
                ) as client:
                    self._client = client
                    backoff = 1
                    _bad_credentials_attempts = 0
                    await self._notify_availability(TransportAvailability.CONNECTED)

                    for topic in self._topics:
                        await client.subscribe(topic)

                    async for message in client.messages:
                        if self._stop_event.is_set():
                            break
                        await self._dispatch(str(message.topic), bytes(message.payload))

            except aiomqtt.MqttCodeError as exc:
                rc = exc.rc
                if rc == 134 or "bad user name" in str(exc).lower():
                    # rc=134 = Bad User Name or Password — JWT is expired/invalid
                    _bad_credentials_attempts += 1
                    if _bad_credentials_attempts <= _BAD_CREDENTIALS_MAX:
                        _logger.debug(
                            "MQTT rc=134 (bad credentials), JWT refresh attempt %d/%d",
                            _bad_credentials_attempts,
                            _BAD_CREDENTIALS_MAX,
                        )
                        if await self._refresh_jwt():
                            _bad_credentials_attempts = 0
                            continue
                    _logger.error(
                        "MQTT auth failed after %d JWT refresh attempt(s) — stopping",
                        _bad_credentials_attempts,
                    )
                    self._stop_event.set()
                    await self._notify_availability(TransportAvailability.DISCONNECTED)
                    raise AuthError(str(exc)) from exc
                if rc in (4, 5, 135) or "not authorized" in str(exc).lower():
                    _logger.error("MQTT auth refused (rc=%s): %s — attempting JWT refresh", rc, exc)
                    if await self._refresh_jwt():
                        _logger.debug("Credentials refreshed after auth failure — retrying")
                        continue
                    self._stop_event.set()
                    await self._notify_availability(TransportAvailability.DISCONNECTED)
                    raise AuthError(str(exc)) from exc
                _logger.warning("MQTT error (rc=%s): %s — retry in %ds", rc, exc, backoff)
            except aiomqtt.MqttError as exc:
                _logger.warning("MQTT disconnected: %s — retry in %ds", exc, backoff)
            except asyncio.CancelledError:
                break
            finally:
                self._client = None
                if self._availability is TransportAvailability.CONNECTED:
                    await self._notify_availability(TransportAvailability.DISCONNECTED)

            if not self._stop_event.is_set():
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    break
                backoff = min(backoff * 2, 120)

    async def _dispatch(self, topic: str, raw: bytes) -> None:
        """Route an incoming message to the appropriate callback.

        thing/status messages are dispatched to on_device_status regardless of
        which other callbacks are registered.

        If ``on_device_message`` is set, the topic is parsed to derive the
        iot_id, the JSON envelope is unwrapped, and the raw protobuf bytes
        are forwarded together with the iot_id.

        Falls back to the plain ``on_message`` callback (raw bytes, no routing)
        when ``on_device_message`` is not set.
        """
        if topic.endswith("/thing/status"):
            await self._dispatch_device_status(topic, raw)
            return

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

    async def _dispatch_device_status(self, topic: str, raw: bytes) -> None:
        """Parse a thing/status message and notify on_device_status."""
        if self.on_device_status is None:
            return
        try:
            from pymammotion.data.mqtt.status import StatusType, ThingStatusMessage

            msg = ThingStatusMessage.from_json(raw)
            iot_id = msg.params.iot_id
            status = "online" if msg.params.status.value is StatusType.CONNECTED else "offline"
            if iot_id:
                await self.on_device_status(iot_id, status)
        except Exception:
            _logger.debug("MQTTTransport: failed to parse thing/status on %s", topic, exc_info=True)

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
