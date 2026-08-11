"""Token and credential management for PyMammotion accounts."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import logging
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

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scheduled-refresh tuning
#
# How long before expiry each credential is renewed.  These match the thresholds
# the on-demand getters already use, so a scheduled refresh and a lazy one make
# the same decision about what counts as "due".
# ---------------------------------------------------------------------------
_HTTP_REFRESH_LEAD = 300.0  # 5 min — mirrors ensure_token_valid
_MQTT_REFRESH_LEAD = 1800.0  # 30 min — mirrors get_mammotion_mqtt_credentials
_ALIYUN_REFRESH_LEAD = 3600.0  # 1 h — mirrors get_aliyun_credentials

#: Longest the scheduler will sleep before re-evaluating.  Bounds the damage from
#: a missing or nonsensical expiry, and lets credentials that appear *after* the
#: scheduler started (a transport added later) get picked up.
_MAX_SCHEDULER_SLEEP = 3600.0

#: Backoff after a refresh fails, or succeeds without moving the expiry forward.
#: Stops an unrenewable credential from becoming a hot loop.
_SCHEDULER_RETRY_DELAY = 300.0


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

    All three credential types (HTTP OAuth token, Aliyun IoT token, Mammotion MQTT
    JWT) are refreshed proactively before they expire.  A single asyncio.Lock
    prevents concurrent refresh races.

    **No automatic password re-login.**  Every refresh here uses a refresh token
    (HTTP, Mammotion MQTT) or the existing login's authCode chain (Aliyun).  A
    password grant happens only when the caller explicitly logs in.  A refresh
    that is *rejected* is therefore terminal, and failures are scoped:

    * **Account-scoped** (:attr:`reauth_required`) — the HTTP refresh token was
      rejected, so nothing about this account can be renewed.  Raises
      :class:`ReLoginRequiredError`; the host should prompt the user to
      re-authenticate.
    * **Transport-scoped** (:attr:`aliyun_unavailable`, :attr:`mqtt_unavailable`)
      — one cloud transport's credentials are unrenewable while the HTTP login is
      still healthy.  Only that transport is given up; the HTTP session, the
      cached credentials, and the *other* transport all keep working.

    A transient network failure is neither: it propagates as its own exception
    type so callers back off and retry, and never marks anything terminal.
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
        #: Fired (async) after any credential type is successfully refreshed.
        #: Integrations can wire this to persist the updated token cache.
        self.on_credentials_updated: Callable[[], Awaitable[None]] | None = None
        # Terminal failure reasons — None means healthy.  Once set, the matching
        # getters and refreshers fail fast with ReLoginRequiredError and never touch
        # the network again; recovery is a fresh caller-initiated login, which builds
        # a new TokenManager.
        #
        # These replace the previous cooldown timers (_force_refresh_failed_at,
        # _invoke_refresh_failed_at, _aliyun_refresh_failures).  Those existed to
        # rate-limit an automatic password re-login that no longer happens — and a
        # rejected refresh token does not become valid again by waiting, so retrying
        # it on a timer only ever hammered the auth server.
        self._reauth_required: str | None = None  # account-wide: the HTTP login is dead
        self._aliyun_unavailable: str | None = None  # transport-scoped: Aliyun IoT session is dead
        self._mqtt_unavailable: str | None = None  # transport-scoped: Mammotion MQTT JWT is dead
        # Background task that renews credentials shortly before they expire — see
        # start_refresh_scheduler().
        self._scheduler_task: asyncio.Task[None] | None = None
        # RAII subscriptions to device handle error buses — kept alive here so they
        # are never garbage-collected while this token manager is active.
        self._handle_subscriptions: list[Subscription] = []
        # Mirror HTTP-level token rotations (including refresh_token_decorator
        # refreshes that never pass through this manager) into our snapshot and
        # persist them — see _on_http_login_refreshed.
        mammotion_http.on_login_refreshed = self._on_http_login_refreshed

    @property
    def http(self) -> MammotionHTTP:
        """The MammotionHTTP this manager refreshes tokens on.

        Exposed so wiring code can assert a transport and its TokenManager share one
        login session (see ``MammotionClient._setup_mammotion_transport``): a refresh
        only reaches ``mqtt_invoke`` when both read/write the same instance.
        """
        return self._http

    @property
    def cloud_gateway(self) -> CloudIOTGateway | None:
        """The Aliyun gateway this manager refreshes IoT sessions on, if any."""
        return self._cloud_gateway

    def attach_cloud_gateway(self, cloud_gateway: CloudIOTGateway) -> None:
        """Give this manager the account's Aliyun gateway.

        An account has one login session and therefore one TokenManager, but its Aliyun
        gateway may only appear later — a restore establishes the HTTP login first, and
        a Mammotion-MQTT-only account may never have one at all.  Attaching keeps that
        single manager (and its running refresh scheduler, terminal flags, and the
        transports holding a reference to it) rather than replacing it with a second
        one built around the gateway.
        """
        self._cloud_gateway = cloud_gateway

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

    def seed_from_http(self) -> None:
        """Adopt the credentials the login session is already carrying.

        A restored — or freshly logged-in — :class:`MammotionHTTP` arrives holding an
        access token and, usually, MQTT credentials.  Without seeding, this manager
        starts with empty snapshots, so the first ``get_mammotion_mqtt_credentials()``
        spends a network round-trip re-fetching a JWT we already have, and
        ``seconds_until_next_refresh`` is meaningless until something refreshes once.

        Only fills gaps: a snapshot already held here is never downgraded to whatever
        the http object happens to be carrying.
        """
        if self._http_creds is None and (login := self._http.login_info) is not None:
            self._http_creds = HTTPCredentials(
                access_token=login.access_token,
                refresh_token=login.refresh_token,
                expires_at=self._http.expires_in,
            )
        if self._mqtt_creds is None and (mqtt := self._http.mqtt_credentials) is not None:
            self._set_mqtt_creds(mqtt)

    # ------------------------------------------------------------------
    # Terminal failure state
    # ------------------------------------------------------------------

    @property
    def reauth_required(self) -> str | None:
        """Reason the account needs re-authentication, or ``None`` while healthy.

        Set only when the HTTP refresh token itself is rejected — nothing about
        this account can be renewed and the user must log in again.
        """
        return self._reauth_required

    @property
    def aliyun_unavailable(self) -> str | None:
        """Reason the Aliyun IoT session is unrenewable, or ``None`` while healthy.

        Transport-scoped: the HTTP login and the Mammotion MQTT transport are
        unaffected and must keep working.
        """
        return self._aliyun_unavailable

    @property
    def mqtt_unavailable(self) -> str | None:
        """Reason the Mammotion MQTT JWT is unrenewable, or ``None`` while healthy.

        Transport-scoped: the HTTP login and the Aliyun transport are unaffected
        and must keep working.
        """
        return self._mqtt_unavailable

    def _raise_if_reauth_required(self) -> None:
        """Fail fast when the account is already known to need re-authentication.

        Costs no network round-trip: a rejected refresh token cannot recover on
        its own, so every subsequent caller gets the same terminal answer
        immediately rather than queueing another doomed request.
        """
        if self._reauth_required is not None:
            raise ReLoginRequiredError(self._account_id, self._reauth_required)

    def _mark_reauth_required(self, reason: str) -> ReLoginRequiredError:
        """Mark the account terminally unauthenticated and build the error to raise."""
        if self._reauth_required is None:
            self._reauth_required = reason
        return ReLoginRequiredError(self._account_id, reason)

    def _mark_aliyun_unavailable(self, reason: str) -> ReLoginRequiredError:
        """Mark the Aliyun IoT session terminally unrenewable and build the error to raise.

        Deliberately does NOT touch :attr:`reauth_required`: the HTTP login is
        still good, so the account's credentials stay cached and any Mammotion
        MQTT transport keeps working.  Only the Aliyun transport is given up.
        """
        if self._aliyun_unavailable is None:
            self._aliyun_unavailable = reason
        return ReLoginRequiredError(self._account_id, reason)

    def _mark_mqtt_unavailable(self, reason: str) -> ReLoginRequiredError:
        """Mark the Mammotion MQTT JWT terminally unrenewable and build the error to raise.

        Deliberately does NOT touch :attr:`reauth_required`: the HTTP login is
        still good, so the account's credentials stay cached and any Aliyun
        transport keeps working.  Only the Mammotion MQTT transport is given up.
        """
        if self._mqtt_unavailable is None:
            self._mqtt_unavailable = reason
        return ReLoginRequiredError(self._account_id, reason)

    # ------------------------------------------------------------------
    # Public credential getters — both follow the same pattern:
    #
    #   1. Lock-free fast path: read the cached credentials without taking the
    #      lock and return immediately if they're still valid.  This keeps the
    #      common case off the lock entirely so an in-flight refresh on one
    #      caller does not stall every other caller that already has a usable
    #      token.
    #   2. Slow path: acquire the lock, re-check the cache (a concurrent
    #      refresher may have just succeeded while we yielded), and call the
    #      relevant refresh helper if still needed.  Refreshes bound their own
    #      network work (see ``MammotionHTTP._REFRESH_TIMEOUT_SEC``) so the lock
    #      cannot be held indefinitely by a stalled server.
    #
    # The pattern is double-checked locking; idiomatic in async Python because
    # the lock-acquisition wait IS the contention point we want to skip.
    # ------------------------------------------------------------------

    async def get_aliyun_credentials(self) -> AliyunCredentials:
        """Return valid Aliyun IoT credentials, refreshing proactively if they expire within 1 hour.

        Returns:
            The current :class:`AliyunCredentials` snapshot.

        Raises:
            RuntimeError: If no :class:`CloudIOTGateway` was provided at construction time.
            ReLoginRequiredError: If the Aliyun session is unrenewable or the account
                needs re-authentication.

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
            ReLoginRequiredError: If the MQTT JWT is unrenewable or the account
                needs re-authentication.

        """
        # Fast path: lock-free read for the common "token is still valid" case.
        creds = self._mqtt_creds
        if creds is not None and creds.expires_at >= time.time() + 1800:
            return creds
        async with self._lock:
            if self._mqtt_creds is None or self._mqtt_creds.expires_at < time.time() + 1800:
                await self._refresh_mqtt()
            if self._mqtt_creds is None:
                raise ReLoginRequiredError(self._account_id, "MQTT credentials unavailable after refresh")
            return self._mqtt_creds

    async def refresh_aliyun_credentials(self) -> None:
        """Force-refresh only Aliyun IoT credentials; called when identityId is blank (29003) or session expires.

        Does not disconnect MQTT or touch HTTP/Mammotion-MQTT credentials.

        Raises:
            ReLoginRequiredError: If the Aliyun session cannot be renewed.  The
                HTTP login and any Mammotion MQTT transport remain usable unless
                :attr:`reauth_required` is also set.

        """
        async with self._lock:
            await self._refresh_aliyun()

    async def refresh_mqtt_credentials(self) -> MQTTCredentials:
        """Force-refresh only Mammotion MQTT JWT credentials; called on MQTT auth errors (401/460).

        Does not touch Aliyun credentials.  The HTTP access token is renewed
        first if it is close to expiry, via the refresh token only.  Acquires
        ``self._lock`` so concurrent refresh attempts serialize.

        Returns:
            The refreshed :class:`MQTTCredentials`.

        Raises:
            ReLoginRequiredError: If the MQTT credentials cannot be renewed.  The
                HTTP login and any Aliyun transport remain usable unless
                :attr:`reauth_required` is also set.

        """
        async with self._lock:
            return await self._refresh_mqtt()

    # ------------------------------------------------------------------
    # Scheduled refresh
    #
    # Every other refresh path in this class is lazy — it runs because something
    # asked for a credential.  That is not enough on its own: when every device on
    # the account is offline, the poll loop skips sending (no usable transport), so
    # no HTTP call is made, ``ensure_token_valid`` never fires, and the in-band
    # Aliyun expiry check inside ``send_cloud_command`` never runs.  Nothing would
    # renew anything, and the credentials would sit there until the *refresh*
    # tokens expired — at which point recovery needs the user.
    #
    # So renewal is driven by the clock rather than by traffic.  The loop sleeps
    # until the earliest credential is due and then renews just that one; it does
    # not poll.
    # ------------------------------------------------------------------

    def start_refresh_scheduler(self) -> None:
        """Start renewing credentials shortly before they expire.

        Idempotent, and safe to call before any credentials exist — the loop
        re-evaluates at least hourly, so credential types that appear later (a
        transport added after login) are picked up without a restart.

        Requires a running event loop.
        """
        if self._scheduler_task is not None and not self._scheduler_task.done():
            return
        self._scheduler_task = asyncio.get_running_loop().create_task(self._refresh_scheduler())

    async def stop_refresh_scheduler(self) -> None:
        """Cancel the scheduled-refresh task and wait for it to unwind."""
        task = self._scheduler_task
        self._scheduler_task = None
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    @property
    def seconds_until_next_refresh(self) -> float:
        """Seconds until the earliest credential falls due (clamped to the sleep cap)."""
        return self._seconds_until_next_refresh()

    @staticmethod
    def _expiry(value: object) -> float | None:
        """Coerce a stored expiry to a usable timestamp, or None when unusable.

        Defensive on purpose: this feeds a long-lived background task, and an
        unset or malformed expiry should make the scheduler skip that credential
        and re-check later, not kill the task with a TypeError that nothing
        surfaces.
        """
        # bool is an int subclass, and an expiry of True/False is meaningless.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value) or None

    def _seconds_until_next_refresh(self) -> float:
        now = time.time()
        due_at: list[float] = []
        # The HTTP token's authoritative expiry lives on MammotionHTTP — that is what
        # ensure_token_valid gates on, so scheduling off anything else could have the
        # two disagree about whether a refresh is needed.
        if (http_exp := self._expiry(self._http.expires_in)) is not None:
            due_at.append(http_exp - _HTTP_REFRESH_LEAD)
        if self._mqtt_creds is not None and (exp := self._expiry(self._mqtt_creds.expires_at)) is not None:
            due_at.append(exp - _MQTT_REFRESH_LEAD)
        if (
            self._aliyun_creds is not None
            and (exp := self._expiry(self._aliyun_creds.iot_token_expires_at)) is not None
        ):
            due_at.append(exp - _ALIYUN_REFRESH_LEAD)
        if not due_at:
            return _MAX_SCHEDULER_SLEEP
        return max(0.0, min(min(due_at) - now, _MAX_SCHEDULER_SLEEP))

    async def _refresh_due_credentials(self) -> bool:
        """Renew every credential currently within its lead window.

        Returns True when everything due was renewed successfully.  HTTP goes first:
        both the Mammotion JWT and the Aliyun session are minted using the HTTP
        access token, so renewing them against a stale bearer would just fail.
        """
        now = time.time()
        ok = True

        http_exp = self._expiry(self._http.expires_in)
        if http_exp is not None and http_exp - _HTTP_REFRESH_LEAD <= now:
            _LOGGER.debug("token scheduler [%s]: HTTP access token due — refreshing", self._account_id)
            async with self._lock:
                await self.refresh_http()

        if (
            self._mqtt_unavailable is None
            and self._mqtt_creds is not None
            and self._mqtt_creds.expires_at - _MQTT_REFRESH_LEAD <= now
        ):
            _LOGGER.debug("token scheduler [%s]: Mammotion MQTT JWT due — refreshing", self._account_id)
            try:
                await self.refresh_mqtt_credentials()
            except ReLoginRequiredError:
                # Transport-scoped give-up: the flag now short-circuits this branch,
                # and the account's other credentials keep being scheduled.
                _LOGGER.warning("token scheduler [%s]: Mammotion MQTT unrenewable", self._account_id)
                ok = False

        if (
            self._aliyun_unavailable is None
            and self._cloud_gateway is not None
            and self._aliyun_creds is not None
            and self._aliyun_creds.iot_token_expires_at - _ALIYUN_REFRESH_LEAD <= now
        ):
            _LOGGER.debug("token scheduler [%s]: Aliyun IoT session due — refreshing", self._account_id)
            try:
                await self.refresh_aliyun_credentials()
            except ReLoginRequiredError:
                _LOGGER.warning("token scheduler [%s]: Aliyun session unrenewable", self._account_id)
                ok = False

        return ok

    async def _refresh_scheduler(self) -> None:
        """Sleep until the next credential is due, renew it, repeat."""
        while True:
            try:
                if self._reauth_required is not None:
                    _LOGGER.debug("token scheduler [%s]: account needs re-authentication — stopping", self._account_id)
                    return

                delay = self._seconds_until_next_refresh()
                if delay > 0:
                    await asyncio.sleep(delay)
                    continue

                progressed = await self._refresh_due_credentials()
                if not progressed or self._seconds_until_next_refresh() <= 0:
                    # Either something failed, or a refresh "succeeded" without moving
                    # the expiry (clock skew, or the server reissuing the same
                    # lifetime).  Back off rather than spinning on it.
                    await asyncio.sleep(_SCHEDULER_RETRY_DELAY)
            except asyncio.CancelledError:
                raise
            except ReLoginRequiredError:
                # Raised by refresh_http: the account itself is finished.  The loop
                # exits on the next pass via the _reauth_required check above.
                _LOGGER.warning("token scheduler [%s]: re-authentication required — stopping", self._account_id)
                return
            except Exception:
                # Transient (network/DNS/server) — never terminal.  Back off and retry;
                # the credentials are probably still fine, we just could not reach the
                # server, and treating that as an auth failure would strand a working
                # login behind a re-auth prompt.
                _LOGGER.debug(
                    "token scheduler [%s]: refresh attempt failed — retrying in %.0fs",
                    self._account_id,
                    _SCHEDULER_RETRY_DELAY,
                    exc_info=True,
                )
                await asyncio.sleep(_SCHEDULER_RETRY_DELAY)

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

    async def _on_http_login_refreshed(self) -> None:
        """Mirror an HTTP-level token rotation into this manager's snapshot and persist it.

        Fired by MammotionHTTP after any successful oauth2/token exchange —
        including refreshes triggered by the ``refresh_token_decorator``, which
        never pass through this manager.  Without this, a decorator refresh
        rotates the server-side refresh token while the persisted cache keeps the
        dead one, so the next restart starts with a failed refresh and falls back
        to a password re-login.

        Deliberately lock-free: it can fire while :meth:`refresh_http` already
        holds ``self._lock`` (refresh_login → callback), so taking the lock here
        would deadlock.
        """
        login_info = self._http.login_info
        if login_info is None:
            return
        self._http_creds = HTTPCredentials(
            access_token=login_info.access_token,
            refresh_token=login_info.refresh_token,
            expires_at=self._http.expires_in,
        )
        await self._fire_credentials_updated()

    async def _fire_credentials_updated(self) -> None:
        """Notify the on_credentials_updated listener, swallowing listener errors.

        Called at the end of every successful credential refresh so integrations
        can persist the updated token cache.
        """
        if self.on_credentials_updated is not None:
            with contextlib.suppress(Exception):
                await self.on_credentials_updated()

    async def refresh_http(self) -> None:
        """Renew the HTTP OAuth access token using the refresh token.

        This is the only automatic renewal path for the account's HTTP session:
        ``refresh_token_v2`` and nothing else.  A rejected refresh token is
        terminal and marks the whole account :attr:`reauth_required` — there is no
        password fallback, because an automatic password grant would bypass the
        host's re-auth prompt and, during a server-side outage, fire once per
        queued request.

        Updates *_http_creds* in place.  Callers hold ``self._lock``.

        Raises:
            ReLoginRequiredError: The refresh token was rejected — the user must
                re-authenticate.  Transient network failures instead propagate as
                their own type so the caller backs off, and never mark the account
                terminal.

        """
        self._raise_if_reauth_required()
        try:
            response = await self._http.refresh_token_v2()
            data = response.data
            if response.code != 0 or data is None:
                raise self._mark_reauth_required(f"refresh token rejected by oauth2/token (code={response.code})")
            self._http_creds = HTTPCredentials(
                access_token=data.access_token,
                refresh_token=data.refresh_token,
                expires_at=time.time() + data.expires_in,
            )
        except ReLoginRequiredError:
            # Raised above, or from inside MammotionHTTP.ensure_token_valid — both
            # mean the refresh token is dead, so the account is terminal either way.
            self._mark_reauth_required("HTTP refresh token rejected")
            raise
        except Exception as exc:
            # DNS / connection / timeout failures must propagate as-is so the
            # caller's reconnect-with-backoff path handles them.  Treating a
            # network outage as an auth failure would strand a perfectly good
            # login behind a re-auth prompt the user cannot satisfy.
            if is_transient_network_error(exc):
                raise
            raise self._mark_reauth_required(str(exc)) from exc
        await self._fire_credentials_updated()

    async def _refresh_aliyun(self) -> None:
        """Refresh the Aliyun IoT session via check_or_refresh_session().

        On a 2401 ("refreshToken invalid") the session is rebuilt once from the
        existing HTTP login's authCode chain (:meth:`connect_iot`).  That path uses
        no password, so it is legitimate automatic recovery rather than a re-login.

        If the rebuild also fails, the *Aliyun transport* is terminally
        unavailable — but the HTTP login and any Mammotion MQTT transport are
        untouched and keep working, so the account's cached credentials are
        deliberately left in place.

        Updates *_aliyun_creds* in place.  Callers hold ``self._lock``.

        Raises:
            ReLoginRequiredError: The Aliyun session cannot be renewed.

        """
        if self._cloud_gateway is None:
            raise ReLoginRequiredError(self._account_id, "No Aliyun cloud gateway configured")
        if self._aliyun_unavailable is not None:
            raise ReLoginRequiredError(self._account_id, self._aliyun_unavailable)
        self._raise_if_reauth_required()
        try:
            try:
                await self._cloud_gateway.check_or_refresh_session(force=True)
            except SessionExpiredError as session_exc:
                # 2401 "refreshToken invalid" — rebuild the IoT session from the
                # still-valid HTTP login.  Do NOT return here: fall through so
                # _aliyun_creds is updated from the newly established session.
                # Returning early was the bug that handed the caller a stale
                # iotToken and caused an infinite bind-failure loop.
                try:
                    await self.connect_iot()
                except Exception as rebuild_exc:
                    if is_transient_network_error(rebuild_exc):
                        raise
                    raise self._mark_aliyun_unavailable(
                        f"Aliyun session rebuild failed after refreshToken rejection: {rebuild_exc}"
                    ) from session_exc

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
            raise self._mark_aliyun_unavailable(str(exc)) from exc
        except Exception as exc:
            # DNS / connection / timeout failures must propagate as-is — see
            # refresh_http() for the rationale.
            if is_transient_network_error(exc):
                raise
            raise self._mark_aliyun_unavailable(str(exc)) from exc
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

    async def refresh_invoke_token(self, stale_token: str | None = None) -> None:
        """Renew the HTTP bearer token used for ``mqtt_invoke`` after a 401.

        Renews the OAuth access token via the refresh token — bypassing the
        time-based expiry check, because a 401 means the server rejected a token
        our local clock still considers valid — then fetches a fresh authorization
        code via POST /authorization/code.

        Args:
            stale_token: The access token the failed request actually used.  When
                the live token has already moved on, some other caller refreshed
                while we queued for the lock, so this returns immediately and the
                caller simply retries with the new token.

                Without that check a burst of commands that all 401 on the same
                dead token produces one refresh *each*, serialized by the lock —
                and every refresh rotates the refresh token server-side, so the
                later rotations race the earlier ones.  The Android app guards the
                identical way, comparing the failing request's ``Authorization``
                header against its stored token before refreshing
                (``SpecialCodeIntercepter.refreshToken``).

        No cooldown is needed: if the refresh token is dead, :meth:`refresh_http`
        marks the account terminal and every subsequent caller fails fast without
        touching the network.

        Raises:
            ReLoginRequiredError: The refresh token was rejected — the user must
                re-authenticate.
            AuthError: The authorization-code fetch failed for a non-network reason.

        """
        async with self._lock:
            if stale_token is not None:
                login_info = self._http.login_info
                current = login_info.access_token if login_info is not None else None
                if current is not None and current != stale_token:
                    return
            try:
                await self.refresh_http()
                await self._http.fetch_authorization_token()
            except ReLoginRequiredError:
                raise
            except UnauthorizedExceptionError as exc:
                raise self._mark_reauth_required(str(exc)) from exc
            except Exception as exc:
                # Network outage / DNS failure isn't an auth problem — let the
                # caller see the original exception and back off instead of
                # treating it as an unrecoverable token error.
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

    async def _refresh_mqtt(self) -> MQTTCredentials:
        """Fetch a fresh Mammotion MQTT JWT.  Callers hold ``self._lock``.

        ``get_mqtt_credentials`` carries ``@refresh_token_decorator``, so the
        access token is renewed first if — and only if — it is close to expiry.
        If the JWT endpoint still refuses, the access token is force-renewed once
        and the fetch retried; that covers a server-side revocation the local
        expiry clock cannot see.

        A second refusal gives up on the Mammotion MQTT transport *only*: the HTTP
        login and any Aliyun transport are still good, so the account's cached
        credentials are deliberately left intact.

        Updates *_mqtt_creds* in place.  Expiry is taken from the JWT's ``exp``
        claim (see :func:`_jwt_expiry`), falling back to 24 hours when absent.

        Raises:
            ReLoginRequiredError: The MQTT JWT cannot be renewed.  Transient
                network failures propagate as their own type instead.

        """
        self._raise_if_reauth_required()
        if self._mqtt_unavailable is not None:
            raise ReLoginRequiredError(self._account_id, self._mqtt_unavailable)
        try:
            response = await self._http.get_mqtt_credentials()
            if response.data is None:
                # Force-renew the access token and re-fetch the authorization code,
                # then retry once.  Reading self._http.mqtt_credentials here would
                # yield the prior (now-rejected) JWT.
                await self.refresh_http()
                await self._http.fetch_authorization_token()
                response = await self._http.get_mqtt_credentials()
                if response.data is None:
                    # Do NOT fall through to the old snapshot — returning stale creds
                    # loops 401 → refresh → 401, rotating refresh tokens server-side
                    # on every pass.
                    raise self._mark_mqtt_unavailable("MQTT JWT endpoint returned no data after access-token refresh")
            creds = self._set_mqtt_creds(response.data)
        except ReLoginRequiredError:
            raise
        except Exception as exc:
            if is_transient_network_error(exc):
                raise
            raise self._mark_mqtt_unavailable(str(exc)) from exc
        await self._fire_credentials_updated()
        return creds

    @property
    def account_id(self) -> str:
        """Return the account identifier for this token manager."""
        return self._account_id
