"""Tests for pymammotion.auth.token_manager.

Covers the credential getters and their fast paths, the refresh_mqtt /
refresh_aliyun / refresh_http semantics (strict refresh-token-only, never
login_v2), the two-tier terminal-flag model (account-scoped vs
transport-scoped), refresh_invoke_token with its stale-token dedup, the
on_reauth_required kill switch, and on_login_refreshed mirroring.

Scheduler behaviour lives in test_refresh_scheduler.py; transient-network-error
classification lives in test_network_errors.py.
"""

from __future__ import annotations

import asyncio
import socket
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.auth.token_manager import HTTPCredentials, TokenManager
from pymammotion.http.model.http import UnauthorizedExceptionError
from pymammotion.transport.base import ReLoginRequiredError
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig

from tests.unit.auth._helpers import (
    encode_jwt,
    make_aliyun_creds,
    make_http_creds,
    make_http_mock,
    make_mqtt_creds,
)


def _fresh_http_creds(ttl: float = 3600.0) -> HTTPCredentials:
    return make_http_creds(ttl, access_token="access-old", refresh_token="refresh-old")


async def test_relogin_error_has_account_id() -> None:
    """ReLoginRequiredError must expose account_id and include it in the message."""
    err = ReLoginRequiredError("my_account", "expired")
    assert err.account_id == "my_account"
    assert "my_account" in str(err)


async def test_get_aliyun_credentials_does_not_block_on_in_flight_refresh() -> None:
    """Fast path: aliyun getter must not wait on the lock when creds are valid."""
    http = make_http_mock()
    gateway = MagicMock()
    tm = TokenManager("acc1", http, cloud_gateway=gateway)
    creds = make_aliyun_creds(7200)  # 2 hours — well above 1-hour threshold
    await tm.initialize(make_http_creds(3600), creds, None)

    lock_held = asyncio.Event()
    release = asyncio.Event()

    async def hold_lock() -> None:
        async with tm._lock:  # noqa: SLF001
            lock_held.set()
            await release.wait()

    holder = asyncio.create_task(hold_lock())
    await lock_held.wait()

    result = await asyncio.wait_for(tm.get_aliyun_credentials(), timeout=0.5)
    assert result is creds

    release.set()
    await holder


async def test_get_mqtt_credentials_does_not_block_on_in_flight_refresh() -> None:
    """Fast path: mqtt getter must not wait on the lock when creds are valid."""
    http = make_http_mock()
    tm = TokenManager("acc1", http)
    mqtt = make_mqtt_creds(7200)  # 2 hours — above 30-min threshold
    await tm.initialize(make_http_creds(3600), None, mqtt)

    lock_held = asyncio.Event()
    release = asyncio.Event()

    async def hold_lock() -> None:
        async with tm._lock:  # noqa: SLF001
            lock_held.set()
            await release.wait()

    holder = asyncio.create_task(hold_lock())
    await lock_held.wait()

    result = await asyncio.wait_for(tm.get_mammotion_mqtt_credentials(), timeout=0.5)
    assert result is mqtt

    release.set()
    await holder


async def test_initialize_stores_credentials() -> None:
    """initialize() must store all three credential types."""
    http = make_http_mock()
    tm = TokenManager("acc1", http)
    http_creds = make_http_creds(3600)
    mqtt_creds = make_mqtt_creds(86400)
    aliyun_creds = make_aliyun_creds(7200)
    await tm.initialize(http_creds, aliyun_creds, mqtt_creds)
    assert tm._http_creds is http_creds
    assert tm._aliyun_creds is aliyun_creds
    assert tm._mqtt_creds is mqtt_creds


# ---------------------------------------------------------------------------
# TokenManager — MQTT credential refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_mammotion_mqtt_credentials_refreshes_when_near_expiry() -> None:
    """MQTT credentials expiring within 30 minutes must trigger a proactive refresh."""
    http = make_http_mock(refresh_code=0, mqtt_jwt="jwt-new")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(
        http_creds=_fresh_http_creds(),
        aliyun_creds=None,
        mqtt_creds=make_mqtt_creds(100, jwt="jwt-expiring"),
    )

    creds = await tm.get_mammotion_mqtt_credentials()

    assert creds.jwt == "jwt-new"
    http.get_mqtt_credentials.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_mammotion_mqtt_credentials_no_refresh_when_valid() -> None:
    """Fresh MQTT credentials must be returned without a network call."""
    http = make_http_mock(refresh_code=0, mqtt_jwt="jwt-new")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(
        http_creds=_fresh_http_creds(),
        aliyun_creds=None,
        mqtt_creds=make_mqtt_creds(86400, jwt="jwt-old"),
    )

    creds = await tm.get_mammotion_mqtt_credentials()

    assert creds.jwt == "jwt-old"
    http.get_mqtt_credentials.assert_not_awaited()


