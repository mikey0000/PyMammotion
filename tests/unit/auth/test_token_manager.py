"""Tests for pymammotion.auth.token_manager."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.auth.token_manager import (
    AliyunCredentials,
    HTTPCredentials,
    MQTTCredentials,
    TokenManager,
)
from pymammotion.transport.base import ReLoginRequiredError


def make_http_creds(expires_in_seconds: float) -> HTTPCredentials:
    """Build an HTTPCredentials with the given expiry offset from now."""
    return HTTPCredentials(
        access_token="tok",
        refresh_token="ref",
        expires_at=time.time() + expires_in_seconds,
    )


def make_mqtt_creds(expires_in_seconds: float) -> MQTTCredentials:
    """Build a MQTTCredentials with the given expiry offset from now."""
    return MQTTCredentials(
        host="host",
        client_id="cid",
        username="user",
        jwt="jwt",
        expires_at=time.time() + expires_in_seconds,
    )


async def test_http_token_refreshed_when_expiring_soon() -> None:
    """get_valid_http_token() must call _refresh_http when creds expire in < 5 min."""
    http = AsyncMock()
    http.refresh_login = AsyncMock(
        return_value=MagicMock(
            data=MagicMock(access_token="new_tok", refresh_token="new_ref", expires_in=3600)
        )
    )
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(180), None, None)  # expires in 3 min
    # Patch _refresh_http to verify it's called
    tm.refresh_http = AsyncMock()  # type: ignore[method-assign]
    # Re-set creds to force refresh
    tm._http_creds = make_http_creds(180)
    await tm.get_valid_http_token()
    tm.refresh_http.assert_awaited_once()  # type: ignore[attr-defined]


async def test_http_token_not_refreshed_when_fresh() -> None:
    """get_valid_http_token() must NOT call _refresh_http when token is fresh."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(600), None, None)  # expires in 10 min
    tm.refresh_http = AsyncMock()  # type: ignore[method-assign]
    await tm.get_valid_http_token()
    tm.refresh_http.assert_not_awaited()  # type: ignore[attr-defined]


async def test_mqtt_creds_refreshed_when_expiring_soon() -> None:
    """get_mammotion_mqtt_credentials() must refresh when creds expire in < 30 min."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(600), None, make_mqtt_creds(900))  # expires in 15 min < 30 min
    tm.refresh_mqtt_creds = AsyncMock()  # type: ignore[method-assign]
    await tm.get_mammotion_mqtt_credentials()
    tm.refresh_mqtt_creds.assert_awaited_once()  # type: ignore[attr-defined]


async def test_concurrent_refresh_called_once() -> None:
    """Concurrent calls to get_valid_http_token() must only trigger one refresh."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(100), None, None)  # will refresh (< 300 s)

    refresh_count = 0

    async def counting_refresh() -> None:
        nonlocal refresh_count
        refresh_count += 1
        await asyncio.sleep(0.01)
        tm._http_creds = make_http_creds(3600)

    tm.refresh_http = counting_refresh  # type: ignore[method-assign]
    await asyncio.gather(
        tm.get_valid_http_token(),
        tm.get_valid_http_token(),
    )
    assert refresh_count == 1


async def test_force_refresh_raises_relogin_on_auth_failure() -> None:
    """force_refresh() must propagate ReLoginRequiredError from _refresh_http."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(100), None, None)

    async def failing_refresh() -> None:
        raise ReLoginRequiredError("acc1", "401")

    tm.refresh_http = failing_refresh  # type: ignore[method-assign]
    with pytest.raises(ReLoginRequiredError):
        await tm.force_refresh()


async def test_relogin_error_has_account_id() -> None:
    """ReLoginRequiredError must expose account_id and include it in the message."""
    err = ReLoginRequiredError("my_account", "expired")
    assert err.account_id == "my_account"
    assert "my_account" in str(err)


async def test_get_aliyun_credentials_raises_without_gateway() -> None:
    """get_aliyun_credentials() must raise RuntimeError when no gateway is configured."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(None, None, None)
    with pytest.raises(RuntimeError, match="No Aliyun cloud gateway configured"):
        await tm.get_aliyun_credentials()


