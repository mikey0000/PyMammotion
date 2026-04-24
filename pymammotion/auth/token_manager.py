"""Token and credential management for PyMammotion accounts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from typing import TYPE_CHECKING

from pymammotion.aliyun.exceptions import LoginException
from pymammotion.http.model.http import MQTTConnection, UnauthorizedException
from pymammotion.transport import AuthError
from pymammotion.transport.base import ReLoginRequiredError, TransportType

if TYPE_CHECKING:
    from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
    from pymammotion.http.http import MammotionHTTP
    from collections.abc import Callable


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

    async def initialize(
        self,
        http_creds: HTTPCredentials | None,
        aliyun_creds: AliyunCredentials | None,
        mqtt_creds: MQTTCredentials | None,
    ) -> None:
        """Store initial credentials obtained during the login flow.

        Args:
            http_creds: Initial HTTP OAuth credentials, or *None* if unavailable.
            aliyun_creds: Initial Aliyun IoT credentials, or *None* if unavailable.
            mqtt_creds: Initial MQTT credentials, or *None* if unavailable.

        """
        self._http_creds = http_creds
        self._aliyun_creds = aliyun_creds
        self._mqtt_creds = mqtt_creds

    async def get_valid_http_token(self) -> str:
        """Return a valid HTTP access token, refreshing proactively if it expires within 5 minutes.

        Returns:
            The current access token string.

        Raises:
            ReLoginRequiredError: If the token cannot be refreshed and re-authentication is needed.

        """
        async with self._lock:
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

    async def refresh_mqtt_credentials(self) -> None:
        """Force-refresh only Mammotion MQTT JWT credentials; called on MQTT auth errors (401/460).

        Does not touch HTTP or Aliyun credentials.

        Raises:
            ReLoginRequiredError: If the MQTT credentials cannot be renewed.

        """
        async with self._lock:
            await self.refresh_mqtt_creds()

    # ------------------------------------------------------------------
    # Private helpers — callers are responsible for holding self._lock.
    # ------------------------------------------------------------------

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
            raise ReLoginRequiredError(self._account_id, str(exc)) from exc

    async def _refresh_aliyun(self) -> None:
        """Refresh the Aliyun IoT session via check_or_refresh_session().

        Updates *_aliyun_creds* in place.

        Raises:
            ReLoginRequiredError: If the refresh token has expired or the session cannot be renewed.

        """
        from pymammotion.aliyun.exceptions import AuthRefreshException
        from pymammotion.transport.base import SessionExpiredError

        if self._cloud_gateway is None:
            raise ReLoginRequiredError(self._account_id, "No Aliyun cloud gateway configured")
        try:
            try:
                await self._cloud_gateway.check_or_refresh_session()
            except SessionExpiredError:
                # refreshToken was rejected (2401) — re-run the full IoT login sequence.
                # Do NOT return here: fall through so _aliyun_creds is updated from the
                # newly established session.  Returning early was the bug that handed the
                # caller a stale iotToken and caused an infinite bind-failure loop.
                await self.connect_iot(self._cloud_gateway)

            session = self._cloud_gateway.session_by_authcode_response
            session_data = session.data
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
            raise ReLoginRequiredError(self._account_id, str(exc)) from exc

    @staticmethod
    async def connect_iot(cloud_client: CloudIOTGateway) -> None:
        """Run the Aliyun IoT gateway setup sequence (region, AEP, session, devices)."""
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
            except UnauthorizedException as exc:
                raise ReLoginRequiredError(self._account_id, str(exc)) from exc
            except Exception as exc:
                raise AuthError(exc)

    async def force_refresh_invoke_token(self) -> None:
        """Reactive refresh of the HTTP bearer token after a 401 from mqtt_invoke.

        Unconditionally force-refreshes the OAuth access token first (bypassing
        the time-based decorator check), then fetches a fresh authorization code
        via POST /authorization/code.  Use this whenever an actual 401 has
        already been received so that a potentially server-revoked token is
        replaced regardless of what the local expiry clock says.
        """
        async with self._lock:
            await self.refresh_http()  # force: uses refresh_token or full re-login
            try:
                await self._http.fetch_authorization_token()
            except UnauthorizedException as exc:
                raise ReLoginRequiredError(self._account_id, str(exc)) from exc
            except Exception as exc:
                raise AuthError(exc)

    async def refresh_mqtt_creds(self) -> MQTTCredentials:
        """Fetch fresh MQTT credentials from the Mammotion API.

        Updates *_mqtt_creds* in place. The API does not return an explicit expiry,
        so credentials are assumed valid for 24 hours.

        Raises:
            ReLoginRequiredError: If the underlying HTTP request fails with an auth error.

        """

        def _store_mqtt_creds(data: MQTTConnection) -> None:
            """Store MQTTConnection data into self._mqtt_creds."""
            self._mqtt_creds = MQTTCredentials(
                host=data.host,
                client_id=data.client_id,
                username=data.username,
                jwt=data.jwt,
                expires_at=time.time() + 86400,
            )

        try:
            response = await self._http.get_mqtt_credentials()
            data = response.data
            if data is None:
                raise AuthError("get_mqtt_credentials returned no data")
            _store_mqtt_creds(data)
        except AuthError:
            # JWT endpoint failed — refresh the authorization code first (which
            # internally calls get_mqtt_credentials() and stores the result on self._http).
            try:
                await self._http.refresh_authorization_token()
                creds = self._http.mqtt_credentials
                if creds is None:
                    raise AuthError("refresh_authorization_code returned no MQTT credentials")
                _store_mqtt_creds(creds)
            except (Exception, AuthError):
                # Authorization code refresh also failed — fall back to a full HTTP re-login.
                try:
                    await self._http.refresh_login()
                    await self._http.refresh_authorization_token()
                    creds = self._http.mqtt_credentials
                    if creds is not None:
                        _store_mqtt_creds(creds)
                except ReLoginRequiredError:
                    raise
                except Exception as exc:
                    raise ReLoginRequiredError(self._account_id, str(exc)) from exc
        except Exception as exc:
            raise ReLoginRequiredError(self._account_id, str(exc)) from exc
        return self._mqtt_creds

    @property
    def account_id(self) -> str:
        """Return the account identifier for this token manager."""
        return self._account_id