# ---------------------------------------------------------------------------
# MQTT JWT expiry is read from the token's exp claim, not a fixed 24h assumption
# ---------------------------------------------------------------------------


def test_jwt_expiry_reads_exp_claim() -> None:
    """_jwt_expiry returns the absolute exp claim from the token."""
    from pymammotion.auth.token_manager import _jwt_expiry

    exp = int(time.time()) + 7200
    assert _jwt_expiry(encode_jwt({"exp": exp})) == pytest.approx(exp)


def test_jwt_expiry_falls_back_for_opaque_token() -> None:
    """A non-JWT / undecodable token falls back to now + default_ttl."""
    from pymammotion.auth.token_manager import _jwt_expiry

    before = time.time()
    result = _jwt_expiry("not-a-jwt", default_ttl=123.0)
    assert before + 123.0 <= result <= time.time() + 123.0


def test_jwt_expiry_falls_back_when_exp_claim_absent() -> None:
    """A valid JWT without an exp claim falls back to now + default_ttl."""
    from pymammotion.auth.token_manager import _jwt_expiry

    before = time.time()
    result = _jwt_expiry(encode_jwt({"sub": "x"}), default_ttl=456.0)
    assert before + 456.0 <= result <= time.time() + 456.0


@pytest.mark.asyncio
async def test_refresh_mqtt_creds_sets_expiry_from_jwt_exp() -> None:
    """refresh_mqtt_creds must read expires_at from the JWT exp claim so proactive
    refresh tracks the broker's real lifetime rather than assuming 24 hours.
    """
    exp = int(time.time()) + 7200
    http = make_http_mock(refresh_code=0, mqtt_jwt=encode_jwt({"exp": exp}))
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    creds = await tm.refresh_mqtt_credentials()

    assert creds.expires_at == pytest.approx(exp)


@pytest.mark.asyncio
async def test_refresh_mqtt_creds_falls_back_to_24h_for_opaque_jwt() -> None:
    """An opaque (non-decodable) JWT keeps the 24h fallback so refresh still works."""
    http = make_http_mock(refresh_code=0, mqtt_jwt="opaque-token")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    before = time.time()
    creds = await tm.refresh_mqtt_credentials()

    assert before + 86400 <= creds.expires_at <= time.time() + 86400


# ---------------------------------------------------------------------------
# Strict Mammotion refresh — refresh-token only, never login_v2
# ---------------------------------------------------------------------------


def _make_strict_http_mock(*, refresh_code: int = 0, jwt: str = "jwt-strict") -> AsyncMock:
    """HTTP mock whose refresh_token_v2 + get_mqtt_credentials drive the strict path."""
    return make_http_mock(
        refresh_code=refresh_code,
        access_token="access-strict",
        refresh_token="refresh-strict",
        mqtt_jwt=jwt,
        mqtt_client_id="client-strict",
        mqtt_username="user-strict",
    )


@pytest.mark.asyncio
async def test_refresh_mqtt_credentials_never_calls_login_v2() -> None:
    """Renewing the MQTT JWT must never mint a session from the stored password."""
    http = _make_strict_http_mock(jwt="jwt-strict")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    creds = await tm.refresh_mqtt_credentials()

    assert creds.jwt == "jwt-strict"
    http.login_v2.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_mqtt_credentials_retries_once_via_refresh_token() -> None:
    """A refused JWT endpoint triggers ONE forced access-token renewal, then a retry.

    Covers the server-side revocation our local expiry clock cannot see: the first
    fetch comes back empty, so the access token is renewed via refresh_token_v2 (not
    a password login) and the fetch is retried.
    """
    http = _make_strict_http_mock(jwt="jwt-after-retry")
    empty, good = MagicMock(data=None), http.get_mqtt_credentials.return_value
    http.get_mqtt_credentials = AsyncMock(side_effect=[empty, good])
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    creds = await tm.refresh_mqtt_credentials()

    assert creds.jwt == "jwt-after-retry"
    http.refresh_token_v2.assert_awaited_once()
    http.login_v2.assert_not_called()
    assert http.get_mqtt_credentials.await_count == 2


