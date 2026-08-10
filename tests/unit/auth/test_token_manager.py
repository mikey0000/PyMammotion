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


async def test_mqtt_creds_refreshed_when_expiring_soon() -> None:
    """get_mammotion_mqtt_credentials() must refresh when creds expire in < 30 min."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(600), None, make_mqtt_creds(900))  # expires in 15 min < 30 min
    tm._refresh_mqtt = AsyncMock()  # type: ignore[method-assign]
    await tm.get_mammotion_mqtt_credentials()
    tm._refresh_mqtt.assert_awaited_once()  # type: ignore[attr-defined]


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
    tm._refresh_mqtt = AsyncMock()  # type: ignore[method-assign]
    await tm.get_mammotion_mqtt_credentials()
    tm._refresh_mqtt.assert_not_awaited()  # type: ignore[attr-defined]


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
    """Return a MammotionHTTP mock whose refresh_token_v2 returns valid data."""
    http = AsyncMock()
    data = MagicMock()
    data.access_token = access_token
    data.refresh_token = refresh_token
    data.expires_in = expires_in
    http.refresh_token_v2.return_value = MagicMock(code=0, data=data)
    return http


def _make_mqtt_http_mock(
    host: str = "mqtt.new.example.com",
    client_id: str = "client-new",
    username: str = "user-new",
    jwt: str = "jwt-new",
) -> AsyncMock:
    """Return a MammotionHTTP mock whose get_mqtt_credentials returns valid data."""
    http = AsyncMock()
    # refresh_token_v2 used by refresh_http
    http_data = MagicMock()
    http_data.access_token = "access-new"
    http_data.refresh_token = "refresh-new"
    http_data.expires_in = 3600.0
    http.refresh_token_v2.return_value = MagicMock(code=0, data=http_data)

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
    http.refresh_token_v2.assert_awaited_once()
    http.login_v2.assert_not_called()
    http.fetch_authorization_token.assert_awaited_once()


# ---------------------------------------------------------------------------
# TokenManager — force_refresh
# ---------------------------------------------------------------------------


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

    http = AsyncMock()
    http.refresh_token_v2.side_effect = tracked_refresh
    http.get_mqtt_credentials.side_effect = tracked_mqtt

    tm = TokenManager(account_id="acc", mammotion_http=http)
    await tm.initialize(http_creds=None, aliyun_creds=None, mqtt_creds=_expiring_mqtt_creds(100))

    # Fire three concurrent refresh paths that all touch the HTTP client.
    await asyncio.gather(
        tm.refresh_mqtt_credentials(),
        tm.refresh_mqtt_credentials(),
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
        await tm.refresh_mqtt_credentials()

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
        await tm.refresh_mqtt_credentials()

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
    http.refresh_token_v2 = AsyncMock(return_value=MagicMock(code=0))
    tm = TokenManager(account_id="user@test", mammotion_http=http)
    return tm


def test_refresh_http_propagates_dns_failure(token_manager: TokenManager) -> None:
    """A DNS failure raised by the underlying HTTP refresh must surface as
    the original exception type — NOT wrapped as ReLoginRequiredError.

    This is the exact bug from the 2026-05-25 incident: gaierror got wrapped,
    triggering a destructive full re-login on every network blip.
    """
    dns_err = socket.gaierror(-3, "Temporary failure in name resolution")
    token_manager._http.refresh_token_v2.side_effect = dns_err

    with pytest.raises(socket.gaierror):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_http())


def test_refresh_http_propagates_aiohttp_connector_error(token_manager: TokenManager) -> None:
    """aiohttp.ClientConnectorDNSError isn't wrapped as ReLoginRequiredError."""

    class ClientConnectorDNSError(Exception):
        pass

    network_err = ClientConnectorDNSError("Cannot connect to host id.mammotion.com:443")
    token_manager._http.refresh_token_v2.side_effect = network_err

    with pytest.raises(ClientConnectorDNSError):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_http())


