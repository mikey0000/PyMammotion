"""Tests for stream/token 401 recovery and regional host fallback."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import JWTTokenInfo, Response


def _json_response(payload: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.headers = {"Content-Type": "application/json"}
    resp.text = AsyncMock(return_value=__import__("json").dumps(payload))
    return resp


def _make_http() -> tuple[MammotionHTTP, MagicMock]:
    http = MammotionHTTP(account="user@example.com", password="secret")
    http.login_info = MagicMock(
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=3600,
    )
    http.expires_in = 9_999_999_999.0
    http.jwt_info = JWTTokenInfo(
        iot="https://api-iot-business-eu.example",
        robot="https://api-robot-eu.example",
    )
    mock_session = MagicMock()
    mock_session.post = AsyncMock()

    @asynccontextmanager
    async def _fake_session() -> object:  # type: ignore[misc]
        yield mock_session

    http._client_session = _fake_session  # type: ignore[method-assign]
    return http, mock_session


@pytest.mark.asyncio
async def test_stream_subscription_retries_after_401_with_refresh() -> None:
    """A 401 triggers refresh_login and a second stream/token request."""
    http, session = _make_http()
    session.post.side_effect = [
        _json_response(
            {"code": 401, "msg": "Access to this resource requires authentication", "data": None}
        ),
        _json_response(
            {
                "code": 0,
                "msg": "success",
                "data": {
                    "appid": "app",
                    "openEncrypt": 0,
                    "cameras": [{"cameraId": 0, "token": "cam"}],
                    "channelName": "ch",
                    "areaCode": "AREA_CODE_EU",
                    "token": "tok",
                    "uid": 1,
                },
            }
        ),
    ]
    http.refresh_login = AsyncMock(return_value=Response(code=0, msg="ok", data=MagicMock()))

    result = await http.get_stream_subscription("iot-1", is_yuka=False)

    assert result.data is not None
    assert result.data.token == "tok"
    http.refresh_login.assert_awaited_once()
    assert session.post.await_count == 2
    first_url = session.post.await_args_list[0].args[0]
    assert first_url.endswith("/device-server/v1/stream/token")
    assert "domestic.mammotion.com" in first_url


@pytest.mark.asyncio
async def test_stream_subscription_falls_back_to_robot_host() -> None:
    """Empty domestic response falls through to the JWT robot host."""
    http, session = _make_http()
    session.post.side_effect = [
        _json_response({"code": 0, "msg": "success", "data": None}),
        _json_response(
            {
                "code": 0,
                "msg": "success",
                "data": {
                    "appid": "app",
                    "openEncrypt": 0,
                    "cameras": [{"cameraId": 0, "token": "cam"}],
                    "channelName": "ch",
                    "areaCode": "AREA_CODE_EU",
                    "token": "eu-tok",
                    "uid": 2,
                },
            }
        ),
    ]

    result = await http.get_stream_subscription("iot-1", is_yuka=True)

    assert result.data is not None
    assert result.data.token == "eu-tok"
    assert session.post.await_count == 2
    second_url = session.post.await_args_list[1].args[0]
    assert second_url.startswith("https://api-robot-eu.example/")


@pytest.mark.asyncio
async def test_stream_subscription_returns_last_error_when_all_bases_fail() -> None:
    http, session = _make_http()
    session.post.side_effect = [
        _json_response(
            {"code": 401, "msg": "Access to this resource requires authentication", "data": None}
        ),
        _json_response(
            {"code": 401, "msg": "Access to this resource requires authentication", "data": None}
        ),
        _json_response({"code": 500, "msg": "boom", "data": None}),
    ]
    http.refresh_login = AsyncMock(return_value=Response(code=0, msg="ok", data=MagicMock()))

    result = await http.get_stream_subscription("iot-1", is_yuka=False)

    assert result.data is None
    assert result.code == 500
    http.refresh_login.assert_awaited_once()
    # domestic 401 + domestic retry after refresh + robot host
    assert session.post.await_count == 3
