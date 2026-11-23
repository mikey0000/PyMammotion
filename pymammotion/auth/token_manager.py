"""Token and credential management for PyMammotion accounts."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING

import jwt

from pymammotion.aliyun.exceptions import CloudSetupError, LoginException
from pymammotion.http.model.http import (
    AuthorizationCodeError,
    MQTTConnection,
    RateLimitedError,
    UnauthorizedExceptionError,
)
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

#: Ceiling for the doubling delay between attempts to establish a deferred Aliyun session.
_MAX_ALIYUN_RETRY_DELAY = 4 * 3600.0


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


@dataclass(frozen=True)
class _HandleSubscription:
    """A device's error-bus subscription, with the handle it was taken out for.

    The handle is kept so a re-registered device can be told apart from the same
    handle subscribing twice; it is not otherwise used.
    """

    handle: DeviceHandle
    subscription: Subscription


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
        self._cloud_gateway: CloudIOTGateway | None = None
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
        #: Fired exactly once, on the None → reason transition of _reauth_required,
        #: with (reason, error).  MammotionClient wires this to quiesce the whole
        #: account: disconnect both cloud transports, stop the scheduler, and
        #: notify the host — regardless of which refresh path found the rejection.
        self.on_reauth_required: Callable[[str, Exception], Awaitable[None]] | None = None
        # Strong ref to the detached quiesce task so it is not garbage-collected
        # mid-flight; _mark_reauth_required runs under self._lock on arbitrary
        # tasks, so the callback must never be awaited inline.
        self._reauth_task: asyncio.Task[None] | None = None
        # Background task that renews credentials shortly before they expire — see
        # start_refresh_scheduler().
        self._scheduler_task: asyncio.Task[None] | None = None
        # A gateway whose session could not be established for a transient reason; the
        # scheduler retries it at _aliyun_retry_at, doubling the delay each time.
        self._aliyun_pending: CloudIOTGateway | None = None
        self._aliyun_retry_at: float = 0.0
        self._aliyun_retries: int = 0
        #: Fired with the gateway once a deferred Aliyun session is established, so the
        #: client can build its transport and attach the account's Aliyun devices.
        self.on_aliyun_established: Callable[[CloudIOTGateway], Awaitable[None]] | None = None
        #: Fired (async, detached) on each edge of a transport-scoped flag: with the
        #: reason when Aliyun or Mammotion MQTT is given up, with None when it recovers.
        self.on_transport_availability_changed: Callable[[TransportType, str | None], Awaitable[None]] | None = None
        self._availability_tasks: set[asyncio.Task[None]] = set()
        # RAII subscriptions to device handle error buses — kept alive here so they
        # are never garbage-collected while this token manager is active.
        self._handle_subscriptions: dict[str, _HandleSubscription] = {}
        # Mirror HTTP-level token rotations (including refresh_token_decorator
        # refreshes that never pass through this manager) into our snapshot and
        # persist them — see _on_http_login_refreshed.
        mammotion_http.on_login_refreshed = self._on_http_login_refreshed
        mammotion_http.on_reauth_required = self._mark_reauth_required
        if cloud_gateway is not None:
            self.attach_cloud_gateway(cloud_gateway)

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

        The manager owns the gateway's session from here on: it adopts the session now
        so the scheduler renews it, and hears of every later renewal — the gateway's
        in-band ones included — to hand the new iotToken to the transport and persist it.
        """
        self._cloud_gateway = cloud_gateway
        cloud_gateway.on_session_refreshed = self._sync_aliyun_session
        self._adopt_aliyun_session()

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

    def _adopt_http_reauth(self) -> None:
        """Raise if a decorated endpoint already marked the HTTP layer terminal.

        ``@refresh_token_decorator`` sees a rejected refresh before this manager
        does; adopting its verdict fires the account quiesce and keeps the two
        layers' flags consistent instead of spending another doomed round trip.
        """
        if (http_reason := self._http.reauth_required) is not None:
            raise self._mark_reauth_required(http_reason)

    def reject_login(self, reason: str) -> ReLoginRequiredError:
        """Record that the server refused this login and build the error to raise.

        For a refusal found outside this manager — a restore whose cached login the
        server no longer accepts.  Sets :attr:`reauth_required` and fires
        :attr:`on_reauth_required` exactly as a rejected refresh token does.
        """
        return self._mark_reauth_required(reason)

    def _mark_reauth_required(self, reason: str) -> ReLoginRequiredError:
        """Mark the account terminally unauthenticated and build the error to raise.

        On the first (and only the first) call this also pushes the terminal state
        down to :class:`MammotionHTTP` — so decorated endpoints that never touch
        this manager stop spending oauth2/token round trips — and fires
        :attr:`on_reauth_required` as a detached task, never inline: this method
        runs inside refresh calls that hold ``self._lock``, and the quiesce
        callback re-enters client code that must not run under that lock.
        """
        err = ReLoginRequiredError(self._account_id, reason)
        if self._reauth_required is None:
            self._reauth_required = reason
            self._http.mark_reauth_required(reason)
            if self.on_reauth_required is not None:
                self._reauth_task = asyncio.ensure_future(self.on_reauth_required(reason, err))
        return err

    def _mark_aliyun_unavailable(self, reason: str) -> ReLoginRequiredError:
        """Mark the Aliyun IoT session terminally unrenewable and build the error to raise.

        Deliberately does NOT touch :attr:`reauth_required`: the HTTP login is
        still good, so the account's credentials stay cached and any Mammotion
        MQTT transport keeps working.  Only the Aliyun transport is given up.
        """
        if self._aliyun_unavailable is None:
            self._aliyun_unavailable = reason
            self._aliyun_pending = None
            self._notify_availability(TransportType.CLOUD_ALIYUN, reason)
        return ReLoginRequiredError(self._account_id, reason)

    def _mark_mqtt_unavailable(self, reason: str) -> ReLoginRequiredError:
        """Mark the Mammotion MQTT JWT terminally unrenewable and build the error to raise.

        Deliberately does NOT touch :attr:`reauth_required`: the HTTP login is
        still good, so the account's credentials stay cached and any Aliyun
        transport keeps working.  Only the Mammotion MQTT transport is given up.
        """
        if self._mqtt_unavailable is None:
            self._mqtt_unavailable = reason
            self._notify_availability(TransportType.CLOUD_MAMMOTION, reason)
        return ReLoginRequiredError(self._account_id, reason)

    def mark_transport_unavailable(self, transport_type: TransportType, reason: str) -> ReLoginRequiredError:
        """Give one cloud transport up after its own recovery was exhausted; the login is untouched.

        For a give-up found outside this manager — a broker that keeps refusing the
        bind after every refresh.  Idempotent; the first reason wins.
        """
        if transport_type is TransportType.CLOUD_ALIYUN:
            return self._mark_aliyun_unavailable(reason)
        return self._mark_mqtt_unavailable(reason)

    @property
    def unavailable_transports(self) -> dict[TransportType, str]:
        """Cloud transports given up for this account, with the reason for each."""
        flags = {
            TransportType.CLOUD_ALIYUN: self._aliyun_unavailable,
            TransportType.CLOUD_MAMMOTION: self._mqtt_unavailable,
        }
        return {transport_type: reason for transport_type, reason in flags.items() if reason is not None}

    def _notify_availability(self, transport_type: TransportType, reason: str | None) -> None:
        """Fire :attr:`on_transport_availability_changed` detached: callers may hold ``self._lock``."""
        if self.on_transport_availability_changed is None:
            return
        task = asyncio.ensure_future(self.on_transport_availability_changed(transport_type, reason))
        self._availability_tasks.add(task)
        task.add_done_callback(self._availability_tasks.discard)

    async def reestablish_aliyun(self, cloud_gateway: CloudIOTGateway) -> CloudIOTGateway:
        """Make one password-free attempt to mint a new Aliyun session; clear the give-up only on success.

        Raises whatever the attempt raised, leaving :attr:`aliyun_unavailable` as it was.
        """
        async with self._lock:
            gateway = await self.establish_aliyun(cloud_gateway)
        self._aliyun_pending = None
        self._aliyun_retries = 0
        if self._aliyun_unavailable is not None:
            self._aliyun_unavailable = None
            self._notify_availability(TransportType.CLOUD_ALIYUN, None)
        return gateway

    async def retry_mqtt_credentials(self) -> MQTTCredentials:
        """Make one attempt to fetch a Mammotion MQTT JWT after a give-up; clear it only on success.

        Raises whatever the attempt raised, leaving :attr:`mqtt_unavailable` as it was.
        """
        async with self._lock:
            creds = await self._refresh_mqtt(retrying=True)
        if self._mqtt_unavailable is not None:
            self._mqtt_unavailable = None
            self._notify_availability(TransportType.CLOUD_MAMMOTION, None)
        return creds

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

    # Renewal is clock-driven: every other path is lazy, and an account whose devices
    # are all offline makes no calls, so its credentials would otherwise rot.

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
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        # Let an in-flight quiesce finish rather than cancelling it: its tail is
        # the host's on_unrecoverable_auth_error, which clears the dead cached
        # credentials — cancelling mid-disconnect would skip that and let the next
        # restart spend the rejected refresh token again.  Never await it from
        # within itself (the quiesce path calls this method).
        reauth_task = self._reauth_task
        if reauth_task is not None and not reauth_task.done() and reauth_task is not asyncio.current_task():
            self._reauth_task = None
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await reauth_task

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
        # Credentials behind a terminal transport flag are excluded — mirroring
        # _refresh_due_credentials — so a given-up transport's permanently past-due
        # expiry doesn't wake the scheduler every retry interval forever.
        if (
            self._mqtt_unavailable is None
            and self._mqtt_creds is not None
            and (exp := self._expiry(self._mqtt_creds.expires_at)) is not None
        ):
            due_at.append(exp - _MQTT_REFRESH_LEAD)
        if (
            self._aliyun_unavailable is None
            and self._aliyun_creds is not None
            and (exp := self._expiry(self._aliyun_creds.iot_token_expires_at)) is not None
        ):
            due_at.append(exp - _ALIYUN_REFRESH_LEAD)
        if self._aliyun_pending is not None:
            due_at.append(self._aliyun_retry_at)
        if not due_at:
            return _MAX_SCHEDULER_SLEEP
        return max(0.0, min(min(due_at) - now, _MAX_SCHEDULER_SLEEP))

    def _http_refresh_due(self, now: float) -> bool:
        """Report whether the HTTP access token is inside its refresh lead at *now*."""
        http_exp = self._expiry(self._http.expires_in)
        return http_exp is not None and http_exp - _HTTP_REFRESH_LEAD <= now

    async def _refresh_due_credentials(self) -> bool:
        """Renew every credential currently within its lead window.

        Returns True when everything due was renewed successfully.  HTTP goes first:
        both the Mammotion JWT and the Aliyun session are minted using the HTTP
        access token, so renewing them against a stale bearer would just fail.
        """
        now = time.time()
        ok = True

        if self._http_refresh_due(now):
            _LOGGER.debug("token scheduler [%s]: HTTP access token due — refreshing", self._account_id)
            async with self._lock:
                # Another path may have refreshed while this one queued for the lock.
                if self._http_refresh_due(time.time()):
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

        if (pending := self._aliyun_pending) is not None and self._aliyun_retry_at <= now:
            _LOGGER.debug("token scheduler [%s]: retrying the deferred Aliyun session", self._account_id)
            self._aliyun_pending = None
            if (gateway := await self.recover_aliyun(pending)) is None:
                ok = False
            elif self.on_aliyun_established is not None:
                await self.on_aliyun_established(gateway)

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
                # A refresh that did not move the expiry (clock skew, same lifetime reissued) must not spin.
                if not progressed or self._seconds_until_next_refresh() <= 0:
                    await asyncio.sleep(_SCHEDULER_RETRY_DELAY)
            except asyncio.CancelledError:
                raise
            except ReLoginRequiredError:
                _LOGGER.warning("token scheduler [%s]: re-authentication required — stopping", self._account_id)
                return
            except RateLimitedError as exc:
                _LOGGER.warning("token scheduler [%s]: %s — pausing renewals", self._account_id, exc)
                await asyncio.sleep(exc.retry_after)
            except Exception:
                # Transient, never terminal: the credentials are probably still fine.
                _LOGGER.debug(
                    "token scheduler [%s]: refresh attempt failed — retrying in %.0fs",
                    self._account_id,
                    _SCHEDULER_RETRY_DELAY,
                    exc_info=True,
                )
                await asyncio.sleep(_SCHEDULER_RETRY_DELAY)

    def subscribe_handle(self, handle: DeviceHandle) -> None:
        """Subscribe to auth errors from *handle* and refresh credentials automatically.

        Keyed on the handle's ``device_id``
        One subscription per device; a new handle for a device replaces the
        old one's.
        """
        key = handle.device_id
        if (existing := self._handle_subscriptions.get(key)) is not None:
            if existing.handle is handle:
                return
            existing.subscription.cancel()

        async def _on_error(exc: Exception) -> None:
            try:
                if isinstance(exc, SessionExpiredError) and exc.transport_type == TransportType.CLOUD_MAMMOTION:
                    await self.refresh_mqtt_credentials()
                elif isinstance(exc, SessionExpiredError) and exc.transport_type == TransportType.CLOUD_ALIYUN:
                    await self.refresh_aliyun_credentials()
            except Exception:
                _LOGGER.debug("token manager [%s]: reactive refresh failed", self._account_id, exc_info=True)

        self._handle_subscriptions[key] = _HandleSubscription(handle, handle.subscribe_errors(_on_error))

    # ------------------------------------------------------------------
    # Private helpers — callers are responsible for holding self._lock.
    # ------------------------------------------------------------------

    async def _on_http_login_refreshed(self) -> None:
        """Mirror an HTTP-level token rotation into this manager's snapshot and persist it.

        Fired by MammotionHTTP after any oauth2/token exchange, including decorator
        refreshes that bypass this manager, so the cache never keeps a spent refresh
        token.  Lock-free: it fires while :meth:`refresh_http` already holds the lock.
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
            RateLimitedError: oauth2/token answered 429, or its cooldown is running.
                Marks nothing; every refresh path passes it through unchanged.

        """
        self._raise_if_reauth_required()
        self._adopt_http_reauth()
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
            self._mark_reauth_required("HTTP refresh token rejected")
            raise
        except RateLimitedError:
            raise
        except Exception as exc:
            if is_transient_network_error(exc):
                raise
            raise self._mark_reauth_required(str(exc)) from exc
        # The rotation fired _on_http_login_refreshed, which persists it.

    async def _refresh_aliyun(self) -> None:
        """Refresh the Aliyun IoT session, rebuilding it from the HTTP login on a 2401.

        A failed rebuild gives up the Aliyun transport only; the HTTP login, the
        Mammotion MQTT transport and the cached credentials stay.  Callers hold ``self._lock``.

        Raises:
            ReLoginRequiredError: The Aliyun session cannot be renewed.

        """
        if self._cloud_gateway is None:
            raise ReLoginRequiredError(self._account_id, "No Aliyun cloud gateway configured")
        if self._aliyun_unavailable is not None:
            raise ReLoginRequiredError(self._account_id, self._aliyun_unavailable)
        self._raise_if_reauth_required()
        try:
            await self._renew_aliyun_session(self._cloud_gateway)
            if (session := self._cloud_gateway.session_by_authcode_response) is None or session.data is None:
                raise ReLoginRequiredError(self._account_id, "Aliyun session data is None after refresh")
            await self._sync_aliyun_session()
        except ReLoginRequiredError:
            self._adopt_http_reauth()
            raise
        except RateLimitedError:
            raise
        except LoginException as exc:
            raise self._mark_aliyun_unavailable(str(exc)) from exc
        except Exception as exc:
            if is_transient_network_error(exc):
                raise
            raise self._mark_aliyun_unavailable(str(exc)) from exc

    async def _renew_aliyun_session(self, gateway: CloudIOTGateway) -> None:
        """Renew *gateway*'s session; a rejected refreshToken (2401) rebuilds it via the authCode chain."""
        try:
            await gateway.check_or_refresh_session(force=True)
        except SessionExpiredError as session_exc:
            try:
                await self.establish_aliyun()
            except Exception as rebuild_exc:
                if (
                    is_transient_network_error(rebuild_exc)
                    or isinstance(rebuild_exc, RateLimitedError)
                    or self._reauth_required is not None
                ):
                    raise
                raise self._mark_aliyun_unavailable(
                    f"Aliyun session rebuild failed after refreshToken rejection: {rebuild_exc}"
                ) from session_exc

    def _adopt_aliyun_session(self) -> AliyunCredentials | None:
        """Snapshot the attached gateway's current session as this manager's Aliyun credentials."""
        if self._cloud_gateway is None or (session := self._cloud_gateway.session_by_authcode_response) is None:
            return None
        if (data := session.data) is None:
            return None
        issued_at = self._cloud_gateway._iot_token_issued_at  # noqa: SLF001
        self._aliyun_creds = AliyunCredentials(
            iot_token=data.iotToken,
            iot_token_expires_at=issued_at + data.iotTokenExpire,
            refresh_token=data.refreshToken,
            refresh_token_expires_at=issued_at + data.refreshTokenExpire,
        )
        return self._aliyun_creds

    async def _sync_aliyun_session(self) -> None:
        """Adopt the gateway's session; a new iotToken goes to the transport's next bind and is persisted.

        Lock-free and idempotent: it runs both as the gateway's renewal hook (inside
        refreshes that already hold ``self._lock``) and after a refresh made here.
        """
        previous = self._aliyun_creds
        if (creds := self._adopt_aliyun_session()) is None:
            return
        if previous is not None and previous.iot_token == creds.iot_token:
            return
        if self.on_aliyun_token_refreshed is not None:
            self.on_aliyun_token_refreshed(creds.iot_token)
        await self._fire_credentials_updated()

    async def establish_aliyun(
        self, cloud_gateway: CloudIOTGateway | None = None, *, fresh_code: bool = True
    ) -> CloudIOTGateway:
        """Mint an Aliyun IoT session from the HTTP login via the authCode chain, and attach its gateway.

        The one place the chain runs: a fresh login, a restore whose cached session is
        unusable, and a runtime rebuild after a 2401 all come here.  No password is
        involved.  The gateway defaults to the attached one, rebuilt in place so the
        transport holding it sees the new session.

        Args:
            cloud_gateway: The gateway to establish; defaults to the attached one.
            fresh_code: Mint a new authorization code first.  Only a login that has just
                returned one may pass False — a code is spent by its first loginbyoauth.

        Raises:
            CloudSetupError: A step answered without the region, AEP or session it should have.

        """
        gateway = cloud_gateway or self._cloud_gateway
        if gateway is None:
            raise ReLoginRequiredError(self._account_id, "No Aliyun cloud gateway configured")
        if (login_info := self._http.login_info) is None:
            raise ReLoginRequiredError(self._account_id, "no HTTP login to mint an Aliyun session from")
        country_code = login_info.userInformation.domainAbbreviation
        if fresh_code:
            await self._mint_authorization_code()
        if gateway.region_response is None:
            await gateway.get_region(country_code)
        await gateway.connect()
        await gateway.login_by_oauth(country_code)
        await gateway.aep_handle()
        await gateway.session_by_auth_code()
        await gateway.list_binding_by_account()
        if (
            gateway.aep_response is None
            or gateway.region_response is None
            or gateway.session_by_authcode_response is None
            or gateway.session_by_authcode_response.data is None
        ):
            msg = "Aliyun setup incomplete — no AEP, region or session response"
            raise CloudSetupError(msg)
        if gateway is not self._cloud_gateway:
            self.attach_cloud_gateway(gateway)
        return gateway

    async def recover_aliyun(self, cloud_gateway: CloudIOTGateway) -> CloudIOTGateway | None:
        """Establish an Aliyun session for a restore, without letting its failure escape.

        Returns the gateway once established.  A transient failure defers it: the
        scheduler retries with a doubling delay and fires :attr:`on_aliyun_established`
        on success.  A throttle defers it to the end of its cooldown.  A refusal gives
        the Aliyun transport up (:attr:`aliyun_unavailable`).  Only an account-level
        rejection raises.
        """
        try:
            async with self._lock:
                gateway = await self.establish_aliyun(cloud_gateway)
        except RateLimitedError as exc:
            _LOGGER.warning("Aliyun session for %s deferred: %s", self._account_id, exc)
            self._aliyun_pending = cloud_gateway
            self._aliyun_retry_at = time.time() + exc.retry_after
            return None
        except Exception as exc:
            if self._reauth_required is not None:
                raise
            if is_transient_network_error(exc):
                delay = min(_SCHEDULER_RETRY_DELAY * 2**self._aliyun_retries, _MAX_ALIYUN_RETRY_DELAY)
                _LOGGER.warning(
                    "Aliyun session for %s unavailable (%s) — retrying in %.0fs", self._account_id, exc, delay
                )
                self._aliyun_pending = cloud_gateway
                self._aliyun_retry_at = time.time() + delay
                self._aliyun_retries += 1
            else:
                self._mark_aliyun_unavailable(f"Aliyun session could not be established: {exc}")
            return None
        self._aliyun_retries = 0
        return gateway

    async def _mint_authorization_code(self) -> None:
        """Fetch a fresh single-use authorization code with a bearer the server accepts.

        The expiry check comes first; a 401 means the bearer was revoked server-side,
        which earns one forced refresh and one retry.  A second 401 is the login itself.
        """
        try:
            await self._http.refresh_authorization_token()
        except UnauthorizedExceptionError:
            await self.refresh_http()
            await self._fetch_code_with_fresh_bearer()

    async def _fetch_code_with_fresh_bearer(self) -> None:
        """Fetch a code right after :meth:`refresh_http`; a 401 now means the login is dead."""
        try:
            await self._http.fetch_authorization_token()
        except UnauthorizedExceptionError as exc:
            raise self._mark_reauth_required(f"authorization code refused a freshly refreshed bearer: {exc}") from exc

    async def _force_refresh_bearer(self) -> None:
        """Renew the access token regardless of its expiry, then a code; a refused or throttled code is ignored."""
        await self.refresh_http()
        with contextlib.suppress(AuthorizationCodeError, RateLimitedError):
            await self._fetch_code_with_fresh_bearer()

    async def connect_iot(self) -> None:
        """Rebuild the attached gateway's Aliyun session; kept for callers of the old name."""
        await self.establish_aliyun()

    async def refresh_invoke_token(self, stale_token: str | None = None) -> None:
        """Renew the HTTP bearer used for ``mqtt_invoke`` after a 401, ignoring the local expiry clock.

        Args:
            stale_token: The access token the failed request used.  When the live token
                has moved on, another caller already refreshed, so this returns and the
                caller retries — a burst of 401s then costs one refresh, not one each.

        Raises:
            ReLoginRequiredError: The refresh token, or the refreshed bearer, was rejected.
                A transient failure propagates as itself.

        """
        async with self._lock:
            if stale_token is not None:
                login_info = self._http.login_info
                current = login_info.access_token if login_info is not None else None
                if current is not None and current != stale_token:
                    return
            await self._force_refresh_bearer()

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

    async def _refresh_mqtt(self, *, retrying: bool = False) -> MQTTCredentials:
        """Fetch a fresh Mammotion MQTT JWT.  Callers hold ``self._lock``.

        A refusal force-renews the access token once and retries, covering a
        server-side revocation the expiry clock cannot see.  A second refusal gives
        up the Mammotion MQTT transport only; the login and cached credentials stay.

        Raises:
            ReLoginRequiredError: The MQTT JWT cannot be renewed.  Transient
                network failures propagate as their own type instead.

        """
        self._raise_if_reauth_required()
        if self._mqtt_unavailable is not None and not retrying:
            raise ReLoginRequiredError(self._account_id, self._mqtt_unavailable)
        try:
            response = await self._http.get_mqtt_credentials()
            if response.data is None:
                await self._force_refresh_bearer()
                response = await self._http.get_mqtt_credentials()
                if response.data is None:
                    # Never fall back to the old snapshot: that loops 401 → refresh → 401.
                    raise self._mark_mqtt_unavailable("MQTT JWT endpoint returned no data after access-token refresh")
            creds = self._set_mqtt_creds(response.data)
        except ReLoginRequiredError:
            self._adopt_http_reauth()
            raise
        except RateLimitedError:
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
