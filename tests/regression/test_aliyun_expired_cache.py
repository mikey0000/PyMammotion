"""An expired Aliyun cache must not abort the account's independent MQTT restore."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from unittest.mock import create_autospec, patch

import pytest
import time_machine

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.model.aep_response import AepResponse, DeviceData
from pymammotion.aliyun.model.connect_response import ConnectResponse
from pymammotion.aliyun.model.dev_by_account_response import Data, ListingDevAccountResponse
from pymammotion.aliyun.model.login_by_oauth_response import LoginByOAuthResponse
from pymammotion.auth.token_manager import TokenManager
from pymammotion.client import MammotionClient
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import DeviceRecords, LoginResponseData, LoginResponseUserInformation, Response
from pymammotion.transport.aliyun_mqtt import AliyunMQTTTransport
from pymammotion.transport.base import SessionExpiredError, TransportType
from tests._helpers import encode_jwt
from tests.unit.aliyun._helpers import make_region, make_session


@pytest.fixture
def fixed_clock() -> Iterator[None]:
    with time_machine.travel("2026-01-01", tick=False):
        yield


def _credential_cache() -> dict:
    """Use real credential models; opaque connect/OAuth blobs only need their interfaces.

    The latter are not read during refresh and recreating their nested account
    payloads would obscure the expired session that this regression exercises.
    """
    login = LoginResponseData(
        access_token=encode_jwt(exp=9999999999),
        token_type="bearer",
        refresh_token="synthetic",
        expires_in=3600,
        authorization_code="synthetic",
        userInformation=LoginResponseUserInformation(
            areaCode="44",
            domainAbbreviation="EU",
            userId="u1",
            userAccount="123",
            authType="email",
        ),
    )
    return {
        "mammotion_data": Response(code=0, msg="ok", data=login),
        "connect_data": create_autospec(ConnectResponse, instance=True),
        "auth_data": create_autospec(LoginByOAuthResponse, instance=True),
        "region_data": make_region(),
        "aep_data": AepResponse(code=200, data=DeviceData("synthetic", "pk", "device")),
        "device_data": ListingDevAccountResponse(code=200, data=Data(total=0, data=[], pageNo=1, pageSize=10)),
        "session_data": make_session(),
        "mammotion_mqtt": None,
        "mammotion_device_records": DeviceRecords(),
    }


@pytest.fixture
async def client(fixed_clock: None) -> AsyncIterator[MammotionClient]:
    client = MammotionClient()
    yield client
    await client.stop()


@pytest.fixture
def cloud_boundaries(client: MammotionClient) -> Iterator[SimpleNamespace]:
    """Replace network and scheduler boundaries while restore and TokenManager run for real."""
    expired = SessionExpiredError(TransportType.CLOUD_ALIYUN, "2460 refreshToken expired")
    transport = create_autospec(AliyunMQTTTransport, instance=True)
    with (
        patch.object(CloudIOTGateway, "check_or_refresh_session", autospec=True, side_effect=expired) as refresh,
        patch.object(TokenManager, "establish_aliyun", autospec=True) as rebuild,
        patch.object(client, "_setup_aliyun_transport", autospec=True, return_value=transport) as setup,
        patch.object(client, "_restore_mammotion_mqtt", autospec=True, return_value=[]) as mqtt,
        patch.object(client, "login_and_initiate_cloud", autospec=True) as login,
        patch.object(
            MammotionHTTP, "get_user_device_list", autospec=True, return_value=Response(code=0, msg="ok", data=[])
        ),
        patch.object(TokenManager, "start_refresh_scheduler", autospec=True),
    ):
        yield SimpleNamespace(refresh=refresh, rebuild=rebuild, setup=setup, mqtt=mqtt, login=login)


def _complete_rebuild(tm: TokenManager, gateway: CloudIOTGateway, **_: object) -> CloudIOTGateway:
    """Supply the responses that the mocked IoT API chain would install.

    These responses have read-only properties; the real gateway has no public
    setter because its network methods own them.
    """
    gateway._aep_response = AepResponse(code=200, data=DeviceData("synthetic", "pk", "device"))
    gateway._region_response = make_region()
    gateway._session_by_authcode_response = make_session()
    tm.attach_cloud_gateway(gateway)
    return gateway


@pytest.mark.regression
async def test_expired_aliyun_cache_rebuilds_without_password_login(
    client: MammotionClient,
    cloud_boundaries: SimpleNamespace,
) -> None:
    """An expired refresh escaped from_cache before its caller could rebuild the IoT session."""
    cloud_boundaries.rebuild.side_effect = _complete_rebuild
    await client.restore_credentials("user@example.com", "unused", _credential_cache(), check_for_new_devices=False)

    cloud_boundaries.refresh.assert_awaited_once()
    cloud_boundaries.rebuild.assert_awaited_once()
    cloud_boundaries.setup.assert_called_once()
    cloud_boundaries.mqtt.assert_awaited_once()
    cloud_boundaries.login.assert_not_awaited()
    assert client.token_manager is not None
    assert client.token_manager.cloud_gateway is cloud_boundaries.rebuild.call_args.args[1]
    assert client.reauth_required is None


@pytest.mark.regression
async def test_failed_aliyun_rebuild_still_reaches_mammotion_restore(
    client: MammotionClient,
    cloud_boundaries: SimpleNamespace,
) -> None:
    """The same escaping refresh also prevented the independent MQTT restore from running."""
    cloud_boundaries.rebuild.side_effect = ConnectionError("Aliyun unavailable")
    await client.restore_credentials("user@example.com", "unused", _credential_cache(), check_for_new_devices=False)

    cloud_boundaries.refresh.assert_awaited_once()
    cloud_boundaries.rebuild.assert_awaited_once()
    cloud_boundaries.setup.assert_not_called()
    cloud_boundaries.mqtt.assert_awaited_once()
    cloud_boundaries.login.assert_not_awaited()
    assert client.token_manager is not None
    assert client.token_manager.cloud_gateway is None
    assert client.reauth_required is None


@pytest.mark.parametrize("error", [ConnectionError("offline"), TimeoutError("timeout")])
async def test_network_failure_during_aliyun_cache_refresh_propagates(error: Exception, fixed_clock: None) -> None:
    """A network failure is not evidence that the IoT session was rejected."""
    with (
        patch.object(CloudIOTGateway, "check_or_refresh_session", autospec=True, side_effect=error),
        pytest.raises(type(error)),
    ):
        await CloudIOTGateway.from_cache(_credential_cache(), MammotionHTTP())
