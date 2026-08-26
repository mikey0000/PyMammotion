"""Bounded-recovery behaviour: every failure costs a fixed, small number of calls."""

from __future__ import annotations

import pytest

from pymammotion.auth.token_manager import TokenManager
from pymammotion.client import MammotionClient
from pymammotion.http.http import MammotionHTTP
from pymammotion.transport.base import NoTransportAvailableError
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig
from tests.fakeserver.cloud import FakeMammotionCloud

from .conftest import wait_for

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _wired_transport(cloud: FakeMammotionCloud) -> tuple[MammotionHTTP, TokenManager, MQTTTransport]:
    """Hand-wire http + token manager + transport (no client, no background loops)."""
    scenario = cloud.scenario
    http = MammotionHTTP(account=scenario.account, password=scenario.password)
    resp = await http.login_v2(scenario.account, scenario.password)
    assert resp.code == 0
    token_manager = TokenManager(scenario.account, http)
    token_manager.seed_from_http()
    creds = await http.get_mqtt_credentials()
    assert creds.data is not None
    config = MQTTTransportConfig(
        host="127.0.0.1",
        port=cloud.mammotion_broker.port,
        client_id=creds.data.client_id,
        username=creds.data.username,
        password=creds.data.jwt,
    )
    return http, token_manager, MQTTTransport(config, http, token_manager)


async def test_revoked_bearer_costs_one_refresh_and_one_retry(fake_cloud: FakeMammotionCloud) -> None:
    """Server-side bearer revocation: invoke 401 → refresh → retry succeeds."""
    scenario = fake_cloud.scenario
    _, _, transport = await _wired_transport(fake_cloud)
    scenario.counters.clear()

    scenario.revoke_access_tokens()  # refresh token stays valid
    await transport.send(b"\x08\x01", iot_id=scenario.device.iot_id)

    assert scenario.counters.get("invoke_calls") == 2  # rejected + retried
    assert scenario.counters.get("refresh_grants") == 1
    assert scenario.counters.get("password_grants", 0) == 0  # never a password grant
    assert transport.is_usable


async def test_persistent_460_gives_up_after_one_refresh(fake_cloud: FakeMammotionCloud) -> None:
    """The in-body 460 dead end: one refresh, one retry, then transport-scoped give-up."""
    scenario = fake_cloud.scenario
    _, token_manager, transport = await _wired_transport(fake_cloud)
    scenario.counters.clear()
    scenario.invoke_mode = "body_460"

    with pytest.raises(NoTransportAvailableError):
        await transport.send(b"\x08\x01", iot_id=scenario.device.iot_id)

    assert scenario.counters.get("invoke_calls") == 2
    assert scenario.counters.get("refresh_grants") == 1
    assert not transport.is_usable
    # Transport-scoped: the account login survives.
    assert token_manager.reauth_required is None

    # Nothing retries on its own: further sends fail fast with zero traffic.
    scenario.counters.clear()
    with pytest.raises(Exception):  # noqa: B017 — any failure is fine, traffic is the assertion
        await transport.send(b"\x08\x01", iot_id=scenario.device.iot_id)
    assert scenario.counters.get("refresh_grants", 0) <= 1  # at most the dedup'd one
    assert scenario.counters.get("password_grants", 0) == 0


async def test_broker_auth_rejection_is_bounded(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """CONNACK rc=5 forever: one forced credential refresh, then give-up — no storm."""
    scenario = fake_cloud.scenario
    scenario.mammotion_connack_rc = 5

    await client.login_and_initiate_cloud(scenario.account, scenario.password)
    session = client._account_registry.get(scenario.account)
    transport = session.mammotion_transport
    assert transport is not None

    await wait_for(lambda: not transport.is_usable, timeout=10)
    # Attempt 1 (rejected) + one refresh + attempt 2 (rejected) → give up.
    assert scenario.counters.get("mammotion_mqtt_connects") == 2
    assert client.reauth_required is None  # transport-scoped, account alive

    # And it stays given up — no reconnect loop in the background.
    # (With backoff at 0.05s this window covers several would-be cycles.)
    import asyncio

    await asyncio.sleep(0.4)
    assert scenario.counters.get("mammotion_mqtt_connects") == 2
