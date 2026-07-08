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
from urllib.parse import urlparse

from aiohttp import ClientConnectorDNSError
import aiomqtt
import jwt
from packaging.version import InvalidVersion, Version

from pymammotion.aliyun.exceptions import DeviceOfflineException, GatewayTimeoutException
from pymammotion.data.mqtt.properties import MammotionPropertiesMessage, ThingPropertiesMessage
from pymammotion.data.mqtt.status import MammotionStatusMessage, ThingStatusMessage
from pymammotion.http.model.http import UnauthorizedExceptionError
from pymammotion.transport.base import (
    AuthError,
    NoTransportAvailableError,
    ReLoginRequiredError,
    Transport,
    TransportAvailability,
    TransportError,
    TransportRateLimitedError,
    TransportType,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.auth.token_manager import MQTTCredentials, TokenManager
    from pymammotion.http.http import MammotionHTTP

_logger = logging.getLogger(__name__)

_MQTT_RECONNECT_MIN_SEC = 1
_MQTT_RECONNECT_MAX_SEC = 120
RATE_LIMIT_REMOVED_VERSION = Version("1.30.25.1")


def _jwt_claims_summary(token: str | None) -> str:
    """Return a non-sensitive summary of a broker JWT's claims for diagnostics.

    Decoded WITHOUT signature verification (we only want the claims for logging)
    and the token itself is never emitted.  Surfaces the fields that explain a
    broker "Not Authorized": ``clientId``/``username`` (must match the CONNECT),
    ``location`` (region the JWT is valid for), and ``iat``/``exp`` (expiry).
    """
    if not token:
        return "jwt=none"
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except Exception:  # noqa: BLE001 — diagnostics must never raise
        return "jwt=undecodable"
    attrs = claims.get("client_attrs") or {}
    return (
        f"jwt[clientId={claims.get('clientId', '?')} username={claims.get('username', '?')} "
        f"location={claims.get('location', '?')} identityId={attrs.get('identityId', '?')} "
        f"connectType={attrs.get('connectType', '?')} iat={claims.get('iat', '?')} exp={claims.get('exp', '?')}]"
    )


def _broker_identity_summary(config: MQTTTransportConfig) -> str:
    """Non-sensitive description of the identity the transport presented to the broker.

    Pairs the CONNECT params (host/client_id/username) with the JWT claims so a
    rejection is immediately diagnosable: a region mismatch (host vs jwt.location),
    a CONNECT/JWT identity mismatch (config.client_id vs jwt.clientId), an empty
    client_id, or an expired token.  The JWT/password itself is never logged.
    """
    return (
        f"host={config.host}:{config.port} client_id={config.client_id or '<empty>'} "
        f"username={config.username or '<empty>'} {_jwt_claims_summary(config.password)}"
    )


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

    # NOTE: on_message is deliberately NOT redeclared here — a class attribute would
    # shadow the base Transport.on_message property and defeat its receive-timestamping.
    on_device_message: Callable[[str, bytes], Awaitable[None]] | None = None
    #: Fired for ``/thing/event/{identifier}/post`` messages on the Mammotion MQTT.
    #: Called with (iot_id, identifier) — the identifier is the event name extracted
    #: from the topic path (e.g. ``"device_notification_event"``).
    on_device_notification: Callable[[str, str], Awaitable[None]] | None = None

    #: Fired when the connection loop exhausts JWT refresh attempts and gives up.
    #: The callback receives the underlying exception.  The client should trigger
    #: a full re-login and then call ``connect()`` again.
    on_fatal_auth_error: Callable[[Exception], Awaitable[None]] | None = None

    def __init__(
        self,
        config: MQTTTransportConfig,
        mammotion_http: MammotionHTTP,
        token_manager: TokenManager,
        creds_refresher: Callable[[bool], Awaitable[MQTTCredentials]] | None = None,
    ) -> None:
        """Initialise the transport with the supplied configuration.

        Args:
            config: Frozen MQTT connection configuration.
            mammotion_http: HTTP client for the invoke API.
            creds_refresher: Optional async callable ``(force: bool) -> MQTTCredentials``
                           returning a fresh credential set (host/client_id/username/jwt).
                           Called before each connect with ``force=False`` (routine —
                           refresh only if near expiry) and once after a broker auth
                           rejection with ``force=True`` (full refresh-token-based refresh).
                           Returns the full set — not just the JWT — because a fresh
                           login can rotate the client_id/username the broker binds the
                           JWT to.  Specific to Mammotion direct-MQTT (post-2025 devices).
            token_manager: Optional TokenManager used by send() to refresh the HTTP
                           bearer token via get_valid_http_token() rather than calling
                           refresh_login() directly.

        """
        super().__init__()
        self._config = config
        self._http = mammotion_http
        self._creds_refresher = creds_refresher
        self._token_manager = token_manager
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

    def update_credentials(self, creds: MQTTCredentials) -> None:
        """Replace the full MQTT credential set for the next connection attempt.

        Rotates password, host, client_id, and username together.  A full
        re-login (``login_v2``) can mint a new client_id/username bound to the new
        JWT; reconnecting with only a swapped password leaves the stale
        client_id/username and the broker rejects it as "Not Authorized".
        """
        self._apply_credentials(creds)

    def _apply_credentials(self, creds: MQTTCredentials) -> None:
        """Fold a freshly-minted credential set into ``self._config``.

        Re-derives host/port/use_ssl from ``creds.host`` exactly as
        :meth:`MammotionClient._setup_mammotion_transport` does at first connect,
        so a rebuilt config and a refreshed one stay identical.
        """
        parsed = urlparse(creds.host if "://" in creds.host else "tcp://" + creds.host)
        use_ssl = parsed.scheme in ("mqtts", "ssl")
        self._config = replace(
            self._config,
            host=parsed.hostname or creds.host,
            port=parsed.port or (8883 if use_ssl else 1883),
            use_ssl=use_ssl,
            client_id=creds.client_id,
            username=creds.username,
            password=creds.jwt,
        )
        if use_ssl and self._tls_context is None:
            self._tls_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS)
        self._stop_event.clear()

    async def add_topic(self, topic: str) -> None:
        """Register a topic to subscribe to on next (or current) connect.

        If the transport is already connected, subscribes immediately on the live
        client so that messages start arriving without waiting for a reconnect.
        """
        if topic not in self._topics:
            self._topics.append(topic)
            if self._client is not None:
                try:
                    await self._client.subscribe(topic)
                except Exception:
                    _logger.debug("add_topic: live subscribe failed (will retry on reconnect)", exc_info=True)

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

        Idempotent: does nothing if the task is already running (connected or
        in a retry-sleep). If the task has died unexpectedly it is restarted.
        Refuses to start once the re-login circuit breaker has tripped —
        otherwise queued ``call_soon(connect())`` callbacks from earlier
        ``_on_fatal_auth`` cycles would resurrect the loop indefinitely.
        """
        if self._unrecoverable_auth_failure:
            _logger.debug("MQTTTransport.connect() called after unrecoverable auth failure — refusing")
            return
        if self.is_connected:
            _logger.debug("MQTTTransport.connect() called while already connected — ignoring")
            return
        if self._task is not None and not self._task.done():
            _logger.debug(
                "MQTTTransport.connect() called while task is running (availability=%s) — ignoring",
                self._availability.value,
            )
            return

        self._stop_event.clear()
        _logger.debug(
            "MQTTTransport.connect(): spawning new _run task (transport=%s)",
            self.transport_type.value,
        )
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run())

    async def disconnect(self) -> None:
        """Signal the receive loop to stop and wait for it to finish."""
        _logger.debug(
            "MQTTTransport.disconnect(): state=%s, task_running=%s",
            self._availability.value,
            self._task is not None and not self._task.done(),
        )
        self._stop_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._client = None
        if self._availability is not TransportAvailability.DISCONNECTED:
            await self._notify_availability(TransportAvailability.DISCONNECTED)

    async def _fire_fatal_auth(self, exc: Exception) -> None:
        """Fire on_fatal_auth_error if registered, suppressing callback exceptions."""
        if self.on_fatal_auth_error is not None:
            with contextlib.suppress(Exception):
                await self.on_fatal_auth_error(exc)

    async def _give_up(self, exc: Exception) -> None:
        """Stop the receive loop and hand off to the fatal-auth handler.

        Used when Mammotion MQTT auth can't be recovered without a full re-login —
        which this transport never does.  The handler (``on_fatal_auth_error``)
        marks this transport unrecoverable and signals the affected mowers.
        """
        self._stop_event.set()
        self.mark_auth_failed()
        await self._fire_fatal_auth(exc)

    async def _invoke(self, payload: bytes, iot_id: str) -> None:
        """Invoke the Mammotion HTTP endpoint (shared by send/send_heartbeat)."""
        if not iot_id:
            msg = "MQTTTransport.send() requires a non-empty iot_id"
            raise TransportError(msg)
        content = base64.b64encode(payload).decode()
        try:
            res = await self._http.mqtt_invoke(content, "", iot_id)
        except ClientConnectorDNSError:
            raise TransportError("MQTTTransport.send: DNS lookup timed out") from None
        except UnauthorizedExceptionError:
            _logger.info("MQTTTransport.send: HTTP access token expired — refreshing invoke token (no re-login)")
            if self._token_manager is None:
                raise TransportError("Token manager not configured for MQTT transport") from None
            # Mammotion never re-logins (login_v2) on the send path — refresh the
            # invoke token via the refresh token only.  If that fails, give up.
            try:
                await self._token_manager.force_refresh_invoke_token(allow_relogin=False)
            except (ReLoginRequiredError, AuthError) as refresh_exc:
                await self._give_up(refresh_exc)
                raise NoTransportAvailableError(f"Mammotion MQTT auth unrecoverable: {refresh_exc}") from refresh_exc
            try:
                res = await self._http.mqtt_invoke(content, "", iot_id)
            except UnauthorizedExceptionError as exc:
                give_up_exc = ReLoginRequiredError(
                    self._token_manager.account_id, f"MQTT invoke still 401 after token refresh: {exc}"
                )
                await self._give_up(give_up_exc)
                raise NoTransportAvailableError(f"Mammotion MQTT auth unrecoverable: {give_up_exc}") from exc
            except Exception as retry_exc:
                raise AuthError(
                    f"Access token expired and retry failed after credential refresh {retry_exc}"
                ) from retry_exc
        if res.code in (401, 460):
            raise AuthError(f"Access token expired (code={res.code})")
        # 50103 / 50104 = MA_DEVICE_OFFLINE per the APK (AppConstants.java:279).
        # APK's MAIotManager.java:232-233 groups both codes under onDeviceIotOffLine.
        # 6205 is the legacy Aliyun "device not online" code.
        if res.code in (6205, 50103, 50104):
            raise DeviceOfflineException(res.code, iot_id)
        if res.code == 20056:
            raise GatewayTimeoutException(res.code, iot_id)
        if res.code not in (0, 200):
            msg = f"mqtt_invoke failed: code={res.code} msg={res.msg} iot_id={iot_id}"
            raise TransportError(msg)

    async def send(self, payload: bytes, iot_id: str = "", firmware_version: str = "1.0.0.0") -> None:
        """Send *payload* to the device and count it against the send quota."""
        if self.is_rate_limited and self._version_is_rate_limited(firmware_version):
            remaining = self.seconds_until_send_available()
            msg = f"MQTTTransport rate-limited for {remaining:.0f}s more"
            raise TransportRateLimitedError(msg)
        _logger.debug("Sending Mammotion MQTT payload: %s, %s iot_id", payload, iot_id)
        await self._invoke(payload, iot_id)
        self.record_send()

    async def send_heartbeat(self, payload: bytes, iot_id: str = "") -> None:
        """Send a keepalive heartbeat without counting it against the send quota."""
        await self._invoke(payload, iot_id)

    @staticmethod
    def _version_is_rate_limited(firmware_version: str) -> bool:
        """True when *firmware_version* predates the firmware that removed rate limiting.

        An unknown/unparseable version (e.g. "" before the first update-check frame)
        is treated as pre-removal so the rate-limit gate stays engaged rather than
        letting Version("") raise InvalidVersion out of the send path.
        """
        try:
            return Version(firmware_version) < RATE_LIMIT_REMOVED_VERSION
        except InvalidVersion:
            return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _notify_availability(self, state: TransportAvailability) -> None:
        """Update internal state and notify all availability listeners."""
        if self._availability is not state:
            _logger.debug(
                "MQTTTransport %s: %s -> %s",
                self.transport_type.value,
                self._availability.value,
                state.value,
            )
        self._availability = state
        await self._fire_availability_listeners(state)

    async def _refresh_credentials(self, *, force: bool) -> None:
        """Apply a fresh credential set from the creds_refresher.

        ``force=False`` is the routine pre-connect refresh (refresh only if near
        expiry); ``force=True`` is the post-auth-rejection full refresh.  Raises
        whatever the refresher raises (ReLoginRequiredError → give up; transient
        network errors → caller backs off).
        """
        if self._creds_refresher is None:
            return
        creds = await self._creds_refresher(force)
        self._apply_credentials(creds)

    async def _run(self) -> None:
        """Run the main connection loop.

        Auth recovery is deliberately minimal: on a broker auth rejection we force
        ONE full credential refresh (refresh-token based — never ``login_v2``) and
        retry; if the broker still rejects, we give up (``_give_up`` marks this
        transport unrecoverable and signals the affected mowers).  Non-auth
        disconnects reconnect with exponential backoff as usual.
        """
        backoff = _MQTT_RECONNECT_MIN_SEC
        auth_force_refreshed = False

        while not self._stop_event.is_set():
            await self._notify_availability(TransportAvailability.CONNECTING)

            # Routine pre-connect credential check (Mammotion MQTT only): refresh
            # only if near expiry — usually returns cached creds, no network call.
            try:
                await self._refresh_credentials(force=False)
            except ReLoginRequiredError as rle:
                _logger.error("Pre-connect credential refresh requires re-login — giving up: %s", rle)
                await self._give_up(rle)
                await self._notify_availability(TransportAvailability.DISCONNECTED)
                return
            except Exception:
                _logger.warning("Pre-connect credential refresh failed (transient?)", exc_info=True)

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
                    timeout=60,
                ) as client:
                    self._client = client
                    backoff = _MQTT_RECONNECT_MIN_SEC
                    auth_force_refreshed = False
                    await self._notify_availability(TransportAvailability.CONNECTED)

                    for topic in self._topics:
                        await client.subscribe(topic)

                    async for message in client.messages:
                        if self._stop_event.is_set():
                            break
                        await self._dispatch(str(message.topic), bytes(message.payload))

            except aiomqtt.MqttCodeError as exc:
                rc = exc.rc
                exc_str = str(exc).lower()
                # rc=4/134 = Bad User Name or Password (MQTT 3.1.1 / 5.0)
                # rc=5/135 = Not Authorized (MQTT 3.1.1 / 5.0)
                is_auth_failure = rc in (4, 5, 134, 135) or "bad user name" in exc_str or "not authorized" in exc_str
                if is_auth_failure:
                    if not auth_force_refreshed and self._creds_refresher is not None:
                        _logger.warning(
                            "MQTT broker rejected auth (rc=%s) — forcing full credential refresh [%s]",
                            rc,
                            _broker_identity_summary(self._config),
                        )
                        try:
                            await self._refresh_credentials(force=True)
                        except ReLoginRequiredError as rle:
                            _logger.error(
                                "MQTT credential refresh requires re-login — giving up on %s: %s",
                                self.transport_type.value,
                                rle,
                            )
                            await self._give_up(rle)
                            return
                        except Exception:
                            # Transient refresh failure (network) — back off and
                            # retry without giving up.
                            _logger.warning("Forced credential refresh failed (transient?)", exc_info=True)
                        else:
                            # Retry once, immediately, with the refreshed credentials.
                            auth_force_refreshed = True
                            continue
                    else:
                        # Already force-refreshed this cycle and the broker still
                        # rejects — the credentials are genuinely bad; give up.
                        _logger.error(
                            "MQTT auth still rejected after full credential refresh (rc=%s) — giving up on %s [%s]",
                            rc,
                            self.transport_type.value,
                            _broker_identity_summary(self._config),
                        )
                        auth_exc = ReLoginRequiredError(
                            self._token_manager.account_id,
                            f"MQTT auth rejected after full credential refresh (rc={rc})",
                        )
                        await self._give_up(auth_exc)
                        return
                else:
                    _logger.warning("MQTT error (rc=%s): %s — retry in %ds", rc, exc, backoff)
            except ReLoginRequiredError as exc:
                _logger.error("Re-login required during MQTT connection loop — giving up: %s", exc)
                await self._give_up(exc)
                return
            except aiomqtt.MqttError as exc:
                _logger.warning("MQTT disconnected: %s — retry in %ds", exc, backoff)
            except asyncio.CancelledError:
                break
            except Exception:
                # Catch-all so an unexpected error (TLS handshake, aiomqtt
                # internal RuntimeError, etc.) cannot silently kill the receive
                # loop and leave the transport wedged in CONNECTING forever.
                _logger.exception(
                    "MQTTTransport %s: unexpected error in _run — retry in %ds",
                    self.transport_type.value,
                    backoff,
                )
            finally:
                self._client = None
                await self._notify_availability(TransportAvailability.DISCONNECTED)

            if not self._stop_event.is_set():
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    break
                backoff = min(backoff * 2, _MQTT_RECONNECT_MAX_SEC)

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
        self._mark_received()
        if topic.endswith("/thing/status"):
            await self._dispatch_device_status(topic, raw)
            return

        if topic.endswith("/thing/properties"):
            await self._dispatch_device_properties(topic, raw)
            return

        if topic.endswith("/property/post"):
            await self._dispatch_mammotion_properties(topic, raw)
            return

        if "/thing/event/" in topic and topic.endswith("/post"):
            await self._dispatch_mammotion_event(topic, raw)
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
            _logger.debug("MQTTTransport: could not route message on topic %s: %s", topic, raw)
            return

        if self.on_message is not None:
            await self.on_message(raw)

    async def _dispatch_device_status(self, topic: str, raw: bytes) -> None:
        """Parse a thing/status message and notify on_device_status.

        Handles two formats:

        * **Aliyun** — ``{"method":"thing.status","params":{...},"version":"1.0"}``
        * **Mammotion MQTT** — ``{"action":"online","iotId":"...","productKey":"..."}``
        """
        if self.on_device_status is None:
            return
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            _logger.debug("MQTTTransport: non-JSON thing/status on %s: %s", topic, raw)
            return
        try:
            if "action" in parsed:
                msg = MammotionStatusMessage.from_dict(parsed).to_thing_status()
            else:
                msg = ThingStatusMessage.from_dict(parsed)
            if msg.params.iot_id:
                await self.on_device_status(msg.params.iot_id, msg)
        except Exception:
            _logger.debug("MQTTTransport: failed to parse thing/status on %s: %s", topic, raw, exc_info=True)

    async def _dispatch_device_properties(self, topic: str, raw: bytes) -> None:
        """Parse a thing/properties message and notify on_device_properties."""
        if self.on_device_properties is None:
            return
        try:
            props = ThingPropertiesMessage.from_json(raw)
            if props.params.iot_id:
                await self.on_device_properties(props.params.iot_id, props)
        except Exception:  # noqa: BLE001
            _logger.debug("MQTTTransport: failed to parse thing/properties on %s", topic, exc_info=True)

    async def _dispatch_mammotion_properties(self, topic: str, raw: bytes) -> None:
        """Parse a Mammotion MQTT flat property/post message and notify on_device_mammotion_properties."""
        if self.on_device_mammotion_properties is None:
            return
        parts = topic.split("/")
        if len(parts) < 4:
            return
        pk, dn = parts[2], parts[3]
        iot_id = self._device_to_iot.get((pk, dn))
        if not iot_id:
            _logger.debug("MQTTTransport: no iot_id for property/post on %s", topic)
            return
        try:
            msg = MammotionPropertiesMessage.from_json(raw)
            await self.on_device_mammotion_properties(iot_id, msg)
        except Exception:
            _logger.debug("MQTTTransport: failed to parse property/post on %s: %s", topic, raw, exc_info=True)

    async def _dispatch_mammotion_event(self, topic: str, raw: bytes) -> None:
        """Dispatch a Mammotion direct-MQTT thing/event/{identifier}/post message.

        Topic structure: /sys/{product_key}/{device_name}/thing/event/{identifier}/post

        ``device_protobuf_msg_event`` carries a base64-encoded LubaMsg and is
        forwarded to ``on_device_message`` exactly like a raw protobuf delivery.
        All other identifiers (notification, warning-code, information, …) are
        passed to ``on_device_notification`` so the client can react (e.g. by
        refreshing the report config).
        """
        parts = topic.split("/")
        # parts: ['', 'sys', pk, dn, 'thing', 'event', identifier, 'post']
        if len(parts) < 8:
            _logger.debug("MQTTTransport: malformed thing/event topic %s", topic)
            return
        pk, dn, identifier = parts[2], parts[3], parts[6]
        iot_id = self._device_to_iot.get((pk, dn))
        if not iot_id:
            _logger.debug("MQTTTransport: no iot_id for thing/event on %s", topic)
            return

        if identifier == "device_protobuf_msg_event":
            decoded = self._unwrap_envelope(topic, raw)
            if decoded is not None and self.on_device_message is not None:
                await self.on_device_message(iot_id, decoded)
            else:
                _logger.debug("MQTTTransport: could not unwrap protobuf on %s", topic)
            return

        if self.on_device_notification is not None:
            await self.on_device_notification(iot_id, identifier)

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
