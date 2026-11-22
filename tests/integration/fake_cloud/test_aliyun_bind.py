"""Aliyun MQTT bind flow against the live fake broker, for the transport alone and through the client.

The transport hard-requires TLS against the bundled Aliyun CA; the ``fake_cloud``
fixture patches ``get_ssl_context`` to None because the fake broker listens in plaintext.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.client import MammotionClient
from pymammotion.transport import aliyun_mqtt
from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport
from tests._helpers import advance_real_time, wait_until
from tests.fakeserver.cloud import FakeMammotionCloud

from ._helpers import aliyun_transport, counts, make_aliyun_account

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _make_aliyun_transport(cloud: FakeMammotionCloud) -> AliyunMQTTTransport:
    config = AliyunMQTTConfig(
        host="127.0.0.1",
        port=cloud.aliyun_broker.port,
        client_id_base="fakeapp&FAKEAPPPK",
        username="fakeapp&FAKEAPPPK",
        device_name="fakeapp",
        product_key="FAKEAPPPK",
        device_secret="fake-secret",
        iot_token="fake-iot-token",
    )
    gateway = AsyncMock(spec=CloudIOTGateway)
    return AliyunMQTTTransport(config, gateway)


async def test_bind_accepted_stays_connected(
    fake_cloud: FakeMammotionCloud
) -> None:
    transport = _make_aliyun_transport(fake_cloud)
    await transport.connect()
    try:
        await wait_until(lambda: fake_cloud.scenario.counters.get("aliyun_binds", 0) == 1)
        assert fake_cloud.bind_requests[0]["params"]["iotToken"] == "fake-iot-token"
        await advance_real_time(0.3)  # an accepted bind must not trigger reconnects
        assert fake_cloud.scenario.counters.get("aliyun_mqtt_connects") == 1
        assert transport.is_connected
    finally:
        await transport.disconnect()


async def test_bind_2043_replay_is_bounded_to_three_refreshes(
    fake_cloud: FakeMammotionCloud
) -> None:
    """The historical account-blocking hammer, against a real broker: the broker
    rejects every bind with 2043 while credential refreshes keep 'succeeding' —
    the transport must stop after 3 refresh cycles, not loop at ~1 Hz forever."""
    scenario = fake_cloud.scenario
    scenario.bind_reply_code = 2043
    transport = _make_aliyun_transport(fake_cloud)
    refreshes = AsyncMock(return_value=True)
    transport.on_auth_failure = refreshes
    fatal = AsyncMock()
    transport.on_fatal_auth_error = fatal

    # Returns rather than raising: the loop runs as a task nobody awaits, so a raise was only ever
    # logged as "Task exception was never retrieved" after the give-up had already been handled.
    await asyncio.wait_for(transport._run(), timeout=30)

    assert refreshes.await_count == 3  # _MAX_AUTH_REFRESH_CYCLES
    assert scenario.counters.get("aliyun_binds") == 4  # initial + one per refresh
    assert fatal.await_count == 1
    assert not transport.is_usable

    # Given up means given up: no further connects arrive at the broker.
    # (With backoff at 0.05s this window covers several would-be cycles.)
    connects = scenario.counters.get("aliyun_mqtt_connects")
    await advance_real_time(0.4)
    assert scenario.counters.get("aliyun_mqtt_connects") == connects


@pytest.mark.regression
async def test_a_transient_auth_refresh_failure_backs_off_instead_of_giving_up(
    fake_cloud: FakeMammotionCloud,
) -> None:
    """A network error from the bind-refresh callback was treated as a verdict and the transport given up for good."""
    scenario = fake_cloud.scenario
    scenario.bind_reply_code = 2043
    transport = _make_aliyun_transport(fake_cloud)

    async def _refresh() -> bool:
        if refreshes.await_count == 1:
            raise ConnectionError("cloud unreachable")
        scenario.bind_reply_code = 200
        return True

    refreshes = AsyncMock(side_effect=_refresh)
    transport.on_auth_failure = refreshes
    fatal = AsyncMock()
    transport.on_fatal_auth_error = fatal

    await transport.connect()
    try:
        await wait_until(lambda: transport.is_connected)
        assert refreshes.await_count == 2
        fatal.assert_not_awaited()
        assert transport.is_usable
    finally:
        await transport.disconnect()


@pytest.mark.regression
async def test_bind_2152_account_in_use_retries_until_the_lock_is_released(
    fake_cloud: FakeMammotionCloud, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A held account lock must be waited out, not treated as a dead login.

    The transport raised AccountInUseError as a ReLoginRequiredError through the fatal
    auth path: it was marked auth-failed and never reconnected, so the mowers stayed
    unavailable after the Mammotion app signed out and released the lock.

    The lock retry is an event-loop timer, which time_machine cannot move, so the
    delay is shortened the way ``fast_backoff`` shortens the reconnect backoff.
    """
    monkeypatch.setattr(aliyun_mqtt, "ACCOUNT_IN_USE_RETRY_SEC", 0.1)
    scenario = fake_cloud.scenario
    scenario.bind_reply_code = 2152
    transport = _make_aliyun_transport(fake_cloud)
    refreshes = AsyncMock(return_value=True)
    transport.on_auth_failure = refreshes
    fatal = AsyncMock()
    transport.on_fatal_auth_error = fatal
    changes: list[bool] = []

    async def _on_change(held: bool) -> None:
        changes.append(held)

    transport.on_account_in_use_changed = _on_change

    await transport.connect()
    try:
        await wait_until(lambda: changes == [True])
        await wait_until(lambda: scenario.counters.get("aliyun_binds", 0) >= 2)  # it retried
        assert transport.account_in_use is True
        assert not transport.is_connected
        assert not transport.is_usable
        assert not transport.is_unrecoverable_auth_failure
        assert refreshes.await_count == 0  # no refresh can fix a held account lock
        assert fatal.await_count == 0

        scenario.bind_reply_code = 200
        await wait_until(lambda: changes == [True, False])
        await wait_until(lambda: transport.is_connected)
        assert transport.account_in_use is False
        assert transport.is_usable
        assert fatal.await_count == 0
    finally:
        await transport.disconnect()


async def test_account_lock_at_login_is_reported_to_the_host_and_waited_out_without_auth_traffic(
    fake_cloud: FakeMammotionCloud, client: MammotionClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The full client flow for a held lock: the host hears both edges and no credential is touched."""
    monkeypatch.setattr(aliyun_mqtt, "ACCOUNT_IN_USE_RETRY_SEC", 0.1)
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario)
    scenario.bind_reply_code = 2152
    changes: list[tuple[str, bool]] = []

    async def _on_change(account_id: str, held: bool) -> None:
        changes.append((account_id, held))

    client.on_account_in_use_changed = _on_change
    await client.login_and_initiate_cloud(scenario.account, scenario.password)
    await wait_until(lambda: changes == [(scenario.account, True)])
    await fake_cloud.baseline_counters()
    await wait_until(lambda: scenario.counters.get("aliyun_binds", 0) >= 2)  # it keeps retrying while held

    scenario.bind_reply_code = 200
    await wait_until(lambda: changes == [(scenario.account, True), (scenario.account, False)])
    await wait_until(lambda: aliyun_transport(client, scenario).is_connected)
    auth_traffic = ("password_grants", "refresh_grants", "auth_code_fetches", "aliyun_check_session", "aliyun_oauth")
    assert counts(scenario, *auth_traffic) == dict.fromkeys(auth_traffic, 0)
    assert client.token_manager is not None
    assert client.token_manager.aliyun_unavailable is None