@pytest.mark.asyncio
async def test_refresh_mqtt_credentials_raises_when_refresh_token_dead() -> None:
    """A rejected refresh token during the retry is terminal — and never a login_v2."""
    http = _make_strict_http_mock(refresh_code=401)
    http.get_mqtt_credentials = AsyncMock(return_value=MagicMock(data=None))
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_mqtt_credentials()
    http.login_v2.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_mqtt_credentials_strict_raises_when_jwt_endpoint_empty() -> None:
    """If the JWT endpoint returns no data after a token refresh, give up — no login_v2."""
    http = _make_strict_http_mock()
    http.get_mqtt_credentials.return_value = MagicMock(data=None)
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_mqtt_credentials()
    http.login_v2.assert_not_called()


@pytest.mark.asyncio
async def test_force_refresh_invoke_token_strict_uses_refresh_token_only() -> None:
    """allow_relogin=False must refresh via refresh_token_v2 (not refresh_login/login_v2)."""
    http = _make_strict_http_mock()
    http.fetch_authorization_token = AsyncMock()
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    await tm.refresh_invoke_token()

    http.refresh_token_v2.assert_awaited_once()
    http.login_v2.assert_not_called()
    http.fetch_authorization_token.assert_awaited_once()


# ---------------------------------------------------------------------------
# TokenManager — mutex / concurrency safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_mqtt_credentials_serialises_with_other_refresh_paths() -> None:
    """The public refresh_mqtt_credentials() (with -s) must hold the same lock as
    force_refresh()/refresh_aliyun_credentials() so concurrent refresh paths run
    sequentially, not in parallel.

    This is the lock the MQTT transport's _refresh_jwt callback (in client.py)
    relies on — without it, the pre-connect JWT refresh in MQTTTransport._run can
    race with TokenManager.force_refresh_invoke_token() or another coroutine's
    force_refresh(), and two concurrent HTTP token-refresh calls clobber each
    other's state.
    """
    overlap_max = 0
    active = 0

    async def tracked_refresh(*_args, **_kwargs) -> MagicMock:  # type: ignore[no-untyped-def]
        nonlocal active, overlap_max
        active += 1
        overlap_max = max(overlap_max, active)
        await asyncio.sleep(0.02)
        active -= 1
        data = MagicMock()
        data.access_token = "tok"
        data.refresh_token = "ref"
        data.expires_in = 3600.0
        return MagicMock(data=data)

    async def tracked_mqtt(*_args, **_kwargs) -> MagicMock:  # type: ignore[no-untyped-def]
        nonlocal active, overlap_max
        active += 1
        overlap_max = max(overlap_max, active)
        await asyncio.sleep(0.02)
        active -= 1
        d = MagicMock()
        d.host = "h"
        d.client_id = "c"
        d.username = "u"
        d.jwt = "jwt-fresh"
        return MagicMock(data=d)

    http = make_http_mock()
    http.refresh_token_v2.side_effect = tracked_refresh
    http.get_mqtt_credentials.side_effect = tracked_mqtt

    tm = TokenManager(account_id="acc", mammotion_http=http)
    await tm.initialize(http_creds=None, aliyun_creds=None, mqtt_creds=make_mqtt_creds(100, jwt="jwt-expiring"))

    # Fire three concurrent refresh paths that all touch the HTTP client.
    await asyncio.gather(
        tm.refresh_mqtt_credentials(),
        tm.refresh_mqtt_credentials(),
        tm.refresh_mqtt_credentials(),
    )

    # If the lock works, only one HTTP call is ever in flight at a time.
    assert overlap_max == 1, f"Concurrent refreshes overlapped (max active = {overlap_max})"


# ---------------------------------------------------------------------------
# MQTTTransport.send() raises AuthError on expired token response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [401, 460])
async def test_mqtt_transport_send_in_body_rejection_refreshes_once_then_gives_up(code: int) -> None:
    """A dead-token rejection gets exactly one invoke-token refresh and one retry, then the transport gives up.

    ``mqtt_invoke`` raises UnauthorizedExceptionError for every 401/460 shape (HTTP
    status or in-body); the transport must not need its own code check.  Previously
    a 460 raised a bare AuthError with no refresh and no give-up, so a persistently
    rejected token produced one failed invoke per poll tick forever.
    """
    from pymammotion.transport.base import NoTransportAvailableError

    http = make_http_mock(login_info=MagicMock(access_token="tok-sent"))
    http.mqtt_invoke.side_effect = UnauthorizedExceptionError(f"rejected (code={code})")
    token_manager = AsyncMock()

    config = MQTTTransportConfig(host="mqtt.example.com", client_id="c1", username="u", password="p")
    transport = MQTTTransport(config=config, mammotion_http=http, token_manager=token_manager)

    with pytest.raises(NoTransportAvailableError):
        await transport.send(b"\x00\x01", iot_id="device-001")

    token_manager.refresh_invoke_token.assert_awaited_once_with(stale_token="tok-sent")
    assert http.mqtt_invoke.await_count == 2
    assert transport.is_usable is False


