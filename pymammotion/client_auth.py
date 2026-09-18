"""Cloud login, credential-cache restore and TokenManager lifecycle.

Split out of ``client.py`` for navigability, as a mixin rather than a collaborator.
That is deliberate: this code needs fourteen members of the client (the account
registry, the Aliyun/Mammotion transport builders, ``_quiesce_account``,
``_on_credentials_updated``, …) while three transport-construction sites call back
into ``_ensure_token_manager`` here.  The dependency is genuinely bidirectional —
the authCode chain that mints an Aliyun session *is* part of logging in — so a
separate object would need fourteen host hooks and still be re-entered from the
code it calls.  A mixin keeps ``self`` resolution and every invariant identical
while making both files readable.

The invariants this file owns (see CLAUDE.md):

* One account is one login session is one TokenManager, and
  :meth:`CloudAuthMixin._ensure_token_manager` is the only place one is constructed.
* Only :meth:`CloudAuthMixin.login_and_initiate_cloud` may reach a password grant.
  :meth:`CloudAuthMixin.restore_credentials` falls back to it only when the cache
  cannot produce a usable *login*.
* Credential renewal is clock-driven: :meth:`CloudAuthMixin._start_token_refresh`
  is called from the two public entry points, and stopped in ``_sign_out_session``
  and ``MammotionClient.stop``.
"""

from __future__ import annotations

from functools import partial
import logging
from typing import TYPE_CHECKING, Any

from pymammotion.account.registry import AccountSession
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.auth.token_manager import TokenManager
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import UnauthorizedExceptionError
from pymammotion.transport.base import AuthError, LoginFailedError, ReLoginRequiredError, TransportType

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from aiohttp import ClientSession

    from pymammotion.account.registry import AccountRegistry
    from pymammotion.transport.aliyun_mqtt import AliyunMQTTTransport


_logger = logging.getLogger(__name__)

#: Exceptions that mean "the server rejected this session", as opposed to a network
#: blip.  Best-effort blocks around token-bearing calls step over transient failures
#: but must re-raise these: a restore that swallowed one would report success on a
#: login the server has already invalidated.
_AUTH_REJECTED = (UnauthorizedExceptionError, ReLoginRequiredError, AuthError)