async def test_mqtt_creds_not_refreshed_when_fresh() -> None:
    """get_mammotion_mqtt_credentials() must NOT refresh when creds are fresh (> 30 min)."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(600), None, make_mqtt_creds(7200))  # expires in 2 hours
    tm.refresh_mqtt_creds = AsyncMock()  # type: ignore[method-assign]
    await tm.get_mammotion_mqtt_credentials()
    tm.refresh_mqtt_creds.assert_not_awaited()  # type: ignore[attr-defined]


async def test_get_valid_http_token_does_not_block_on_in_flight_refresh() -> None:
    """Fast path: if creds are still valid, the getter must not wait on the lock.

    Regression: TokenManager._lock used to be acquired unconditionally, so a
    slow in-flight refresh of one credential type stalled every other caller
    that already had a usable token.
    """
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(3600), None, None)  # valid for 1 hour

    # Hold the lock from another coroutine for a long time.
    lock_held = asyncio.Event()
    release = asyncio.Event()

    async def hold_lock() -> None:
        async with tm._lock:  # noqa: SLF001
            lock_held.set()
            await release.wait()

    holder = asyncio.create_task(hold_lock())
    await lock_held.wait()

    # Fast path must complete without acquiring the lock.
    token = await asyncio.wait_for(tm.get_valid_http_token(), timeout=0.5)
    assert token == "tok"

    release.set()
    await holder


async def test_get_aliyun_credentials_does_not_block_on_in_flight_refresh() -> None:
    """Fast path: aliyun getter must not wait on the lock when creds are valid."""
    http = AsyncMock()
    gateway = MagicMock()
    tm = TokenManager("acc1", http, cloud_gateway=gateway)
    creds = AliyunCredentials(
        iot_token="iot",
        iot_token_expires_at=time.time() + 7200,  # 2 hours — well above 1-hour threshold
        refresh_token="ref",
        refresh_token_expires_at=time.time() + 86400,
    )
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
    http = AsyncMock()
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
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    http_creds = make_http_creds(3600)
    mqtt_creds = make_mqtt_creds(86400)
    aliyun_creds = AliyunCredentials(
        iot_token="iot",
        iot_token_expires_at=time.time() + 7200,
        refresh_token="ref",
        refresh_token_expires_at=time.time() + 86400,
    )
    await tm.initialize(http_creds, aliyun_creds, mqtt_creds)
    assert tm._http_creds is http_creds
    assert tm._aliyun_creds is aliyun_creds
    assert tm._mqtt_creds is mqtt_creds


# ===========================================================================
# Verifies that:
# ===========================================================================
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.auth.token_manager import (
    AliyunCredentials,
    HTTPCredentials,
    MQTTCredentials,
    TokenManager,
)
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.transport.base import AuthError, ReLoginRequiredError
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_http_creds(ttl: float = 3600.0) -> HTTPCredentials:
    return HTTPCredentials(
        access_token="access-old",
        refresh_token="refresh-old",
        expires_at=time.time() + ttl,
    )


def _expiring_http_creds(seconds_left: float = 100.0) -> HTTPCredentials:
    """Return credentials that expire within the 300-second refresh window."""
    return HTTPCredentials(
        access_token="access-expiring",
        refresh_token="refresh-expiring",
        expires_at=time.time() + seconds_left,
    )


def _fresh_mqtt_creds(ttl: float = 86400.0) -> MQTTCredentials:
    return MQTTCredentials(
        host="mqtt.example.com",
        client_id="client-1",
        username="user",
        jwt="jwt-old",
        expires_at=time.time() + ttl,
    )


def _expiring_mqtt_creds(seconds_left: float = 100.0) -> MQTTCredentials:
    return MQTTCredentials(
        host="mqtt.example.com",
        client_id="client-1",
        username="user",
        jwt="jwt-expiring",
        expires_at=time.time() + seconds_left,
    )


def _fresh_aliyun_creds(ttl: float = 7200.0) -> AliyunCredentials:
    return AliyunCredentials(
        iot_token="iot-old",
        iot_token_expires_at=time.time() + ttl,
        refresh_token="aliyun-refresh-old",
        refresh_token_expires_at=time.time() + ttl * 10,
    )


def _expiring_aliyun_creds(seconds_left: float = 100.0) -> AliyunCredentials:
    """Return Aliyun credentials that expire within the 3600-second refresh window."""
    return AliyunCredentials(
        iot_token="iot-expiring",
        iot_token_expires_at=time.time() + seconds_left,
        refresh_token="aliyun-refresh-expiring",
        refresh_token_expires_at=time.time() + 86400,
    )


def _make_http_mock(
    access_token: str = "access-new",
    refresh_token: str = "refresh-new",
    expires_in: float = 3600.0,
) -> AsyncMock:
    """Return a MammotionHTTP mock whose refresh_login returns valid data."""
    http = AsyncMock()
    data = MagicMock()
    data.access_token = access_token
    data.refresh_token = refresh_token
    data.expires_in = expires_in
    http.refresh_login.return_value = MagicMock(data=data)
    return http


def _make_mqtt_http_mock(
    host: str = "mqtt.new.example.com",
    client_id: str = "client-new",
    username: str = "user-new",
    jwt: str = "jwt-new",
) -> AsyncMock:
    """Return a MammotionHTTP mock whose get_mqtt_credentials returns valid data."""
    http = AsyncMock()
    # refresh_login used by refresh_http
    http_data = MagicMock()
    http_data.access_token = "access-new"
    http_data.refresh_token = "refresh-new"
    http_data.expires_in = 3600.0
    http.refresh_login.return_value = MagicMock(data=http_data)

    # get_mqtt_credentials
    mqtt_data = MagicMock()
    mqtt_data.host = host
    mqtt_data.client_id = client_id
    mqtt_data.username = username
    mqtt_data.jwt = jwt
    http.get_mqtt_credentials.return_value = MagicMock(data=mqtt_data)
    return http


# ---------------------------------------------------------------------------
# TokenManager — HTTP token refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_valid_http_token_refreshes_when_near_expiry() -> None:
    """Credentials expiring within 5 minutes must trigger a proactive refresh."""
    http = _make_http_mock(access_token="access-new")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_expiring_http_creds(seconds_left=100), aliyun_creds=None, mqtt_creds=None)

    token = await tm.get_valid_http_token()

    assert token == "access-new"
    http.refresh_login.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_valid_http_token_no_refresh_when_valid() -> None:
    """A freshly issued token (well within 5-minute window) must NOT trigger a refresh."""
    http = _make_http_mock()
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(ttl=3600), aliyun_creds=None, mqtt_creds=None)

    token = await tm.get_valid_http_token()

    assert token == "access-old"
    http.refresh_login.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_valid_http_token_raises_on_api_failure() -> None:
    """When refresh_login raises, get_valid_http_token must raise ReLoginRequiredError."""
    http = AsyncMock()
    http.refresh_login.side_effect = RuntimeError("network error")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=None, aliyun_creds=None, mqtt_creds=None)

    with pytest.raises(ReLoginRequiredError) as exc_info:
        await tm.get_valid_http_token()

    assert exc_info.value.account_id == "user@example.com"


@pytest.mark.asyncio
async def test_get_valid_http_token_raises_when_data_is_none() -> None:
    """When refresh_login returns data=None, ReLoginRequiredError must be raised."""
    http = AsyncMock()
    http.refresh_login.return_value = MagicMock(data=None)
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=None, aliyun_creds=None, mqtt_creds=None)

    with pytest.raises(ReLoginRequiredError):
        await tm.get_valid_http_token()


# ---------------------------------------------------------------------------
# TokenManager — MQTT credential refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_mammotion_mqtt_credentials_refreshes_when_near_expiry() -> None:
    """MQTT credentials expiring within 30 minutes must trigger a proactive refresh."""
    http = _make_mqtt_http_mock(jwt="jwt-new")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(
        http_creds=_fresh_http_creds(),
        aliyun_creds=None,
        mqtt_creds=_expiring_mqtt_creds(seconds_left=100),
    )

    creds = await tm.get_mammotion_mqtt_credentials()

    assert creds.jwt == "jwt-new"
    http.get_mqtt_credentials.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_mammotion_mqtt_credentials_no_refresh_when_valid() -> None:
    """Fresh MQTT credentials must be returned without a network call."""
    http = _make_mqtt_http_mock()
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(
        http_creds=_fresh_http_creds(),
        aliyun_creds=None,
        mqtt_creds=_fresh_mqtt_creds(ttl=86400),
    )

    creds = await tm.get_mammotion_mqtt_credentials()

    assert creds.jwt == "jwt-old"
    http.get_mqtt_credentials.assert_not_awaited()


# ---------------------------------------------------------------------------
# MQTT JWT expiry is read from the token's exp claim, not a fixed 24h assumption
# ---------------------------------------------------------------------------


def _encode_jwt(claims: dict) -> str:
    import jwt as _pyjwt

    return _pyjwt.encode(claims, "x" * 32, algorithm="HS256")


def test_jwt_expiry_reads_exp_claim() -> None:
    """_jwt_expiry returns the absolute exp claim from the token."""
    from pymammotion.auth.token_manager import _jwt_expiry

    exp = int(time.time()) + 7200
    assert _jwt_expiry(_encode_jwt({"exp": exp})) == pytest.approx(exp)


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
    result = _jwt_expiry(_encode_jwt({"sub": "x"}), default_ttl=456.0)
    assert before + 456.0 <= result <= time.time() + 456.0


@pytest.mark.asyncio
async def test_refresh_mqtt_creds_sets_expiry_from_jwt_exp() -> None:
    """refresh_mqtt_creds must read expires_at from the JWT exp claim so proactive
    refresh tracks the broker's real lifetime rather than assuming 24 hours.
    """
    exp = int(time.time()) + 7200
    http = _make_mqtt_http_mock(jwt=_encode_jwt({"exp": exp}))
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    creds = await tm.refresh_mqtt_credentials()

    assert creds.expires_at == pytest.approx(exp)


@pytest.mark.asyncio
async def test_refresh_mqtt_creds_falls_back_to_24h_for_opaque_jwt() -> None:
    """An opaque (non-decodable) JWT keeps the 24h fallback so refresh still works."""
    http = _make_mqtt_http_mock(jwt="opaque-token")
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
    http = AsyncMock()
    rt_data = MagicMock()
    rt_data.access_token = "access-strict"
    rt_data.refresh_token = "refresh-strict"
    rt_data.expires_in = 3600.0
    http.refresh_token_v2.return_value = MagicMock(code=refresh_code, data=rt_data if refresh_code == 0 else None)
    mqtt_data = MagicMock()
    mqtt_data.host = "mqtt.new.example.com"
    mqtt_data.client_id = "client-strict"
    mqtt_data.username = "user-strict"
    mqtt_data.jwt = jwt
    http.get_mqtt_credentials.return_value = MagicMock(data=mqtt_data)
    return http


@pytest.mark.asyncio
async def test_refresh_mqtt_credentials_strict_uses_refresh_token_not_login() -> None:
    """The strict path must use refresh_token_v2 and never call refresh_login/login_v2."""
    http = _make_strict_http_mock(jwt="jwt-strict")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    creds = await tm.refresh_mqtt_credentials_strict()

    assert creds.jwt == "jwt-strict"
    http.refresh_token_v2.assert_awaited_once()
    http.refresh_login.assert_not_called()
    http.login_v2.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_mqtt_credentials_strict_raises_when_refresh_token_dead() -> None:
    """If refresh_token_v2 returns a non-zero code, give up (ReLoginRequiredError) — no login_v2."""
    http = _make_strict_http_mock(refresh_code=401)
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_mqtt_credentials_strict()
    http.login_v2.assert_not_called()
    http.get_mqtt_credentials.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_mqtt_credentials_strict_raises_when_jwt_endpoint_empty() -> None:
    """If the JWT endpoint returns no data after a token refresh, give up — no login_v2."""
    http = _make_strict_http_mock()
    http.get_mqtt_credentials.return_value = MagicMock(data=None)
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_mqtt_credentials_strict()
    http.login_v2.assert_not_called()


@pytest.mark.asyncio
async def test_force_refresh_invoke_token_strict_uses_refresh_token_only() -> None:
    """allow_relogin=False must refresh via refresh_token_v2 (not refresh_login/login_v2)."""
    http = _make_strict_http_mock()
    http.fetch_authorization_token = AsyncMock()
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    await tm.force_refresh_invoke_token(allow_relogin=False)

    http.refresh_token_v2.assert_awaited_once()
    http.refresh_login.assert_not_called()
    http.login_v2.assert_not_called()
    http.fetch_authorization_token.assert_awaited_once()


# ---------------------------------------------------------------------------
# TokenManager — force_refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_force_refresh_refreshes_all_active_credentials() -> None:
    """force_refresh() must refresh HTTP and MQTT credentials when both are initialised."""
    http = _make_mqtt_http_mock(jwt="jwt-forced")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(
        http_creds=_fresh_http_creds(),
        aliyun_creds=None,
        mqtt_creds=_fresh_mqtt_creds(),
    )

    await tm.force_refresh()

    http.refresh_login.assert_awaited_once()
    http.get_mqtt_credentials.assert_awaited_once()

    new_creds = await tm.get_mammotion_mqtt_credentials()
    assert new_creds.jwt == "jwt-forced"


@pytest.mark.asyncio
async def test_force_refresh_skips_uninitialised_mqtt_credentials() -> None:
    """force_refresh() must not call get_mqtt_credentials if MQTT was never initialised."""
    http = _make_http_mock()
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    await tm.force_refresh()

    http.refresh_login.assert_awaited_once()
    http.get_mqtt_credentials.assert_not_awaited()


@pytest.mark.asyncio
async def test_force_refresh_raises_re_login_required_on_failure() -> None:
    """force_refresh() must propagate ReLoginRequiredError when the HTTP refresh fails."""
    http = AsyncMock()
    http.refresh_login.side_effect = RuntimeError("server error")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(), aliyun_creds=None, mqtt_creds=None)

    with pytest.raises(ReLoginRequiredError):
        await tm.force_refresh()


# ---------------------------------------------------------------------------
# TokenManager — mutex / concurrency safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_calls_trigger_single_refresh() -> None:
    """Two concurrent calls to get_valid_http_token must result in exactly one refresh."""
    refresh_count = 0

    async def slow_refresh() -> MagicMock:
        nonlocal refresh_count
        await asyncio.sleep(0.05)  # simulate latency
        refresh_count += 1
        data = MagicMock()
        data.access_token = f"access-{refresh_count}"
        data.refresh_token = "refresh-new"
        data.expires_in = 3600.0
        return MagicMock(data=data)

    http = AsyncMock()
    http.refresh_login.side_effect = slow_refresh
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    # Start with expired credentials so both calls want to refresh
    await tm.initialize(http_creds=None, aliyun_creds=None, mqtt_creds=None)

    results = await asyncio.gather(
        tm.get_valid_http_token(),
        tm.get_valid_http_token(),
    )

    # The lock serialises the calls — exactly one refresh happens, both return the same token
    assert refresh_count == 1
    assert results[0] == results[1]


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

    http = AsyncMock()
    http.refresh_login.side_effect = tracked_refresh
    http.get_mqtt_credentials.side_effect = tracked_mqtt

    tm = TokenManager(account_id="acc", mammotion_http=http)
    await tm.initialize(http_creds=None, aliyun_creds=None, mqtt_creds=_expiring_mqtt_creds(100))

    # Fire three concurrent refresh paths that all touch the HTTP client.
    await asyncio.gather(
        tm.refresh_mqtt_credentials(),
        tm.force_refresh(),
        tm.refresh_mqtt_credentials(),
    )

    # If the lock works, only one HTTP call is ever in flight at a time.
    assert overlap_max == 1, f"Concurrent refreshes overlapped (max active = {overlap_max})"


# ---------------------------------------------------------------------------
# Broker subscriptions survive token refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broker_subscriptions_survive_token_refresh() -> None:
    """Unsolicited subscriptions on DeviceMessageBroker must keep working after a
    TokenManager.force_refresh() call — the two are completely independent layers.
    """
    # Set up a broker with an active subscription
    broker = DeviceMessageBroker()
    received: list[object] = []

    async def _handler(msg: object) -> None:
        received.append(msg)

    with broker.subscribe_unsolicited(_handler):
        # Simulate a token refresh happening while the subscription is live
        http = _make_mqtt_http_mock()
        tm = TokenManager(account_id="user@example.com", mammotion_http=http)
        await tm.initialize(
            http_creds=_expiring_http_creds(seconds_left=100),
            aliyun_creds=None,
            mqtt_creds=_fresh_mqtt_creds(),
        )
        await tm.force_refresh()

        # Deliver an unsolicited message (no pending future → goes to event bus)
        sentinel = object()
        # Use a simple object that won't match any pending future field
        # We need to deliver it through the broker's on_message; since sentinel
        # has no protobuf structure, it falls through to the event bus.
        await broker._event_bus.emit(sentinel)  # noqa: SLF001

    # The subscription should have received the message
    assert len(received) == 1
    assert received[0] is sentinel


@pytest.mark.asyncio
async def test_broker_subscription_cancelled_after_context_exit() -> None:
    """A Subscription used as a context manager must unsubscribe on exit — subsequent
    messages must NOT be delivered to the cancelled handler.
    """
    broker = DeviceMessageBroker()
    received: list[object] = []

    async def _handler(msg: object) -> None:
        received.append(msg)

    with broker.subscribe_unsolicited(_handler):
        pass  # immediately exit the context

    # Emit after unsubscribe — handler must NOT be called
    await broker._event_bus.emit(object())  # noqa: SLF001

    assert received == []


@pytest.mark.asyncio
async def test_multiple_subscriptions_all_receive_after_token_refresh() -> None:
    """All active subscriptions must receive events after a token refresh."""
    broker = DeviceMessageBroker()
    calls_a: list[object] = []
    calls_b: list[object] = []

    async def handler_a(msg: object) -> None:
        calls_a.append(msg)

    async def handler_b(msg: object) -> None:
        calls_b.append(msg)

    sub_a = broker.subscribe_unsolicited(handler_a)
    sub_b = broker.subscribe_unsolicited(handler_b)

    try:
        # Simulate token refresh
        http = _make_http_mock()
        tm = TokenManager(account_id="user@example.com", mammotion_http=http)
        await tm.initialize(http_creds=_expiring_http_creds(100), aliyun_creds=None, mqtt_creds=None)
        await tm.force_refresh()

        sentinel = object()
        await broker._event_bus.emit(sentinel)  # noqa: SLF001

        assert len(calls_a) == 1
        assert calls_a[0] is sentinel
        assert len(calls_b) == 1
        assert calls_b[0] is sentinel
    finally:
        sub_a.cancel()
        sub_b.cancel()


# ---------------------------------------------------------------------------
# MQTTTransport.send() raises AuthError on expired token response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [401, 460])
async def test_mqtt_transport_send_raises_auth_error_on_expired_token(code: int) -> None:
    """MQTTTransport.send() must raise AuthError when the HTTP invoke API returns 401 or 460."""
    http = AsyncMock()
    http.mqtt_invoke.return_value = MagicMock(code=code, msg="token expired")

    config = MQTTTransportConfig(host="mqtt.example.com", client_id="c1", username="u", password="p")
    transport = MQTTTransport(config=config, mammotion_http=http, token_manager=AsyncMock())

    with pytest.raises(AuthError):
        await transport.send(b"\x00\x01", iot_id="device-001")


@pytest.mark.asyncio
async def test_mqtt_transport_send_raises_transport_error_when_no_iot_id() -> None:
    """MQTTTransport.send() must raise TransportError immediately when iot_id is empty."""
    from pymammotion.transport.base import TransportError

    http = AsyncMock()
    config = MQTTTransportConfig(host="mqtt.example.com", client_id="c1", username="u", password="p")
    transport = MQTTTransport(config=config, mammotion_http=http, token_manager=AsyncMock())

    with pytest.raises(TransportError):
        await transport.send(b"\x00\x01", iot_id="")

    http.mqtt_invoke.assert_not_awaited()


# ===========================================================================
# Regression: two concurrent callers on an expired token both fired HTTP
# ===========================================================================
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway


def _make_session(iot_token_expire: int = 72000, issued_at: int | None = None) -> MagicMock:
    """Build a minimal SessionByAuthCodeResponse mock."""
    data = MagicMock()
    data.iotToken = "tok_initial"
    data.iotTokenExpire = iot_token_expire
    data.refreshToken = "ref_initial"
    data.refreshTokenExpire = 720000
    data.identityId = "identity123"
    session = MagicMock()
    session.data = data
    session.token_issued_at = issued_at if issued_at is not None else int(time.time()) - iot_token_expire - 7200
    return session


def _make_expired_session() -> MagicMock:
    """Session whose iotToken expired more than 1 h ago."""
    return _make_session(iot_token_expire=1, issued_at=0)


def _make_fresh_session() -> MagicMock:
    """Session whose iotToken is valid for the next 20 h."""
    return _make_session(iot_token_expire=72000, issued_at=int(time.time()))


def _make_gateway(session: MagicMock) -> CloudIOTGateway:
    """Build a CloudIOTGateway with a mocked MammotionHTTP."""
    http = MagicMock()
    region = MagicMock()
    region.data.apiGatewayEndpoint = "https://api.example.com"
    gw = CloudIOTGateway.__new__(CloudIOTGateway)
    gw.mammotion_http = http
    gw._app_key = "key"
    gw._app_secret = "secret"
    gw.domain = "aliyun.example.com"
    gw.message_delay = 1
    gw._rate_limited_until = 0.0
    gw._rate_limit_backoff = 60.0
    gw._client_id = "cid"
    gw._device_sn = "sn"
    gw._utdid = "utdid"
    gw._connect_response = None
    gw._login_by_oauth_response = None
    gw._aep_response = None
    gw._session_by_authcode_response = session
    gw._region_response = region
    gw._devices_by_account_response = None
    gw._iot_token_issued_at = session.token_issued_at
    gw._refresh_lock = asyncio.Lock()
    return gw


async def test_concurrent_calls_only_refresh_once() -> None:
    """Two concurrent callers on an expired token must produce exactly one HTTP call.

    Before the fix: both coroutines called the HTTP endpoint, rotating the
    refreshToken twice and invalidating the first caller's iotToken.
    After the fix: the second waiter finds the token fresh and returns early.
    """
    gw = _make_gateway(_make_expired_session())

    http_call_count = 0
    fresh_session = _make_fresh_session()

    async def _fake_refresh(*_args, **_kwargs) -> MagicMock:
        nonlocal http_call_count
        http_call_count += 1
        await asyncio.sleep(0.02)  # simulate network latency so both enter concurrently
        # Update gateway state as a real HTTP call would
        gw._session_by_authcode_response = fresh_session
        gw._iot_token_issued_at = int(time.time())
        resp = MagicMock()
        resp.body = b'{"code":200,"data":{"iotToken":"new_tok","iotTokenExpire":72000,"refreshToken":"new_ref","refreshTokenExpire":720000,"identityId":"id"}}'
        resp.status_message = "OK"
        resp.headers = {}
        resp.status_code = 200
        return resp

    with patch(
        "pymammotion.aliyun.cloud_gateway.Client.async_do_request",
        side_effect=_fake_refresh,
    ):
        with patch(
            "pymammotion.aliyun.cloud_gateway.SessionByAuthCodeResponse.from_dict",
            return_value=fresh_session,
        ):
            await asyncio.gather(
                gw.check_or_refresh_session(force=True),
                gw.check_or_refresh_session(force=True),
            )

    assert http_call_count == 1, (
        f"Expected exactly 1 HTTP refresh call, got {http_call_count}. "
        "Race condition: both concurrent callers fired a token rotation."
    )


async def test_force_bypasses_freshness_check() -> None:
    """force=True must hit the network even when the local token clock says fresh.

    This covers the account-blocked / 460-on-fresh-token case: Aliyun has
    rejected the token server-side even though our expiry timestamp is fine.
    Without force=True the freshness re-check would skip the HTTP call, silently
    dropping every subsequent command indefinitely.
    """
    gw = _make_gateway(_make_fresh_session())  # token is locally fresh

    http_called = False

    async def _fake_refresh(*_args, **_kwargs) -> MagicMock:
        nonlocal http_called
        http_called = True
        resp = MagicMock()
        resp.body = b'{"code":200,"data":{"iotToken":"t","iotTokenExpire":72000,"refreshToken":"r","refreshTokenExpire":720000,"identityId":"i"}}'
        resp.status_message = "OK"
        resp.headers = {}
        resp.status_code = 200
        return resp

    with patch(
        "pymammotion.aliyun.cloud_gateway.Client.async_do_request",
        side_effect=_fake_refresh,
    ):
        with patch(
            "pymammotion.aliyun.cloud_gateway.SessionByAuthCodeResponse.from_dict",
            return_value=_make_fresh_session(),
        ):
            await gw.check_or_refresh_session(force=True)

    assert http_called, "force=True must bypass the freshness re-check and hit the network"


async def test_fresh_token_skips_http_call() -> None:
    """check_or_refresh_session must be a no-op when the token is already fresh."""
    gw = _make_gateway(_make_fresh_session())

    with patch(
        "pymammotion.aliyun.cloud_gateway.Client.async_do_request",
        new_callable=AsyncMock,
    ) as mock_http:
        await gw.check_or_refresh_session()

    mock_http.assert_not_called()


async def test_second_waiter_skips_after_first_refreshes() -> None:
    """After the first caller refreshes, the second must not make another HTTP call."""
    gw = _make_gateway(_make_expired_session())
    http_calls: list[str] = []
    fresh = _make_fresh_session()

    async def _fake_refresh(*_args, **_kwargs) -> MagicMock:
        http_calls.append("refresh")
        await asyncio.sleep(0.01)
        gw._session_by_authcode_response = fresh
        gw._iot_token_issued_at = int(time.time())
        resp = MagicMock()
        resp.body = b'{"code":200,"data":{"iotToken":"t","iotTokenExpire":72000,"refreshToken":"r","refreshTokenExpire":720000,"identityId":"i"}}'
        resp.status_message = "OK"
        resp.headers = {}
        resp.status_code = 200
        return resp

    with patch(
        "pymammotion.aliyun.cloud_gateway.Client.async_do_request",
        side_effect=_fake_refresh,
    ):
        with patch(
            "pymammotion.aliyun.cloud_gateway.SessionByAuthCodeResponse.from_dict",
            return_value=fresh,
        ):
            # Run sequentially to confirm the second is a genuine no-op (not just lucky timing)
            await gw.check_or_refresh_session()  # first: refreshes
            await gw.check_or_refresh_session()  # second: token is now fresh → skip

    assert len(http_calls) == 1


# ===========================================================================
# Regression for the 2026-05-25 production incident: a DNS resolution failure
# ===========================================================================
import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.auth.token_manager import TokenManager
from pymammotion.transport.base import (
    AuthError,
    ReLoginRequiredError,
    is_transient_network_error,
)


# ---------------------------------------------------------------------------
# Classifier — the single source of truth
# ---------------------------------------------------------------------------


def test_classifier_recognises_dns_failure() -> None:
    """socket.gaierror (the underlying DNS failure) must be transient."""
    exc = socket.gaierror(-3, "Temporary failure in name resolution")
    assert is_transient_network_error(exc) is True


def test_classifier_recognises_connection_error() -> None:
    """Standard library ConnectionError must be transient."""
    assert is_transient_network_error(ConnectionError("Connection refused")) is True
    assert is_transient_network_error(ConnectionResetError("reset")) is True
    assert is_transient_network_error(ConnectionRefusedError("refused")) is True


def test_classifier_recognises_timeout() -> None:
    """asyncio / built-in TimeoutError must be transient."""
    assert is_transient_network_error(TimeoutError("read timeout")) is True
    assert is_transient_network_error(asyncio.TimeoutError()) is True


def test_classifier_recognises_oserror() -> None:
    """Bare OSError (e.g. EHOSTUNREACH) must be transient."""
    assert is_transient_network_error(OSError(101, "Network is unreachable")) is True


def test_classifier_recognises_aiohttp_dns_error_by_name() -> None:
    """aiohttp.ClientConnectorDNSError isn't imported here to avoid a hard dep —
    classification must work by class-name match so unit tests don't need aiohttp."""

    class ClientConnectorDNSError(Exception):
        pass

    assert is_transient_network_error(ClientConnectorDNSError("dns fail")) is True


