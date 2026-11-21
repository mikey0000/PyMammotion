"""``MammotionClient``'s saga starters: a request for a fetch that is already queued adds no second run.

The auto-fetch watchers, the poll loops and the host all start the same fetches, and
their ``is_saga_active`` guards only see a saga that is *running*.  Every run of a
fetch is a burst of cloud sends (a request plus an ack per frame), so the number of
runs is the contract here.  ``Saga.execute`` is patched out: the starters, the queue
and its dedup are real.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from unittest.mock import patch

import pytest

from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowerDevice
from pymammotion.device.handle import DeviceHandle
from pymammotion.messaging.saga import Saga
from tests._helpers import make_bare_client, make_mock_handle

_NAME = "Luba-LA123"
_DRAIN_TIMEOUT = 2.0

Start = Callable[[MammotionClient], Awaitable[object]]


@pytest.fixture
async def handle() -> AsyncIterator[DeviceHandle]:
    """A registered handle whose queue is not running yet, so whatever is started stays queued."""
    handle = make_mock_handle("dev1", _NAME, device=MowerDevice(name=_NAME))
    yield handle
    await handle.queue.stop()


@pytest.fixture
async def client(handle: DeviceHandle) -> MammotionClient:
    client = make_bare_client()
    await client.device_registry.register(handle)
    return client


async def _runs(client: MammotionClient, handle: DeviceHandle, *starts: Start) -> list[str]:
    """Call each of *starts* while the queue is held, then let it drain; return the sagas that ran."""
    with patch.object(Saga, "execute", autospec=True) as execute:
        for start in starts:
            await start(client)
        handle.queue.start()
        await asyncio.wait_for(handle.queue._queue.join(), _DRAIN_TIMEOUT)  # noqa: SLF001
    return [call.args[0].name for call in execute.call_args_list]


def _fetch_route(client: MammotionClient) -> Awaitable[bool]:
    return client.start_mow_path_saga(_NAME, zone_hashs=[], skip_planning=True)


@pytest.mark.regression
@pytest.mark.parametrize(
    ("start", "saga"),
    [
        pytest.param(lambda c: c.start_plan_sync(_NAME), "plan_fetch", id="plans"),
        pytest.param(lambda c: c.start_spino_plan_sync(_NAME), "spino_plan_fetch", id="spino plans"),
        pytest.param(lambda c: c.start_map_sync(_NAME), "map_fetch", id="map"),
        pytest.param(_fetch_route, "mow_path_fetch", id="cover path"),
        pytest.param(lambda c: c.get_dynamics_line(_NAME), "common_data_fetch", id="dynamics line"),
    ],
)
async def test_a_fetch_requested_twice_before_it_starts_runs_once(
    client: MammotionClient, handle: DeviceHandle, start: Start, saga: str
) -> None:
    """Each request queued its own saga, so a watcher and a host asking for the same fetch ran it twice."""
    assert await _runs(client, handle, start, start) == [saga]


async def test_an_incremental_map_sync_does_not_stand_in_for_a_full_one(
    client: MammotionClient, handle: DeviceHandle
) -> None:
    """Only the full sync re-reads the area names."""
    runs = await _runs(
        client, handle, lambda c: c.start_map_sync(_NAME, skip_area_names=True), lambda c: c.start_map_sync(_NAME)
    )

    assert runs == ["map_fetch", "map_fetch"]


async def test_route_planning_is_never_dropped(client: MammotionClient, handle: DeviceHandle) -> None:
    """Each plan is a different request, not a repeat of the one before."""

    def plan(c: MammotionClient) -> Awaitable[bool]:
        return c.start_mow_path_saga(_NAME, zone_hashs=[1])

    assert await _runs(client, handle, _fetch_route, plan, plan) == ["mow_path_fetch"] * 3


async def test_a_fetch_its_caller_waits_on_is_queued_and_signalled(
    client: MammotionClient, handle: DeviceHandle
) -> None:
    """Dropped, its ``completed`` event would never be set and the caller would wait out its timeout."""
    completed = asyncio.Event()

    def awaited(c: MammotionClient) -> Awaitable[bool]:
        return c.start_mow_path_saga(_NAME, zone_hashs=[], skip_planning=True, completed=completed)

    assert await _runs(client, handle, _fetch_route, awaited) == ["mow_path_fetch"] * 2
    assert completed.is_set()
