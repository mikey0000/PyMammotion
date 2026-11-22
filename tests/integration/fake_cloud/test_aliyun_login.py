"""First login of an account with Aliyun-bound mowers, through the fake cloud's Aliyun chain.

The login's own authorization code is what seeds the chain, so none of these
spend a call on /authorization/code.
"""

from __future__ import annotations

import pytest

from pymammotion.client import MammotionClient
from tests.fakeserver.cloud import FakeMammotionCloud

from ._helpers import aliyun_transport, counts, make_aliyun_account
from .conftest import wait_for

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CHAIN = ("password_grants", "refresh_grants", "auth_code_fetches", "aliyun_region", "aliyun_oauth", "aliyun_session")


async def test_aliyun_only_login_binds_the_mower_with_one_chain_run(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario)

    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    transport = aliyun_transport(client, scenario)
    await wait_for(lambda: transport.is_connected)
    assert counts(scenario, *_CHAIN, "aliyun_binds", "mammotion_mqtt_connects") == {
        "password_grants": 1,
        "refresh_grants": 0,
        "auth_code_fetches": 0,
        "aliyun_region": 1,
        "aliyun_oauth": 1,
        "aliyun_session": 1,
        "aliyun_binds": 1,
        "mammotion_mqtt_connects": 0,
    }
    assert "aep_data" in client.to_cache(), "the Aliyun session must be cacheable for the next restore"


async def test_hybrid_login_brings_up_both_transports(fake_cloud: FakeMammotionCloud, client: MammotionClient) -> None:
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario, hybrid=True)

    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    transport = aliyun_transport(client, scenario)
    await wait_for(lambda: transport.is_connected)
    await wait_for(lambda: len(fake_cloud.mammotion_broker.sessions) == 1)
    mammotion_mower = client.mower(scenario.device.device_name)
    assert mammotion_mower is not None
    assert mammotion_mower.has_usable_transport
    assert counts(scenario, *_CHAIN) == {
        "password_grants": 1,
        "refresh_grants": 0,
        "auth_code_fetches": 0,
        "aliyun_region": 1,
        "aliyun_oauth": 1,
        "aliyun_session": 1,
    }
    cached = client.to_cache()
    assert {"aep_data", "session_data", "mammotion_mqtt"} <= cached.keys()


async def test_login_accepts_a_pending_aliyun_share(fake_cloud: FakeMammotionCloud, client: MammotionClient) -> None:
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario)
    scenario.aliyun_pending_share = True

    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    assert scenario.confirmed_shares == [["fake-share-record"]]


async def test_second_login_replaces_the_aliyun_session_without_leaking_the_first(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """A reauth or reconfigure logs in again on the live client: one password grant, one fresh chain."""
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario, hybrid=True)
    await client.login_and_initiate_cloud(scenario.account, scenario.password)
    await wait_for(lambda: aliyun_transport(client, scenario).is_connected)
    await fake_cloud.baseline_counters()

    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    transport = aliyun_transport(client, scenario)
    await wait_for(lambda: transport.is_connected)
    # A leaked first transport keeps its broker session, so this times out rather than settling.
    await wait_for(lambda: len(fake_cloud.aliyun_broker.sessions) == 1)
    assert counts(scenario, *_CHAIN) == {
        "password_grants": 1,
        "refresh_grants": 0,
        "auth_code_fetches": 0,
        "aliyun_region": 1,
        "aliyun_oauth": 1,
        "aliyun_session": 1,
    }
