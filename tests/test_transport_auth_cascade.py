"""End-to-end auth-error cascade tests for both MQTT transports.

Covers the two failure paths for each transport:

Mammotion MQTT (MQTTTransport)
    Path 1 — MQTT broker rejects credentials (rc=134):
        jwt_refresher raises ReLoginRequiredError
        → propagates from _run() task
        → on_fatal_auth_error is invoked

    Path 2 — mqtt_invoke HTTP API returns 401:
        UnauthorizedException → send() calls refresh_mqtt_token()
        → ReLoginRequiredError propagates from send() if token refresh fails
        → ReLoginRequiredError also raised if retry still returns 401

Aliyun MQTT (AliyunMQTTTransport)
    Only the cloud_gateway invoke path is relevant once connected
    (the MQTT broker connection itself is stable after initial handshake).

    cloud_gateway.send_cloud_command raises CheckSessionException
    → AliyunMQTTTransport.send() propagates it uncaught
    → _send_with_auth_retry catches SessionExpiredError(CLOUD_ALIYUN)
        → refresh_aliyun_credentials raises ReLoginRequiredError
        → _full_relogin fails
        → LoginFailedError raised to caller
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiomqtt
import pytest

from pymammotion.aliyun.exceptions import CheckSessionException
from pymammotion.account.registry import AccountSession
from pymammotion.client import MammotionClient
from pymammotion.transport.base import (
    AuthError,
    LoginFailedError,
    ReLoginRequiredError,
)
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _mammotion_config() -> MQTTTransportConfig:
    return MQTTTransportConfig(host="mqtt.example.com", client_id="c1", username="u", password="jwt")


def _make_session() -> AccountSession:
    session = AccountSession(
        account_id="test@example.com",
        email="test@example.com",
        password="secret",
    )
    session.mammotion_http = AsyncMock()
    session.token_manager = AsyncMock()
    return session


def _make_client(session: AccountSession) -> MammotionClient:
    from pymammotion.account.registry import AccountRegistry

    client = MammotionClient.__new__(MammotionClient)
    client._account_registry = AccountRegistry()
    client._account_registry._sessions[session.account_id] = session
    return client


# ---------------------------------------------------------------------------
# Mammotion MQTT — Path 1: MQTT broker rejects credentials (rc=134)
# ---------------------------------------------------------------------------


class _MqttAuthFailClient:
    """Fake aiomqtt.Client whose __aenter__ raises MqttCodeError(rc=134)."""

    async def __aenter__(self) -> "_MqttAuthFailClient":
        raise aiomqtt.MqttCodeError(134)

    async def __aexit__(self, *args: object) -> None:
        pass


@pytest.mark.asyncio
async def test_mammotion_mqtt_broker_auth_failure_propagates_relogin() -> None:
    """rc=134 from MQTT broker + jwt_refresher raising ReLoginRequiredError
    must surface as ReLoginRequiredError via on_fatal_auth_error."""
    fatal_errors: list[Exception] = []

    async def _on_fatal(exc: Exception) -> None:
        fatal_errors.append(exc)

    relogin = ReLoginRequiredError("acc", "JWT refresh exhausted")

    async def _jwt_refresher() -> str:
        raise relogin

    http = AsyncMock()
    transport = MQTTTransport(
        _mammotion_config(),
        http,
        jwt_refresher=_jwt_refresher,
    )
    transport.on_fatal_auth_error = _on_fatal

    with patch("aiomqtt.Client", return_value=_MqttAuthFailClient()):
        with pytest.raises(ReLoginRequiredError):
            await transport._run()

    assert len(fatal_errors) == 1
    assert isinstance(fatal_errors[0], ReLoginRequiredError)


@pytest.mark.asyncio
async def test_mammotion_mqtt_broker_auth_failure_exhausts_retries_then_relogin() -> None:
    """rc=134 exhausts _BAD_CREDENTIALS_MAX refresh attempts → on_fatal_auth_error called
    even when jwt_refresher succeeds (returns a JWT) but the broker keeps rejecting it."""
    fatal_errors: list[Exception] = []

    async def _on_fatal(exc: Exception) -> None:
        fatal_errors.append(exc)

    refresh_count = 0

    async def _jwt_refresher() -> str:
        nonlocal refresh_count
        refresh_count += 1
        return "new-jwt"

    http = AsyncMock()
    transport = MQTTTransport(
        _mammotion_config(),
        http,
        jwt_refresher=_jwt_refresher,
    )
    transport.on_fatal_auth_error = _on_fatal

    # Broker always rejects — all refresh attempts fail
    with patch("aiomqtt.Client", return_value=_MqttAuthFailClient()):
        with pytest.raises(ReLoginRequiredError):
            await transport._run()

    # Refresh was attempted _BAD_CREDENTIALS_MAX (3) times before giving up
    assert refresh_count == 3
    assert len(fatal_errors) == 1
    assert isinstance(fatal_errors[0], ReLoginRequiredError)


# ---------------------------------------------------------------------------
# Mammotion MQTT — Path 2: mqtt_invoke HTTP API returns 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mammotion_invoke_401_force_refresh_invoke_token_called() -> None:
    """UnauthorizedException from mqtt_invoke must call force_refresh_invoke_token()."""
    from pymammotion.http.model.http import UnauthorizedException

    http = AsyncMock()
    http.mqtt_invoke.side_effect = [UnauthorizedException("expired"), MagicMock(code=0)]

    tm = AsyncMock()
    transport = MQTTTransport(_mammotion_config(), http, token_manager=tm)

    await transport.send(b"\x00\x01", iot_id="device-001")

    tm.force_refresh_invoke_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_mammotion_invoke_401_force_refresh_invoke_token_raises_relogin_propagates() -> None:
    """If force_refresh_invoke_token() raises ReLoginRequiredError it must
    propagate from send() so the caller can trigger a full re-login."""
    from pymammotion.http.model.http import UnauthorizedException

    http = AsyncMock()
    http.mqtt_invoke.side_effect = UnauthorizedException("expired")

    tm = AsyncMock()
    tm.force_refresh_invoke_token.side_effect = ReLoginRequiredError("acc", "all credentials exhausted")

    transport = MQTTTransport(_mammotion_config(), http, token_manager=tm)

    with pytest.raises(ReLoginRequiredError, match="all credentials exhausted"):
        await transport.send(b"\x00\x01", iot_id="device-001")

    tm.force_refresh_invoke_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_mammotion_invoke_401_cascade_to_full_relogin_via_client() -> None:
    """Full cascade: mqtt_invoke 401 → send() raises ReLoginRequiredError
    → _send_with_auth_retry triggers _full_relogin → success."""
    from pymammotion.http.model.http import UnauthorizedException

    session = _make_session()
    client = _make_client(session)

    http = AsyncMock()
    # First send_fn call: send() will raise ReLoginRequiredError (force_refresh fails)
    # Second call (after full re-login): succeeds
    call_count = 0

    async def _send_fn() -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            http.mqtt_invoke.side_effect = UnauthorizedException("expired")
            transport = MQTTTransport(_mammotion_config(), http, token_manager=session.token_manager)
            session.token_manager.force_refresh.side_effect = ReLoginRequiredError("acc", "exhausted")
            await transport.send(b"\x00", iot_id="dev")

    login_resp = MagicMock()
    login_resp.code = 0
    session.mammotion_http.login_v2 = AsyncMock(return_value=login_resp)
    # force_refresh is called inside _full_relogin after login_v2 succeeds — must succeed.
    session.token_manager.force_refresh = AsyncMock()

    # _send_with_auth_retry catches ReLoginRequiredError → _full_relogin → retry
    send_fn = AsyncMock(side_effect=[ReLoginRequiredError("acc", "exhausted"), None])
    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2
    session.mammotion_http.login_v2.assert_awaited_once()


@pytest.mark.asyncio
async def test_mammotion_invoke_401_full_relogin_fails_raises_login_failed() -> None:
    """When both force_refresh and _full_relogin fail, LoginFailedError propagates."""
    session = _make_session()
    client = _make_client(session)

    session.token_manager.force_refresh.side_effect = ReLoginRequiredError("acc", "exhausted")
    login_resp = MagicMock()
    login_resp.code = 500
    login_resp.msg = "server unavailable"
    session.mammotion_http.login_v2 = AsyncMock(return_value=login_resp)

    send_fn = AsyncMock(side_effect=ReLoginRequiredError("acc", "exhausted"))

    with pytest.raises(LoginFailedError, match="server unavailable"):
        await client._send_with_auth_retry(send_fn, session)


# ---------------------------------------------------------------------------
# Aliyun MQTT — cloud_gateway invoke failure cascade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aliyun_cloud_gateway_session_expired_cascade_to_relogin() -> None:
    """cloud_gateway.send_cloud_command raises CheckSessionException (SessionExpiredError
    with CLOUD_ALIYUN) → targeted refresh raises ReLoginRequiredError → _full_relogin
    succeeds → retry succeeds."""
    from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport

    session = _make_session()
    client = _make_client(session)

    cloud_gateway = AsyncMock()
    cloud_gateway.send_cloud_command = AsyncMock(
        side_effect=[CheckSessionException("session gone"), None]
    )

    config = AliyunMQTTConfig(
        host="pk.iot-as-mqtt.cn-shanghai.aliyuncs.com",
        client_id_base="pk&dn",
        username="dn&pk",
        device_name="dn",
        product_key="pk",
        device_secret="secret",
        iot_token="tok",
    )
    aliyun_transport = AliyunMQTTTransport(config, cloud_gateway)

    # Targeted refresh raises ReLoginRequiredError; _full_relogin then succeeds
    session.token_manager.refresh_aliyun_credentials = AsyncMock(
        side_effect=ReLoginRequiredError("acc", "aliyun session exhausted")
    )
    login_resp = MagicMock()
    login_resp.code = 0
    session.mammotion_http.login_v2 = AsyncMock(return_value=login_resp)
    session.token_manager.force_refresh = AsyncMock()

    invoke_count = 0

    async def _send_fn() -> None:
        nonlocal invoke_count
        invoke_count += 1
        await aliyun_transport.send(b"\x00", iot_id="dev-aliyun")

    await client._send_with_auth_retry(_send_fn, session)

    assert invoke_count == 2
    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()
    session.mammotion_http.login_v2.assert_awaited_once()


@pytest.mark.asyncio
async def test_aliyun_cloud_gateway_session_expired_full_relogin_fails() -> None:
    """When CheckSessionException → targeted refresh → ReLoginRequiredError
    → _full_relogin also fails → LoginFailedError propagates to caller."""
    from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport

    session = _make_session()
    client = _make_client(session)

    cloud_gateway = AsyncMock()
    cloud_gateway.send_cloud_command = AsyncMock(
        side_effect=CheckSessionException("session expired")
    )

    config = AliyunMQTTConfig(
        host="pk.iot-as-mqtt.cn-shanghai.aliyuncs.com",
        client_id_base="pk&dn",
        username="dn&pk",
        device_name="dn",
        product_key="pk",
        device_secret="secret",
        iot_token="tok",
    )
    aliyun_transport = AliyunMQTTTransport(config, cloud_gateway)

    session.token_manager.refresh_aliyun_credentials = AsyncMock(
        side_effect=ReLoginRequiredError("acc", "aliyun exhausted")
    )
    login_resp = MagicMock()
    login_resp.code = 401
    login_resp.msg = "invalid credentials"
    session.mammotion_http.login_v2 = AsyncMock(return_value=login_resp)

    async def _send_fn() -> None:
        await aliyun_transport.send(b"\x00", iot_id="dev-aliyun")

    with pytest.raises(LoginFailedError, match="invalid credentials"):
        await client._send_with_auth_retry(_send_fn, session)

    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()
    session.mammotion_http.login_v2.assert_awaited_once()


@pytest.mark.asyncio
async def test_aliyun_cloud_gateway_auth_error_force_refresh_then_relogin() -> None:
    """A plain AuthError from send_cloud_command goes straight to force_refresh
    (not targeted refresh), then LoginFailedError if full re-login fails."""
    from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport

    session = _make_session()
    client = _make_client(session)

    cloud_gateway = AsyncMock()
    cloud_gateway.send_cloud_command = AsyncMock(side_effect=AuthError("gateway auth refused"))

    config = AliyunMQTTConfig(
        host="pk.iot-as-mqtt.cn-shanghai.aliyuncs.com",
        client_id_base="pk&dn",
        username="dn&pk",
        device_name="dn",
        product_key="pk",
        device_secret="secret",
        iot_token="tok",
    )
    aliyun_transport = AliyunMQTTTransport(config, cloud_gateway)

    # force_refresh raises ReLoginRequiredError; full re-login fails
    session.token_manager.force_refresh = AsyncMock(
        side_effect=ReLoginRequiredError("acc", "all gone")
    )
    login_resp = MagicMock()
    login_resp.code = 500
    login_resp.msg = "server error"
    session.mammotion_http.login_v2 = AsyncMock(return_value=login_resp)

    async def _send_fn() -> None:
        await aliyun_transport.send(b"\x00", iot_id="dev-aliyun")

    with pytest.raises(LoginFailedError, match="server error"):
        await client._send_with_auth_retry(_send_fn, session)

    session.token_manager.force_refresh.assert_awaited_once()
    session.token_manager.refresh_aliyun_credentials.assert_not_awaited()
