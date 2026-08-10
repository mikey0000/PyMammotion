"""Tests for the reauth flow: refresh-token-only, terminal on rejection.

Covers two flows:

1. TokenManager._refresh_mqtt() — fetch the JWT; if the endpoint refuses, force ONE
   access-token renewal via refresh_token_v2 and retry.  A second refusal gives up
   on the Mammotion MQTT transport.  No tier of this ever calls login_v2.

2. MQTTTransport.send() — a 401 from mqtt_invoke renews the invoke token via the
   refresh token.  If that fails the transport gives up (NoTransportAvailableError)
   rather than re-logging in.
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
# _refresh_mqtt() — fast path
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
# _refresh_mqtt() — one forced access-token renewal, then retry
# ---------------------------------------------------------------------------


async def test_refresh_mqtt_creds_retries_after_forced_token_renewal() -> None:
    """A refused JWT endpoint triggers ONE forced access-token renewal, then a retry.

    Previously the fallback read self._http.mqtt_credentials directly — but that
    field is never repopulated by a token refresh, so the JWT was whatever stale
    value was last cached (often the one the broker had just rejected).
    """
    http = AsyncMock()
    # First call returns None data → triggers the forced renewal;
    # second call (after refresh_token_v2) returns a real JWT.
    http.get_mqtt_credentials.side_effect = [
        MagicMock(data=None),
        MagicMock(data=_make_mqtt_data("jwt-after-renewal")),
    ]
    http.refresh_token_v2.return_value = MagicMock(
        code=0, data=MagicMock(access_token="a", refresh_token="r", expires_in=3600.0)
    )

    tm = TokenManager("acc", http)
    await tm.initialize(None, None, None)
    creds = await tm.get_mammotion_mqtt_credentials()

    assert creds.jwt == "jwt-after-renewal"
    http.refresh_token_v2.assert_awaited_once()
    http.login_v2.assert_not_called()
    assert http.get_mqtt_credentials.await_count == 2


async def test_refresh_mqtt_creds_gives_up_on_transport_when_jwt_never_arrives() -> None:
    """Two refusals give up on the MQTT transport — without a password login.

    The transport is marked unavailable, but the account is NOT marked as needing
    re-authentication: the HTTP login is still perfectly good.
    """
    http = AsyncMock()
    http.get_mqtt_credentials.return_value = MagicMock(data=None)
    http.refresh_token_v2.return_value = MagicMock(
        code=0, data=MagicMock(access_token="a", refresh_token="r", expires_in=3600.0)
    )

    tm = TokenManager("acc", http)
    await tm.initialize(None, None, None)

    with pytest.raises(ReLoginRequiredError):
        await tm.get_mammotion_mqtt_credentials()

    http.login_v2.assert_not_called()
    assert tm.mqtt_unavailable is not None
    assert tm.reauth_required is None


# ---------------------------------------------------------------------------
# _refresh_mqtt() — full failure → ReLoginRequiredError
# ---------------------------------------------------------------------------


async def test_refresh_mqtt_creds_raises_relogin_when_all_fail() -> None:
    """When every tier of the cascade fails, ReLoginRequiredError propagates."""
    http = AsyncMock()
    http.get_mqtt_credentials.return_value = MagicMock(data=None)
    http.refresh_authorization_token.side_effect = RuntimeError("authtoken down")
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
# MQTTTransport.send() — HTTP token path uses refresh_invoke_token
# ---------------------------------------------------------------------------


async def test_send_unauthorized_calls_refresh_invoke_token_not_mqtt_credentials() -> None:
    """UnauthorizedException → token_manager.refresh_invoke_token(), NOT get_mammotion_mqtt_credentials."""
    from pymammotion.http.model.http import UnauthorizedExceptionError

    http = AsyncMock()
    http.mqtt_invoke.side_effect = [UnauthorizedExceptionError("expired"), MagicMock(code=0)]

    tm = AsyncMock()

    transport = _make_transport(http, tm)
    await transport.send(b"\x00\x01", iot_id="device-001")

    tm.refresh_invoke_token.assert_awaited_once()
    tm.get_mammotion_mqtt_credentials.assert_not_awaited()


async def test_send_retries_successfully_after_http_token_refresh() -> None:
    """After force_refresh() updates credentials, the retry invoke must succeed."""
    from pymammotion.http.model.http import UnauthorizedExceptionError

    http = AsyncMock()
    http.mqtt_invoke.side_effect = [UnauthorizedExceptionError("expired"), MagicMock(code=0)]

    transport = _make_transport(http)
    await transport.send(b"\x00\x01", iot_id="device-001")

    assert http.mqtt_invoke.await_count == 2


async def test_send_gives_up_as_no_transport_when_invoke_token_refresh_fails() -> None:
    """No send path re-logins: if the invoke-token refresh raises ReLoginRequiredError,
    send() gives up and raises NoTransportAvailableError so nothing further up the
    stack attempts a password grant."""
    from pymammotion.http.model.http import UnauthorizedExceptionError
    from pymammotion.transport.base import NoTransportAvailableError

    http = AsyncMock()
    http.mqtt_invoke.side_effect = UnauthorizedExceptionError("expired")

    tm = AsyncMock()
    tm.account_id = "acc"
    tm.refresh_invoke_token.side_effect = ReLoginRequiredError("acc", "refresh token expired")

    transport = _make_transport(http, tm)

    with pytest.raises(NoTransportAvailableError):
        await transport.send(b"\x00\x01", iot_id="device-001")

    # Called with the token the failed request used, so a concurrent refresh can be detected.
    tm.refresh_invoke_token.assert_awaited_once()
    assert "stale_token" in tm.refresh_invoke_token.await_args.kwargs


async def test_send_raises_auth_error_when_retry_fails_after_token_refresh() -> None:
    """Token refresh succeeds but the retry invoke also fails → AuthError."""
    from pymammotion.http.model.http import UnauthorizedExceptionError

    http = AsyncMock()
    http.mqtt_invoke.side_effect = [
        UnauthorizedExceptionError("expired"),
        RuntimeError("server still broken"),
    ]

    transport = _make_transport(http)

    with pytest.raises(AuthError):
        await transport.send(b"\x00\x01", iot_id="device-001")
