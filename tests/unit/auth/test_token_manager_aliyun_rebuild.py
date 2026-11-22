"""Rebuilding a rejected Aliyun session from the HTTP login's authCode chain."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.exceptions import CloudSetupError
from pymammotion.auth.token_manager import TokenManager
from pymammotion.transport.base import SessionExpiredError, TransportType
from tests.unit.auth._helpers import make_http_mock


@pytest.mark.regression
async def test_aliyun_2401_rebuild_uses_a_fresh_authorization_code() -> None:
    """The rebuild reused the login's saved code, which is single-use and already spent, so Aliyun refused it."""
    http = make_http_mock(access_token="a", refresh_token="r")
    gateway = create_autospec(CloudIOTGateway, instance=True, mammotion_http=http, region_response=None)
    gateway.check_or_refresh_session.side_effect = SessionExpiredError(
        TransportType.CLOUD_ALIYUN, "2401 refreshToken invalid"
    )
    gateway.session_by_authcode_response = MagicMock(
        data=MagicMock(iotToken="iot-new", iotTokenExpire=7200, refreshToken="r", refreshTokenExpire=86400)
    )
    gateway._iot_token_issued_at = 1_700_000_000
    tm = TokenManager(account_id="user@example.com", mammotion_http=http, cloud_gateway=gateway)
    http.login_info.authorization_code = "spent"

    async def issue_code() -> None:
        http.login_info.authorization_code = "fresh"

    http.fetch_authorization_token = AsyncMock(side_effect=issue_code)
    codes_used: list[str] = []

    async def login_by_oauth(_country_code: str) -> None:
        codes_used.append(http.login_info.authorization_code)

    gateway.login_by_oauth.side_effect = login_by_oauth
    gateway.get_region.side_effect = lambda _country_code: setattr(gateway, "region_response", MagicMock())

    await tm.refresh_aliyun_credentials()

    assert codes_used == ["fresh"]


def _chain_gateway(http: AsyncMock, *, complete: bool = True) -> MagicMock:
    """A gateway double whose chain steps succeed; *complete* decides whether they leave a usable session."""
    gateway = create_autospec(CloudIOTGateway, instance=True, mammotion_http=http, region_response=None)
    steps: list[str] = []
    for step in ("connect", "login_by_oauth", "aep_handle", "session_by_auth_code"):
        getattr(gateway, step).side_effect = lambda *_, name=step: steps.append(name)

    def _get_region(_country_code: str) -> None:
        steps.append("get_region")
        gateway.region_response = MagicMock()

    gateway.get_region.side_effect = _get_region
    gateway.list_binding_by_account.side_effect = lambda: steps.append("list_binding_by_account")
    gateway.aep_response = MagicMock() if complete else None
    gateway.session_by_authcode_response = MagicMock(data=MagicMock()) if complete else None
    gateway.steps = steps
    return gateway


async def test_establish_aliyun_mints_a_code_runs_the_chain_and_attaches_the_gateway() -> None:
    http = make_http_mock(access_token="a", refresh_token="r")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)
    gateway = _chain_gateway(http)

    assert await tm.establish_aliyun(gateway) is gateway

    http.fetch_authorization_token.assert_awaited_once()
    assert gateway.steps == [
        "get_region",
        "connect",
        "login_by_oauth",
        "aep_handle",
        "session_by_auth_code",
        "list_binding_by_account",
    ]
    assert tm.cloud_gateway is gateway


async def test_establish_aliyun_for_a_fresh_login_spends_the_logins_own_code() -> None:
    http = make_http_mock(access_token="a", refresh_token="r")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)

    await tm.establish_aliyun(_chain_gateway(http), fresh_code=False)

    http.fetch_authorization_token.assert_not_awaited()


async def test_establish_aliyun_refuses_a_session_the_chain_left_incomplete() -> None:
    http = make_http_mock(access_token="a", refresh_token="r")
    tm = TokenManager(account_id="user@example.com", mammotion_http=http)

    with pytest.raises(CloudSetupError):
        await tm.establish_aliyun(_chain_gateway(http, complete=False))

    assert tm.cloud_gateway is None
