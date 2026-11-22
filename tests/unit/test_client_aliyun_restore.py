"""Which devices a cache restore binds to Aliyun: the live listing decides, the cache is the fallback."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.exceptions import CloudSetupError
from pymammotion.aliyun.model.dev_by_account_response import Data, ListingDevAccountResponse
from pymammotion.auth.token_manager import TokenManager
from pymammotion.client import MammotionClient
from pymammotion.transport.base import TransportType
from tests._helpers import make_mock_http, make_mock_transport
from tests.unit.aliyun._helpers import make_gateway, make_listing_device, seed_listing

ACCOUNT = "user@test.com"


@pytest.fixture
async def client() -> AsyncIterator[MammotionClient]:
    c = MammotionClient()
    yield c
    await c.stop()


async def _restore(client: MammotionClient, gateway: CloudIOTGateway) -> None:
    """Run ``_restore_aliyun`` against *gateway* as the restored Aliyun session."""
    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
    session.mammotion_http = make_mock_http()
    gateway.mammotion_http = session.mammotion_http
    with (
        patch.object(CloudIOTGateway, "from_cache", AsyncMock(return_value=gateway)),
        patch.object(
            MammotionClient, "_setup_aliyun_transport", return_value=make_mock_transport(TransportType.CLOUD_ALIYUN)
        ),
        patch.object(
            MammotionClient,
            "_ensure_token_manager",
            AsyncMock(return_value=MagicMock(spec=TokenManager, reauth_required=None, aliyun_unavailable=None)),
        ),
        patch.object(CloudIOTGateway, "check_or_refresh_session", AsyncMock()),
    ):
        await client._restore_aliyun(ACCOUNT, {}, session, check_for_new_devices=True)  # noqa: SLF001


def _bound(client: MammotionClient) -> list[str]:
    return sorted(h.device_name for h in client._device_registry.all_devices)  # noqa: SLF001


@pytest.mark.regression
async def test_a_device_gone_from_the_live_listing_is_not_bound_from_the_cache(client: MammotionClient) -> None:
    """The cached listing was bound first, so a device unbound since it was written came back on every restart.

    It then 29004'd on its first send and failed whatever command the user had pressed.
    """
    gateway = make_gateway()
    seed_listing(gateway, make_listing_device("Yuka-MOVED", "iot-moved"), make_listing_device("RTK-KEEP", "iot-rtk"))

    async def _live_listing() -> None:
        seed_listing(gateway, make_listing_device("RTK-KEEP", "iot-rtk"))

    with patch.object(gateway, "list_binding_by_account", side_effect=_live_listing):
        await _restore(client, gateway)

    assert _bound(client) == ["RTK-KEEP"]
    assert [d.device_name for d in gateway.devices_by_account_response.data.data] == ["RTK-KEEP"]


async def test_the_cached_listing_is_used_when_the_live_one_cannot_be_fetched(client: MammotionClient) -> None:
    """A failed listing call is not "no devices": the cached bindings still come up."""
    gateway = make_gateway()
    seed_listing(gateway, make_listing_device("RTK-KEEP", "iot-rtk"))

    with patch.object(gateway, "list_binding_by_account", side_effect=CloudSetupError("401 request auth error")):
        await _restore(client, gateway)

    assert _bound(client) == ["RTK-KEEP"]


@pytest.mark.regression
async def test_an_unusable_cached_session_is_rebuilt_with_a_fresh_authorization_code(client: MammotionClient) -> None:
    """The rebuild reused the login's saved code, which is single-use and already spent, so Aliyun refused it."""
    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
    http = session.mammotion_http = make_mock_http()
    http.login_info.authorization_code = "spent"

    async def issue_code() -> None:
        http.login_info.authorization_code = "fresh"

    http.refresh_authorization_token = AsyncMock(side_effect=issue_code)
    codes_used: list[str] = []

    async def get_region(_country_code: str) -> None:
        codes_used.append(http.login_info.authorization_code)
        raise CloudSetupError("stop after the code is read")

    with (
        patch.object(CloudIOTGateway, "from_cache", AsyncMock(return_value=None)),
        patch.object(CloudIOTGateway, "get_region", side_effect=get_region),
    ):
        await client._restore_aliyun(ACCOUNT, {}, session, check_for_new_devices=True)  # noqa: SLF001

    assert codes_used == ["fresh"]


async def _restore_without_a_session(client: MammotionClient, cached_data: dict, session: AccountSession) -> None:
    """Run ``_restore_aliyun`` where neither the cached session nor a rebuild yields a gateway."""
    session.mammotion_http = session.mammotion_http or make_mock_http()
    token_manager = MagicMock(spec=TokenManager, reauth_required=None, aliyun_unavailable="refused")
    token_manager.recover_aliyun.return_value = None
    with (
        patch.object(CloudIOTGateway, "from_cache", AsyncMock(return_value=None)),
        patch.object(MammotionClient, "_ensure_token_manager", AsyncMock(return_value=token_manager)),
    ):
        await client._restore_aliyun(ACCOUNT, cached_data, session, check_for_new_devices=True)  # noqa: SLF001


def _listing_cache(*devices: object) -> dict:
    listing = ListingDevAccountResponse(
        code=200, data=Data(total=len(devices), data=list(devices), pageNo=1, pageSize=20)
    )
    return {"device_data": listing.to_dict()}


async def test_without_an_aliyun_session_the_cached_listing_keeps_its_devices_unavailable(
    client: MammotionClient,
) -> None:
    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
    await client.account_registry.register(session)

    await _restore_without_a_session(client, _listing_cache(make_listing_device("Luba-ALIYUN", "iot-1")), session)

    handle = client.mower("Luba-ALIYUN")
    assert handle is not None
    assert not handle.has_usable_transport
    assert [d.device_name for d in client.aliyun_device_list] == ["Luba-ALIYUN"]


async def test_a_listed_device_already_on_mammotion_mqtt_gets_no_aliyun_handle(client: MammotionClient) -> None:
    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
    session.mammotion_http = make_mock_http()
    session.mammotion_http.device_records = MagicMock(records=[MagicMock(device_name="Luba-MOVED")])

    await _restore_without_a_session(client, _listing_cache(make_listing_device("Luba-MOVED", "iot-1")), session)

    assert client.mower("Luba-MOVED") is None


@pytest.mark.parametrize("cached_data", [{}, {"device_data": {"code": "not-a-listing"}}], ids=["missing", "corrupt"])
async def test_an_absent_or_corrupt_cached_listing_keeps_no_devices(client: MammotionClient, cached_data: dict) -> None:
    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")

    await _restore_without_a_session(client, cached_data, session)

    assert _bound(client) == []
