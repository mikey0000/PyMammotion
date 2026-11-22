"""First login of an account with Aliyun-bound mowers, through the fake cloud's Aliyun chain.

The login's own authorization code is what seeds the chain, so none of these
spend a call on /authorization/code.
"""

from __future__ import annotations

import pytest

from pymammotion.client import MammotionClient
from pymammotion.transport.base import TransportType, is_transient_network_error
from tests._helpers import wait_until
from tests.fakeserver.cloud import FakeMammotionCloud

from ._helpers import aliyun_transport, counts, make_aliyun_account, make_cached_login

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CHAIN = ("password_grants", "refresh_grants", "auth_code_fetches", "aliyun_region", "aliyun_oauth", "aliyun_session")


async def test_aliyun_only_login_binds_the_mower_with_one_chain_run(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario)

    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    transport = aliyun_transport(client, scenario)
    await wait_until(lambda: transport.is_connected)
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
    await wait_until(lambda: transport.is_connected)
    await wait_until(lambda: len(fake_cloud.mammotion_broker.sessions) == 1)
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
    first = aliyun_transport(client, scenario)
    await wait_until(lambda: first.is_connected)
    await fake_cloud.baseline_counters()

    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    second = aliyun_transport(client, scenario)
    assert second is not first, "the second login kept the first login's transport"
    await wait_until(lambda: second.is_connected)
    assert not first.is_connected
    # A leaked first transport keeps its broker session, so this times out rather than settling.
    await wait_until(lambda: len(fake_cloud.aliyun_broker.sessions) == 1)
    assert counts(scenario, *_CHAIN) == {
        "password_grants": 1,
        "refresh_grants": 0,
        "auth_code_fetches": 0,
        "aliyun_region": 1,
        "aliyun_oauth": 1,
        "aliyun_session": 1,
    }


@pytest.mark.regression
async def test_a_hybrid_login_whose_aliyun_side_is_refused_reports_it(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """The refusal was logged and dropped: the login looked complete, so the host saved a cache with no Aliyun half.

    Every later restore then skipped Aliyun for want of ``aep_data``, and the mowers stayed gone.
    """
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario, hybrid=True)
    scenario.faults["aliyun_session"] = 2064

    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    assert set(client.unavailable_transports(scenario.account)) == {TransportType.CLOUD_ALIYUN}
    assert client.mower(scenario.device.device_name) is not None


@pytest.mark.regression
async def test_a_hybrid_login_whose_aliyun_side_hits_a_network_fault_raises_it(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """A transient fault was swallowed like a refusal, so a login that a retry would complete was saved half-built."""
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario, hybrid=True)
    scenario.faults["aliyun_oauth"] = "disconnect"

    with pytest.raises(Exception) as excinfo:  # noqa: PT011 — the classification below is the assertion
        await client.login_and_initiate_cloud(scenario.account, scenario.password)

    assert is_transient_network_error(excinfo.value), f"{excinfo.value!r} would read as a verdict"


@pytest.mark.regression
async def test_restore_establishes_aliyun_for_a_cache_saved_without_it(fake_cloud: FakeMammotionCloud) -> None:
    """The restore tried Aliyun only when ``aep_data`` was cached, so a half-saved cache lost its Aliyun mowers for good.

    The healthy login is enough to mint the session: the account owns a device the
    Mammotion device page does not list, so Aliyun is expected.
    """
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario, hybrid=True)
    cached = await make_cached_login(fake_cloud)
    for key in ("connect_data", "auth_data", "region_data", "aep_data", "session_data", "device_data"):
        cached.pop(key, None)
    restored = MammotionClient()
    try:
        await restored.restore_credentials(scenario.account, scenario.password, cached)

        await wait_until(lambda: aliyun_transport(restored, scenario).is_connected)
        assert scenario.counters.get("password_grants", 0) == 0
    finally:
        await restored.stop()
