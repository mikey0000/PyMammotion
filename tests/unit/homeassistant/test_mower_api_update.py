"""``HomeAssistantMowerApi.update``: what one coordinator refresh fetches, and what it leaves alone.

The saga starters and the queued read are patched with ``autospec``: whether a refresh
starts a sync or sends a read *is* the contract.  The device and handle are real.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import FrameList
from pymammotion.data.model.report_info import LocationData
from pymammotion.homeassistant import mower_api
from pymammotion.utility.constant.device_constant import WorkMode
from tests._helpers import make_mower_with_synced_map
from tests.unit.homeassistant._helpers import NAME, make_api

_VERSION_READS = [
    "get_device_version_main",
    "get_device_version_info",
    "get_device_base_info",
    "get_device_product_model",
]


@dataclass
class _Client:
    """The patched client methods a refresh may call."""

    start_map_sync: MagicMock
    start_plan_sync: MagicMock
    queue_command_and_wait: MagicMock
    send_command_and_wait: MagicMock
    send_command_with_args: MagicMock


@pytest.fixture
def client() -> Iterator[_Client]:
    with (
        patch.object(MammotionClient, "start_map_sync", autospec=True) as start_map_sync,
        patch.object(MammotionClient, "start_plan_sync", autospec=True) as start_plan_sync,
        patch.object(MammotionClient, "queue_command_and_wait", autospec=True) as queue_command_and_wait,
        patch.object(MammotionClient, "send_command_and_wait", autospec=True) as send_command_and_wait,
        patch.object(MammotionClient, "send_command_with_args", autospec=True) as send_command_with_args,
    ):
        yield _Client(
            start_map_sync, start_plan_sync, queue_command_and_wait, send_command_and_wait, send_command_with_args
        )


def _known_device(device: MowerDevice | None = None) -> MowerDevice:
    """*device* with every version field and its plans already held, so only the map can be due."""
    device = device if device is not None else make_mower_with_synced_map(NAME)
    device.mower_state.swversion = "1.0"
    device.device_firmwares.main_controller = "1.0"
    device.device_firmwares.device_version = "1.0"
    device.mower_state.model_id = "HM010"
    device.map.plans_fetched = True
    return device


def _stale_map(sys_status: WorkMode) -> MowerDevice:
    """A device holding one area whose report names a map hash that area does not make."""
    device = _known_device(MowerDevice(name=NAME))
    device.map.area = {1: FrameList()}
    device.report_data.locations = [LocationData(bol_hash=12345)]
    device.report_data.dev.sys_status = sys_status
    return device


async def test_update_returns_the_devices_state(client: _Client) -> None:
    api, handle = await make_api(_known_device())

    assert await api.update(NAME) is handle.snapshot.raw


@pytest.mark.regression
async def test_update_reads_missing_version_info_through_the_queue(client: _Client) -> None:
    """The reads went straight to the broker, so they interleaved with a running saga.

    A saga holding the same reply field made them fail with ``ConcurrentRequestError``.
    """
    api, _ = await make_api(MowerDevice(name=NAME))

    await api.update(NAME)

    assert [call.args[2] for call in client.queue_command_and_wait.await_args_list] == _VERSION_READS
    client.send_command_and_wait.assert_not_awaited()


async def test_update_reads_version_info_before_it_starts_a_sync(client: _Client) -> None:
    """Read after the sync was queued, a version read would wait behind the whole saga."""
    order: list[str] = []
    client.queue_command_and_wait.side_effect = lambda *_a, **_k: order.append("read")
    client.start_map_sync.side_effect = lambda *_a, **_k: order.append("map")
    device = _stale_map(WorkMode.MODE_READY)
    device.mower_state.swversion = ""
    api, _ = await make_api(device)

    await api.update(NAME)

    assert order == ["read", "map"]


async def test_update_skips_version_info_already_held(client: _Client) -> None:
    api, _ = await make_api(_known_device())

    await api.update(NAME)

    client.queue_command_and_wait.assert_not_awaited()


async def test_update_sends_nothing_while_the_queue_has_work(client: _Client) -> None:
    api, handle = await make_api(_stale_map(WorkMode.MODE_READY))

    async def _queued() -> None: ...

    await handle.queue.enqueue(_queued)

    await api.update(NAME)

    client.start_map_sync.assert_not_awaited()
    client.send_command_with_args.assert_not_awaited()


async def test_update_syncs_a_stale_map_while_idle(client: _Client) -> None:
    api, _ = await make_api(_stale_map(WorkMode.MODE_READY))

    await api.update(NAME)

    client.start_map_sync.assert_awaited_once_with(api.mammotion, NAME)


@pytest.mark.regression
async def test_update_does_not_sync_the_map_while_a_job_runs(client: _Client) -> None:
    """The facade kept its own map rule, so it synced mid-job, where the map re-hashes as it mows.

    D16: automatic syncs ask ``MowerDevice.map_sync_due`` and wait for the job to end.
    """
    api, _ = await make_api(_stale_map(WorkMode.MODE_WORKING))

    await api.update(NAME)

    client.start_map_sync.assert_not_awaited()


async def test_update_does_not_sync_a_map_before_the_first_report(client: _Client) -> None:
    """With no report the hash reads as 0, which says nothing about the map held."""
    api, _ = await make_api(_known_device(MowerDevice(name=NAME)))

    await api.update(NAME)

    client.start_map_sync.assert_not_awaited()


async def test_update_does_not_sync_a_map_already_in_sync(client: _Client) -> None:
    api, _ = await make_api(_known_device())

    await api.update(NAME)

    client.start_map_sync.assert_not_awaited()


async def test_update_starts_no_sync_for_an_unreachable_device(client: _Client) -> None:
    """A saga queued for a device nothing can reach dies on ``NoTransportAvailableError``."""
    device = _stale_map(WorkMode.MODE_READY)
    device.map.plans_fetched = False
    api, _ = await make_api(device, reachable=False)

    await api.update(NAME)

    client.start_map_sync.assert_not_awaited()
    client.start_plan_sync.assert_not_awaited()


class _FrozenClock:
    """Stands in for the facade module's ``time``: a monotonic clock only the test moves."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


async def test_update_retries_a_stale_map_only_at_its_pacing(client: _Client) -> None:
    api, _ = await make_api(_stale_map(WorkMode.MODE_READY))
    clock = _FrozenClock()

    with patch.object(mower_api, "time", clock):
        await api.update(NAME)
        clock.now += 60 * 60
        await api.update(NAME)
        assert client.start_map_sync.await_count == 1, "retried before the two-hour pacing"
        clock.now += 60 * 60
        await api.update(NAME)

    assert client.start_map_sync.await_count == 2


@pytest.mark.parametrize(
    ("fetched", "stale", "syncs"),
    [(False, False, True), (True, True, True), (True, False, False)],
    ids=["never-fetched", "stale", "current"],
)
async def test_update_syncs_plans_never_fetched_or_reported_stale(
    client: _Client, fetched: bool, stale: bool, syncs: bool
) -> None:
    device = _known_device()
    device.map.plans_fetched = fetched
    device.map.plans_stale = stale
    api, _ = await make_api(device)

    await api.update(NAME)

    assert client.start_plan_sync.await_count == int(syncs)
