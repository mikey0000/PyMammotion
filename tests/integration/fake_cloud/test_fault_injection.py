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


async def _set_fault(cloud: FakeMammotionCloud, endpoint: str, fault: int | str | None) -> int:
    async with (
        aiohttp.ClientSession() as session,
        session.post(f"{cloud.base_url}/control/set-fault", json={"endpoint": endpoint, "fault": fault}) as resp,
    ):
        return resp.status


async def _fetch_auth_code(cloud: FakeMammotionCloud) -> tuple[int, str, int | None]:
    """POST /authorization/code with a live bearer; (status, content type, in-body code or None)."""
    access_token = cloud.scenario.mint_login_data(cloud.base_url)["access_token"]
    async with (
        aiohttp.ClientSession() as session,
        session.post(
            f"{cloud.base_url}/authorization/code", headers={"Authorization": f"Bearer {access_token}"}
        ) as resp,
    ):
        code = (await resp.json())["code"] if resp.content_type == "application/json" else None
        return resp.status, resp.content_type, code


async def test_an_unfaulted_endpoint_answers_success(fake_cloud: FakeMammotionCloud) -> None:
    assert await _fetch_auth_code(fake_cloud) == (200, "application/json", 0)


@pytest.mark.parametrize(
    ("fault", "reply"),
    [
        ("http_500", (500, "application/json", 500)),
        ("http_401", (401, "application/json", 401)),
        ("body_401", (200, "application/json", 401)),
        ("non_json", (200, "text/html", None)),
        (2401, (200, "application/json", 2401)),
    ],
)
async def test_control_fault_shapes_the_endpoint_reply(
    fake_cloud: FakeMammotionCloud, fault: int | str, reply: tuple[int, str, int | None]
) -> None:
    assert await _set_fault(fake_cloud, "auth_code_fetches", fault) == 200

    assert await _fetch_auth_code(fake_cloud) == reply


async def test_clearing_a_fault_restores_the_endpoint(fake_cloud: FakeMammotionCloud) -> None:
    await _set_fault(fake_cloud, "auth_code_fetches", "http_500")
    await _set_fault(fake_cloud, "auth_code_fetches", None)

    assert await _fetch_auth_code(fake_cloud) == (200, "application/json", 0)


async def test_a_fault_on_an_unknown_endpoint_is_refused(fake_cloud: FakeMammotionCloud) -> None:
    """A misspelt endpoint would otherwise be stored and never fire, and the test using it would pass vacuously."""
    assert await _set_fault(fake_cloud, "auth_code_fetch", "http_500") == 400

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
