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
* Only :meth:`CloudAuthMixin.login_and_initiate_cloud` may reach a password grant;
  :meth:`CloudAuthMixin.restore_credentials` never does.
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
from pymammotion.transport.base import (
    AuthError,
    CachedLoginUnusableError,
    LoginFailedError,
    ReLoginRequiredError,
    TransportType,
    is_transient_network_error,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from aiohttp import ClientSession

    from pymammotion.account.registry import AccountRegistry
    from pymammotion.http.model.http import DeviceInfo, DeviceRecords
    from pymammotion.transport.aliyun_mqtt import AliyunMQTTTransport


_logger = logging.getLogger(__name__)

#: Exceptions that mean "the server rejected this session", as opposed to a network
#: blip.  Best-effort blocks around token-bearing calls step over transient failures
#: but must re-raise these: a restore that swallowed one would report success on a
#: login the server has already invalidated.
_AUTH_REJECTED = (UnauthorizedExceptionError, ReLoginRequiredError, AuthError)


async def _accept_pending_mammotion_shares(mammotion_http: MammotionHTTP) -> None:
    """Accept pending Mammotion share invitations; a failure leaves them for the next fetch."""
    try:
        shared_resp = await mammotion_http.get_user_shared_device_page()
        if not (shared_resp.data and shared_resp.data.records):
            return
        pending_by_batch: dict[str, list[int]] = {}
        for record in shared_resp.data.records:
            if record.is_receiver == 1 and record.status == -1:
                pending_by_batch.setdefault(record.batch_id, []).append(int(record.record_id))
        for batch_id, record_ids in pending_by_batch.items():
            await mammotion_http.confirm_share(batch_id, record_ids)
    except _AUTH_REJECTED:
        raise
    except Exception:
        _logger.warning("Could not accept pending Mammotion share invitations — continuing", exc_info=True)


async def _fetch_owned_devices(mammotion_http: MammotionHTTP) -> list[DeviceInfo] | None:
    """Fetch the devices the account owns, or ``None`` when the fetch failed."""
    try:
        owned_resp = await mammotion_http.get_user_device_list()
    except _AUTH_REJECTED:
        raise
    except Exception:
        _logger.warning("Owned device list fetch failed", exc_info=True)
        return None
    if owned_resp.code != 0:
        _logger.warning("Owned device list fetch failed (code=%s)", owned_resp.code)
        return None
    return owned_resp.data or []


def _owned_iot_id_map(owned_devices: list[DeviceInfo] | None) -> dict[str, str]:
    """Map each owned device's name to its canonical iot_id."""
    return {d.device_name: d.iot_id for d in owned_devices or [] if d.device_name and d.iot_id}


async def _fetch_mammotion_device_page(mammotion_http: MammotionHTTP) -> DeviceRecords | None:
    """Fetch the account's device page, or ``None`` when the fetch failed and the held records stand."""
    try:
        page_resp = await mammotion_http.get_user_device_page()
    except _AUTH_REJECTED:
        raise
    except Exception:
        _logger.warning("Mammotion device page fetch failed — keeping the cached devices", exc_info=True)
        return None
    if page_resp.code != 0 or page_resp.data is None:
        _logger.warning("Mammotion device page fetch failed (code=%s) — keeping the cached devices", page_resp.code)
        return None
    return page_resp.data


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
        async def _on_aliyun_established(self, acct_session: AccountSession, cloud_client: CloudIOTGateway) -> None: ...
        async def _rebuild_mammotion_transport(self, acct_session: AccountSession) -> None: ...
        async def _relay_transport_availability(
            self, session: AccountSession, transport_type: TransportType, reason: str | None
        ) -> None: ...

        on_transport_availability_changed: Callable[[str, TransportType, bool, str | None], Awaitable[None]] | None

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
        ) -> bool: ...
        async def _restore_aliyun(
            self,
            account: str,
            cached_data: dict[str, Any],
            acct_session: AccountSession,
            *,
            check_for_new_devices: bool,
        ) -> None: ...
        async def _restore_mammotion_mqtt(
            self, account: str, acct_session: AccountSession
        ) -> list[DeviceInfo] | None: ...
        async def _bootstrap_mammotion_mqtt(
            self,
            account: str,
            mammotion_http: MammotionHTTP,
            acct_session: AccountSession,
            owned_iot_id_map: dict[str, str],
            *,
            skip_ids: set[str] | None = None,
        ) -> None: ...

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
                except Exception:
                    _logger.warning("HTTP logout failed — proceeding anyway", exc_info=True)
            session.mammotion_http = None
        if session.cloud_client is not None:
            if revoke:
                try:
                    await session.cloud_client.sign_out()
                except Exception:
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
        device set.  The only password grant in the library: call it on a user action.

        A login can be partial: when one platform refuses while the other binds
        devices, the refused transport is in :meth:`unavailable_transports` (and
        ``on_transport_availability_changed`` fires), so a host can decline to save
        a half-built cache.

        Args:
            account:  Mammotion account (email or phone number).
            password: Account password.
            session:  Optional :class:`aiohttp.ClientSession` to reuse.

        Raises:
            LoginFailedError: The password grant was refused.
            CloudSetupError / LoginException: The Aliyun chain was refused and no
                Mammotion device was bound either.
            ClientError / TimeoutError / ConnectionError: A network fault, on either
                platform; nothing is half-registered, and a retry may succeed.

        """
        given_up = self.unavailable_transports(account)
        # Not revoked: login_v2 supersedes it, and revoking would kill the host's cached credentials first.
        await self._sign_out_existing_session(account, revoke=False)
        mammotion_http = MammotionHTTP(session=session, ha_version=self._ha_version)
        login_resp = await mammotion_http.login_v2(account, password)
        if login_resp.code != 0:
            raise LoginFailedError(account, login_resp.msg)

        owned_devices = await _fetch_owned_devices(mammotion_http)
        await _accept_pending_mammotion_shares(mammotion_http)

        device_page = await _fetch_mammotion_device_page(mammotion_http)
        mammotion_records = (device_page.records if device_page else []) or []

        # The owned list's iot_ids are canonical; Aliyun bindings and device-page records can be stale.
        owned_iot_id_map = _owned_iot_id_map(owned_devices)

        acct_session = AccountSession(
            account_id=account,
            email=account,
            password=password,
            mammotion_http=mammotion_http,
        )
        acct_session.user_account = self._extract_user_account(mammotion_http)
        token_manager = await self._ensure_token_manager(acct_session, mammotion_http)

        cloud_client, aliyun_error = await self._login_aliyun(account, token_manager)
        if cloud_client is not None:
            await self._connect_login_aliyun_transport(acct_session, cloud_client, owned_iot_id_map)

        if mammotion_records:
            if aliyun_error is not None:
                # A partial login: the host sees it in unavailable_transports and need not save it.
                token_manager.mark_transport_unavailable(
                    TransportType.CLOUD_ALIYUN, f"Aliyun login failed: {aliyun_error}"
                )
            await self._bootstrap_mammotion_mqtt(account, mammotion_http, acct_session, owned_iot_id_map)
        elif aliyun_error is not None:
            raise aliyun_error

        await self._account_registry.register(acct_session)
        self._start_token_refresh(acct_session)
        # The old session's give-ups went with it; tell the host which this login cured.
        for transport_type in given_up.keys() - token_manager.unavailable_transports.keys():
            await self._relay_transport_availability(acct_session, transport_type, None)

    async def _login_aliyun(
        self, account: str, token_manager: TokenManager
    ) -> tuple[CloudIOTGateway | None, Exception | None]:
        """Establish the login's Aliyun session: the gateway, or the refusal that leaves the login partial.

        A transient failure is raised so the host retries the whole login.
        """
        # The app starts its Aliyun login from this code alone (IOTConnectViewModel.iotLogin).
        if (login_info := token_manager.http.login_info) is None or not login_info.authorization_code:
            return None, None
        try:
            return await self._connect_aliyun_for_login(token_manager), None
        except _AUTH_REJECTED:
            raise
        except Exception as exc:
            if is_transient_network_error(exc):
                raise
            _logger.warning("login: Aliyun setup failed for %s", account, exc_info=True)
            return None, exc

    async def _connect_login_aliyun_transport(
        self, acct_session: AccountSession, cloud_client: CloudIOTGateway, owned_iot_id_map: dict[str, str]
    ) -> None:
        """Bind the login's Aliyun devices to a new transport and connect it, even with none bound."""
        acct_session.cloud_client = cloud_client
        transport = self._setup_aliyun_transport(cloud_client, acct_session)
        acct_session.aliyun_transport = transport
        for device in cloud_client.devices_by_account_response.data.data:  # type: ignore
            if device.device_name:
                iot_id = owned_iot_id_map.get(device.device_name) or device.iot_id
                await self._register_aliyun_device(
                    device.device_name,
                    iot_id,
                    transport,
                    acct_session.user_account,
                    device.product_key,
                    acct_session=acct_session,
                )
        await transport.connect()

    @staticmethod
    async def _connect_aliyun_for_login(token_manager: TokenManager) -> CloudIOTGateway:
        """Run the Aliyun chain on the login's own code and accept any pending Aliyun shares."""
        cloud_client = await token_manager.establish_aliyun(CloudIOTGateway(token_manager.http), fresh_code=False)
        shared_notice = await cloud_client.get_shared_notice_list()
        if shared_notice.data and shared_notice.data.data:
            pending = [d.record_id for d in shared_notice.data.data if d.status == -1]
            if pending:
                await cloud_client.confirm_share(pending)
        return cloud_client

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
                # An empty list is written (a missing key keeps the host's cached records); unknown is not.
                if (records := session.mammotion_http.device_records) is not None:
                    raw["mammotion_device_records"] = records
            if session.mammotion_http.jwt_info is not None:
                raw["mammotion_jwt_info"] = session.mammotion_http.jwt_info
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

        * **Aliyun** (pre-2025 devices) — when ``aep_data`` is cached, or the account
          owns a device its Mammotion device page does not list.  The cached session
          is used if it holds, else one is minted from the login.
        * **Mammotion MQTT** (post-2025 devices) — detected by the presence of
          ``mammotion_mqtt`` and ``mammotion_device_records`` in *cached_data*.

        Never logs in with the password: a restore runs on the cached login or not at
        all, and only a user-initiated :meth:`login_and_initiate_cloud` may mint one.

        Args:
            account:               Mammotion account e-mail or phone number.
            password:              Account password — stored on the session for callers,
                                   never sent.
            cached_data:           Dict previously returned by :meth:`to_cache`.
            session:               Optional :class:`aiohttp.ClientSession` to reuse.
            check_for_new_devices: When True, run a lightweight discovery call after
                                   restoring known devices to register any new ones.

        Raises:
            CachedLoginUnusableError: The cache holds no usable login (missing or
                undecodable); the user must log in.
            ReLoginRequiredError: The server no longer accepts the cached login.
                ``reauth_required`` is set and ``on_unrecoverable_auth_error`` fires.
            ClientError / TimeoutError / ConnectionError: The login could not be
                validated because the network or server is unavailable.  The cached
                credentials may well still be good, so the caller should back off and
                retry rather than treat this as an auth failure.

        """
        acct_session = await self._restore_account_session(account, password)
        mammotion_http = self._restore_cached_login(account, password, cached_data, session)

        # Wired before validating: validation may rotate the refresh token, and only the
        # TokenManager persists a rotation — an unpersisted one strands the account.
        acct_session.mammotion_http = mammotion_http
        acct_session.user_account = self._extract_user_account(mammotion_http)
        token_manager = await self._ensure_token_manager(acct_session, mammotion_http)

        if not await mammotion_http.validate_login():
            _logger.warning("restore_credentials: the server no longer accepts the cached login for %s", account)
            raise token_manager.reject_login("the server no longer accepts the cached login")

        if "aep_data" in cached_data or self._expects_aliyun(mammotion_http):
            await self._restore_aliyun(account, cached_data, acct_session, check_for_new_devices=check_for_new_devices)

        owned_devices: list[DeviceInfo] | None = None
        if "mammotion_mqtt" in cached_data and "mammotion_device_records" in cached_data:
            owned_devices = await self._restore_mammotion_mqtt(account, acct_session)

        if check_for_new_devices:
            await self._restore_new_mammotion_devices(account, acct_session, owned_devices)

        self._start_token_refresh(acct_session)

    async def _restore_account_session(self, account: str, password: str) -> AccountSession:
        """Return the account's registered session, registering a new one if it has none."""
        if (acct_session := self._account_registry.get(account)) is not None:
            acct_session.password = password
            return acct_session
        acct_session = AccountSession(account_id=account, email=account, password=password)
        await self._account_registry.register(acct_session)
        return acct_session

    def _restore_cached_login(
        self, account: str, password: str, cached_data: dict[str, Any], session: ClientSession | None
    ) -> MammotionHTTP:
        """Rebuild the cached HTTP login, or raise :class:`CachedLoginUnusableError` when the cache has none."""
        mammotion_http = MammotionHTTP.from_cache(
            cached_data, account, password, session=session, ha_version=self._ha_version
        )
        if mammotion_http is None:
            reason = (
                f"no usable login in the cached data (mammotion_data "
                f"{'present but undecodable' if 'mammotion_data' in cached_data else 'missing'})"
            )
            _logger.warning("restore_credentials: %s for %s — the user must log in", reason, account)
            raise CachedLoginUnusableError(account, reason)
        return mammotion_http

    async def _restore_new_mammotion_devices(
        self, account: str, acct_session: AccountSession, owned_devices: list[DeviceInfo] | None
    ) -> None:
        """Register Mammotion MQTT devices added since the cache was written, building the transport if needed."""
        if (mammotion_http := acct_session.mammotion_http) is None:
            return
        try:
            if owned_devices is None:
                owned_devices = await _fetch_owned_devices(mammotion_http)
            await self._bootstrap_mammotion_mqtt(
                account,
                mammotion_http,
                acct_session,
                _owned_iot_id_map(owned_devices),
                skip_ids=set(acct_session.device_ids),
            )
        except _AUTH_REJECTED:
            raise
        except Exception:
            _logger.warning("restore_credentials: Mammotion MQTT bootstrap failed", exc_info=True)

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
                existing.on_aliyun_established = partial(self._on_aliyun_established, acct_session)
                existing.on_transport_availability_changed = partial(self._relay_transport_availability, acct_session)
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
            existing.on_aliyun_established = None
            existing.on_transport_availability_changed = None
            if acct_session.aliyun_transport is not None:
                await acct_session.aliyun_transport.disconnect()
                acct_session.aliyun_transport = None
            if acct_session.mammotion_transport is not None:
                await acct_session.mammotion_transport.disconnect()
                acct_session.mammotion_transport = None

        token_manager = TokenManager(acct_session.account_id, mammotion_http)
        token_manager.on_credentials_updated = self._on_credentials_updated
        token_manager.on_reauth_required = partial(self._quiesce_account, acct_session)
        token_manager.on_aliyun_established = partial(self._on_aliyun_established, acct_session)
        token_manager.on_transport_availability_changed = partial(self._relay_transport_availability, acct_session)
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

    def unavailable_transports(self, account_id: str) -> dict[TransportType, str]:
        """Return the cloud transports given up for *account_id*, with the reason for each.

        The query behind ``on_transport_availability_changed``: a host reconciles with it
        after a login or restore returns.  Empty while every transport is healthy, and
        for an account with no session.
        """
        session = self._account_registry.get(account_id)
        if session is None or session.token_manager is None:
            return {}
        return session.token_manager.unavailable_transports

    async def retry_transport(self, account_id: str, transport_type: TransportType) -> None:
        """Make one bounded, password-free attempt to bring a given-up cloud transport back.

        Aliyun is re-minted from the HTTP login's authCode chain; Mammotion MQTT fetches
        a new JWT.  On success the transport is rebuilt, its mowers re-attached, and
        ``on_transport_availability_changed`` fires with ``available`` True.  A no-op
        when the transport is not given up.

        Raises:
            ValueError: *account_id* has no cloud session.
            ReLoginRequiredError: The attempt was refused (the transport stays given up),
                or the account itself needs re-authentication (``reauth_required``).
            CloudSetupError / AuthorizationCodeError: The Aliyun chain refused a step.
            ClientError / TimeoutError / ConnectionError: The cloud could not be reached.

        """
        session = self._account_registry.get(account_id)
        if session is None or session.token_manager is None or session.mammotion_http is None:
            msg = f"account {account_id!r} has no cloud session"
            raise ValueError(msg)
        token_manager = session.token_manager
        if transport_type not in token_manager.unavailable_transports:
            return
        if transport_type is TransportType.CLOUD_ALIYUN:
            gateway = await token_manager.reestablish_aliyun(CloudIOTGateway(session.mammotion_http))
            await self._on_aliyun_established(session, gateway)
        else:
            await token_manager.retry_mqtt_credentials()
            await self._rebuild_mammotion_transport(session)

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
    def _expects_aliyun(mammotion_http: MammotionHTTP) -> bool:
        """Report whether the account owns a device its Mammotion device page does not list, i.e. an Aliyun one.

        Lets a restore establish Aliyun from the healthy login when the cache was saved
        without it (a login whose Aliyun half failed).
        """
        owned = {d.device_name for d in mammotion_http.device_info if d.device_name}
        records = mammotion_http.device_records
        return bool(owned - {r.device_name for r in records.records} if records is not None else owned)

    @staticmethod
    def _extract_user_account(mammotion_http: MammotionHTTP) -> int:
        """Extract the numeric user account from login_info, or 0."""
        if mammotion_http.login_info is not None:
            return int(mammotion_http.login_info.userInformation.userAccount)
        return 0
