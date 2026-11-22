"""The fake cloud's fault vocabulary, driven through /control the way a test or a human drives it.

The fix phases express their failure scenarios with these knobs, so each one must
reach the client in the shape the real cloud uses.
"""

from __future__ import annotations

import aiohttp
import pytest

from pymammotion.client import MammotionClient
from pymammotion.transport.base import is_transient_network_error
from tests.fakeserver.cloud import FakeMammotionCloud

from ._helpers import log_in_aliyun_account

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _set_fault(cloud: FakeMammotionCloud, endpoint: str, fault: int | str | None) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{cloud.base_url}/control/set-fault", json={"endpoint": endpoint, "fault": fault}
        ) as resp:
            assert resp.status == 200


@pytest.mark.parametrize(
    ("fault", "status", "content_type"),
    [
        ("http_500", 500, "application/json"),
        ("http_401", 401, "application/json"),
        ("body_401", 200, "application/json"),
        ("non_json", 200, "text/html"),
        (2401, 200, "application/json"),
    ],
)
async def test_control_fault_shapes_the_endpoint_reply(
    fake_cloud: FakeMammotionCloud, fault: int | str, status: int, content_type: str
) -> None:
    await _set_fault(fake_cloud, "auth_code_fetches", fault)

    async with aiohttp.ClientSession() as session, session.post(f"{fake_cloud.base_url}/authorization/code") as resp:
        assert (resp.status, resp.content_type) == (status, content_type)


async def test_clearing_a_fault_restores_the_endpoint(fake_cloud: FakeMammotionCloud) -> None:
    await _set_fault(fake_cloud, "auth_code_fetches", "http_500")
    await _set_fault(fake_cloud, "auth_code_fetches", None)

    assert fake_cloud.scenario.faults == {}


async def test_disconnect_fault_reaches_the_gateway_as_a_transient_network_error(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    await log_in_aliyun_account(fake_cloud, client)
    assert client.token_manager is not None
    gateway = client.token_manager.cloud_gateway
    assert gateway is not None
    await _set_fault(fake_cloud, "aliyun_check_session", "disconnect")

    with pytest.raises(Exception) as excinfo:  # noqa: PT011 — the classification below is the assertion
        await gateway.check_or_refresh_session(force=True)

    assert is_transient_network_error(excinfo.value), f"{excinfo.value!r} would be treated as an auth verdict"
