"""Rebuilding a rejected Aliyun session at runtime, and how each failure of the rebuild is classified.

The rebuild runs ``TokenManager.establish_aliyun``: mint a fresh authorization code
from the HTTP login, then the region / loginbyoauth / session chain.  Each test makes
Aliyun forget the session (``revoke_aliyun_session``) so the next refresh answers 2401,
then drives that refresh directly rather than through the transport.
"""

from __future__ import annotations

import pytest

from pymammotion.client import MammotionClient
from pymammotion.transport.base import is_transient_network_error
from tests._helpers import wait_until
from tests.fakeserver.cloud import FakeMammotionCloud

from ._helpers import aliyun_transport, counts, log_in_aliyun_account

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CHAIN = ("password_grants", "refresh_grants", "auth_code_fetches", "aliyun_region", "aliyun_oauth")


@pytest.mark.regression
async def test_a_refused_bearer_on_the_code_fetch_is_refreshed_once_and_the_rebuild_completes(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """A bearer revoked server-side made /authorization/code answer 401, and the rebuild ran on with the spent code.

    That made the Aliyun transport terminal although one refresh of the bearer would have fixed it.
    """
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client)
    token_manager = client.token_manager
    assert token_manager is not None
    scenario.revoke_access_tokens()
    scenario.revoke_aliyun_session()

    await token_manager.refresh_aliyun_credentials()

    assert counts(scenario, *_CHAIN) == {
        "password_grants": 0,
        "refresh_grants": 1,
        "auth_code_fetches": 2,
        "aliyun_region": 0,
        "aliyun_oauth": 1,
    }
    assert token_manager.aliyun_unavailable is None


@pytest.mark.regression
@pytest.mark.parametrize("fault", ["http_500", "non_json"])
async def test_a_server_fault_on_the_code_fetch_is_transient_and_runs_no_chain(
    fake_cloud: FakeMammotionCloud, client: MammotionClient, fault: str
) -> None:
    """The fetch answered ``Response(200)`` on a fault, the chain spent the old code, and Aliyun was given up for good."""
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client)
    token_manager = client.token_manager
    assert token_manager is not None
    scenario.revoke_aliyun_session()
    scenario.faults["auth_code_fetches"] = fault

    with pytest.raises(Exception) as excinfo:  # noqa: PT011 — the classification below is the assertion
        await token_manager.refresh_aliyun_credentials()

    assert is_transient_network_error(excinfo.value), f"{excinfo.value!r} would be treated as a verdict"
    assert token_manager.aliyun_unavailable is None
    assert counts(scenario, "auth_code_fetches", "aliyun_region", "aliyun_oauth") == {
        "auth_code_fetches": 1,
        "aliyun_region": 0,
        "aliyun_oauth": 0,
    }


@pytest.mark.regression
async def test_a_transient_rebuild_failure_on_reconnect_backs_off_and_recovers(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """A network fault while the transport rebuilt its session killed the transport until a restart.

    The auth-failure callback swallowed the transient error and answered "give up", so the
    transport was marked auth-failed and refused to reconnect once the cloud was back.
    """
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client)
    transport = aliyun_transport(client, scenario)
    scenario.faults["auth_code_fetches"] = "http_500"
    scenario.revoke_aliyun_session()
    fake_cloud.aliyun_broker.drop_all_clients()

    await wait_until(lambda: scenario.counters.get("auth_code_fetches", 0) >= 2, message="it never retried")
    assert transport.is_usable, "a transient fault gave the transport up"
    del scenario.faults["auth_code_fetches"]

    await wait_until(lambda: transport.is_connected)
    assert client.token_manager is not None
    assert client.token_manager.aliyun_unavailable is None
    assert scenario.counters.get("password_grants", 0) == 0
