"""Fixtures: a per-test fake Mammotion cloud with pymammotion pointed at it."""

from __future__ import annotations

import asyncio
import time

import pytest

from pymammotion import client as client_module
from pymammotion.aliyun import cloud_gateway
from pymammotion.client import MammotionClient
from pymammotion.http import http
from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport
from tests.fakeserver.cloud import FakeMammotionCloud

# Async fixtures run in the session-scoped loop (asyncio_default_fixture_loop_scope
# = "session" in pyproject).  The servers bind to that loop, so the tests must run
# in it too — otherwise their HTTP requests are never serviced.
pytestmark = pytest.mark.asyncio(loop_scope="session")

#: Ceiling on fixture teardown.  Nothing here legitimately takes seconds — a whole
#: suite run is ~3s — so this only ever fires on a genuine hang.
_TEARDOWN_TIMEOUT = 30.0


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the reconnect backoff so bounded-retry tests run in milliseconds.

    Both transports read MQTT_RECONNECT_MIN_SEC as a module global inside _run,
    so patching the importing modules is enough.  Every assertion in this suite
    is count-based, never timing-based, so nothing is weakened — and the trailing
    "it stays given up" sleeps now cover several would-be backoff cycles instead
    of one.
    """
    for mod in ("pymammotion.transport.aliyun_mqtt", "pymammotion.transport.mqtt"):
        monkeypatch.setattr(f"{mod}.MQTT_RECONNECT_MIN_SEC", 0.05)


@pytest.fixture
async def fake_cloud(monkeypatch: pytest.MonkeyPatch) -> FakeMammotionCloud:
    """The fake cloud, with every Mammotion and Aliyun endpoint the library uses pointed at it.

    The Aliyun MQTT host is derived from the AEP product key and region, so the
    transport is redirected at its config instead; the fake broker is plaintext,
    so the pinned-CA TLS context is dropped too.
    """
    cloud = FakeMammotionCloud()
    await cloud.start()
    # The modules import the constants by value, so patch the names where they are read.
    monkeypatch.setattr(http, "MAMMOTION_DOMAIN", cloud.base_url)
    monkeypatch.setattr(http, "MAMMOTION_API_DOMAIN", cloud.base_url)
    monkeypatch.setattr(cloud_gateway, "ALIYUN_DOMAIN", cloud.base_url)
    monkeypatch.setattr(cloud_gateway, "ALIYUN_OPENACCOUNT_DOMAIN", cloud.base_url)

    def _loopback_aliyun_config(**kwargs: object) -> AliyunMQTTConfig:
        return AliyunMQTTConfig(**{**kwargs, "host": "127.0.0.1", "port": cloud.aliyun_broker.port})

    async def _no_tls() -> None:
        return None

    monkeypatch.setattr(client_module, "AliyunMQTTConfig", _loopback_aliyun_config)
    monkeypatch.setattr(AliyunMQTTTransport, "get_ssl_context", staticmethod(_no_tls))
    yield cloud
    # A shutdown that cannot finish is a bug either way; surface it as a failed test
    # with a traceback instead of wedging the whole run (pre-commit once blocked on
    # this for ten minutes before anyone noticed).
    await asyncio.wait_for(cloud.stop(), timeout=_TEARDOWN_TIMEOUT)


@pytest.fixture
async def client(fake_cloud: FakeMammotionCloud) -> MammotionClient:
    mammotion = MammotionClient()
    yield mammotion
    await asyncio.wait_for(mammotion.stop(), timeout=_TEARDOWN_TIMEOUT)


async def wait_for(predicate, timeout: float = 5.0, interval: float = 0.05) -> None:
    """Poll *predicate* until truthy or fail the test after *timeout* seconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s: {predicate}")