def test_classifier_recognises_aiohttp_client_connector_error_by_name() -> None:
    class ClientConnectorError(Exception):
        pass

    assert is_transient_network_error(ClientConnectorError("connector fail")) is True


def test_classifier_walks_cause_chain() -> None:
    """aiohttp typically wraps OSError; the classifier must follow __cause__."""
    cause = socket.gaierror(-3, "dns")
    wrapper = RuntimeError("outer")
    wrapper.__cause__ = cause
    assert is_transient_network_error(wrapper) is True


def test_classifier_rejects_unrelated_exceptions() -> None:
    """Auth-class and unrelated exceptions must NOT be classified as transient."""
    assert is_transient_network_error(ValueError("bad data")) is False
    assert is_transient_network_error(KeyError("missing")) is False
    assert is_transient_network_error(ReLoginRequiredError("acc", "expired token")) is False
    assert is_transient_network_error(AuthError("forbidden")) is False


# ---------------------------------------------------------------------------
# token_manager.refresh_http — DNS failure must propagate, not become
# ReLoginRequiredError
# ---------------------------------------------------------------------------


@pytest.fixture
def token_manager() -> TokenManager:
    """Minimal TokenManager — only the HTTP client is exercised here."""
    http = MagicMock()
    http.refresh_login = AsyncMock()
    tm = TokenManager(account_id="user@test", mammotion_http=http)
    return tm