# ---------------------------------------------------------------------------
# on_login_refreshed — HTTP-level rotations are mirrored and persisted
# ---------------------------------------------------------------------------


def test_token_manager_wires_on_login_refreshed() -> None:
    """Constructing a TokenManager must subscribe it to HTTP-level token rotations."""
    http = MagicMock()
    http.reauth_required = None
    tm = TokenManager("acc", http)

    assert http.on_login_refreshed == tm._on_http_login_refreshed


async def test_on_http_login_refreshed_syncs_snapshot_and_persists() -> None:
    """A decorator-driven refresh must update _http_creds and fire persistence.

    Without this, the rotation leaves the persisted cache holding a dead refresh
    token and the next restart falls back to a password login.
    """
    http = MagicMock()
    http.reauth_required = None
    http.login_info = MagicMock(access_token="rotated-tok", refresh_token="rotated-ref")
    http.expires_in = 1234567890.0
    tm = TokenManager("acc", http)
    tm.on_credentials_updated = AsyncMock()

    await tm._on_http_login_refreshed()

    assert tm._http_creds == HTTPCredentials(
        access_token="rotated-tok", refresh_token="rotated-ref", expires_at=1234567890.0
    )
    tm.on_credentials_updated.assert_awaited_once()


async def test_on_http_login_refreshed_noop_without_login_info() -> None:
    http = MagicMock()
    http.reauth_required = None
    http.login_info = None
    tm = TokenManager("acc", http)
    tm.on_credentials_updated = AsyncMock()

    await tm._on_http_login_refreshed()

    assert tm._http_creds is None
    tm.on_credentials_updated.assert_not_awaited()


# ---------------------------------------------------------------------------
# Two-tier failure model: account-scoped vs transport-scoped
#
# A dead HTTP refresh token means nothing about the account can be renewed —
# that is terminal and the user must re-authenticate.  A dead Aliyun IoT session
# or Mammotion MQTT JWT, while the HTTP login is still good, must give up on that
# ONE transport and leave the account's credentials and other transport alone.
# ---------------------------------------------------------------------------


def _tm_with_gateway(*, refresh_code: int = 0) -> tuple[TokenManager, AsyncMock, MagicMock]:
    """Build a TokenManager wired to both an HTTP client and an Aliyun gateway."""
    http = make_http_mock(
        refresh_code=refresh_code,
        access_token="a",
        refresh_token="r",
        mqtt_jwt="jwt-ok",
        mqtt_host="h",
        mqtt_client_id="c",
        mqtt_username="u",
    )
    gateway = MagicMock()
    gateway.check_or_refresh_session = AsyncMock()
    tm = TokenManager(account_id="user@example.com", mammotion_http=http, cloud_gateway=gateway)
    return tm, http, gateway


@pytest.mark.asyncio
async def test_rejected_http_refresh_token_is_account_terminal() -> None:
    """A dead refresh token marks the whole account — nothing can be renewed."""
    tm, http, _ = _tm_with_gateway(refresh_code=401)

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_http()

    assert tm.reauth_required is not None
    http.login_v2.assert_not_called()


@pytest.mark.asyncio
async def test_account_terminal_fails_fast_without_network() -> None:
    """Once terminal, further callers must not queue more doomed oauth2/token hits."""
    tm, http, _ = _tm_with_gateway(refresh_code=401)

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_http()
    first_calls = http.refresh_token_v2.await_count

    for _ in range(5):
        with pytest.raises(ReLoginRequiredError):
            await tm.refresh_http()

    assert http.refresh_token_v2.await_count == first_calls, "terminal state must not re-hit the network"


