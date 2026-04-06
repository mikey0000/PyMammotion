"""Unit tests for TokenManager credential refresh behaviour.

Verifies that:
- Expired (or near-expiry) tokens are refreshed proactively.
- Valid tokens are returned without triggering a refresh.
- force_refresh() refreshes all active credential types.
- Uninitialised credential types are skipped by force_refresh().
- ReLoginRequiredError is raised when the underlying API call fails.
- Concurrent calls do not trigger redundant refreshes (mutex).
- Broker unsolicited subscriptions survive a token refresh unaffected.
- MQTTTransport.send() raises AuthError on HTTP 401/460 responses.
"""

from __future__ import annotations

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
    http.refresh_token_v2.return_value = MagicMock(data=data)
    return http


def _make_mqtt_http_mock(
    host: str = "mqtt.new.example.com",
    client_id: str = "client-new",
    username: str = "user-new",
    jwt: str = "jwt-new",
) -> AsyncMock:
    """Return a MammotionHTTP mock whose get_mqtt_credentials returns valid data."""
    http = AsyncMock()
    # refresh_token_v2 used by _refresh_http
    http_data = MagicMock()
    http_data.access_token = "access-new"
    http_data.refresh_token = "refresh-new"
    http_data.expires_in = 3600.0
    http.refresh_token_v2.return_value = MagicMock(data=http_data)

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
    http.refresh_token_v2.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_valid_http_token_no_refresh_when_valid() -> None:
    """A freshly issued token (well within 5-minute window) must NOT trigger a refresh."""
    http = _make_http_mock()
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=_fresh_http_creds(ttl=3600), aliyun_creds=None, mqtt_creds=None)

    token = await tm.get_valid_http_token()

    assert token == "access-old"
    http.refresh_token_v2.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_valid_http_token_raises_on_api_failure() -> None:
    """When refresh_token_v2 raises, get_valid_http_token must raise ReLoginRequiredError."""
    http = AsyncMock()
    http.refresh_token_v2.side_effect = RuntimeError("network error")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    await tm.initialize(http_creds=None, aliyun_creds=None, mqtt_creds=None)

    with pytest.raises(ReLoginRequiredError) as exc_info:
        await tm.get_valid_http_token()

    assert exc_info.value.account_id == "user@example.com"


@pytest.mark.asyncio
async def test_get_valid_http_token_raises_when_data_is_none() -> None:
    """When refresh_token_v2 returns data=None, ReLoginRequiredError must be raised."""
    http = AsyncMock()
    http.refresh_token_v2.return_value = MagicMock(data=None)
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

    http.refresh_token_v2.assert_awaited_once()
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

    http.refresh_token_v2.assert_awaited_once()
    http.get_mqtt_credentials.assert_not_awaited()


@pytest.mark.asyncio
async def test_force_refresh_raises_re_login_required_on_failure() -> None:
    """force_refresh() must propagate ReLoginRequiredError when the HTTP refresh fails."""
    http = AsyncMock()
    http.refresh_token_v2.side_effect = RuntimeError("server error")
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
    http.refresh_token_v2.side_effect = slow_refresh
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
    transport = MQTTTransport(config=config, mammotion_http=http)

    with pytest.raises(AuthError):
        await transport.send(b"\x00\x01", iot_id="device-001")


@pytest.mark.asyncio
async def test_mqtt_transport_send_raises_transport_error_when_no_iot_id() -> None:
    """MQTTTransport.send() must raise TransportError immediately when iot_id is empty."""
    from pymammotion.transport.base import TransportError

    http = AsyncMock()
    config = MQTTTransportConfig(host="mqtt.example.com", client_id="c1", username="u", password="p")
    transport = MQTTTransport(config=config, mammotion_http=http)

    with pytest.raises(TransportError):
        await transport.send(b"\x00\x01", iot_id="")

    http.mqtt_invoke.assert_not_awaited()