def test_refresh_http_propagates_dns_failure(token_manager: TokenManager) -> None:
    """A DNS failure raised by the underlying HTTP refresh must surface as
    the original exception type — NOT wrapped as ReLoginRequiredError.

    This is the exact bug from the 2026-05-25 incident: gaierror got wrapped,
    triggering a destructive full re-login on every network blip.
    """
    dns_err = socket.gaierror(-3, "Temporary failure in name resolution")
    token_manager._http.refresh_login.side_effect = dns_err

    with pytest.raises(socket.gaierror):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_http())


def test_refresh_http_propagates_aiohttp_connector_error(token_manager: TokenManager) -> None:
    """aiohttp.ClientConnectorDNSError isn't wrapped as ReLoginRequiredError."""

    class ClientConnectorDNSError(Exception):
        pass

    network_err = ClientConnectorDNSError("Cannot connect to host id.mammotion.com:443")
    token_manager._http.refresh_login.side_effect = network_err

    with pytest.raises(ClientConnectorDNSError):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_http())


def test_refresh_http_wraps_genuine_auth_error(token_manager: TokenManager) -> None:
    """A non-network exception (e.g. ValueError from bad response parsing)
    is still wrapped as ReLoginRequiredError — the classifier must only
    short-circuit for transient network errors."""
    token_manager._http.refresh_login.side_effect = ValueError("malformed response")

    with pytest.raises(ReLoginRequiredError):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_http())


def test_refresh_http_wraps_response_with_no_data(token_manager: TokenManager) -> None:
    """The explicit 'refresh_login returned no data' path still raises ReLoginRequiredError."""
    response = MagicMock()
    response.data = None
    token_manager._http.refresh_login.return_value = response

    with pytest.raises(ReLoginRequiredError):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_http())


# ---------------------------------------------------------------------------
# refresh_invoke_token — same classification rule applies
# ---------------------------------------------------------------------------


def test_refresh_invoke_token_propagates_dns_failure(token_manager: TokenManager) -> None:
    """refresh_invoke_token's generic-Exception path must let network errors through."""
    token_manager._http.refresh_authorization_token = AsyncMock(
        side_effect=socket.gaierror(-3, "dns")
    )

    with pytest.raises(socket.gaierror):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_invoke_token())


def test_refresh_invoke_token_wraps_non_network_error(token_manager: TokenManager) -> None:
    """Non-network exceptions still become AuthError."""
    token_manager._http.refresh_authorization_token = AsyncMock(side_effect=ValueError("bad"))

    with pytest.raises(AuthError):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_invoke_token())
