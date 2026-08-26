"""Aliyun MQTT bind flow against the live fake broker.

The transport hard-requires TLS against the bundled Aliyun CA, so these tests
patch ``get_ssl_context`` to None — the fake broker listens in plaintext.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport
from pymammotion.transport.base import ReLoginRequiredError
from tests.fakeserver.cloud import FakeMammotionCloud

from .conftest import wait_for

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _make_transport(cloud: FakeMammotionCloud, monkeypatch: pytest.MonkeyPatch) -> AliyunMQTTTransport:
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
    transport = _make_transport(fake_cloud, monkeypatch)
    await transport.connect()
    try:
        await wait_for(lambda: fake_cloud.scenario.counters.get("aliyun_binds", 0) == 1)
        assert fake_cloud.bind_requests[0]["params"]["iotToken"] == "fake-iot-token"
        await asyncio.sleep(0.3)  # an accepted bind must not trigger reconnects
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
    transport = _make_transport(fake_cloud, monkeypatch)
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
    await asyncio.sleep(0.4)
    assert scenario.counters.get("aliyun_mqtt_connects") == connects


async def test_bind_2152_account_in_use_is_immediately_fatal(
    fake_cloud: FakeMammotionCloud, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = fake_cloud.scenario
    scenario.bind_reply_code = 2152
    transport = _make_transport(fake_cloud, monkeypatch)
    refreshes = AsyncMock(return_value=True)
    transport.on_auth_failure = refreshes
    fatal = AsyncMock()
    transport.on_fatal_auth_error = fatal

    with pytest.raises(Exception, match="another session"):
        await asyncio.wait_for(transport._run(), timeout=10)

    assert refreshes.await_count == 0  # no refresh can fix a held account lock
    assert scenario.counters.get("aliyun_binds") == 1
    assert fatal.await_count == 1
