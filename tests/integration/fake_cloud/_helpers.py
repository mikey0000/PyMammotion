"""Builders shared by the fake-cloud flow suites."""

from __future__ import annotations

from typing import Any

from pymammotion.client import MammotionClient
from pymammotion.transport.aliyun_mqtt import AliyunMQTTTransport
from pymammotion.transport.base import TransportType
from tests.fakeserver.cloud import FakeMammotionCloud
from tests.fakeserver.scenario import Scenario

from .conftest import wait_for


def make_aliyun_account(scenario: Scenario, *, hybrid: bool = False) -> None:
    """Give the fake account an Aliyun-bound mower, and keep its Mammotion one only when *hybrid*."""
    scenario.issue_authorization_code = True
    scenario.mammotion_device_bound = hybrid


def counts(scenario: Scenario, *names: str) -> dict[str, int]:
    """The named server-side counters, zero when never hit — compared as one dict for a readable diff."""
    return {name: scenario.counters.get(name, 0) for name in names}


def aliyun_transport(client: MammotionClient, scenario: Scenario) -> AliyunMQTTTransport:
    """The Aliyun transport the fake account's Aliyun mower is attached to."""
    handle = client.mower(scenario.aliyun_device.device_name)
    assert handle is not None, "the Aliyun mower was never registered"
    transport = handle.get_transport(TransportType.CLOUD_ALIYUN)
    assert isinstance(transport, AliyunMQTTTransport), f"expected an Aliyun transport, got {transport!r}"
    return transport


async def make_cached_login(cloud: FakeMammotionCloud) -> dict[str, Any]:
    """Log in on a throwaway client and return its cache, with the counters zeroed once the cloud is idle."""
    first = MammotionClient()
    try:
        await first.login_and_initiate_cloud(cloud.scenario.account, cloud.scenario.password)
        cached = first.to_cache()
    finally:
        await first.stop()
    await cloud.baseline_counters()
    return cached


async def log_in_aliyun_account(cloud: FakeMammotionCloud, client: MammotionClient, *, hybrid: bool = False) -> None:
    """Log *client* in to an Aliyun account, wait for the bind, and zero the counters once the cloud is idle."""
    make_aliyun_account(cloud.scenario, hybrid=hybrid)
    await client.login_and_initiate_cloud(cloud.scenario.account, cloud.scenario.password)
    await wait_for(lambda: aliyun_transport(client, cloud.scenario).is_connected)
    await cloud.baseline_counters()


def record_persisted(client: MammotionClient) -> list[dict[str, Any]]:
    """Return a list that receives the client's cache each time it asks the host to persist it."""
    persisted: list[dict[str, Any]] = []

    async def _persist() -> None:
        persisted.append(client.to_cache())

    client.on_credentials_updated = _persist
    return persisted
