"""Rebuilding a rejected Aliyun session from the HTTP login's authCode chain."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.auth.token_manager import TokenManager
from pymammotion.transport.base import SessionExpiredError, TransportType
from tests.unit.auth._helpers import make_http_mock


@pytest.mark.regression
async def test_aliyun_2401_rebuild_uses_a_fresh_authorization_code() -> None:
    """The rebuild reused the login's saved code, which is single-use and already spent, so Aliyun refused it."""
    http = make_http_mock(access_token="a", refresh_token="r")
    gateway = MagicMock(mammotion_http=http, region_response=None)
    gateway.check_or_refresh_session = AsyncMock(
        side_effect=SessionExpiredError(TransportType.CLOUD_ALIYUN, "2401 refreshToken invalid")
    )
    for step in ("get_region", "connect", "aep_handle", "session_by_auth_code", "list_binding_by_account"):
        setattr(gateway, step, AsyncMock())
    gateway.session_by_authcode_response = MagicMock(
        data=MagicMock(iotToken="iot-new", iotTokenExpire=7200, refreshToken="r", refreshTokenExpire=86400)
    )
    gateway._iot_token_issued_at = int(time.time())
    tm = TokenManager(account_id="user@example.com", mammotion_http=http, cloud_gateway=gateway)
    http.login_info.authorization_code = "spent"

    async def issue_code() -> None:
        http.login_info.authorization_code = "fresh"

    http.fetch_authorization_token = AsyncMock(side_effect=issue_code)
    codes_used: list[str] = []

    async def login_by_oauth(_country_code: str) -> None:
        codes_used.append(http.login_info.authorization_code)

    gateway.login_by_oauth = AsyncMock(side_effect=login_by_oauth)

    await tm.refresh_aliyun_credentials()

    assert codes_used == ["fresh"]
    http.login_v2.assert_not_called()