def test_refresh_http_wraps_genuine_auth_error(token_manager: TokenManager) -> None:
    """A non-network exception (e.g. ValueError from bad response parsing)
    is still wrapped as ReLoginRequiredError — the classifier must only
    short-circuit for transient network errors."""
    token_manager._http.refresh_token_v2.side_effect = ValueError("malformed response")

    with pytest.raises(ReLoginRequiredError):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_http())


def test_refresh_http_wraps_response_with_no_data(token_manager: TokenManager) -> None:
    """The explicit 'refresh_token_v2 returned no data' path still raises ReLoginRequiredError."""
    response = MagicMock()
    response.code = 0
    response.data = None
    token_manager._http.refresh_token_v2 = AsyncMock(return_value=response)

    with pytest.raises(ReLoginRequiredError):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_http())


# ---------------------------------------------------------------------------
# refresh_invoke_token — same classification rule applies
# ---------------------------------------------------------------------------


def test_refresh_invoke_token_propagates_dns_failure(token_manager: TokenManager) -> None:
    """refresh_invoke_token's generic-Exception path must let network errors through."""
    token_manager._http.refresh_token_v2 = AsyncMock(side_effect=socket.gaierror(-3, "dns"))
    token_manager._http.fetch_authorization_token = AsyncMock()

    with pytest.raises(socket.gaierror):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_invoke_token())


def test_refresh_invoke_token_dns_failure_leaves_account_usable(token_manager: TokenManager) -> None:
    """A network blip must not strand the account behind a re-auth prompt."""
    token_manager._http.refresh_token_v2 = AsyncMock(side_effect=socket.gaierror(-3, "dns"))
    token_manager._http.fetch_authorization_token = AsyncMock()

    with pytest.raises(socket.gaierror):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_invoke_token())

    assert token_manager.reauth_required is None


def test_refresh_invoke_token_wraps_non_network_error(token_manager: TokenManager) -> None:
    """Non-network exceptions still become AuthError."""
    token_manager._http.refresh_authorization_token = AsyncMock(side_effect=ValueError("bad"))

    with pytest.raises(AuthError):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_invoke_token())


# ---------------------------------------------------------------------------
# force_refresh — failure cooldown (oauth2/token hammering guard)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# on_login_refreshed — HTTP-level rotations are mirrored and persisted
# ---------------------------------------------------------------------------


def test_token_manager_wires_on_login_refreshed() -> None:
    """Constructing a TokenManager must subscribe it to HTTP-level token rotations."""
    http = MagicMock()
    tm = TokenManager("acc", http)

    assert http.on_login_refreshed == tm._on_http_login_refreshed


