"""Aliyun MQTT bind flow against the live fake broker.

The transport hard-requires TLS against the bundled Aliyun CA, so these tests
patch ``get_ssl_context`` to None — the fake broker listens in plaintext.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from pymammotion.transport import aliyun_mqtt
from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport
from pymammotion.transport.base import ReLoginRequiredError
from tests.fakeserver.cloud import FakeMammotionCloud
from tests._helpers import advance_real_time

from .conftest import wait_for

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _make_aliyun_transport(cloud: FakeMammotionCloud, monkeypatch: pytest.MonkeyPatch) -> AliyunMQTTTransport:
    async def _no_tls() -> None:
        return None

    monkeypatch.setattr(AliyunMQTTTransport, "get_ssl_context", staticmethod(_no_tls))
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
    gateway = AsyncMock()
    return AliyunMQTTTransport(config, gateway)


async def test_bind_accepted_stays_connected(
    fake_cloud: FakeMammotionCloud, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _make_aliyun_transport(fake_cloud, monkeypatch)
    await transport.connect()
    try:
        await wait_for(lambda: fake_cloud.scenario.counters.get("aliyun_binds", 0) == 1)
        assert fake_cloud.bind_requests[0]["params"]["iotToken"] == "fake-iot-token"
        await advance_real_time(0.3)  # an accepted bind must not trigger reconnects
        assert fake_cloud.scenario.counters.get("aliyun_mqtt_connects") == 1
        assert transport.is_connected
    finally:
        await transport.disconnect()


async def test_bind_2043_replay_is_bounded_to_three_refreshes(
    fake_cloud: FakeMammotionCloud, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The historical account-blocking hammer, against a real broker: the broker
    rejects every bind with 2043 while credential refreshes keep 'succeeding' —
    the transport must stop after 3 refresh cycles, not loop at ~1 Hz forever."""
    scenario = fake_cloud.scenario
    scenario.bind_reply_code = 2043
    transport = _make_aliyun_transport(fake_cloud, monkeypatch)
    refreshes = AsyncMock(return_value=True)
    transport.on_auth_failure = refreshes
    fatal = AsyncMock()
    transport.on_fatal_auth_error = fatal

    with pytest.raises(ReLoginRequiredError):
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
    transport = _make_aliyun_transport(fake_cloud, monkeypatch)
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
        await wait_for(lambda: changes == [True])
        await wait_for(lambda: scenario.counters.get("aliyun_binds", 0) >= 2)  # it retried
        assert transport.account_in_use is True
        assert not transport.is_connected
        assert not transport.is_usable
        assert not transport.is_unrecoverable_auth_failure
        assert refreshes.await_count == 0  # no refresh can fix a held account lock
        assert fatal.await_count == 0

        scenario.bind_reply_code = 200
        await wait_for(lambda: changes == [True, False])
        await wait_for(lambda: transport.is_connected)
        assert transport.account_in_use is False
        assert transport.is_usable
        assert fatal.await_count == 0
    finally:
        await transport.disconnect()
