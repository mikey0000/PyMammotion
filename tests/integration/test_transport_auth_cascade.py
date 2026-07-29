"""End-to-end auth-error cascade tests for both MQTT transports.

Covers the two failure paths for each transport:

Mammotion MQTT (MQTTTransport)
    Path 1 — MQTT broker rejects credentials (rc=134):
        jwt_refresher raises ReLoginRequiredError
        → propagates from _run() task
        → on_fatal_auth_error is invoked

    Path 2 — mqtt_invoke HTTP API returns 401:
        UnauthorizedException → send() renews the invoke token via the refresh token
        → give up (NoTransportAvailableError) if that refresh is rejected
        → give up as well if the retry still returns 401

Aliyun MQTT (AliyunMQTTTransport)
    Only the cloud_gateway invoke path is relevant once connected
    (the MQTT broker connection itself is stable after initial handshake).

    cloud_gateway.send_cloud_command raises CheckSessionException
    → AliyunMQTTTransport.send() propagates it uncaught
    → _send_with_auth_retry catches SessionExpiredError(CLOUD_ALIYUN)
        → refresh_aliyun_credentials raises ReLoginRequiredError
        → that error propagates to the caller; no password re-login is attempted
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiomqtt
import pytest

from pymammotion.aliyun.exceptions import CheckSessionException
from pymammotion.account.registry import AccountSession
from pymammotion.auth.token_manager import MQTTCredentials
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


def _make_client_with_session() -> tuple[MammotionClient, AccountSession]:
    """Return a (client, session) pair with the session already registered."""
    session = _make_session()
    return _make_client(session), session


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
    """A creds_refresher that raises ReLoginRequiredError (refresh token dead) must
    surface as ReLoginRequiredError via on_fatal_auth_error — the transport gives up.

    _run() exits cleanly after firing the handler — the handler owns recovery,
    so re-raising would only produce an unretrieved task exception.
    """
    fatal_errors: list[Exception] = []

    async def _on_fatal(exc: Exception) -> None:
        fatal_errors.append(exc)

    relogin = ReLoginRequiredError("acc", "refresh token rejected")

    async def _creds_refresher(force: bool) -> MQTTCredentials:  # noqa: ARG001
        raise relogin

    http = AsyncMock()
    transport = MQTTTransport(
        _mammotion_config(),
        http,
        AsyncMock(),
        creds_refresher=_creds_refresher,
    )
    transport.on_fatal_auth_error = _on_fatal

    with patch("aiomqtt.Client", return_value=_MqttAuthFailClient()):
        await transport._run()

    assert len(fatal_errors) == 1
    assert isinstance(fatal_errors[0], ReLoginRequiredError)


@pytest.mark.asyncio
async def test_mammotion_mqtt_broker_auth_failure_refreshes_once_then_gives_up() -> None:
    """When the broker keeps rejecting even after a full credential refresh, the
    transport forces ONE refresh (force=True), retries, and then gives up — firing
    on_fatal_auth_error.  It never loops indefinitely and never re-logins.
    """
    fatal_errors: list[Exception] = []

    async def _on_fatal(exc: Exception) -> None:
        fatal_errors.append(exc)

    forces: list[bool] = []

    async def _creds_refresher(force: bool) -> MQTTCredentials:
        forces.append(force)
        return MQTTCredentials(
            host="mqtt.example.com",
            client_id="c1",
            username="u",
            jwt="new-jwt",
            expires_at=0.0,
        )

    http = AsyncMock()
    transport = MQTTTransport(
        _mammotion_config(),
        http,
        AsyncMock(),
        creds_refresher=_creds_refresher,
    )
    transport.on_fatal_auth_error = _on_fatal

    with patch("aiomqtt.Client", return_value=_MqttAuthFailClient()):
        await transport._run()

    # Exactly one forced refresh happened, then we gave up (fatal fired once).
    assert forces.count(True) == 1
    assert len(fatal_errors) == 1
    assert isinstance(fatal_errors[0], ReLoginRequiredError)


# ---------------------------------------------------------------------------
# Mammotion MQTT — Path 2: mqtt_invoke HTTP API returns 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mammotion_invoke_401_refreshes_invoke_token_without_relogin() -> None:
    """UnauthorizedException from mqtt_invoke renews the invoke token via the
    refresh token — never a password login."""
    from pymammotion.http.model.http import UnauthorizedExceptionError

    http = AsyncMock()
    http.mqtt_invoke.side_effect = [UnauthorizedExceptionError("expired"), MagicMock(code=0)]

    tm = AsyncMock()
    transport = MQTTTransport(_mammotion_config(), http, token_manager=tm)

    await transport.send(b"\x00\x01", iot_id="device-001")

    # Called with the token the failed request used, so a concurrent refresh can be detected.
    tm.refresh_invoke_token.assert_awaited_once()
    assert "stale_token" in tm.refresh_invoke_token.await_args.kwargs


@pytest.mark.asyncio
async def test_mammotion_invoke_401_gives_up_as_no_transport_available() -> None:
    """If the invoke-token refresh raises ReLoginRequiredError, send() gives up:
    it fires the fatal handler and raises NoTransportAvailableError (NOT
    ReLoginRequiredError) so nothing upstream attempts a password grant."""
    from pymammotion.http.model.http import UnauthorizedExceptionError
    from pymammotion.transport.base import NoTransportAvailableError

    http = AsyncMock()
    http.mqtt_invoke.side_effect = UnauthorizedExceptionError("expired")

    tm = AsyncMock()
    tm.account_id = "acc"
    tm.refresh_invoke_token.side_effect = ReLoginRequiredError("acc", "all credentials exhausted")

    fatal_errors: list[Exception] = []

    async def _on_fatal(exc: Exception) -> None:
        fatal_errors.append(exc)

    transport = MQTTTransport(_mammotion_config(), http, token_manager=tm)
    transport.on_fatal_auth_error = _on_fatal

    with pytest.raises(NoTransportAvailableError):
        await transport.send(b"\x00\x01", iot_id="device-001")

    # Called with the token the failed request used, so a concurrent refresh can be detected.
    tm.refresh_invoke_token.assert_awaited_once()
    assert "stale_token" in tm.refresh_invoke_token.await_args.kwargs
    assert len(fatal_errors) == 1


@pytest.mark.asyncio
async def test_mammotion_invoke_401_never_reaches_a_password_login() -> None:
    """End-to-end: a 401 storm on mqtt_invoke must not produce a single login_v2.

    This is the shape of the reported oauth2/token hammering: every queued command
    hit the same expired token, and each one walked the cascade all the way to a
    password grant.
    """
    from pymammotion.http.model.http import UnauthorizedExceptionError
    from pymammotion.transport.base import NoTransportAvailableError

    client, session = _make_client_with_session()
    session.mammotion_http.login_v2 = AsyncMock()
    session.mammotion_http.logout = AsyncMock()

    http = AsyncMock()
    http.mqtt_invoke.side_effect = UnauthorizedExceptionError("expired")
    tm = AsyncMock()
    tm.account_id = "acc"
    tm.refresh_invoke_token.side_effect = ReLoginRequiredError("acc", "refresh token dead")
    transport = MQTTTransport(_mammotion_config(), http, token_manager=tm)

    async def _send() -> None:
        await transport.send(b"\x00\x01", iot_id="device-001")

    # NoTransportAvailableError is re-raised for the caller to retry on reconnect.
    for _ in range(5):
        with pytest.raises(NoTransportAvailableError):
            await client._send_with_auth_retry(_send, session)

    session.mammotion_http.login_v2.assert_not_awaited()
    session.mammotion_http.logout.assert_not_awaited()


# ---------------------------------------------------------------------------
# Aliyun MQTT — cloud_gateway invoke failure cascade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aliyun_session_expired_relogin_required_propagates() -> None:
    """A dead Aliyun session surfaces ReLoginRequiredError to the caller.

    It must not be answered with a password login: the Aliyun IoT refreshToken is a
    separate credential chain, and the account's HTTP login is very likely still fine.
    """
    client, session = _make_client_with_session()
    session.token_manager.refresh_aliyun_credentials = AsyncMock(
        side_effect=ReLoginRequiredError("acc", "aliyun refreshToken exhausted")
    )
    session.mammotion_http.login_v2 = AsyncMock()
    session.mammotion_http.logout = AsyncMock()

    async def _send() -> None:
        raise CheckSessionException("iotToken rejected")

    with pytest.raises(ReLoginRequiredError):
        await client._send_with_auth_retry(_send, session)

    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()
    session.mammotion_http.login_v2.assert_not_awaited()
    session.mammotion_http.logout.assert_not_awaited()


@pytest.mark.asyncio
async def test_aliyun_failure_does_not_touch_mammotion_credentials() -> None:
    """Recovering Aliyun must not rotate the Mammotion MQTT JWT."""
    client, session = _make_client_with_session()
    session.token_manager.refresh_aliyun_credentials = AsyncMock()
    session.token_manager.refresh_mqtt_credentials = AsyncMock()

    calls = 0

    async def _send() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise CheckSessionException("iotToken rejected")

    await client._send_with_auth_retry(_send, session)

    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()
    session.token_manager.refresh_mqtt_credentials.assert_not_awaited()


@pytest.mark.asyncio
async def test_aliyun_plain_auth_error_propagates_without_relogin() -> None:
    """A plain AuthError has no transport to target — it propagates untouched."""
    client, session = _make_client_with_session()
    session.mammotion_http.login_v2 = AsyncMock()

    async def _send() -> None:
        raise AuthError("aliyun rejected")

    with pytest.raises(AuthError):
        await client._send_with_auth_retry(_send, session)

    session.mammotion_http.login_v2.assert_not_awaited()