async def test_on_http_login_refreshed_syncs_snapshot_and_persists() -> None:
    """A decorator-driven refresh must update _http_creds and fire persistence.

    Without this, the rotation leaves the persisted cache holding a dead refresh
    token and the next restart falls back to a password login.
    """
    http = MagicMock()
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
    http = AsyncMock()
    data = MagicMock(access_token="a", refresh_token="r", expires_in=3600.0)
    http.refresh_token_v2.return_value = MagicMock(code=refresh_code, data=data if refresh_code == 0 else None)
    mqtt_data = MagicMock(host="h", client_id="c", username="u", jwt="jwt-ok")
    http.get_mqtt_credentials.return_value = MagicMock(data=mqtt_data)
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
    http = AsyncMock()
    http.login_info = MagicMock(access_token="tok-old")
    http.refresh_token_v2.return_value = MagicMock(
        code=0, data=MagicMock(access_token="tok-new", refresh_token="r", expires_in=3600.0)
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
# Scheduled refresh
#
# Every other refresh path is lazy — it runs because something asked for a
# credential.  When all of an account's devices are offline the poll loop stops
# sending, so no HTTP call is made, ensure_token_valid never fires, and the
# in-band Aliyun expiry check inside send_cloud_command never runs.  Without a
# clock-driven renewal the credentials rot until the *refresh* tokens expire and
# recovery needs the user.
# ---------------------------------------------------------------------------


def _tm_scheduled(
    *, http_ttl: float = 7200.0, mqtt_ttl: float | None = None, aliyun_ttl: float | None = None
) -> tuple[TokenManager, AsyncMock]:
    http = AsyncMock()
    http.expires_in = time.time() + http_ttl
    http.login_info = MagicMock(access_token="tok", refresh_token="ref")
    http.refresh_token_v2.return_value = MagicMock(
        code=0, data=MagicMock(access_token="tok2", refresh_token="ref2", expires_in=7200.0)
    )
    mqtt_data = MagicMock(host="h", client_id="c", username="u", jwt="jwt-new")
    http.get_mqtt_credentials.return_value = MagicMock(data=mqtt_data)
    gateway = MagicMock()
    gateway.check_or_refresh_session = AsyncMock()
    tm = TokenManager("user@example.com", http, cloud_gateway=gateway if aliyun_ttl is not None else None)
    if mqtt_ttl is not None:
        tm._mqtt_creds = MQTTCredentials("h", "c", "u", "j", time.time() + mqtt_ttl)  # noqa: SLF001
    if aliyun_ttl is not None:
        tm._aliyun_creds = AliyunCredentials("iot", time.time() + aliyun_ttl, "r", time.time() + 864000)  # noqa: SLF001
        session_data = MagicMock(iotToken="iot-new", iotTokenExpire=7200, refreshToken="r", refreshTokenExpire=86400)
        gateway.session_by_authcode_response = MagicMock(data=session_data)
        gateway._iot_token_issued_at = int(time.time())  # noqa: SLF001
    return tm, http


# ── when the next refresh is due ────────────────────────────────────────────


def test_next_refresh_uses_http_lead_time() -> None:
    """The HTTP token is renewed 5 minutes before it expires."""
    tm, _ = _tm_scheduled(http_ttl=3600.0)
    assert 3600 - 300 - 2 < tm.seconds_until_next_refresh <= 3600 - 300


def test_next_refresh_picks_the_earliest_credential() -> None:
    """Whichever expires soonest sets the wake-up, not the first one checked."""
    tm, _ = _tm_scheduled(http_ttl=86400.0, mqtt_ttl=3600.0)  # mqtt lead is 1800
    assert 3600 - 1800 - 2 < tm.seconds_until_next_refresh <= 3600 - 1800


def test_next_refresh_is_zero_when_already_due() -> None:
    tm, _ = _tm_scheduled(http_ttl=60.0)  # inside the 300s lead
    assert tm.seconds_until_next_refresh == 0.0


def test_next_refresh_is_capped() -> None:
    """A far-future expiry still re-checks hourly, so later credentials get picked up."""
    tm, _ = _tm_scheduled(http_ttl=86400.0 * 30)
    assert tm.seconds_until_next_refresh == 3600.0


def test_next_refresh_survives_unusable_expiry() -> None:
    """A malformed expiry must not kill the background task."""
    tm, http = _tm_scheduled()
    http.expires_in = "not a number"
    assert tm.seconds_until_next_refresh == 3600.0


# ── what gets refreshed ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_due_http_token_is_refreshed_with_no_api_traffic() -> None:
    """The case this exists for: nothing is being sent, yet the token still renews."""
    tm, http = _tm_scheduled(http_ttl=60.0)

    assert await tm._refresh_due_credentials() is True  # noqa: SLF001

    http.refresh_token_v2.assert_awaited_once()
    http.login_v2.assert_not_called()


@pytest.mark.asyncio
async def test_nothing_refreshed_when_nothing_is_due() -> None:
    tm, http = _tm_scheduled(http_ttl=7200.0, mqtt_ttl=86400.0)

    await tm._refresh_due_credentials()  # noqa: SLF001

    http.refresh_token_v2.assert_not_awaited()
    http.get_mqtt_credentials.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_the_due_credential_is_refreshed() -> None:
    """A due MQTT JWT must not drag the healthy HTTP token into a rotation."""
    tm, http = _tm_scheduled(http_ttl=86400.0, mqtt_ttl=60.0)

    await tm._refresh_due_credentials()  # noqa: SLF001

    http.get_mqtt_credentials.assert_awaited_once()
    http.refresh_token_v2.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_is_refreshed_before_the_credentials_derived_from_it() -> None:
    """Both due: the JWT is minted with the access token, so HTTP must go first."""
    tm, http = _tm_scheduled(http_ttl=60.0, mqtt_ttl=60.0)
    order: list[str] = []
    http.refresh_token_v2.side_effect = lambda *a, **k: (
        order.append("http"),
        MagicMock(code=0, data=MagicMock(access_token="t", refresh_token="r", expires_in=7200.0)),
    )[1]
    http.get_mqtt_credentials.side_effect = lambda *a, **k: (
        order.append("mqtt"),
        MagicMock(data=MagicMock(host="h", client_id="c", username="u", jwt="j")),
    )[1]

    await tm._refresh_due_credentials()  # noqa: SLF001

    assert order == ["http", "mqtt"]


@pytest.mark.asyncio
async def test_transport_scoped_failure_does_not_stop_other_refreshes() -> None:
    """A dead MQTT JWT must not prevent the Aliyun session from being renewed."""
    tm, http = _tm_scheduled(http_ttl=86400.0, mqtt_ttl=60.0, aliyun_ttl=60.0)
    http.get_mqtt_credentials = AsyncMock(return_value=MagicMock(data=None))

    assert await tm._refresh_due_credentials() is False  # noqa: SLF001

    assert tm.mqtt_unavailable is not None
    assert tm.reauth_required is None
    tm._cloud_gateway.check_or_refresh_session.assert_awaited()  # noqa: SLF001


# ── the loop ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scheduler_renews_a_due_token_then_sleeps() -> None:
    """End-to-end: start the loop with a due token and watch it renew, unprompted."""
    tm, http = _tm_scheduled(http_ttl=60.0)

    def _advance(*_a, **_k) -> MagicMock:
        http.expires_in = time.time() + 7200
        return MagicMock(code=0, data=MagicMock(access_token="t2", refresh_token="r2", expires_in=7200.0))

    http.refresh_token_v2.side_effect = _advance

    tm.start_refresh_scheduler()
    for _ in range(20):  # let the loop run until it settles into its sleep
        await asyncio.sleep(0)
        if http.refresh_token_v2.await_count:
            break
    await tm.stop_refresh_scheduler()

    http.refresh_token_v2.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduler_stops_once_the_account_needs_reauth() -> None:
    """A dead refresh token is terminal — no point waking up again."""
    tm, http = _tm_scheduled(http_ttl=60.0)
    http.refresh_token_v2.return_value = MagicMock(code=401, data=None)

    tm.start_refresh_scheduler()
    for _ in range(20):
        await asyncio.sleep(0)
        if tm._scheduler_task.done():  # noqa: SLF001
            break

    assert tm.reauth_required is not None
    assert tm._scheduler_task.done()  # noqa: SLF001
    await tm.stop_refresh_scheduler()


@pytest.mark.asyncio
async def test_scheduler_is_idempotent_and_cancellable() -> None:
    tm, _ = _tm_scheduled(http_ttl=7200.0)

    tm.start_refresh_scheduler()
    first = tm._scheduler_task  # noqa: SLF001
    tm.start_refresh_scheduler()
    assert tm._scheduler_task is first, "second start must not spawn a rival task"  # noqa: SLF001

    await tm.stop_refresh_scheduler()
    assert first.done()
    await tm.stop_refresh_scheduler()  # stopping twice is safe