@pytest.mark.asyncio
async def test_dead_aliyun_session_does_not_mark_account_terminal() -> None:
    """Aliyun dying must not cost the user their login or the Mammotion transport."""
    tm, http, gateway = _tm_with_gateway()
    gateway.check_or_refresh_session = AsyncMock(side_effect=RuntimeError("aliyun is down for good"))

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_aliyun_credentials()

    assert tm.aliyun_unavailable is not None, "the Aliyun transport should be given up"
    assert tm.reauth_required is None, "the HTTP login is still valid — do not force re-auth"
    assert tm.mqtt_unavailable is None, "the Mammotion MQTT transport is unaffected"


@pytest.mark.asyncio
async def test_mammotion_mqtt_still_works_after_aliyun_dies() -> None:
    """The concrete consequence: a hybrid account keeps its post-2025 devices."""
    tm, http, gateway = _tm_with_gateway()
    gateway.check_or_refresh_session = AsyncMock(side_effect=RuntimeError("aliyun is down for good"))

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_aliyun_credentials()

    creds = await tm.refresh_mqtt_credentials()
    assert creds.jwt == "jwt-ok"


@pytest.mark.asyncio
async def test_dead_mqtt_jwt_does_not_mark_account_terminal() -> None:
    """The mirror case: MQTT dying leaves the login and Aliyun alone."""
    tm, http, _ = _tm_with_gateway()
    http.get_mqtt_credentials = AsyncMock(side_effect=RuntimeError("jwt endpoint is broken"))

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_mqtt_credentials()

    assert tm.mqtt_unavailable is not None
    assert tm.reauth_required is None
    assert tm.aliyun_unavailable is None


@pytest.mark.asyncio
async def test_transient_network_error_marks_nothing_terminal() -> None:
    """A blip must leave every credential type retryable."""
    tm, http, _ = _tm_with_gateway()
    http.refresh_token_v2.side_effect = socket.gaierror(-3, "dns")

    with pytest.raises(socket.gaierror):
        await tm.refresh_http()

    assert tm.reauth_required is None
    assert tm.aliyun_unavailable is None
    assert tm.mqtt_unavailable is None


@pytest.mark.asyncio
async def test_aliyun_2401_rebuilds_session_without_password() -> None:
    """A 2401 is recovered via the authCode chain (connect_iot), never login_v2."""
    from pymammotion.transport.base import SessionExpiredError, TransportType

    tm, http, gateway = _tm_with_gateway()
    gateway.check_or_refresh_session = AsyncMock(
        side_effect=SessionExpiredError(TransportType.CLOUD_ALIYUN, "2401 refreshToken invalid")
    )
    session_data = MagicMock(iotToken="iot-new", iotTokenExpire=7200, refreshToken="r", refreshTokenExpire=86400)
    gateway.session_by_authcode_response = MagicMock(data=session_data)
    gateway._iot_token_issued_at = int(time.time())
    tm.connect_iot = AsyncMock()  # type: ignore[method-assign]

    await tm.refresh_aliyun_credentials()

    tm.connect_iot.assert_awaited_once()
    http.login_v2.assert_not_called()
    assert tm.aliyun_unavailable is None


# ---------------------------------------------------------------------------
# Reactive 401 refresh is deduplicated by access token
#
# Ported from the Android app: SpecialCodeIntercepter.refreshToken() compares the
# failing request's Authorization header against the stored token *before*
# refreshing, so a burst of requests that all 401 on the same dead token produces
# one refresh, not one per request.  Each refresh rotates the refresh token
# server-side, so the duplicates actively race each other.
# ---------------------------------------------------------------------------


def _tm_for_invoke() -> tuple[TokenManager, AsyncMock]:
    http = make_http_mock(
        refresh_code=0,
        access_token="tok-new",
        refresh_token="r",
        login_info=MagicMock(access_token="tok-old"),
    )
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    return tm, http


@pytest.mark.asyncio
async def test_refresh_invoke_token_refreshes_when_token_unchanged() -> None:
    """The token that failed is still the live one — a real refresh is needed."""
    tm, http = _tm_for_invoke()

    await tm.refresh_invoke_token(stale_token="tok-old")

    http.refresh_token_v2.assert_awaited_once()
    http.fetch_authorization_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_invoke_token_skips_when_another_caller_already_refreshed() -> None:
    """The live token has moved on — retry with it instead of rotating again."""
    tm, http = _tm_for_invoke()
    http.login_info = MagicMock(access_token="tok-someone-else-minted")

    await tm.refresh_invoke_token(stale_token="tok-old")

    http.refresh_token_v2.assert_not_awaited()
    http.fetch_authorization_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_401s_produce_exactly_one_refresh() -> None:
    """The end-to-end property: N commands failing on one dead token → one rotation."""
    tm, http = _tm_for_invoke()

    async def _rotate(*_a, **_k) -> MagicMock:
        await asyncio.sleep(0)  # let the others pile up on the lock
        http.login_info = MagicMock(access_token="tok-new")
        return MagicMock(code=0, data=MagicMock(access_token="tok-new", refresh_token="r", expires_in=3600.0))

    http.refresh_token_v2.side_effect = _rotate

    await asyncio.gather(*(tm.refresh_invoke_token(stale_token="tok-old") for _ in range(5)))

    assert http.refresh_token_v2.await_count == 1


