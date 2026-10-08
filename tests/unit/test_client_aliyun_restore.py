"""Which devices a cache restore binds to Aliyun: the live listing decides, the cache is the fallback."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.exceptions import CloudSetupError
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
        patch.object(MammotionClient, "_ensure_token_manager", AsyncMock(return_value=MagicMock(spec=TokenManager))),
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
