"""Unit tests for the reauth cascade introduced in the MQTT auth fix.

Covers three distinct flows:

1. TokenManager._refresh_mqtt_creds() cascade
   fast path  → get_mqtt_credentials() succeeds
   fallback 1 → get_mqtt_credentials() returns no data → refresh_authorization_code()
   fallback 2 → refresh_authorization_code() fails → _refresh_http()
   full fail  → _refresh_http() also fails → ReLoginRequiredError

2. TokenManager.get_valid_http_token() uses refresh_token_v2, not refresh_login

3. MQTTTransport.send() — HTTP token path is separated from MQTT JWT path
   UnauthorizedException → token_manager.get_valid_http_token() (not get_mammotion_mqtt_credentials)
   ReLoginRequiredError from token refresh propagates out of send()
   Retry after refresh fails → AuthError
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.auth.token_manager import HTTPCredentials, MQTTCredentials, TokenManager
from pymammotion.transport.base import AuthError, ReLoginRequiredError
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expiring_http_creds(seconds_left: float = 100.0) -> HTTPCredentials:
    return HTTPCredentials(
        access_token="access-expiring",
        refresh_token="refresh-expiring",
        expires_at=time.time() + seconds_left,
    )


def _make_mqtt_data(jwt: str = "jwt-new") -> MagicMock:
    data = MagicMock()
    data.host = "mqtt.example.com"
    data.client_id = "client-1"
    data.username = "user"
    data.jwt = jwt
    return data


def _make_transport(http: AsyncMock, token_manager: AsyncMock | None = None) -> MQTTTransport:
    config = MQTTTransportConfig(host="mqtt.example.com", client_id="c1", username="u", password="p")
    return MQTTTransport(config=config, mammotion_http=http, token_manager=token_manager or AsyncMock())


# ---------------------------------------------------------------------------
# _refresh_mqtt_creds() — fast path
# ---------------------------------------------------------------------------


async def test_refresh_mqtt_creds_fast_path_stores_credentials() -> None:
    """get_mqtt_credentials() returns valid data → stored directly, no fallback."""
    http = AsyncMock()
    http.get_mqtt_credentials.return_value = MagicMock(data=_make_mqtt_data("jwt-fast"))

    tm = TokenManager("acc", http)
    await tm.initialize(None, None, None)
    creds = await tm.get_mammotion_mqtt_credentials()

    assert creds.jwt == "jwt-fast"
    http.get_mqtt_credentials.assert_awaited_once()
    http.refresh_authorization_code.assert_not_awaited()
    http.refresh_token_v2.assert_not_awaited()


# ---------------------------------------------------------------------------
# _refresh_mqtt_creds() — fallback 1: refresh_authorization_code
# ---------------------------------------------------------------------------


async def test_refresh_mqtt_creds_falls_back_to_authorization_code() -> None:
    """get_mqtt_credentials() returns None data → refresh_authorization_code is called."""
    http = AsyncMock()
    http.get_mqtt_credentials.return_value = MagicMock(data=None)
    # refresh_authorization_code() sets self.mqtt_credentials as a side effect on the real
    # http object; on the mock we pre-set it so _refresh_mqtt_creds can read it back.
    http.mqtt_credentials = _make_mqtt_data("jwt-via-authcode")

    tm = TokenManager("acc", http)
    await tm.initialize(None, None, None)
    creds = await tm.get_mammotion_mqtt_credentials()

    assert creds.jwt == "jwt-via-authcode"
    http.refresh_authorization_code.assert_awaited_once()


async def test_refresh_mqtt_creds_authcode_fallback_raises_relogin_when_credentials_absent() -> None:
    """refresh_authorization_code() leaves mqtt_credentials=None → falls to refresh_login tier."""
    http = AsyncMock()
    http.get_mqtt_credentials.return_value = MagicMock(data=None)
    http.mqtt_credentials = None  # auth code refresh didn't populate credentials

    # refresh_login fallback succeeds but MQTT creds still not set → ReLoginRequiredError
    tm = TokenManager("acc", http)
    await tm.initialize(None, None, None)

    with pytest.raises(ReLoginRequiredError, match="MQTT credentials unavailable"):
        await tm.get_mammotion_mqtt_credentials()

    # Both tiers of the auth-code path were attempted
    assert http.refresh_token_v2.await_count >= 1
    assert http.refresh_authorization_code.await_count >= 1
    http.refresh_login.assert_awaited_once()


# ---------------------------------------------------------------------------
# _refresh_mqtt_creds() — fallback 2: refresh_login
# ---------------------------------------------------------------------------


async def test_refresh_mqtt_creds_falls_back_to_refresh_login_when_authcode_raises() -> None:
    """refresh_authorization_code() raising → refresh_login() is called as last resort."""
    http = AsyncMock()
    http.get_mqtt_credentials.return_value = MagicMock(data=None)
    # First call (inside the refresh_token_v2/refresh_authorization_code tier) raises;
    # second call (inside the refresh_login tier) also raises to trigger full failure.
    http.refresh_authorization_code.side_effect = RuntimeError("authcode endpoint down")

    tm = TokenManager("acc", http)
    await tm.initialize(None, None, None)

    with pytest.raises(ReLoginRequiredError):
        await tm.get_mammotion_mqtt_credentials()

    http.refresh_login.assert_awaited_once()


# ---------------------------------------------------------------------------
# _refresh_mqtt_creds() — full failure → ReLoginRequiredError
# ---------------------------------------------------------------------------


async def test_refresh_mqtt_creds_raises_relogin_when_all_fail() -> None:
    """When every tier of the cascade fails, ReLoginRequiredError propagates."""
    http = AsyncMock()
    http.get_mqtt_credentials.return_value = MagicMock(data=None)
    http.refresh_authorization_code.side_effect = RuntimeError("authcode down")
    http.refresh_login.side_effect = RuntimeError("login also down")

    tm = TokenManager("acc", http)
    await tm.initialize(None, None, None)

    with pytest.raises(ReLoginRequiredError):
        await tm.get_mammotion_mqtt_credentials()


async def test_refresh_mqtt_creds_raises_relogin_on_unexpected_get_credentials_exception() -> None:
    """An unexpected (non-AuthError) exception from get_mqtt_credentials → ReLoginRequiredError.

    The authorization-code fallback must NOT be attempted for non-auth errors.
    """
    http = AsyncMock()
    http.get_mqtt_credentials.side_effect = RuntimeError("network error")

    tm = TokenManager("acc", http)
    await tm.initialize(None, None, None)

    with pytest.raises(ReLoginRequiredError):
        await tm.get_mammotion_mqtt_credentials()

    # Non-AuthError exception hits the outer except, so the auth-code path is never tried
    http.refresh_authorization_code.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_valid_http_token() uses refresh_token_v2, not refresh_login
# ---------------------------------------------------------------------------


async def test_get_valid_http_token_uses_refresh_login() -> None:
    """Expiring HTTP token must be refreshed via refresh_login (which handles fallback to login_v2)."""
    http = AsyncMock()
    data = MagicMock()
    data.access_token = "tok-via-refresh"
    data.refresh_token = "ref-new"
    data.expires_in = 3600.0
    http.refresh_login.return_value = MagicMock(data=data)

    tm = TokenManager("acc", http)
    await tm.initialize(_expiring_http_creds(100), None, None)

    token = await tm.get_valid_http_token()

    assert token == "tok-via-refresh"
    http.refresh_login.assert_awaited_once()
    http.refresh_token_v2.assert_not_awaited()


async def test_get_valid_http_token_raises_relogin_when_refresh_login_fails() -> None:
    """refresh_login failure → ReLoginRequiredError with the correct account_id."""
    http = AsyncMock()
    http.refresh_login.side_effect = RuntimeError("token endpoint down")

    tm = TokenManager("user@example.com", http)
    await tm.initialize(None, None, None)

    with pytest.raises(ReLoginRequiredError) as exc_info:
        await tm.get_valid_http_token()

    assert exc_info.value.account_id == "user@example.com"


async def test_get_valid_http_token_raises_relogin_when_data_none() -> None:
    """refresh_login returning data=None → ReLoginRequiredError."""
    http = AsyncMock()
    http.refresh_login.return_value = MagicMock(data=None)

    tm = TokenManager("acc", http)
    await tm.initialize(None, None, None)

    with pytest.raises(ReLoginRequiredError):
        await tm.get_valid_http_token()


# ---------------------------------------------------------------------------
# MQTTTransport.send() — HTTP token path uses get_valid_http_token
# ---------------------------------------------------------------------------


async def test_send_unauthorized_calls_force_refresh_not_mqtt_credentials() -> None:
    """UnauthorizedException → token_manager.force_refresh(), NOT get_mammotion_mqtt_credentials."""
    from pymammotion.http.model.http import UnauthorizedException

    http = AsyncMock()
    http.mqtt_invoke.side_effect = [UnauthorizedException("expired"), MagicMock(code=0)]

    tm = AsyncMock()

    transport = _make_transport(http, tm)
    await transport.send(b"\x00\x01", iot_id="device-001")

    from pymammotion.transport.base import TransportType

    tm.force_refresh.assert_awaited_once_with(TransportType.CLOUD_MAMMOTION)
    tm.get_mammotion_mqtt_credentials.assert_not_awaited()


async def test_send_retries_successfully_after_http_token_refresh() -> None:
    """After force_refresh() updates credentials, the retry invoke must succeed."""
    from pymammotion.http.model.http import UnauthorizedException

    http = AsyncMock()
    http.mqtt_invoke.side_effect = [UnauthorizedException("expired"), MagicMock(code=0)]

    transport = _make_transport(http)
    await transport.send(b"\x00\x01", iot_id="device-001")

    assert http.mqtt_invoke.await_count == 2


async def test_send_propagates_relogin_required_from_force_refresh() -> None:
    """ReLoginRequiredError from force_refresh() must bubble out of send()."""
    from pymammotion.http.model.http import UnauthorizedException

    http = AsyncMock()
    http.mqtt_invoke.side_effect = UnauthorizedException("expired")

    tm = AsyncMock()
    tm.force_refresh.side_effect = ReLoginRequiredError("acc", "refresh token expired")  # any transport_type

    transport = _make_transport(http, tm)

    with pytest.raises(ReLoginRequiredError):
        await transport.send(b"\x00\x01", iot_id="device-001")


async def test_send_raises_auth_error_when_retry_fails_after_token_refresh() -> None:
    """Token refresh succeeds but the retry invoke also fails → AuthError."""
    from pymammotion.http.model.http import UnauthorizedException

    http = AsyncMock()
    http.mqtt_invoke.side_effect = [
        UnauthorizedException("expired"),
        RuntimeError("server still broken"),
    ]

    transport = _make_transport(http)

    with pytest.raises(AuthError):
        await transport.send(b"\x00\x01", iot_id="device-001")
