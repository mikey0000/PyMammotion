"""AliyunMQTTTransport — concrete Transport for Aliyun IoT MQTT.

Differences from MQTTTransport (Mammotion direct MQTT):
- Credentials use HMAC-SHA1 signed client_id / password (Aliyun IoT convention).
- Topics have separate subscribe sets and a single publish topic.
- Incoming messages are JSON envelopes; the transport unwraps the
  ``params.value.content`` base64 field and forwards raw bytes to on_message.
- TLS uses a bundled Aliyun / GlobalSign CA bundle (port 8883).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
from dataclasses import dataclass
import hashlib
import hmac
from importlib.resources import files
import json
import logging
import ssl
import time
from typing import TYPE_CHECKING

import aiomqtt
from Tea.exceptions import UnretryableException

from pymammotion.data.mqtt.status import ThingStatusMessage
from pymammotion.transport.base import (
    ReLoginRequiredError,
    SessionExpiredError,
    Transport,
    TransportAvailability,
    TransportError,
    TransportRateLimitedError,
    TransportType,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
    from pymammotion.auth.token_manager import AliyunCredentials

_logger = logging.getLogger(__name__)
_CA_CERT_FILE = str(files("pymammotion.resources").joinpath("ca.pem"))

_MQTT_PORT = 8883
_MQTT_KEEPALIVE = 60
_MQTT_MAX_INFLIGHT = 20
_MQTT_MAX_QUEUED = 40
_MQTT_RECONNECT_MIN_SEC = 1
_MQTT_RECONNECT_MAX_SEC = 60

#: Messages with ``params.time`` older than this threshold (in milliseconds)
#: relative to the current wall clock are considered stale and dropped.  Aliyun
#: can buffer events during connectivity gaps; replaying minutes-old telemetry
#: causes state-machine glitches (ghost-mowing, stale battery values).
_STALE_EVENT_THRESHOLD_MS = 60_000


@dataclass(frozen=True)
class AliyunMQTTConfig:
    """Frozen configuration for an AliyunMQTTTransport instance.

    Attributes:
        host: Aliyun IoT MQTT broker hostname, e.g.
            ``"{productKey}.iot-as-mqtt.{region}.aliyuncs.com"``.
        client_id: Full Aliyun MQTT client ID (including securemode / signmethod
            suffix). Built once per connection attempt via
            :meth:`AliyunMQTTTransport._build_credentials`.
        username: Aliyun MQTT username in the form ``"{deviceName}&{productKey}"``.
        password: HMAC-SHA1 signed password derived from the device secret.
        device_name: Aliyun IoT device name.
        product_key: Aliyun IoT product key.
        device_secret: Device secret used to sign connection credentials.
        iot_token: Short-lived Aliyun IoT session token, sent in the bind message.
        port: MQTT broker port (default 8883 for TLS).
        keepalive: MQTT keepalive interval in seconds.

    """

    host: str
    client_id_base: str
    username: str
    device_name: str
    product_key: str
    device_secret: str
    iot_token: str
    port: int = _MQTT_PORT
    keepalive: int = _MQTT_KEEPALIVE

    @classmethod
    def from_aliyun_credentials(
        cls,
        region_id: str,
        product_key: str,
        device_name: str,
        device_secret: str,
        credentials: AliyunCredentials,
        client_id_base: str | None = None,
    ) -> AliyunMQTTConfig:
        """Build an AliyunMQTTConfig from AliyunCredentials.

        Args:
            region_id: Aliyun region, e.g. ``"cn-shanghai"``.
            product_key: Aliyun IoT product key.
            device_name: Aliyun IoT device name.
            device_secret: Device secret for HMAC signing.
            credentials: Current :class:`AliyunCredentials` from the token manager.
            client_id_base: Optional override for the base client ID; defaults to
                ``"{product_key}&{device_name}"``.

        Returns:
            A fully constructed :class:`AliyunMQTTConfig`.

        """
        base = client_id_base or f"{product_key}&{device_name}"
        return cls(
            host=f"{product_key}.iot-as-mqtt.{region_id}.aliyuncs.com",
            client_id_base=base,
            username=f"{device_name}&{product_key}",
            device_name=device_name,
            product_key=product_key,
            device_secret=device_secret,
            iot_token=credentials.iot_token,
        )


class AliyunMQTTTransport(Transport):
    """Concrete Transport for the Aliyun IoT MQTT platform.

    Separate subscribe and publish topics
    ------------------------------------
    Aliyun IoT uses a split topic model: the broker pushes data to
    ``/sys/{productKey}/{deviceName}/app/down/...`` topics, while commands
    are published to ``/sys/{productKey}/{deviceName}/app/up/...`` (or
    thing model topics).  Call :meth:`add_subscribe_topic` to register
    inbound topics and :meth:`set_publish_topic` to set the outbound topic.

    Envelope unwrapping
    -------------------
    Incoming JSON messages wrap the device payload in a base64-encoded
    ``params.value.content`` field.  The transport decodes this field and
    forwards the raw bytes to the ``on_message`` callback; the broker layer
    is responsible for protobuf decoding.

    Authentication
    --------------
    HMAC-SHA1 credentials are re-derived on every connection attempt so that
    the timestamp-embedded signature remains fresh.
    """

    on_message: Callable[[bytes], Awaitable[None]] | None = None
    on_device_message: Callable[[str, bytes], Awaitable[None]] | None = None
    on_fatal_auth_error: Callable[[ReLoginRequiredError], Awaitable[None]] | None = None

    def __init__(self, config: AliyunMQTTConfig, cloud_gateway: CloudIOTGateway) -> None:
        """Initialise the transport with the supplied Aliyun configuration."""
        super().__init__()
        self._config = config
        self._cloud_gateway = cloud_gateway
        self._iot_token: str = config.iot_token
        self._client: aiomqtt.Client | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._availability: TransportAvailability = TransportAvailability.DISCONNECTED
        self._subscribe_topics: list[str] = []

    # ------------------------------------------------------------------
    # Topic management
    # ------------------------------------------------------------------

    def add_subscribe_topic(self, topic: str) -> None:
        """Register a topic to subscribe to on (re)connect.

        Args:
            topic: Full MQTT topic string to subscribe to.

        """
        if topic not in self._subscribe_topics:
            self._subscribe_topics.append(topic)

    def update_iot_token(self, token: str) -> None:
        """Replace the Aliyun IoT session token used in the next bind message.

        Called by the auth-failure callback after a successful credential refresh
        so that the reconnect loop sends the updated token to the broker.
        """
        self._iot_token = token

    # ------------------------------------------------------------------
    # Transport ABC
    # ------------------------------------------------------------------

    @property
    def transport_type(self) -> TransportType:
        """Return TransportType.CLOUD_ALIYUN for this implementation."""
        return TransportType.CLOUD_ALIYUN

    @property
    def is_connected(self) -> bool:
        """True when the receive-loop task is running and the connection is established."""
        return (
            self._availability is TransportAvailability.CONNECTED and self._task is not None and not self._task.done()
        )

    @property
    def availability(self) -> TransportAvailability:
        """Current availability state of this transport."""
        return self._availability

    async def connect(self) -> None:
        """Start the Aliyun MQTT receive loop task.

        Does nothing if the task is already running (connected or in a retry-sleep).
        If the task has died unexpectedly it is restarted.
        """
        if self._task is not None and not self._task.done():
            _logger.debug(
                "AliyunMQTTTransport.connect() called while task is running (availability=%s) — ignoring",
                self._availability.value,
            )
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

    async def _invoke(self, payload: bytes, iot_id: str) -> None:
        """Send *payload* via the Aliyun cloud command API (shared by send/send_heartbeat)."""
        if not iot_id:
            msg = "AliyunMQTTTransport.send() requires a non-empty iot_id"
            raise TransportError(msg)
        try:
            await self._cloud_gateway.send_cloud_command(iot_id, payload)
        except UnretryableException as ex:
            self.record_error()
            raise TransportError(ex.message) from None
        except Exception:
            self.record_error()
            raise

    async def send(self, payload: bytes, iot_id: str = "") -> None:
        """Send *payload* to the device and count it against the 24-hour quota."""
        if self.is_rate_limited:
            remaining = self._rate_limited_until - time.monotonic()
            msg = f"AliyunMQTTTransport rate-limited for {remaining:.0f}s more"
            raise TransportRateLimitedError(msg)
        _logger.debug("Sending Aliyun MQTT payload: %s, %s", payload, iot_id)
        await self._invoke(payload, iot_id)
        self.record_send()

    async def send_heartbeat(self, payload: bytes, iot_id: str = "") -> None:
        """Send a keepalive heartbeat without counting it against the 24-hour quota."""
        _logger.debug("Sending Aliyun MQTT heartbeat %s", iot_id)
        await self._invoke(payload, iot_id)

    # ------------------------------------------------------------------
    # Credential helpers
    # ------------------------------------------------------------------

    def _build_credentials(self) -> tuple[str, str]:
        """Derive a fresh (client_id, password) pair stamped with the current time.

        Aliyun IoT requires a timestamp embedded in both the client ID suffix and
        the HMAC-SHA1 signed password so that stale credentials are rejected.

        Returns:
            A ``(client_id, password)`` tuple ready to pass to aiomqtt.Client.

        """
        timestamp = str(int(time.time()))
        client_id = f"{self._config.client_id_base}|securemode=2,signmethod=hmacsha1,ext=1,_ss=1,timestamp={timestamp}|"
        sign_content = (
            f"clientId{self._config.client_id_base}"
            f"deviceName{self._config.device_name}"
            f"productKey{self._config.product_key}"
            f"timestamp{timestamp}"
        )
        password = hmac.new(
            self._config.device_secret.encode("utf-8"),
            sign_content.encode("utf-8"),
            hashlib.sha1,
        ).hexdigest()
        return client_id, password

    def _default_subscribe_topics(self) -> list[str]:
        """Return the default set of Aliyun IoT subscribe topics for this device."""
        base = f"/sys/{self._config.product_key}/{self._config.device_name}"
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

    def _effective_subscribe_topics(self) -> list[str]:
        """Return subscribe topics, falling back to defaults if none are configured."""
        return self._subscribe_topics if self._subscribe_topics else self._default_subscribe_topics()

    # ------------------------------------------------------------------
    # Connection loop
    # ------------------------------------------------------------------

    async def _notify_availability(self, state: TransportAvailability) -> None:
        """Update internal state and notify all availability listeners."""
        self._availability = state
        await self._fire_availability_listeners(state)

    async def _handle_fatal_auth_error(self, exc: ReLoginRequiredError) -> None:
        """Mark the transport stopped, clean up state, and fire on_fatal_auth_error.

        State must be cleaned up here — before the callback fires — so that any
        downstream handler sees a consistent DISCONNECTED transport, not one that
        still appears connected while recovery is being attempted.
        """
        self._stop_event.set()
        self._client = None
        await self._notify_availability(TransportAvailability.DISCONNECTED)
        if self.on_fatal_auth_error is not None:
            with contextlib.suppress(Exception):
                await self.on_fatal_auth_error(exc)

    @staticmethod
    async def get_ssl_context() -> ssl.SSLContext:
        loop = asyncio.get_running_loop()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.options |= ssl.OP_IGNORE_UNEXPECTED_EOF
        # Offload the blocking disk I/O to a thread, but await it — otherwise the
        # context is returned half-loaded and the TLS handshake races the cert
        # load (any FileNotFoundError on _CA_CERT_FILE would also be lost).
        await loop.run_in_executor(None, context.load_verify_locations, _CA_CERT_FILE)
        return context

    async def _run(self) -> None:
        """Run the main Aliyun MQTT connection loop, reconnecting with exponential backoff."""
        backoff = _MQTT_RECONNECT_MIN_SEC

        _tls_context = await self.get_ssl_context()

        while not self._stop_event.is_set():
            await self._notify_availability(TransportAvailability.CONNECTING)
            client_id, password = self._build_credentials()
            try:
                async with aiomqtt.Client(
                    hostname=self._config.host,
                    port=self._config.port,
                    username=self._config.username,
                    password=password,
                    identifier=client_id,
                    keepalive=self._config.keepalive,
                    tls_context=_tls_context,
                    protocol=aiomqtt.ProtocolVersion.V311,
                    max_inflight_messages=_MQTT_MAX_INFLIGHT,
                    max_queued_incoming_messages=_MQTT_MAX_QUEUED,
                ) as client:
                    self._client = client
                    backoff = _MQTT_RECONNECT_MIN_SEC  # reset on successful connect
                    await self._notify_availability(TransportAvailability.CONNECTED)

                    for topic in self._effective_subscribe_topics():
                        await client.subscribe(topic, qos=1)

                    # Send the Aliyun IoT bind message to register the app client
                    bind_topic = f"/sys/{self._config.product_key}/{self._config.device_name}/app/up/account/bind"
                    await client.publish(
                        bind_topic,
                        json.dumps(
                            {
                                "id": "msgid1",
                                "version": "1.0",
                                "request": {"clientId": self._config.username},
                                "params": {"iotToken": self._iot_token},
                            }
                        ),
                        qos=1,
                    )

                    async for message in client.messages:
                        if self._stop_event.is_set():
                            break
                        topic = str(message.topic)
                        raw = bytes(message.payload)
                        if topic.endswith("/thing/status"):
                            await self._dispatch_device_status(topic, raw)
                        elif topic.endswith("/account/bind_reply"):
                            code = self._handle_bind_reply(raw)
                            if code == 2043:
                                raise SessionExpiredError(
                                    TransportType.CLOUD_ALIYUN,
                                    "Aliyun IoT token rejected by broker (bind_reply 2043) — token needs refresh",
                                )
                        elif topic.endswith(("/thing/events", "/thing/properties")):
                            await self._dispatch_aliyun_event(topic, raw)
                        else:
                            result = self._unwrap_envelope(topic, raw)
                            if result is not None:
                                decoded, iot_id = result
                                if iot_id and self.on_device_message is not None:
                                    await self.on_device_message(iot_id, decoded)
                                elif self.on_message is not None:
                                    await self.on_message(decoded)

            except aiomqtt.MqttCodeError as exc:
                rc = exc.rc
                if rc in (4, 5):
                    _logger.error("Aliyun MQTT auth refused (rc=%s): %s — attempting credential refresh", rc, exc)
                    if self.on_auth_failure is not None:
                        try:
                            if await self.on_auth_failure():
                                _logger.info("Aliyun credentials refreshed after auth failure — retrying")
                                continue
                        except ReLoginRequiredError as relogin_exc:
                            await self._handle_fatal_auth_error(relogin_exc)
                            raise
                        except Exception:
                            _logger.warning("on_auth_failure callback failed", exc_info=True)
                    fatal = ReLoginRequiredError("", f"Aliyun MQTT auth exhausted (rc={rc})")
                    await self._handle_fatal_auth_error(fatal)
                    raise fatal from exc
                _logger.warning("Aliyun MQTT error (rc=%s): %s — retry in %ds", rc, exc, backoff)
            except SessionExpiredError as exc:
                _logger.warning("Aliyun bind token expired — attempting credential refresh: %s", exc)
                if self.on_auth_failure is not None:
                    try:
                        if await self.on_auth_failure():
                            _logger.info("Aliyun credentials refreshed after bind token expiry — reconnecting")
                            continue
                    except ReLoginRequiredError as relogin_exc:
                        await self._handle_fatal_auth_error(relogin_exc)
                        raise
                    except Exception:
                        _logger.warning("on_auth_failure callback failed", exc_info=True)
                fatal = ReLoginRequiredError("", f"Aliyun bind token unrecoverable: {exc}")
                await self._handle_fatal_auth_error(fatal)
                raise fatal from exc
            except aiomqtt.MqttError as exc:
                _logger.debug("Aliyun MQTT disconnected: %s — retry in %ds", exc, backoff)
            except asyncio.CancelledError:
                break
            except OSError as exc:
                # Covers DNS failure (socket.gaierror), ENETUNREACHABLE, connection timeout,
                # and other network-layer errors that aiomqtt does not always wrap.
                _logger.warning("Aliyun MQTT network error: %s — retry in %ds", exc, backoff)
            finally:
                self._client = None
                if self._availability is not TransportAvailability.DISCONNECTED:
                    await self._notify_availability(TransportAvailability.DISCONNECTED)

            if not self._stop_event.is_set():
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    break
                backoff = min(backoff * 2, _MQTT_RECONNECT_MAX_SEC)

    # ------------------------------------------------------------------
    # Device status dispatch
    # ------------------------------------------------------------------

    async def _dispatch_device_status(self, topic: str, raw: bytes) -> None:
        """Parse a thing/status message and notify on_device_status.

        Uses :class:`~pymammotion.data.mqtt.status.ThingStatusMessage` to decode
        the envelope.  ``status`` passed to the callback is ``"online"`` when
        ``StatusType.CONNECTED`` and ``"offline"`` otherwise.
        """
        if self.on_device_status is None:
            return
        try:
            msg = ThingStatusMessage.from_json(raw)
            if msg.params.iot_id:
                await self.on_device_status(msg.params.iot_id, msg)
        except Exception:
            _logger.debug("AliyunMQTTTransport: failed to parse thing/status on %s", topic, exc_info=True)

    def _handle_bind_reply(self, raw: bytes) -> int:
        """Check the account bind reply and log an error if it failed."""
        code = 200
        try:
            parsed = json.loads(raw)
            code = parsed.get("code", 200)
            if code != 200:
                # (code=2043): {'code': 2043, 'id': 'msgid1', 'message': 'check iotToken failed'}
                _logger.error("Aliyun account bind failed (code=%s): %s", code, parsed)
        except Exception:  # noqa: BLE001
            _logger.debug("AliyunMQTTTransport: failed to parse bind_reply", exc_info=True)
        return code

    async def _dispatch_aliyun_event(self, topic: str, raw: bytes) -> None:
        """Dispatch a thing/events or thing/properties message.

        Protobuf events (identifier=device_protobuf_msg_event) are unwrapped and
        forwarded as raw bytes via on_device_message.  All other events are forwarded
        as typed objects via on_device_event (thing/events) or on_device_properties
        (thing/properties).

        Stale events are dropped: if ``params.time`` (Unix ms, cloud-side generation
        time) is more than ``_STALE_EVENT_THRESHOLD_MS`` behind the current wall
        clock, the message is logged and discarded.  This prevents buffered messages
        delivered after a connectivity gap from polluting device state.
        """
        # Non-protobuf: parse and forward typed event
        try:
            parsed = json.loads(raw)
            _logger.debug(parsed)
        except (json.JSONDecodeError, ValueError):
            return

        event_iot_id: str = parsed.get("params", {}).get("iotId", "")
        if not event_iot_id:
            return

        # Drop stale buffered messages using the cloud-side envelope timestamp.
        envelope_time_ms: int = parsed.get("params", {}).get("time", 0) or 0
        if envelope_time_ms > 0:
            now_ms = int(time.time() * 1000)
            age_ms = now_ms - envelope_time_ms
            if age_ms > _STALE_EVENT_THRESHOLD_MS:
                _logger.debug(
                    "AliyunMQTTTransport: dropping stale %s event (age=%dms, threshold=%dms)",
                    topic.rsplit("/", 1)[-1],
                    age_ms,
                    _STALE_EVENT_THRESHOLD_MS,
                )
                return

        if topic.endswith("/thing/events") and self.on_device_event is not None:
            try:
                from pymammotion.data.mqtt.event import ThingEventMessage

                event = ThingEventMessage.from_dicts(parsed)
                await self.on_device_event(event_iot_id, event)
            except Exception:  # noqa: BLE001
                _logger.debug("AliyunMQTTTransport: failed to parse thing/events on %s", topic, exc_info=True)
        elif topic.endswith("/thing/properties") and self.on_device_properties is not None:
            try:
                from pymammotion.data.mqtt.properties import ThingPropertiesMessage

                props = ThingPropertiesMessage.from_dict(parsed)
                await self.on_device_properties(event_iot_id, props)
            except Exception:  # noqa: BLE001
                _logger.debug("AliyunMQTTTransport: failed to parse thing/properties on %s", topic, exc_info=True)

    # ------------------------------------------------------------------
    # Envelope unwrapping
    # ------------------------------------------------------------------

    def _unwrap_envelope(self, topic: str, raw: bytes) -> tuple[bytes, str] | None:
        """Extract the base64-encoded protobuf payload and iot_id from an Aliyun IoT envelope.

        The Aliyun broker wraps device messages in a JSON envelope of the form::

            {
              "method": "thing.events",
              "params": {
                "iotId": "<device iot_id>",
                "identifier": "device_protobuf_msg_event",
                "value": {"content": "<base64-encoded protobuf>"},
                ...
              },
              ...
            }

        For Mammotion direct-MQTT events the path is::

            {
              "params": {"iotId": "<device iot_id>", "content": "<base64-encoded protobuf>"},
              ...
            }

        Both shapes are attempted.  If neither matches, the message is logged
        and *None* is returned so the caller can skip it.

        Args:
            topic: The MQTT topic the message arrived on (used for logging).
            raw: Raw bytes of the JSON envelope.

        Returns:
            ``(decoded_bytes, iot_id)`` tuple, or *None* if unwrapping fails.
            ``iot_id`` may be an empty string if the field is absent.

        """
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            _logger.debug("Non-JSON payload on topic %s, skipping", topic)
            return None

        iot_id: str = parsed.get("params", {}).get("iotId", "")

        # Aliyun thing.events shape: params.value.content
        try:
            content: str | None = parsed["params"]["value"]["content"]
            if content:
                return base64.b64decode(content), iot_id
        except (KeyError, TypeError):
            pass

        # Mammotion direct-MQTT event shape: params.content
        try:
            content = parsed["params"]["content"]
            if content:
                return base64.b64decode(content), iot_id
        except (KeyError, TypeError):
            pass

        _logger.debug("No base64 content field found in envelope on topic %s", topic)
        return None