class CloudAuthMixin:
    """Login / restore / TokenManager lifecycle for :class:`~pymammotion.client.MammotionClient`.

    Not usable alone: it reads the account registry and calls the client's Aliyun /
    Mammotion transport builders, which in turn call back into
    :meth:`_ensure_token_manager` here.  The host surface is deliberately not
    re-declared on this class — duplicated signatures would shadow the real methods
    and drift from them; ``MammotionClient`` is the only implementer.
    """

    # Supplied by MammotionClient.  Signatures are copied from it verbatim, so a
    # change there that this file does not follow surfaces as an override error
    # rather than drifting silently.
    if TYPE_CHECKING:
        _account_registry: AccountRegistry
        _ha_version: str
        _stopped: bool
        _on_credentials_updated: Callable[[], Awaitable[None]] | None

        def _get_default_session(self) -> AccountSession | None: ...
        async def _detach_cloud_from_account(self, session: AccountSession, *, rekey: bool) -> None: ...
        async def _quiesce_account(self, session: AccountSession, reason: str, exc: Exception) -> None: ...
        async def _refresh_for_transport(
            self, transport_type: TransportType, session: AccountSession | None
        ) -> None: ...
        def _setup_aliyun_transport(
            self, cloud_client: CloudIOTGateway, acct_session: AccountSession
        ) -> AliyunMQTTTransport: ...
        async def _register_aliyun_device(
            self,
            device_name: str,
            iot_id: str,
            transport: AliyunMQTTTransport,
            user_account: int = 0,
            product_key: str = "",
            *,
            acct_session: AccountSession,
        ) -> None: ...
        async def _restore_aliyun(
            self,
            account: str,
            cached_data: dict[str, Any],
            acct_session: AccountSession,
            *,
            check_for_new_devices: bool,
        ) -> None: ...
        async def _restore_mammotion_mqtt(self, account: str, acct_session: AccountSession) -> None: ...
        async def _bootstrap_mammotion_mqtt(
            self,
            account: str,
            mammotion_http: MammotionHTTP,
            acct_session: AccountSession,
            owned_iot_id_map: dict[str, str],
            *,
            skip_ids: set[str] | None = None,
        ) -> None: ...
        @staticmethod
        async def _connect_iot(cloud_client: CloudIOTGateway) -> None: ...

    async def _sign_out_session(self, session: AccountSession, *, revoke: bool = True) -> None:
        """Disconnect transports and drop a single account session.

        Args:
            revoke: When True, also end the session server-side (HTTP logout +
                Aliyun sign-out).  Pass False when the session is being *replaced*
                by a fresh login.  A new login supersedes the old session on the
                server anyway, so revoking first buys nothing and opens a window in
                which the credentials still sitting in the host's cache are already
                dead: if the login — or the save that follows it — then fails, the
                account is stranded holding tokens that can only ever answer 401 and
                40102 "Refresh token has expired", recoverable solely by a manual
                re-login.

        """
        await self._detach_cloud_from_account(session, rekey=True)
        if session.aliyun_transport is not None:
            await session.aliyun_transport.disconnect()
            session.aliyun_transport = None
        if session.mammotion_transport is not None:
            await session.mammotion_transport.disconnect()
            session.mammotion_transport = None
        if session.mammotion_http is not None:
            if revoke:
                try:
                    await session.mammotion_http.logout()
                except Exception:  # noqa: BLE001
                    _logger.warning("HTTP logout failed — proceeding anyway", exc_info=True)
            session.mammotion_http = None
        if session.cloud_client is not None:
            if revoke:
                try:
                    await session.cloud_client.sign_out()
                except Exception:  # noqa: BLE001
                    _logger.warning("cloud sign_out failed — proceeding anyway", exc_info=True)
            session.cloud_client = None
        if session.token_manager is not None:
            await session.token_manager.stop_refresh_scheduler()
        session.token_manager = None
        await self._account_registry.unregister(session.account_id)

    async def _sign_out_existing_session(self, account_id: str | None = None, *, revoke: bool = True) -> None:
        """Disconnect active transports and sign out cloud session(s).

        Args:
            account_id: Sign out only this account.  When ``None``, sign out
                        all cloud sessions.  BLE transports are never touched:
                        a handle that owns one lives on unclaimed.
            revoke:     Whether to end the session server-side — see
                        :meth:`_sign_out_session`.

        """
        if account_id is not None:
            session = self._account_registry.get(account_id)
            if session is not None:
                await self._sign_out_session(session, revoke=revoke)
        else:
            for session in self._account_registry.all_sessions:
                await self._sign_out_session(session, revoke=revoke)
        self._stopped = False

    async def login_and_initiate_cloud(
        self,
        account: str,
        password: str,
        session: ClientSession | None = None,
    ) -> None:
        """Log in to the Mammotion cloud and register all account devices.

        Creates an :class:`AliyunMQTTTransport` for pre-2025 devices and/or a
        :class:`MQTTTransport` for post-2025 devices as required by the discovered
        device set.

        Args:
            account:  Mammotion account (email or phone number).
            password: Account password.
            session:  Optional :class:`aiohttp.ClientSession` to reuse.

        """
        # Tear the old session down locally but do NOT revoke it: login_v2 below
        # supersedes it server-side regardless, and revoking first would kill the
        # credentials the host still has cached before their replacement exists.
        await self._sign_out_existing_session(account, revoke=False)
        mammotion_http = MammotionHTTP(session=session, ha_version=self._ha_version)
        login_resp = await mammotion_http.login_v2(account, password)
        if login_resp.code != 0:
            raise LoginFailedError(account, login_resp.msg)

        device_list_owned_resp = await mammotion_http.get_user_device_list()
        device_list_resp = await mammotion_http.get_user_shared_device_page()
        if device_list_resp.data and device_list_resp.data.records:
            pending_by_batch: dict[str, list[int]] = {}
            for record in device_list_resp.data.records:
                if record.is_receiver == 1 and record.status == -1:
                    pending_by_batch.setdefault(record.batch_id, []).append(int(record.record_id))
            for batch_id, record_ids in pending_by_batch.items():
                await mammotion_http.confirm_share(batch_id, record_ids)

        device_page_resp = await mammotion_http.get_user_device_page()
        aliyun_devices = device_list_resp.data
        mammotion_records = (device_page_resp.data.records if device_page_resp.data else []) or []

        # Build an authoritative device_name→iot_id map from /device-server/v1/device/list.
        # This endpoint returns the canonical Mammotion iot_id for every owned device and
        # is used to correct stale or wrong iot_ids that may appear in the Aliyun binding
        # list or the Mammotion device-page records (particularly for RTK base stations).
        owned_iot_id_map: dict[str, str] = {
            d.device_name: d.iot_id for d in (device_list_owned_resp.data or []) if d.device_name and d.iot_id
        }

        acct_session = AccountSession(
            account_id=account,
            email=account,
            password=password,
            mammotion_http=mammotion_http,
        )
        acct_session.user_account = self._extract_user_account(mammotion_http)

        if aliyun_devices:
            cloud_client = CloudIOTGateway(mammotion_http)
            await self._connect_iot(cloud_client)
            shared_notice = await cloud_client.get_shared_notice_list()
            if shared_notice.data and shared_notice.data.data:
                pending = [d.record_id for d in shared_notice.data.data if d.status == -1]
                if pending:
                    await cloud_client.confirm_share(pending)

            if cloud_client.aep_response is None or cloud_client.region_response is None:
                msg = "Aliyun setup incomplete — aep_response or region_response missing"
                raise RuntimeError(msg)
            if cloud_client.session_by_authcode_response.data is None:  # type: ignore
                msg = "Aliyun setup incomplete — session_by_authcode_response.data missing"
                raise RuntimeError(msg)

            acct_session.cloud_client = cloud_client
            token_manager = await self._ensure_token_manager(acct_session, mammotion_http)
            token_manager.attach_cloud_gateway(cloud_client)
            al_transport = self._setup_aliyun_transport(cloud_client, acct_session)
            acct_session.aliyun_transport = al_transport
            ua = acct_session.user_account
            for device in cloud_client.devices_by_account_response.data.data:  # type: ignore
                if device.device_name:
                    iot_id = owned_iot_id_map.get(device.device_name) or device.iot_id
                    await self._register_aliyun_device(
                        device.device_name, iot_id, al_transport, ua, device.product_key, acct_session=acct_session
                    )
            await al_transport.connect()

        if mammotion_records:
            await self._bootstrap_mammotion_mqtt(account, mammotion_http, acct_session, owned_iot_id_map)

        await self._account_registry.register(acct_session)
        self._start_token_refresh(acct_session)

    def to_cache(self) -> dict[str, Any]:
        """Serialize current cloud credentials to a cache dictionary.

        The returned dict can be passed to :meth:`restore_credentials` in a future
        session to skip re-authentication. If an Aliyun cloud client is active its
        full serialization is used (which already includes the Mammotion HTTP data).
        For a Mammotion-MQTT-only setup a minimal dict is produced instead.

        Returns an empty dict when no cloud session has been established yet, or
        when the session's login is terminally dead (``reauth_required``) —
        persisting rejected credentials would just make the next restore re-spend
        them on doomed refresh attempts.
        """
        session = self._get_default_session()
        raw: dict[str, Any] = {}
        if session is None:
            return {}
        if session.token_manager is not None and session.token_manager.reauth_required is not None:
            return {}
        if session.cloud_client is not None:
            raw = session.cloud_client.to_cache()
        if session.mammotion_http is not None:
            if session.mammotion_http.response is not None:
                raw["mammotion_data"] = session.mammotion_http.response
            if session.mammotion_http.mqtt_credentials is not None:
                raw["mammotion_mqtt"] = session.mammotion_http.mqtt_credentials
            if session.mammotion_http.jwt_info is not None:
                raw["mammotion_jwt_info"] = session.mammotion_http.jwt_info
            if session.mammotion_http.device_records.records:
                raw["mammotion_device_records"] = session.mammotion_http.device_records
        return raw

    async def restore_credentials(
        self,
        account: str,
        password: str,
        cached_data: dict[str, Any],
        session: ClientSession | None = None,
        *,
        check_for_new_devices: bool = True,
    ) -> None:
        """Restore a previous cloud session from a serialized cache dictionary.

        The account's HTTP login is restored and validated *first*, then handed to
        whichever transports the cache describes.  An account is one identity → one
        login session → one :class:`MammotionHTTP` → one :class:`TokenManager`, so a
        dead or corrupt login is discovered once, up front, instead of surfacing as a
        401 several calls into a transport restore.

        Known devices from the cache are registered immediately without any cloud
        round-trips.  When *check_for_new_devices* is True (the default) a single
        discovery call is made to pick up any devices added since the cache was saved.

        Handles both credential types transparently:

        * **Aliyun** (pre-2025 devices) — detected by the presence of ``aep_data``
          in *cached_data*.  Uses :meth:`CloudIOTGateway.from_cache` which also
          refreshes the IoT session token if it has expired.
        * **Mammotion MQTT** (post-2025 devices) — detected by the presence of
          ``mammotion_mqtt`` and ``mammotion_device_records`` in *cached_data*.

        Args:
            account:               Mammotion account e-mail or phone number.
            password:              Account password (used only if the cached login
                                   cannot be restored or is no longer accepted).
            cached_data:           Dict previously returned by :meth:`to_cache`.
            session:               Optional :class:`aiohttp.ClientSession` to reuse.
            check_for_new_devices: When True, run a lightweight discovery call after
                                   restoring known devices to register any new ones.

        Raises:
            LoginFailedError: The cached login was unusable and the fallback login
                was rejected.
            ClientError / TimeoutError / ConnectionError: The login could not be
                validated because the network or server is unavailable.  The cached
                credentials may well still be good, so the caller should back off and
                retry rather than treat this as an auth failure.

        """
        # Get or create the session for this account
        acct_session = self._account_registry.get(account)
        if acct_session is None:
            acct_session = AccountSession(account_id=account, email=account, password=password)
            await self._account_registry.register(acct_session)
        else:
            acct_session.password = password

        mammotion_http = MammotionHTTP.from_cache(
            cached_data, account, password, session=session, ha_version=self._ha_version
        )
        # Two distinct outcomes, and which one happened decides what the user should do:
        # a cache carrying no login at all is a first run or a wiped/rolled-back store,
        # while a rejected one means the session was invalidated server-side.  Neither
        # is recoverable from the cache, so both fall back to a full login — the one
        # sanctioned password grant.
        if mammotion_http is None:
            _logger.warning(
                "restore_credentials: falling back to a full login for %s — no usable login session in the cached "
                "data (mammotion_data %s; cached keys: %s)",
                account,
                "present but undecodable" if "mammotion_data" in cached_data else "missing",
                sorted(cached_data),
            )
            await self.login_and_initiate_cloud(account, password, session)
            return

        # Attach the session and its TokenManager BEFORE validating.  Validation can
        # rotate the tokens (ensure_token_valid refreshes near expiry), and the server
        # invalidates the old refresh token the moment a rotation succeeds — so a
        # rotation that isn't persisted strands the account: the cache keeps replaying a
        # spent refresh token and every later attempt comes back 40102 "Refresh token
        # has expired" on credentials that look perfectly fresh.  Only TokenManager wires
        # MammotionHTTP.on_login_refreshed to the host's persistence callback, so it has
        # to exist before the first refresh can happen.
        acct_session.mammotion_http = mammotion_http
        acct_session.user_account = self._extract_user_account(mammotion_http)
        await self._ensure_token_manager(acct_session, mammotion_http)

        if not await mammotion_http.validate_login():
            _logger.warning(
                "restore_credentials: falling back to a full login for %s — the server no longer accepts the "
                "cached login",
                account,
            )
            await self.login_and_initiate_cloud(account, password, session)
            return

        if "aep_data" in cached_data:
            await self._restore_aliyun(account, cached_data, acct_session, check_for_new_devices=check_for_new_devices)

        if "mammotion_mqtt" in cached_data and "mammotion_device_records" in cached_data:
            await self._restore_mammotion_mqtt(account, acct_session)

        # Accept pending shares, check for new post-2025 devices, and bootstrap/extend the
        # Mammotion MQTT transport as needed.  _bootstrap_mammotion_mqtt handles both
        # "no transport yet" (fresh credential fetch + connect) and "transport already
        # connected" (register only devices not in skip_ids) transparently.
        if check_for_new_devices and acct_session.mammotion_http is not None:
            try:
                owned_iot_id_map: dict[str, str] = {}
                try:
                    owned_resp = await acct_session.mammotion_http.get_user_device_list()
                    owned_iot_id_map = {
                        d.device_name: d.iot_id for d in (owned_resp.data or []) if d.device_name and d.iot_id
                    }
                except _AUTH_REJECTED:
                    # A rejected session is not a "couldn't fetch the map" problem —
                    # swallowing it here would let the restore finish and report
                    # success on a login the server has already invalidated.
                    raise
                except Exception:  # noqa: BLE001
                    _logger.warning(
                        "restore_credentials: failed to fetch iot_id map for Mammotion bootstrap", exc_info=True
                    )
                await self._bootstrap_mammotion_mqtt(
                    account,
                    acct_session.mammotion_http,
                    acct_session,
                    owned_iot_id_map,
                    skip_ids=set(acct_session.device_ids),
                )
            except _AUTH_REJECTED:
                raise
            except Exception:  # noqa: BLE001
                _logger.warning("restore_credentials: Mammotion MQTT bootstrap failed", exc_info=True)

        self._start_token_refresh(acct_session)

    @staticmethod
    def _start_token_refresh(session: AccountSession) -> None:
        """Begin clock-driven credential renewal for *session*.

        Called from the two public entry points (login and cache restore) rather than
        at each ``TokenManager`` construction site, so every path that establishes a
        cloud session gets it exactly once.

        This is what keeps an account alive when all of its devices are offline: with
        nothing to send, no HTTP call is made, so none of the lazy refresh paths ever
        fire and the credentials would rot until the refresh tokens themselves
        expired.
        """
        if session.token_manager is None:
            return
        session.token_manager.start_refresh_scheduler()
        _logger.debug(
            "Token refresh scheduler started for %s — next check in %.0fs",
            session.account_id,
            session.token_manager.seconds_until_next_refresh,
        )

    async def _ensure_token_manager(self, acct_session: AccountSession, mammotion_http: MammotionHTTP) -> TokenManager:
        """Return the account's TokenManager, creating one only if it has none.

        One account is one login session is one TokenManager, and this is the single
        place that invariant is enforced.  A second manager for the same account is
        never harmless: the first keeps its refresh scheduler running (nothing stops it
        outside sign-out), so two schedulers rotate the same refresh token concurrently
        — and any transport built earlier still holds a reference to the old manager,
        so the terminal flags it sets land on an object the session no longer points at.

        Reuses the existing manager whenever it refreshes this exact login session,
        wiring the persistence callback and seeding its credential snapshots either way.
        """
        existing = acct_session.token_manager
        if existing is not None:
            if existing.http is mammotion_http:
                existing.on_credentials_updated = self._on_credentials_updated
                existing.on_reauth_required = partial(self._quiesce_account, acct_session)
                existing.seed_from_http()
                return existing
            # The account's login session was replaced (a full re-login).  The old
            # manager refreshes a session nothing reads any more — retire it rather
            # than leave its scheduler competing with the new one.  Its callbacks and
            # the transports still holding it go too: a 401 through an orphaned
            # transport would otherwise quiesce the *new* session via the old manager.
            _logger.debug(
                "Replacing TokenManager for %s — it holds a login session the account no longer uses",
                acct_session.account_id,
            )
            await existing.stop_refresh_scheduler()
            existing.on_reauth_required = None
            existing.on_credentials_updated = None
            if acct_session.aliyun_transport is not None:
                await acct_session.aliyun_transport.disconnect()
                acct_session.aliyun_transport = None
            if acct_session.mammotion_transport is not None:
                await acct_session.mammotion_transport.disconnect()
                acct_session.mammotion_transport = None

        token_manager = TokenManager(acct_session.account_id, mammotion_http)
        token_manager.on_credentials_updated = self._on_credentials_updated
        token_manager.on_reauth_required = partial(self._quiesce_account, acct_session)
        token_manager.seed_from_http()
        acct_session.token_manager = token_manager
        return token_manager

    @property
    def token_manager(self) -> TokenManager | None:
        """Return the active TokenManager, or None if no cloud session."""
        session = self._get_default_session()
        return session.token_manager if session else None

    @property
    def reauth_required(self) -> str | None:
        """Reason the account's login is terminally dead, or ``None`` while healthy.

        The host-facing view of ``TokenManager.reauth_required``: non-None means
        the HTTP refresh token was rejected, every cloud path for the account has
        been quiesced, and only a fresh user-initiated login can recover.
        """
        token_manager = self.token_manager
        return token_manager.reauth_required if token_manager is not None else None

    async def refresh_transport_credentials(self, transport_type: TransportType, account: str | None = None) -> None:
        """Refresh the credentials for one cloud transport of *account* (default session if omitted).

        The host-facing recovery call for a ``SessionExpiredError`` that names its
        transport — refreshing exactly the one that failed, so a dead Aliyun
        session never touches the Mammotion MQTT credentials or vice versa.

        Raises:
            ReLoginRequiredError: The credentials cannot be renewed — account-wide
                when :attr:`reauth_required` is set, otherwise scoped to this
                transport.

        """
        if (session := self._session_for(account, "refresh_transport_credentials")) is None:
            return
        await self._refresh_for_transport(transport_type, session)

    def _session_for(self, account: str | None, caller: str) -> AccountSession | None:
        """Resolve *account* to its session, or the default session when no account is named.

        A named account that is not registered is a no-op with a warning — never a
        fallback to the default session, which would refresh another account's
        credentials.
        """
        if account:
            if (session := self._account_registry.get(account)) is None:
                _logger.warning("%s: account=%s is not registered", caller, account)
            return session
        return self._get_default_session()

    async def refresh_login(self, account: str) -> None:
        """Refresh whichever cloud credentials *account* actually has.

        Routed by what the account is wired for, not by assumption: an Aliyun IoT
        session is refreshed only when the account has an Aliyun gateway, and the
        Mammotion MQTT JWT only when it has a Mammotion transport.  A hybrid
        account refreshes both; each is attempted independently so a failure on one
        does not skip the other.

        Previously this unconditionally refreshed Aliyun, which raised
        ``ReLoginRequiredError("No Aliyun cloud gateway configured")`` for every
        post-2025 (Mammotion-direct) account — the exact accounts for which it was
        the host's generic recovery call.

        Raises:
            ReLoginRequiredError: If every credential type the account has fails to
                refresh.  Re-authentication is required only when the account's HTTP
                login is itself dead — check ``TokenManager.reauth_required``.

        """
        if (session := self._session_for(account, "refresh_login")) is None:
            return
        if (token_manager := session.token_manager) is None:
            _logger.warning("refresh_login: no token manager available for account=%s", account)
            return

        refreshers: list[tuple[str, Callable[[], Awaitable[object]]]] = []
        if session.cloud_client is not None:
            refreshers.append(("aliyun", token_manager.refresh_aliyun_credentials))
        if session.mammotion_transport is not None:
            refreshers.append(("mammotion-mqtt", token_manager.refresh_mqtt_credentials))
        if not refreshers:
            _logger.debug("refresh_login: account=%s has no cloud transports to refresh", account)
            return

        failures: list[Exception] = []
        for name, refresh in refreshers:
            try:
                await refresh()
            except Exception as exc:  # noqa: BLE001 - each transport is independent
                _logger.warning("refresh_login: %s refresh failed for account=%s: %s", name, account, exc)
                failures.append(exc)
            else:
                _logger.info("refresh_login: %s credentials refreshed for account=%s", name, account)
        if len(failures) == len(refreshers):
            raise failures[0]

    # ------------------------------------------------------------------
    # Cloud — private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_user_account(mammotion_http: MammotionHTTP) -> int:
        """Extract the numeric user account from login_info, or 0."""
        if mammotion_http.login_info is not None:
            return int(mammotion_http.login_info.userInformation.userAccount)
        return 0
