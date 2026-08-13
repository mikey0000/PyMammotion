"""Regression test for MammotionHTTP.logout() clearing cached credential state.

Before this fix, logout() reset only `login_info` and the Authorization header,
leaving `mqtt_credentials`, `expires_in`, and `jwt_info` populated with values
bound to the just-invalidated session. After a `logout()` + `login_v2()`
sequence (the path `_full_relogin` takes), anything reading `_http.mqtt_credentials`
got a stale JWT that the MQTT broker would reject — feeding the auth-retry
loop the broker rejections were supposed to break out of.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import JWTTokenInfo, MQTTConnection, UnauthorizedExceptionError


def _make_http_with_session() -> MammotionHTTP:
    """Build a MammotionHTTP whose _client_session yields a mock session."""
    http = MammotionHTTP()
    mock_session = MagicMock()
    mock_session.post = AsyncMock()

    @asynccontextmanager
    async def _fake_session() -> object:  # type: ignore[misc]
        yield mock_session

    http._client_session = _fake_session  # type: ignore[method-assign]
    return http


@pytest.mark.asyncio
async def test_logout_invalidates_cached_mqtt_credentials_and_expiry() -> None:
    http = _make_http_with_session()
    # Populate the state that logout() previously left stale.
    http.login_info = MagicMock(access_token="tok")  # type: ignore[assignment]
    http.mqtt_credentials = MQTTConnection(host="h", jwt="stale-jwt", client_id="c", username="u")
    http.expires_in = 9999999999.0
    http.jwt_info = JWTTokenInfo(iot="https://iot.example", robot="https://robot.example")
    http._headers["Authorization"] = "Bearer stale"

    await http.logout()

    assert http.login_info is None, "login_info must be cleared"
    assert http.mqtt_credentials is None, "stale MQTT JWT must not survive logout"
    assert http.expires_in == 0.0, "expires_in must be reset so the next request triggers a refresh"
    assert http.jwt_info == JWTTokenInfo("", ""), "jwt_info (iot/robot URLs) must be cleared"
    assert "Authorization" not in http._headers, "Authorization header must be removed"


@pytest.mark.asyncio
async def test_logout_is_a_noop_when_already_logged_out() -> None:
    """logout() with login_info=None must not blow up or touch other state."""
    http = MammotionHTTP()
    http.mqtt_credentials = MQTTConnection(host="h", jwt="kept", client_id="c", username="u")

    await http.logout()

    # No login_info means no server-side logout call; cached creds are untouched.
    assert http.mqtt_credentials is not None
    assert http.mqtt_credentials.jwt == "kept"


def _make_http_with_get(status: int, json_data: dict) -> MammotionHTTP:
    """Build a MammotionHTTP whose _client_session GETs return a canned response."""
    http = MammotionHTTP()
    http.login_info = MagicMock(access_token="tok", refresh_token="ref")  # type: ignore[assignment]
    http.expires_in = time.time() + 86400  # far from expiry: no refresh in the way
    resp = MagicMock()
    resp.status = status
    resp.headers = {"Content-Type": "application/json"}
    resp.json = AsyncMock(return_value=json_data)
    mock_session = MagicMock()
    mock_session.get = AsyncMock(return_value=resp)

    @asynccontextmanager
    async def _fake_session() -> object:  # type: ignore[misc]
        yield mock_session

    http._client_session = _fake_session  # type: ignore[method-assign]
    return http


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (401, {"code": 401, "msg": "unauthorized"}),  # 401 as the HTTP status
        (200, {"code": 401, "msg": "unauthorized"}),  # 401 as an in-body code
    ],
)
@pytest.mark.asyncio
async def test_get_user_device_list_raises_on_401(status: int, body: dict) -> None:
    """A rejected token must raise, not come back as Response(code=401).

    Returned as a value it was indistinguishable from "no devices" to every caller,
    so a revoked session restored silently and only failed on the first command.
    The server reports 401 both ways, hence both cases.
    """
    http = _make_http_with_get(status, body)

    with pytest.raises(UnauthorizedExceptionError):
        await http.get_user_device_list()


@pytest.mark.asyncio
async def test_get_user_device_list_returns_devices_on_success() -> None:
    """The success path still decodes and caches the list."""
    http = _make_http_with_get(200, {"code": 0, "msg": "ok", "data": [{"deviceName": "Luba-1", "iotId": "iot-1"}]})

    response = await http.get_user_device_list()

    assert response.code == 0
    assert [d.device_name for d in (response.data or [])] == ["Luba-1"]
    assert [d.device_name for d in http.device_info] == ["Luba-1"]