@pytest.mark.asyncio
async def test_refresh_invoke_token_without_stale_token_always_refreshes() -> None:
    """Callers that cannot say which token failed keep the old unconditional behaviour."""
    tm, http = _tm_for_invoke()
    http.login_info = MagicMock(access_token="something-different")

    await tm.refresh_invoke_token()

    http.refresh_token_v2.assert_awaited_once()


# ---------------------------------------------------------------------------
# on_reauth_required — the account kill switch fires once, on the flag transition
# ---------------------------------------------------------------------------


async def test_reauth_transition_fires_kill_switch_once() -> None:
    """A rejected HTTP refresh fires on_reauth_required exactly once and marks the HTTP layer."""
    http = make_http_mock()
    http.refresh_token_v2.return_value = MagicMock(code=2401, data=None)
    tm = TokenManager("acc1", http)
    on_reauth = AsyncMock()
    tm.on_reauth_required = on_reauth

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_http()
    assert tm._reauth_task is not None
    await tm._reauth_task

    on_reauth.assert_awaited_once()
    http.mark_reauth_required.assert_called_once()
    assert tm.reauth_required is not None

    # A second rejection must not fire the callback again.
    on_reauth.reset_mock()
    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_http()
    on_reauth.assert_not_awaited()


async def test_reauth_fires_via_refresh_invoke_token_401() -> None:
    """A 401 on the authorization-code fetch is account-terminal and fires the kill switch."""
    from pymammotion.http.model.http import UnauthorizedExceptionError

    http = make_http_mock(login_info=MagicMock(access_token="tok"))
    http.refresh_token_v2.return_value = MagicMock(code=0, data=MagicMock())
    http.fetch_authorization_token = AsyncMock(side_effect=UnauthorizedExceptionError("401"))
    tm = TokenManager("acc1", http)
    on_reauth = AsyncMock()
    tm.on_reauth_required = on_reauth

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_invoke_token()
    assert tm._reauth_task is not None
    await tm._reauth_task

    on_reauth.assert_awaited_once()


async def test_transport_scoped_marks_do_not_fire_kill_switch() -> None:
    """aliyun_unavailable / mqtt_unavailable are transport-scoped — the account survives."""
    http = make_http_mock()
    tm = TokenManager("acc1", http)
    on_reauth = AsyncMock()
    tm.on_reauth_required = on_reauth

    tm._mark_aliyun_unavailable("aliyun dead")
    tm._mark_mqtt_unavailable("mqtt dead")

    assert tm._reauth_task is None
    on_reauth.assert_not_awaited()
    http.mark_reauth_required.assert_not_called()
    assert tm.reauth_required is None


async def test_refresh_http_adopts_http_level_terminal_flag() -> None:
    """A rejection first seen by a decorated endpoint reaches the kill switch with no extra network."""
    http = make_http_mock()
    http.reauth_required = "refresh token rejected by oauth2/token (code=2401)"
    tm = TokenManager("acc1", http)
    on_reauth = AsyncMock()
    tm.on_reauth_required = on_reauth

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_http()
    assert tm._reauth_task is not None
    await tm._reauth_task

    on_reauth.assert_awaited_once()
    http.refresh_token_v2.assert_not_awaited()


async def test_stop_refresh_scheduler_lets_in_flight_quiesce_finish() -> None:
    """The quiesce's tail clears the host's dead cached credentials — it must not be cancelled."""
    http = make_http_mock()
    tm = TokenManager("acc1", http)
    started = asyncio.Event()
    finished = False

    async def _quiesce(_reason: str, _err: Exception) -> None:
        nonlocal finished
        started.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        finished = True

    tm.on_reauth_required = _quiesce
    tm._mark_reauth_required("dead refresh token")
    await started.wait()

    await tm.stop_refresh_scheduler()

    assert finished is True
    assert tm._reauth_task is None
