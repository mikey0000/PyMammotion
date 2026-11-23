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
from pymammotion.http.model.http import (
    AuthorizationCodeError,
    JWTTokenInfo,
    MQTTConnection,
    Response,
    UnauthorizedExceptionError,
)
from pymammotion.transport.base import is_transient_network_error
from tests._helpers import encode_jwt
from tests.unit._helpers import make_http_posting


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
async def test_get_user_device_list_raises_on_401(status: int, body: dict) -> None:
    """A rejected token must raise, not come back as Response(code=401).

    Returned as a value it was indistinguishable from "no devices" to every caller,
    so a revoked session restored silently and only failed on the first command.
    The server reports 401 both ways, hence both cases.
    """
    http = _make_http_with_get(status, body)

    with pytest.raises(UnauthorizedExceptionError):
        await http.get_user_device_list()


async def test_get_user_device_list_returns_devices_on_success() -> None:
    """The success path still decodes and caches the list."""
    http = _make_http_with_get(200, {"code": 0, "msg": "ok", "data": [{"deviceName": "Luba-1", "iotId": "iot-1"}]})

    response = await http.get_user_device_list()

    assert response.code == 0
    assert [d.device_name for d in (response.data or [])] == ["Luba-1"]
    assert [d.device_name for d in http.device_info] == ["Luba-1"]


def _make_http_posting(status: int, body: dict, content_type: str = "application/json") -> MammotionHTTP:
    """Build a MammotionHTTP whose _client_session POSTs return a canned response."""
    http, _session = make_http_posting(status, body, content_type)
    return http


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (401, {}),
        (460, {}),
        (200, {"code": 401, "msg": "expired"}),
        (200, {"code": 460, "msg": "expired"}),
        (500, {"code": 460, "msg": "expired"}),
    ],
)
async def test_mqtt_invoke_raises_on_every_dead_token_shape(status: int, body: dict) -> None:
    """A dead token must never come back as a plain Response — under any HTTP status."""
    http = _make_http_posting(status, body)
    with pytest.raises(UnauthorizedExceptionError):
        await http.mqtt_invoke("payload", "", "iot-1")


@pytest.mark.parametrize("status", [408, 500, 503])
async def test_get_mqtt_credentials_raises_connection_error_on_server_fault(status: int) -> None:
    """5xx is a server fault, not a token verdict — it must not read as ``data is None``."""
    http = _make_http_posting(status, {})
    with pytest.raises(ConnectionError):
        await http.get_mqtt_credentials()


def _fetching_code(status: int, body: dict, content_type: str = "application/json") -> MammotionHTTP:
    http, _session = make_http_posting(status, body, content_type)
    http.login_info = MagicMock(access_token="tok", authorization_code="spent")  # type: ignore[assignment]
    return http


@pytest.mark.regression
@pytest.mark.parametrize(
    ("status", "body"),
    [(401, {"code": 401, "msg": "unauthorized"}), (200, {"code": 401, "msg": "unauthorized"})],
    ids=["status", "body"],
)
async def test_fetch_authorization_token_raises_unauthorized_on_401(status: int, body: dict) -> None:
    """A refused bearer came back as a Response nobody read, so the chain ran on with the spent code."""
    http = _fetching_code(status, body)

    with pytest.raises(UnauthorizedExceptionError):
        await http.fetch_authorization_token()


@pytest.mark.regression
@pytest.mark.parametrize(
    ("status", "body", "content_type"),
    [(500, {}, "application/json"), (503, {}, "application/json"), (200, {}, "text/html")],
    ids=["500", "503", "non-json"],
)
async def test_fetch_authorization_token_raises_a_transient_error_on_a_server_fault(
    status: int, body: dict, content_type: str
) -> None:
    """A 5xx or HTML error page answered ``Response(200)``, and the spent code made the rebuild terminal."""
    http = _fetching_code(status, body, content_type)

    with pytest.raises(ConnectionError) as excinfo:
        await http.fetch_authorization_token()

    assert is_transient_network_error(excinfo.value)


async def test_fetch_authorization_token_raises_a_terminal_error_on_any_other_refusal() -> None:
    http = _fetching_code(200, {"code": 20001, "msg": "refused"})

    with pytest.raises(AuthorizationCodeError) as excinfo:
        await http.fetch_authorization_token()

    assert not is_transient_network_error(excinfo.value)


async def test_fetch_authorization_token_keeps_the_new_code() -> None:
    http = _fetching_code(200, {"code": 0, "msg": "ok", "data": {"code": "fresh"}})

    await http.fetch_authorization_token()

    assert http.login_info.authorization_code == "fresh"
    assert http.login_info.access_token == "tok"


@pytest.mark.regression
async def test_fetch_authorization_token_adopts_and_persists_a_returned_access_token() -> None:
    """A rotated bearer replaced the token but kept the old expiry and was never persisted."""
    exp = int(time.time()) + 7200
    rotated = encode_jwt(exp=exp)
    http = _fetching_code(200, {"code": 0, "msg": "ok", "data": {"code": "fresh", "accessToken": rotated}})
    http.login_info.access_token = encode_jwt(exp=exp - 3600)
    http.response = Response(code=0, msg="ok", data=http.login_info)  # type: ignore[arg-type]
    persisted = AsyncMock()
    http.on_login_refreshed = persisted

    await http.fetch_authorization_token()

    assert http.login_info.access_token == rotated
    assert http.expires_in == exp
    persisted.assert_awaited_once()
