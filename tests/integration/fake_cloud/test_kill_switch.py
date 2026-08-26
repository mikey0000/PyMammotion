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
from pymammotion.transport.base import NoTransportAvailableError, ReLoginRequiredError
from tests.fakeserver.cloud import FakeMammotionCloud

from .conftest import wait_for

pytestmark = pytest.mark.asyncio(loop_scope="session")

_OAUTH_COUNTERS = ("password_grants", "refresh_grants", "auth_code_fetches", "invoke_calls", "mqtt_jwt_fetches")


async def test_server_side_session_death_quiesces_everything(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    scenario = fake_cloud.scenario
    await client.login_and_initiate_cloud(scenario.account, scenario.password)
    await wait_for(lambda: len(fake_cloud.mammotion_broker.sessions) == 1)

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
    await wait_for(lambda: client.reauth_required is not None)
    await wait_for(lambda: not transport.is_usable)
    await wait_for(lambda: len(fake_cloud.mammotion_broker.sessions) == 0)
    await wait_for(lambda: on_dead.await_count == 1)
    assert on_dead.await_args.args[0] == scenario.account

    # From here on: total silence.  Whatever poll loops or queues still exist,
    # not one more oauth2/token, invoke, or credential fetch may reach the server.
    before = {name: scenario.counters.get(name, 0) for name in _OAUTH_COUNTERS}
    mqtt_connects_before = scenario.counters.get("mammotion_mqtt_connects", 0)

    with pytest.raises(ReLoginRequiredError):
        await client.mammotion_http.get_user_device_list()

    await asyncio.sleep(0.8)

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

    await wait_for(lambda: client.reauth_required is not None)
    # One rejection is terminal; the stale-token dedup and the terminal flags
    # must keep the total refresh spend at exactly one for the whole burst.
    assert scenario.counters.get("refresh_grants", 0) == refresh_before + 1
