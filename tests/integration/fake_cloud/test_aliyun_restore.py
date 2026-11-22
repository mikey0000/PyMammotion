"""Restoring an account with Aliyun-bound mowers from its credential cache.

A healthy cache costs no login and no chain run.  A cached Aliyun session the
server has rejected is rebuilt from the validated HTTP login, which needs a fresh
authorization code: the one the login carried was spent by the first chain run.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pymammotion.client import MammotionClient
from tests._helpers import wait_until
from tests.fakeserver.cloud import FakeMammotionCloud
from tests.fakeserver.scenario import Scenario

from ._helpers import aliyun_transport, counts, make_aliyun_account, make_cached_login, record_persisted

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CHAIN = ("password_grants", "refresh_grants", "auth_code_fetches", "aliyun_region", "aliyun_oauth")


@pytest.mark.parametrize("hybrid", [False, True], ids=["aliyun-only", "hybrid"])
async def test_restore_with_a_healthy_cache_runs_no_login_and_no_chain(
    fake_cloud: FakeMammotionCloud, hybrid: bool
) -> None:
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario, hybrid=hybrid)
    cached = await make_cached_login(fake_cloud)

    client = MammotionClient()
    try:
        await client.restore_credentials(scenario.account, scenario.password, cached)

        transport = aliyun_transport(client, scenario)
        await wait_until(lambda: transport.is_connected)
        assert counts(scenario, *_CHAIN) == dict.fromkeys(_CHAIN, 0)
        # One forced refresh: a cold restore cannot trust the cached iotToken (another client may have rotated it).
        assert scenario.counters.get("aliyun_check_session", 0) == 1
        if hybrid:
            assert client.mower(scenario.device.device_name) is not None
    finally:
        await client.stop()


@pytest.mark.regression
async def test_restore_binds_with_the_iot_token_its_forced_refresh_minted(fake_cloud: FakeMammotionCloud) -> None:
    """The transport was built before the restore's forced session refresh and bound with the token it replaced.

    The refresh went straight to the gateway, so neither the transport nor the host's cache heard of the new token.
    """
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario)
    cached = await make_cached_login(fake_cloud)
    client = MammotionClient()
    persisted = record_persisted(client)
    try:
        await client.restore_credentials(scenario.account, scenario.password, cached)

        transport = aliyun_transport(client, scenario)
        await wait_until(lambda: transport.is_connected)
        refreshed = client.to_cache()["session_data"].data.iotToken
        assert refreshed != cached["session_data"].data.iotToken
        assert fake_cloud.bind_requests[-1]["params"]["iotToken"] == refreshed
        assert persisted, "the refreshed session was never handed to the host to persist"
        assert persisted[-1]["session_data"].data.iotToken == refreshed
    finally:
        await client.stop()


async def test_restore_with_an_expiring_access_token_refreshes_it_once_and_persists_the_rotation(
    fake_cloud: FakeMammotionCloud,
) -> None:
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario, hybrid=True)
    cached = await make_cached_login(fake_cloud)
    scenario.age_cached_access_token(cached, remaining=60.0)
    client = MammotionClient()
    persisted = record_persisted(client)
    try:
        await client.restore_credentials(scenario.account, scenario.password, cached)

        assert counts(scenario, *_CHAIN) == {
            "password_grants": 0,
            "refresh_grants": 1,
            "auth_code_fetches": 0,
            "aliyun_region": 0,
            "aliyun_oauth": 0,
        }
        assert persisted, "the rotated refresh token was never handed to the host to persist"
        assert persisted[-1]["mammotion_data"].data.refresh_token == scenario.current_refresh_token
    finally:
        await client.stop()


def _reject_the_refresh_token(scenario: Scenario) -> None:
    scenario.revoke_aliyun_session()


def _fail_check_session_with_2460(scenario: Scenario) -> None:
    scenario.faults["aliyun_check_session"] = 2460


@pytest.mark.regression
@pytest.mark.parametrize(
    "reject_session",
    [_reject_the_refresh_token, _fail_check_session_with_2460],
    ids=["2401-refresh-token-rejected", "2460"],
)
async def test_restore_rebuilds_a_rejected_aliyun_session_with_a_fresh_code(
    fake_cloud: FakeMammotionCloud, reject_session: Callable[[Scenario], None]
) -> None:
    """A rejected cached Aliyun session is rebuilt from the HTTP login, never from the password.

    The rebuild reused the code the login had carried.  That code was spent by the
    first chain run, so getRegion refused it with ``openId isEmpty``, the rebuild
    failed, and the Aliyun mowers silently vanished until the user logged in again.
    """
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario)
    cached = await make_cached_login(fake_cloud)
    old_refresh_token = cached["session_data"].data.refreshToken
    scenario.age_cached_aliyun_session(cached)
    reject_session(scenario)

    client = MammotionClient()
    try:
        await client.restore_credentials(scenario.account, scenario.password, cached)

        transport = aliyun_transport(client, scenario)
        await wait_until(lambda: transport.is_connected)
        assert counts(scenario, *_CHAIN, "aliyun_session") == {
            "password_grants": 0,
            "refresh_grants": 0,
            "auth_code_fetches": 1,
            "aliyun_region": 1,
            "aliyun_oauth": 1,
            "aliyun_session": 1,
        }
        session = client.to_cache()["session_data"].data
        assert session.refreshToken != old_refresh_token
        assert session.refreshToken in scenario.valid_aliyun_refresh_tokens, (
            "the cache holds a session the server no longer knows"
        )
    finally:
        await client.stop()
