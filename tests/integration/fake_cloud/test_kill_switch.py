"""Account-death behaviour against the live fake cloud.

The core requirement: once the server rejects the refresh token, ALL cloud
traffic for that account stops — MQTT disconnected, no oauth2/token attempts,
no invoke calls, decorated endpoints failing fast — and the host is told once.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from pymammotion.client import MammotionClient
from pymammotion.transport.base import NoTransportAvailableError, ReLoginRequiredError, TransportType
from tests.fakeserver.cloud import FakeMammotionCloud
from tests._helpers import advance_real_time, wait_until

from ._helpers import counts, log_in_aliyun_account

pytestmark = pytest.mark.asyncio(loop_scope="session")

_OAUTH_COUNTERS = ("password_grants", "refresh_grants", "auth_code_fetches", "invoke_calls", "mqtt_jwt_fetches")


async def test_server_side_session_death_quiesces_everything(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    scenario = fake_cloud.scenario
    await client.login_and_initiate_cloud(scenario.account, scenario.password)
    await wait_until(lambda: len(fake_cloud.mammotion_broker.sessions) == 1)

    on_dead = AsyncMock()
    client.on_unrecoverable_auth_error = on_dead
    session = client._account_registry.get(scenario.account)
    assert session is not None and session.mammotion_transport is not None
    transport = session.mammotion_transport

    # The server kills the whole session: bearers revoked AND refresh token dead.
    scenario.expire_session()

    with pytest.raises(NoTransportAvailableError):
        await transport.send(b"\x08\x01", iot_id=scenario.device.iot_id)

    # The kill switch runs as a detached task — wait for its effects.
    await wait_until(lambda: client.reauth_required is not None)
    await wait_until(lambda: not transport.is_usable)
    await wait_until(lambda: len(fake_cloud.mammotion_broker.sessions) == 0)
    await wait_until(lambda: on_dead.await_count == 1)
    assert on_dead.await_args.args[0] == scenario.account

    # From here on: total silence.  Whatever poll loops or queues still exist,
    # not one more oauth2/token, invoke, or credential fetch may reach the server.
    before = {name: scenario.counters.get(name, 0) for name in _OAUTH_COUNTERS}
    mqtt_connects_before = scenario.counters.get("mammotion_mqtt_connects", 0)

    with pytest.raises(ReLoginRequiredError):
        await client.mammotion_http.get_user_device_list()

    # Silence is only provable by letting the would-be traffic have its window.
    await advance_real_time(0.8)

    after = {name: scenario.counters.get(name, 0) for name in _OAUTH_COUNTERS}
    assert after == before, f"network traffic after account death: {before} -> {after}"
    assert scenario.counters.get("mammotion_mqtt_connects", 0) == mqtt_connects_before
    assert client.to_cache() == {}  # a dead session must never be persisted


async def test_exactly_one_refresh_attempt_for_a_burst_of_dead_sends(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """N concurrent sends against a dead session must not each spend a refresh."""
    scenario = fake_cloud.scenario
    await client.login_and_initiate_cloud(scenario.account, scenario.password)
    session = client._account_registry.get(scenario.account)
    transport = session.mammotion_transport
    scenario.expire_session()
    refresh_before = scenario.counters.get("refresh_grants", 0)

    results = await asyncio.gather(
        *(transport.send(b"\x08\x01", iot_id=scenario.device.iot_id) for _ in range(5)),
        return_exceptions=True,
    )
    assert all(isinstance(r, Exception) for r in results)

    await wait_until(lambda: client.reauth_required is not None)
    # One rejection is terminal; the stale-token dedup and the terminal flags
    # must keep the total refresh spend at exactly one for the whole burst.
    assert scenario.counters.get("refresh_grants", 0) == refresh_before + 1


_ALIYUN_TRAFFIC = (
    "password_grants",
    "refresh_grants",
    "auth_code_fetches",
    "aliyun_check_session",
    "aliyun_oauth",
    "aliyun_invokes",
    "aliyun_binds",
    "aliyun_mqtt_connects",
)


async def test_session_death_on_a_hybrid_account_silences_the_aliyun_side_too(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """A dead HTTP login takes the Aliyun session it minted down with it, without a password grant."""
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client, hybrid=True)
    await wait_until(lambda: len(fake_cloud.mammotion_broker.sessions) == 1)
    told: list[str] = []

    async def _on_dead(account_id: str, *_: object) -> None:
        told.append(account_id)

    client.on_unrecoverable_auth_error = _on_dead
    mammotion = client.mower(scenario.device.device_name)
    assert mammotion is not None
    transport = mammotion.get_transport(TransportType.CLOUD_MAMMOTION)
    assert transport is not None

    scenario.expire_session()
    with pytest.raises(NoTransportAvailableError):
        await transport.send(b"\x08\x01", iot_id=scenario.device.iot_id)

    await wait_until(lambda: told == [scenario.account])
    await wait_until(lambda: len(fake_cloud.aliyun_broker.sessions) == 0)
    assert scenario.counters.get("password_grants", 0) == 0
    await fake_cloud.baseline_counters()
    after_death = counts(scenario, *_ALIYUN_TRAFFIC)
    await advance_real_time(0.8)
    assert counts(scenario, *_ALIYUN_TRAFFIC) == after_death, "cloud traffic after account death"
    assert client.to_cache() == {}
