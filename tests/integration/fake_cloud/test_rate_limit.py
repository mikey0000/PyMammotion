"""An auth endpoint answering HTTP 429, end to end: one request, then nothing until the cooldown ends.

A throttle is neither a rejected login nor a network blip, so it costs no password grant,
sets no terminal flag, gives no transport up, and is not retried until the cooldown is over.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest
import time_machine

from pymammotion.client import MammotionClient
from pymammotion.http.http import _AUTH_RATE_LIMIT_COOLDOWN_SEC
from pymammotion.http.model.http import RateLimitedError
from tests._helpers import wait_until
from tests.fakeserver.cloud import FakeMammotionCloud

from ._helpers import aliyun_transport, counts, log_in_aliyun_account, make_cached_login

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _assert_nothing_terminal(client: MammotionClient, account: str) -> None:
    assert client.reauth_required is None, "a throttle marked the login dead"
    assert client.unavailable_transports(account) == {}, "a throttle gave a transport up"


@pytest.mark.regression
async def test_a_throttled_refresh_costs_one_request_until_the_cooldown_ends(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """A 429 on oauth2/token was retried as a network blip, one more throttled grant per caller and per retry."""
    scenario = fake_cloud.scenario
    await client.login_and_initiate_cloud(scenario.account, scenario.password)
    await fake_cloud.baseline_counters()
    http = client.mammotion_http
    assert http is not None
    scenario.oauth_http_status = 429

    with time_machine.travel(time.time() + scenario.access_token_ttl - 60, tick=False) as clock:
        for _ in range(3):
            with pytest.raises(RateLimitedError):
                await http.get_user_device_list()

        # Every oauth2/token request answers 429 here, a password grant included.
        assert counts(scenario, "oauth_429") == {"oauth_429": 1}
        _assert_nothing_terminal(client, scenario.account)

        scenario.oauth_http_status = None
        clock.shift(_AUTH_RATE_LIMIT_COOLDOWN_SEC)
        await http.get_user_device_list()

    assert counts(scenario, "oauth_429", "refresh_grants", "password_grants") == {
        "oauth_429": 1,
        "refresh_grants": 1,
        "password_grants": 0,
    }


@pytest.mark.regression
async def test_a_throttled_jwt_fetch_leaves_the_mammotion_transport_in_place(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """A 429 on mqtt/auth/jwt gave Mammotion MQTT up, so the mower stayed unavailable until reload."""
    scenario = fake_cloud.scenario
    await client.login_and_initiate_cloud(scenario.account, scenario.password)
    await fake_cloud.baseline_counters()
    token_manager = client.token_manager
    assert token_manager is not None
    scenario.faults["mqtt_jwt_fetches"] = "http_429"

    for _ in range(3):
        with pytest.raises(RateLimitedError):
            await token_manager.refresh_mqtt_credentials()

    assert counts(scenario, "mqtt_jwt_fetches", "refresh_grants", "password_grants") == {
        "mqtt_jwt_fetches": 1,
        "refresh_grants": 0,
        "password_grants": 0,
    }
    _assert_nothing_terminal(client, scenario.account)


@pytest.mark.regression
async def test_a_throttled_restore_raises_rate_limited_without_prompting_for_reauth(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """A restore throttled at oauth2/token reached the host as a transient error, which it retried on a backoff."""
    scenario = fake_cloud.scenario
    cached = await make_cached_login(fake_cloud)
    scenario.age_cached_access_token(cached, remaining=60.0)
    scenario.oauth_http_status = 429
    told = AsyncMock()
    client.on_unrecoverable_auth_error = told

    with pytest.raises(RateLimitedError):
        await client.restore_credentials(scenario.account, scenario.password, cached)

    assert counts(scenario, "oauth_429", "password_grants") == {"oauth_429": 1, "password_grants": 0}
    _assert_nothing_terminal(client, scenario.account)
    told.assert_not_awaited()


@pytest.mark.regression
async def test_a_throttled_aliyun_rebuild_backs_off_without_giving_the_transport_up(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """A 429 on the rebuild's authorization code gave the Aliyun transport up for good after a 2401."""
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client)
    transport = aliyun_transport(client, scenario)
    scenario.faults["auth_code_fetches"] = "http_429"

    scenario.revoke_aliyun_session()
    fake_cloud.aliyun_broker.drop_all_clients()
    # Each reconnect is refused (2043) and asks for a rebuild; only the first may reach the code endpoint.
    await wait_until(lambda: scenario.counters.get("aliyun_binds", 0) >= 3)

    assert counts(scenario, "auth_code_fetches", "password_grants") == {"auth_code_fetches": 1, "password_grants": 0}
    assert transport.is_usable, "the Aliyun transport was given up over a throttle"
    _assert_nothing_terminal(client, scenario.account)
