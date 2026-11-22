"""A live session renewing itself: access-token and iotToken expiry, a rejected refresh token, a refused rebuild.

Aliyun forgetting the session is modelled server-side (``revoke_aliyun_session``):
the refresh token answers 2401 and a bind carrying the old iotToken answers 2043.
Dropping the broker connection makes the transport reconnect and present that
token, which is how a running client first learns of it.
"""

from __future__ import annotations

import time

import pytest
import time_machine

from pymammotion.client import MammotionClient
from tests._helpers import advance_real_time, wait_until
from tests.fakeserver.cloud import FakeMammotionCloud

from ._helpers import aliyun_transport, counts, log_in_aliyun_account, record_persisted

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CHAIN = ("password_grants", "refresh_grants", "auth_code_fetches", "aliyun_region", "aliyun_oauth")


async def test_expiring_access_token_is_refreshed_once_by_the_next_call_and_persisted(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client, hybrid=True)
    persisted = record_persisted(client)
    http = client.mammotion_http
    assert http is not None

    with time_machine.travel(time.time() + scenario.access_token_ttl - 60, tick=False):
        await http.get_user_device_list()

    assert counts(scenario, *_CHAIN) == {
        "password_grants": 0,
        "refresh_grants": 1,
        "auth_code_fetches": 0,
        "aliyun_region": 0,
        "aliyun_oauth": 0,
    }
    assert persisted, "the rotated refresh token was never handed to the host to persist"
    assert persisted[-1]["mammotion_data"].data.refresh_token == scenario.current_refresh_token


def _aliyun_forgets_the_session(cloud: FakeMammotionCloud) -> None:
    cloud.scenario.revoke_aliyun_session()
    cloud.aliyun_broker.drop_all_clients()


@pytest.mark.regression
async def test_rejected_refresh_token_is_rebuilt_with_a_fresh_code_and_persisted(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """A 2401 at runtime is recovered from the HTTP login, without the password and without user action.

    The rebuild reused the code the login had carried, which the first chain run had
    spent; loginbyoauth refused it with ``openId isEmpty`` and the Aliyun transport
    was given up for good.
    """
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client)
    persisted = record_persisted(client)

    _aliyun_forgets_the_session(fake_cloud)

    await wait_until(
        lambda: scenario.counters.get("aliyun_binds", 0) >= 2 and aliyun_transport(client, scenario).is_connected
    )
    assert fake_cloud.bind_requests[-1]["params"]["iotToken"] in scenario.iot_tokens, "rebound with a dead iotToken"
    assert counts(scenario, *_CHAIN, "aliyun_check_session") == {
        "password_grants": 0,
        "refresh_grants": 0,
        "auth_code_fetches": 1,
        "aliyun_region": 0,  # cached from the login
        "aliyun_oauth": 1,
        "aliyun_check_session": 1,
    }
    assert client.token_manager is not None
    assert client.token_manager.aliyun_unavailable is None
    assert persisted, "the rebuilt session was never handed to the host to persist"
    assert persisted[-1]["session_data"].data.refreshToken in scenario.valid_aliyun_refresh_tokens


async def test_refused_rebuild_gives_up_on_aliyun_alone(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """The rebuild is refused outright: Aliyun is given up, the login and Mammotion MQTT stay up, and it stays quiet."""
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client, hybrid=True)
    transport = aliyun_transport(client, scenario)
    scenario.faults["aliyun_session"] = 2064

    _aliyun_forgets_the_session(fake_cloud)

    await wait_until(lambda: not transport.is_usable)
    assert client.token_manager is not None
    assert client.token_manager.aliyun_unavailable is not None
    assert client.token_manager.reauth_required is None
    mammotion_mower = client.mower(scenario.device.device_name)
    assert mammotion_mower is not None
    assert mammotion_mower.has_usable_transport
    assert counts(scenario, *_CHAIN) == {
        "password_grants": 0,
        "refresh_grants": 0,
        "auth_code_fetches": 1,
        "aliyun_region": 0,
        "aliyun_oauth": 1,
    }
    given_up = counts(scenario, "aliyun_binds", "aliyun_check_session", "auth_code_fetches", "aliyun_oauth")
    # Silence is only provable by letting several patched reconnect backoffs pass.
    await advance_real_time(0.4)
    assert counts(scenario, *given_up) == given_up


async def test_expiring_iot_token_is_renewed_in_band_by_the_next_command(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    scenario = fake_cloud.scenario
    scenario.access_token_ttl = 4 * 86400  # keep the HTTP login out of the way of the jump below
    await log_in_aliyun_account(fake_cloud, client)
    transport = aliyun_transport(client, scenario)
    iot_id = scenario.aliyun_device.iot_id

    with time_machine.travel(time.time() + scenario.iot_token_ttl - 1800, tick=False):
        await transport.send(b"\x08\x01", iot_id=iot_id)

    assert (iot_id, b"\x08\x01") in fake_cloud.aliyun_invocations
    assert counts(scenario, *_CHAIN, "aliyun_check_session") == {
        "password_grants": 0,
        "refresh_grants": 0,
        "auth_code_fetches": 0,
        "aliyun_region": 0,
        "aliyun_oauth": 0,
        "aliyun_check_session": 1,
    }


@pytest.mark.regression
async def test_an_in_band_iot_token_renewal_reaches_the_transport_and_the_cache(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """The gateway renewed its own session inside a send, out of the TokenManager's sight.

    Nothing was persisted, so a restart restored the token it replaced, and the transport
    kept binding with the old one on every reconnect.
    """
    scenario = fake_cloud.scenario
    scenario.access_token_ttl = 4 * 86400
    await log_in_aliyun_account(fake_cloud, client)
    persisted = record_persisted(client)
    transport = aliyun_transport(client, scenario)
    old_token = client.to_cache()["session_data"].data.iotToken

    with time_machine.travel(time.time() + scenario.iot_token_ttl - 1800, tick=False):
        await transport.send(b"\x08\x01", iot_id=scenario.aliyun_device.iot_id)

    renewed = client.to_cache()["session_data"].data.iotToken
    assert renewed != old_token
    assert persisted, "the renewed session was never handed to the host to persist"
    assert persisted[-1]["session_data"].data.iotToken == renewed
    binds = len(fake_cloud.bind_requests)
    fake_cloud.aliyun_broker.drop_all_clients()
    await wait_until(lambda: len(fake_cloud.bind_requests) > binds and transport.is_connected)
    assert fake_cloud.bind_requests[-1]["params"]["iotToken"] == renewed


@pytest.mark.regression
async def test_a_forced_access_token_refresh_is_persisted_once(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """refresh_http persisted the rotation itself and again through the login-refreshed hook: two writes per refresh."""
    scenario = fake_cloud.scenario
    await client.login_and_initiate_cloud(scenario.account, scenario.password)
    await fake_cloud.baseline_counters()
    persisted = record_persisted(client)
    assert client.token_manager is not None

    await client.token_manager.refresh_invoke_token()

    assert scenario.counters.get("refresh_grants") == 1
    assert len(persisted) == 1, f"persisted {len(persisted)} times for one refresh"
