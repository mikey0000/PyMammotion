"""Token and credential management for PyMammotion accounts."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import time
from typing import TYPE_CHECKING

import jwt

from pymammotion.aliyun.exceptions import AuthRefreshException, LoginException
from pymammotion.http.model.http import MQTTConnection, UnauthorizedExceptionError
from pymammotion.transport import AuthError
from pymammotion.transport.base import (
    ReLoginRequiredError,
    SessionExpiredError,
    TransportType,
    is_transient_network_error,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
    from pymammotion.device.handle import DeviceHandle
    from pymammotion.http.http import MammotionHTTP
    from pymammotion.transport.base import Subscription


@dataclass(frozen=True)
class HTTPCredentials:
    """Immutable snapshot of an HTTP OAuth access/refresh token pair.

    Attributes:
        access_token: The short-lived bearer token used in API requests.
        refresh_token: The long-lived token used to obtain a new access token.
        expires_at: Unix timestamp (seconds) at which the access token expires.

    """

    access_token: str
    refresh_token: str
    expires_at: float


@dataclass(frozen=True)
class AliyunCredentials:
    """Immutable snapshot of Aliyun IoT session credentials.

    Attributes:
        iot_token: Short-lived Aliyun IoT session token.
        iot_token_expires_at: Unix timestamp when *iot_token* expires.
        refresh_token: Long-lived token used to refresh the IoT session.
        refresh_token_expires_at: Unix timestamp when *refresh_token* expires.

    """

    iot_token: str
    iot_token_expires_at: float
    refresh_token: str
    refresh_token_expires_at: float


# Fallback lifetime when an MQTT JWT carries no readable ``exp`` claim.
_MQTT_JWT_DEFAULT_TTL = 86400.0


def _jwt_expiry(token: str, default_ttl: float = _MQTT_JWT_DEFAULT_TTL) -> float:
    """Return the absolute expiry (unix seconds) from a JWT's ``exp`` claim.

    The signature is *not* verified — only the public ``exp`` claim is read, so
    the proactive-refresh window can track the broker's actual JWT lifetime
    rather than assuming a fixed 24 h.  Falls back to ``now + default_ttl`` when
    the token has no ``exp`` claim or cannot be decoded.
    """
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except Exception:  # noqa: BLE001 - malformed/opaque token → use the fallback TTL
        return time.time() + default_ttl
    exp = claims.get("exp") if isinstance(claims, dict) else None
    return float(exp) if exp is not None else time.time() + default_ttl


@dataclass(frozen=True)
class MQTTCredentials:
    """Immutable snapshot of Mammotion MQTT broker credentials.

    Attributes:
        host: MQTT broker hostname.
        client_id: Unique client identifier for this connection.
        username: MQTT username.
        jwt: JSON Web Token used as the MQTT password.
        expires_at: Unix timestamp after which the JWT should be refreshed.

    """

    host: str
    client_id: str
    username: str
    jwt: str
    expires_at: float


class TokenManager:
    """Manages all credentials for one account with proactive refresh and mutex safety.

    All three credential types (HTTP JWT, Aliyun IoT token, Mammotion MQTT JWT)
    are refreshed proactively before they expire. A single asyncio.Lock prevents
    concurrent refresh races. ReLoginRequiredError is raised only when recovery
    is impossible (refresh token itself expired or 401 on refresh).
    """

    _ALIYUN_FAILURE_WINDOW: float = 120.0  # seconds
    _ALIYUN_FAILURE_LIMIT: int = 2

    def __init__(
        self,
        account_id: str,
        mammotion_http: MammotionHTTP,
        cloud_gateway: CloudIOTGateway | None = None,
    ) -> None:
        """Create a TokenManager for a single account.

        Args:
            account_id: An identifier for the account being managed (e.g. email address).
            mammotion_http: An authenticated :class:`MammotionHTTP` instance.
            cloud_gateway: Optional :class:`CloudIOTGateway` for Aliyun IoT credentials.

        """
        self._account_id = account_id
        self._http: MammotionHTTP = mammotion_http
        self._cloud_gateway: CloudIOTGateway | None = cloud_gateway
        self._http_creds: HTTPCredentials | None = None
        self._aliyun_creds: AliyunCredentials | None = None
        self._mqtt_creds: MQTTCredentials | None = None
        self._lock: asyncio.Lock = asyncio.Lock()
        # Called with the fresh iotToken whenever _aliyun_creds is updated, so the
        # AliyunMQTTTransport's bind token stays current without waiting for a bind failure.
        self.on_aliyun_token_refreshed: Callable[[str], None] | None = None
        #: Fired (async) after any credential type is successfully refreshed.
        #: Integrations can wire this to persist the updated token cache.
        self.on_credentials_updated: Callable[[], Awaitable[None]] | None = None
        # Monotonic timestamps of recent 2401 "refreshToken invalid" failures.
        # _ALIYUN_FAILURE_LIMIT failures within _ALIYUN_FAILURE_WINDOW seconds → ReLoginRequiredError.
        self._aliyun_refresh_failures: list[float] = []
        # Monotonic timestamp of the last failed force_refresh_invoke_token() call.
        # Callers that hit the 30 s cooldown window get an immediate ReLoginRequiredError
        # rather than hammering the auth server on every queued command.
        self._invoke_refresh_failed_at: float | None = None
        # RAII subscriptions to device handle error buses — kept alive here so they
        # are never garbage-collected while this token manager is active.
        self._handle_subscriptions: list[Subscription] = []

    @property
    def http(self) -> MammotionHTTP:
        """The MammotionHTTP this manager refreshes tokens on.

        Exposed so wiring code can assert a transport and its TokenManager share one
        login session (see ``MammotionClient._setup_mammotion_transport``): a refresh
        only reaches ``mqtt_invoke`` when both read/write the same instance.
        """
        return self._http

    async def initialize(
        self,
        http_creds: HTTPCredentials | None,
        aliyun_creds: AliyunCredentials | None,
        mqtt_creds: MQTTCredentials | None,
    ) -> None:
        """Seed credentials from an existing login — used in tests and cache-restore paths.

        Args:
            http_creds: HTTP OAuth credentials, or *None* to force a refresh on first use.
            aliyun_creds: Aliyun IoT credentials, or *None* to force a refresh on first use.
            mqtt_creds: MQTT credentials, or *None* to force a refresh on first use.

        """
        self._http_creds = http_creds
        self._aliyun_creds = aliyun_creds
        self._mqtt_creds = mqtt_creds

    # ------------------------------------------------------------------
    # Public credential getters — all three follow the same pattern:
    #
    #   1. Lock-free fast path: read the cached credentials without taking the
    #      lock and return immediately if they're still valid.  This keeps the
    #      common case off the lock entirely so an in-flight refresh on one
    #      caller does not stall every other caller that already has a usable
    #      token.
    #   2. Slow path: acquire the lock, re-check the cache (a concurrent
    #      refresher may have just succeeded while we yielded), and call the
    #      relevant refresh helper if still needed.  HTTP timeouts on the
    #      ClientSession (see ``MammotionHTTP._DEFAULT_HTTP_TIMEOUT``) bound how
    #      long the refresh — and therefore the lock — can hold.
    #
    # The pattern is double-checked locking; idiomatic in async Python because
    # the lock-acquisition wait IS the contention point we want to skip.
    # ------------------------------------------------------------------

    async def get_valid_http_token(self) -> str:
        """Return a valid HTTP access token, refreshing proactively if it expires within 5 minutes.

        Returns:
            The current access token string.

        Raises:
            ReLoginRequiredError: If the token cannot be refreshed and re-authentication is needed.

        """
        # Fast path: lock-free read for the common "token is still valid" case.
        creds = self._http_creds
        if creds is not None and creds.expires_at >= time.time() + 300:
            return creds.access_token
        async with self._lock:
            # Re-check under the lock — another coroutine may have refreshed while we waited.
            if self._http_creds is None or self._http_creds.expires_at < time.time() + 300:
                await self.refresh_http()
            if self._http_creds is None:
                raise ReLoginRequiredError(self._account_id, "HTTP credentials unavailable after refresh")
            return self._http_creds.access_token

    async def get_aliyun_credentials(self) -> AliyunCredentials:
        """Return valid Aliyun IoT credentials, refreshing proactively if they expire within 1 hour.

        Returns:
            The current :class:`AliyunCredentials` snapshot.

        Raises:
            RuntimeError: If no :class:`CloudIOTGateway` was provided at construction time.
            ReLoginRequiredError: If the refresh token is expired and re-authentication is needed.

        """
        if self._cloud_gateway is None:
            msg = "No Aliyun cloud gateway configured"
            raise RuntimeError(msg)
        # Fast path: lock-free read for the common "token is still valid" case.
        creds = self._aliyun_creds
        if creds is not None and creds.iot_token_expires_at >= time.time() + 3600:
            return creds
        async with self._lock:
            if self._aliyun_creds is None or self._aliyun_creds.iot_token_expires_at < time.time() + 3600:
                await self._refresh_aliyun()
            if self._aliyun_creds is None:
                raise ReLoginRequiredError(self._account_id, "Aliyun credentials unavailable after refresh")
            return self._aliyun_creds

    async def get_mammotion_mqtt_credentials(self) -> MQTTCredentials:
        """Return valid MQTT credentials, refreshing proactively if they expire within 30 minutes.

        Returns:
            The current :class:`MQTTCredentials` snapshot.

        Raises:
            ReLoginRequiredError: If the underlying HTTP token refresh fails.

        """
        # Fast path: lock-free read for the common "token is still valid" case.
        creds = self._mqtt_creds
        if creds is not None and creds.expires_at >= time.time() + 1800:
            return creds
        async with self._lock:
            if self._mqtt_creds is None or self._mqtt_creds.expires_at < time.time() + 1800:
                await self.refresh_mqtt_creds()
            if self._mqtt_creds is None:
                raise ReLoginRequiredError(self._account_id, "MQTT credentials unavailable after refresh")
            return self._mqtt_creds

    async def force_refresh(self, transport_type: TransportType | None = None) -> None:
        """Forcibly refresh credentials, bypassing cached expiry timestamps.

        Called by a watchdog or error handler when credentials are known to be stale.
        Always refreshes HTTP credentials first. The *transport_type* argument controls
        which cloud-specific credentials are also refreshed:

        - ``TransportType.CLOUD_MAMMOTION``: HTTP + Mammotion MQTT JWT only.
        - ``TransportType.CLOUD_ALIYUN``: HTTP + Aliyun IoT token only.
        - ``None`` (default): HTTP + all active credential types (MQTT and/or Aliyun).

        Args:
            transport_type: Which transport's credentials to refresh, or ``None`` for all.

        Raises:
            ReLoginRequiredError: If the HTTP refresh itself signals that re-login is required.

        """
        async with self._lock:
            await self.refresh_http()
            refresh_mqtt = transport_type in (TransportType.CLOUD_MAMMOTION, None)
            refresh_aliyun = transport_type in (TransportType.CLOUD_ALIYUN, None)
            if refresh_mqtt and self._mqtt_creds is not None:
                await self.refresh_mqtt_creds()
            if refresh_aliyun and self._cloud_gateway is not None:
                await self._refresh_aliyun()

    async def refresh_aliyun_credentials(self) -> None:
        """Force-refresh only Aliyun IoT credentials; called when identityId is blank (29003) or session expires.

        Does not disconnect MQTT or touch HTTP/Mammotion-MQTT credentials.

        Raises:
            ReLoginRequiredError: If the Aliyun session cannot be renewed.

        """
        async with self._lock:
            await self._refresh_aliyun()

    async def refresh_mqtt_credentials(self) -> MQTTCredentials:
        """Force-refresh only Mammotion MQTT JWT credentials; called on MQTT auth errors (401/460).

        Does not touch HTTP or Aliyun credentials.  Acquires ``self._lock`` so
        concurrent refresh attempts serialize — callers outside TokenManager
        MUST use this method (not the private ``refresh_mqtt_creds``) or they
        race the lock-holding paths.

        Returns:
            The refreshed :class:`MQTTCredentials`.

        Raises:
            ReLoginRequiredError: If the MQTT credentials cannot be renewed.

        """
        async with self._lock:
            return await self.refresh_mqtt_creds()

    def subscribe_handle(self, handle: DeviceHandle) -> None:
        """Subscribe to auth errors from *handle* and refresh credentials automatically.

        The subscription is stored internally and lives as long as this
        TokenManager instance — no external lifetime management needed.
        """

        async def _on_error(exc: Exception) -> None:
            try:
                if isinstance(exc, SessionExpiredError) and exc.transport_type == TransportType.CLOUD_MAMMOTION:
                    await self.refresh_mqtt_credentials()
                elif isinstance(exc, SessionExpiredError) and exc.transport_type == TransportType.CLOUD_ALIYUN:
                    await self.refresh_aliyun_credentials()
            except Exception:
                pass  # refresh methods log internally; swallow here to avoid crashing the error bus

        self._handle_subscriptions.append(handle.subscribe_errors(_on_error))

    # ------------------------------------------------------------------
    # Private helpers — callers are responsible for holding self._lock.
    # ------------------------------------------------------------------

    async def _fire_credentials_updated(self) -> None:
        """Notify the on_credentials_updated listener, swallowing listener errors.

        Called at the end of every successful credential refresh so integrations
        can persist the updated token cache.
        """
        if self.on_credentials_updated is not None:
            with contextlib.suppress(Exception):
                await self.on_credentials_updated()

    async def refresh_http(self) -> None:
        """Refresh the HTTP OAuth access token using the stored MammotionHTTP instance.

        Updates *_http_creds* in place.

        Raises:
            ReLoginRequiredError: On any exception that indicates an auth failure.

        """
        try:
            response = await self._http.refresh_login()
            data = response.data
            if data is None:
                raise ReLoginRequiredError(self._account_id, "refresh_login returned no data")
            self._http_creds = HTTPCredentials(
                access_token=data.access_token,
                refresh_token=data.refresh_token,
                expires_at=time.time() + data.expires_in,
            )
        except ReLoginRequiredError:
            raise
        except Exception as exc:
            # DNS / connection / timeout failures must propagate as-is so the
            # MQTT transport's reconnect-with-backoff path handles them rather
            # than triggering a destructive full re-login on a network outage.
            if is_transient_network_error(exc):
                raise
            raise ReLoginRequiredError(self._account_id, str(exc)) from exc
        await self._fire_credentials_updated()

    async def refresh_http_token_only(self) -> None:
        """Refresh the HTTP access token using the refresh token ONLY — never ``login_v2``.

        Unlike :meth:`refresh_http` (which calls ``refresh_login`` and falls back to a
        full ``login_v2`` when the refresh token is dead), this calls ``refresh_token_v2``
        directly and raises :class:`ReLoginRequiredError` if it is rejected.  Used by the
        Mammotion MQTT paths, which must never trigger a full re-login — they give up
        instead (see :meth:`refresh_mqtt_credentials_strict`).

        Raises:
            ReLoginRequiredError: If the refresh token is rejected (give up — do not re-login).

        """
        try:
            response = await self._http.refresh_token_v2()
            data = response.data
            if response.code != 0 or data is None:
                raise ReLoginRequiredError(self._account_id, "refresh token rejected by refresh_token_v2")
            self._http_creds = HTTPCredentials(
                access_token=data.access_token,
                refresh_token=data.refresh_token,
                expires_at=time.time() + data.expires_in,
            )
        except ReLoginRequiredError:
            raise
        except Exception as exc:
            # Transient network failures propagate as-is so the caller backs off
            # rather than treating a blip as an unrecoverable auth error.
            if is_transient_network_error(exc):
                raise
            raise ReLoginRequiredError(self._account_id, str(exc)) from exc
        await self._fire_credentials_updated()

    async def _refresh_aliyun(self) -> None:
        """Refresh the Aliyun IoT session via check_or_refresh_session().

        Updates *_aliyun_creds* in place.

        Raises:
            ReLoginRequiredError: If the refresh token has expired or the session cannot be renewed.

        """
        if self._cloud_gateway is None:
            raise ReLoginRequiredError(self._account_id, "No Aliyun cloud gateway configured")
        try:
            try:
                await self._cloud_gateway.check_or_refresh_session(force=True)
                # Successful session check — clear any accumulated failure timestamps.
                self._aliyun_refresh_failures.clear()
            except SessionExpiredError as session_exc:
                # 2401 "refreshToken invalid" — track failures within a rolling window.
                now = time.monotonic()
                self._aliyun_refresh_failures = [
                    t for t in self._aliyun_refresh_failures if now - t < self._ALIYUN_FAILURE_WINDOW
                ]
                self._aliyun_refresh_failures.append(now)
                if len(self._aliyun_refresh_failures) >= self._ALIYUN_FAILURE_LIMIT:
                    self._aliyun_refresh_failures.clear()
                    raise ReLoginRequiredError(
                        self._account_id,
                        f"Aliyun refreshToken rejected {self._ALIYUN_FAILURE_LIMIT} times "
                        f"within {self._ALIYUN_FAILURE_WINDOW:.0f}s — re-authentication required",
                    ) from session_exc
                # refreshToken was rejected (2401) — re-run the full IoT login sequence.
                # Do NOT return here: fall through so _aliyun_creds is updated from the
                # newly established session.  Returning early was the bug that handed the
                # caller a stale iotToken and caused an infinite bind-failure loop.
                await self.connect_iot()

            session = self._cloud_gateway.session_by_authcode_response
            session_data = session.data  # type: ignore
            if session_data is None:
                raise ReLoginRequiredError(self._account_id, "Aliyun session data is None after refresh")
            issued_at = self._cloud_gateway._iot_token_issued_at  # noqa: SLF001
            self._aliyun_creds = AliyunCredentials(
                iot_token=session_data.iotToken,
                iot_token_expires_at=issued_at + session_data.iotTokenExpire,
                refresh_token=session_data.refreshToken,
                refresh_token_expires_at=issued_at + session_data.refreshTokenExpire,
            )
            if self.on_aliyun_token_refreshed is not None:
                self.on_aliyun_token_refreshed(session_data.iotToken)
        except ReLoginRequiredError:
            raise
        except (AuthRefreshException, LoginException) as exc:
            raise ReLoginRequiredError(self._account_id, str(exc)) from exc
        except Exception as exc:
            # DNS / connection / timeout failures must propagate as-is — see
            # refresh_http() for the rationale.
            if is_transient_network_error(exc):
                raise
            raise ReLoginRequiredError(self._account_id, str(exc)) from exc
        await self._fire_credentials_updated()

    async def connect_iot(self) -> None:
        """Run the Aliyun IoT gateway setup sequence (region, AEP, session, devices)."""

        if self._cloud_gateway is None:
            raise ReLoginRequiredError(self._account_id, "No Aliyun cloud gateway configured")
        cloud_client = self._cloud_gateway
        mammotion_http = cloud_client.mammotion_http
        login_info = mammotion_http.login_info
        if login_info is None:
            msg = "login_info is None — call login_v2() before _connect_iot()"
            raise ReLoginRequiredError(mammotion_http.account or "", msg)
        country_code = login_info.userInformation.domainAbbreviation
        if cloud_client.region_response is None:
            await cloud_client.get_region(country_code)
        await cloud_client.connect()
        await cloud_client.login_by_oauth(country_code)
        await cloud_client.aep_handle()
        await cloud_client.session_by_auth_code()
        await cloud_client.list_binding_by_account()

    async def refresh_invoke_token(self) -> None:
        """Proactively refresh the HTTP bearer token used for mqtt_invoke.

        Delegates to the decorated refresh_authorization_token() which checks
        whether the OAuth access token is close to expiry and calls
        refresh_login() first only when necessary.  Suitable for scheduled
        background refreshes; do NOT call this after a 401 — use
        force_refresh_invoke_token() instead.
        """
        async with self._lock:
            try:
                await self._http.refresh_authorization_token()
            except UnauthorizedExceptionError as exc:
                raise ReLoginRequiredError(self._account_id, str(exc)) from exc
            except Exception as exc:
                # Network outage / DNS failure isn't an auth problem — let the
                # caller see the original exception and back off instead of
                # treating it as an unrecoverable token error.
                if is_transient_network_error(exc):
                    raise
                raise AuthError(exc) from exc

    async def force_refresh_invoke_token(self, *, allow_relogin: bool = True) -> None:
        """Reactive refresh of the HTTP bearer token after a 401 from mqtt_invoke.

        Unconditionally force-refreshes the OAuth access token first (bypassing
        the time-based decorator check), then fetches a fresh authorization code
        via POST /authorization/code.  Use this whenever an actual 401 has
        already been received so that a potentially server-revoked token is
        replaced regardless of what the local expiry clock says.

        If a refresh attempt failed within the last 30 s, raises
        ReLoginRequiredError immediately to prevent hammering the auth server
        when every queued command hits the same expired-token wall.

        Args:
            allow_relogin: When False, refresh the access token via the refresh
                token only (:meth:`refresh_http_token_only`) and never fall back
                to ``login_v2``.  The Mammotion MQTT send path passes False so it
                gives up instead of re-logging-in.

        """
        _invoke_refresh_cooldown = 30.0

        async with self._lock:
            if self._invoke_refresh_failed_at is not None:
                elapsed = time.monotonic() - self._invoke_refresh_failed_at
                if elapsed < _invoke_refresh_cooldown:
                    raise ReLoginRequiredError(
                        self._account_id,
                        f"invoke token refresh in cooldown ({_invoke_refresh_cooldown - elapsed:.0f}s remaining)",
                    )
            try:
                if allow_relogin:
                    await self.refresh_http()  # uses refresh_token or full re-login
                else:
                    await self.refresh_http_token_only()  # refresh token only — never login_v2
                await self._http.fetch_authorization_token()
                self._invoke_refresh_failed_at = None
            except ReLoginRequiredError:
                self._invoke_refresh_failed_at = time.monotonic()
                raise
            except UnauthorizedExceptionError as exc:
                self._invoke_refresh_failed_at = time.monotonic()
                raise ReLoginRequiredError(self._account_id, str(exc)) from exc
            except Exception as exc:
                self._invoke_refresh_failed_at = time.monotonic()
                if is_transient_network_error(exc):
                    raise
                raise AuthError(exc) from exc

    def _set_mqtt_creds(self, data: MQTTConnection) -> MQTTCredentials:
        """Store MQTTConnection data into self._mqtt_creds and return it.

        Expiry is read from the JWT's own ``exp`` claim so proactive refresh
        tracks the broker's real lifetime; if the token carries no ``exp`` it
        falls back to a 24 h assumption (see :func:`_jwt_expiry`).
        """
        self._mqtt_creds = MQTTCredentials(
            host=data.host,
            client_id=data.client_id,
            username=data.username,
            jwt=data.jwt,
            expires_at=_jwt_expiry(data.jwt),
        )
        return self._mqtt_creds

    async def refresh_mqtt_credentials_strict(self) -> MQTTCredentials:
        """Refresh Mammotion MQTT credentials WITHOUT ever falling back to ``login_v2``.

        Refreshes the HTTP access token via the refresh token only
        (:meth:`refresh_http_token_only`), then re-fetches the MQTT JWT.  Any
        failure raises :class:`ReLoginRequiredError` so the Mammotion MQTT
        transport gives up — it must never trigger a full re-login.  Acquires
        ``self._lock`` like :meth:`refresh_mqtt_credentials`.

        Raises:
            ReLoginRequiredError: If the refresh token is dead or the JWT endpoint
                still rejects after the token refresh (give up — do not re-login).

        """
        async with self._lock:
            await self.refresh_http_token_only()
            # get_mqtt_credentials is @refresh_token_decorator, but the token we
            # just minted is fresh so the decorator won't fire login_v2.
            response = await self._http.get_mqtt_credentials()
            if response.data is None:
                raise ReLoginRequiredError(
                    self._account_id, "MQTT JWT endpoint returned no data after refresh-token refresh"
                )
            creds = self._set_mqtt_creds(response.data)
            await self._fire_credentials_updated()
            return creds

    async def refresh_mqtt_creds(self) -> MQTTCredentials:
        """Fetch fresh MQTT credentials from the Mammotion API.

        Updates *_mqtt_creds* in place. Expiry is taken from the JWT's ``exp``
        claim (see :func:`_jwt_expiry`), falling back to 24 hours when absent.

        Raises:
            ReLoginRequiredError: If the underlying HTTP request fails with an auth error.

        """
        try:
            response = await self._http.get_mqtt_credentials()
            data = response.data
            if data is None:
                raise AuthError("get_mqtt_credentials returned no data")
            self._set_mqtt_creds(data)
        except AuthError:
            # JWT endpoint failed — refresh the authorization code, then re-fetch
            # the MQTT JWT.  Reading self._http.mqtt_credentials here would yield
            # the prior (now-rejected) JWT; refresh_authorization_token does not
            # touch mqtt_credentials.
            try:
                await self._http.refresh_authorization_token()
                response = await self._http.get_mqtt_credentials()
                if response.data is None:
                    raise AuthError("get_mqtt_credentials after authz refresh returned no data")
                self._set_mqtt_creds(response.data)
            except Exception:
                # Authorization code refresh also failed — fall back to a full HTTP re-login.
                try:
                    await self.refresh_http()
                    await self._http.refresh_authorization_token()
                    response = await self._http.get_mqtt_credentials()
                    if response.data is None:
                        # Do NOT fall through to return the old (expired) snapshot —
                        # that persists stale creds and loops 401 → refresh → 401,
                        # with each pass potentially rotating refresh tokens server-side.
                        raise ReLoginRequiredError(
                            self._account_id, "get_mqtt_credentials after full re-login returned no data"
                        )
                    self._set_mqtt_creds(response.data)
                except ReLoginRequiredError:
                    raise
                except Exception as exc:
                    if is_transient_network_error(exc):
                        raise
                    raise ReLoginRequiredError(self._account_id, str(exc)) from exc
        except Exception as exc:
            if is_transient_network_error(exc):
                raise
            raise ReLoginRequiredError(self._account_id, str(exc)) from exc
        await self._fire_credentials_updated()
        if self._mqtt_creds is None:
            raise ReLoginRequiredError(self._account_id, "MQTT credentials unavailable")
        return self._mqtt_creds

    @property
    def account_id(self) -> str:
        """Return the account identifier for this token manager."""
        return self._account_id
