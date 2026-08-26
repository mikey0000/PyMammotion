"""Fixtures: a per-test fake Mammotion cloud with pymammotion pointed at it."""

from __future__ import annotations

import asyncio
import time

import pytest

from pymammotion.client import MammotionClient
from tests.fakeserver.cloud import FakeMammotionCloud

# Async fixtures run in the session-scoped loop (asyncio_default_fixture_loop_scope
# = "session" in pyproject).  The servers bind to that loop, so the tests must run
# in it too — otherwise their HTTP requests are never serviced.
pytestmark = pytest.mark.asyncio(loop_scope="session")


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
    cloud = FakeMammotionCloud()
    await cloud.start()
    # http.py imports the constants by value at module import, so patch the
    # names inside pymammotion.http.http, not pymammotion.const.
    monkeypatch.setattr("pymammotion.http.http.MAMMOTION_DOMAIN", cloud.base_url)
    monkeypatch.setattr("pymammotion.http.http.MAMMOTION_API_DOMAIN", cloud.base_url)
    yield cloud
    await cloud.stop()


@pytest.fixture
async def client(fake_cloud: FakeMammotionCloud) -> MammotionClient:
    mammotion = MammotionClient()
    yield mammotion
    await mammotion.stop()


async def wait_for(predicate, timeout: float = 5.0, interval: float = 0.05) -> None:
    """Poll *predicate* until truthy or fail the test after *timeout* seconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s: {predicate}")
