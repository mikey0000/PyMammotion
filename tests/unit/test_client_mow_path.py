"""``MammotionClient`` cover-path fetches: the stale-route clear, and fetching the route a plan confirmed."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowerDevice
from pymammotion.device.handle import DeviceHandle
from pymammotion.data.model.hash_list import LINE_HASH_SUB_CMD, NavGetHashListData
from tests._helpers import make_bare_client, make_mock_handle

_NAME = "Luba-Test"
_LINES = [5000000000000000001, 5000000000000000002]
_LIVE_PATH_HASH = 7372458040660269014


async def _client_with_stored_route() -> tuple[MammotionClient, MowerDevice]:
    device = MowerDevice(name=_NAME)
    device.map.update_root_hash_list(
        NavGetHashListData(sub_cmd=LINE_HASH_SUB_CMD, current_frame=1, total_frame=1, data_couple=_LINES)
    )
    device.report_data.work.path_hash = _LIVE_PATH_HASH
    client = make_bare_client()
    await client._device_registry.register(make_mock_handle("dev1", _NAME, device=device))  # noqa: SLF001
    return client, device


@pytest.mark.regression
async def test_a_stored_line_list_for_another_route_is_dropped_even_without_cover_paths() -> None:
    """The clear was skipped whenever no cover path was cached, leaving the old route's line list in place."""
    client, device = await _client_with_stored_route()
    assert device.map.computed_path_hash != _LIVE_PATH_HASH

    with patch.object(MammotionClient, "start_mow_path_saga", autospec=True, return_value=True):
        await client.check_and_get_mow_path(_NAME)

    assert device.map.line_root_hashlist == []


def _no_line_route(device: MowerDevice) -> None:
    """Store the line list of a route with nothing left to fetch: one zero placeholder."""
    device.map.update_root_hash_list(
        NavGetHashListData(sub_cmd=LINE_HASH_SUB_CMD, current_frame=1, total_frame=1, data_couple=[0])
    )


def _planned_hash() -> int:
    """The ``path_hash`` the device reports for the route ``_no_line_route`` stores."""
    scratch = MowerDevice(name=_NAME)
    _no_line_route(scratch)
    return scratch.map.computed_path_hash


async def _client_with_planned_route() -> tuple[MammotionClient, MowerDevice]:
    """A device still holding another route's lines, whose plan reply named ``_planned_hash()``."""
    client, device = await _client_with_stored_route()
    device.work.path_hash = _planned_hash()
    return client, device


async def test_the_planned_route_is_fetched_and_the_other_routes_lines_dropped() -> None:
    """Left in place, the earlier route's lines would be handed back as the new plan."""
    client, device = await _client_with_planned_route()
    line_lists_at_fetch = []

    async def _fetch(_client: MammotionClient, _name: str, *, completed: asyncio.Event, **_: object) -> bool:
        line_lists_at_fetch.append(list(device.map.line_root_hashlist))
        _no_line_route(device)
        completed.set()
        return True

    with patch.object(MammotionClient, "start_mow_path_saga", autospec=True, side_effect=_fetch) as start:
        fetched = await asyncio.wait_for(client.fetch_planned_mow_path(_NAME), 5)

    assert fetched == _planned_hash()
    assert line_lists_at_fetch == [[]]
    assert start.call_args.kwargs["skip_planning"] is True


async def test_a_route_already_cached_for_the_plan_is_not_fetched_again() -> None:
    client, device = await _client_with_planned_route()
    device.map.invalidate_mow_path(0)
    _no_line_route(device)

    with patch.object(MammotionClient, "start_mow_path_saga", autospec=True, return_value=True) as start:
        fetched = await asyncio.wait_for(client.fetch_planned_mow_path(_NAME), 5)

    assert fetched == _planned_hash()
    start.assert_not_called()


async def test_a_device_that_confirmed_no_route_has_nothing_to_fetch() -> None:
    """``path_hash`` 0 and 1 mean no route; fetching would return whatever was cached before."""
    client, device = await _client_with_planned_route()
    device.work.path_hash = 0
    device.report_data.work.path_hash = 0

    with patch.object(MammotionClient, "start_mow_path_saga", autospec=True, return_value=True) as start:
        fetched = await asyncio.wait_for(client.fetch_planned_mow_path(_NAME), 5)

    assert fetched == 0
    start.assert_not_called()


async def test_a_fetch_that_is_gated_off_reports_no_route() -> None:
    """``start_mow_path_saga`` answers False when the fetch would go over MQTT with fetching off."""
    client, _ = await _client_with_planned_route()

    with patch.object(MammotionClient, "start_mow_path_saga", autospec=True, return_value=False):
        fetched = await asyncio.wait_for(client.fetch_planned_mow_path(_NAME), 5)

    assert fetched == 0


async def test_a_fetch_that_never_finishes_reports_no_route() -> None:
    """The saga never signals: the caller's own timeout is the stimulus, shrunk to 10 ms."""
    client, _ = await _client_with_planned_route()

    with patch.object(MammotionClient, "start_mow_path_saga", autospec=True, return_value=True):
        fetched = await asyncio.wait_for(client.fetch_planned_mow_path(_NAME, timeout=0.01), 5)

    assert fetched == 0


async def test_a_fetch_that_ends_with_lines_missing_reports_no_route() -> None:
    """The saga gives up on a stalled line without raising, so finishing is not proof of a route."""
    client, device = await _client_with_planned_route()

    async def _fetch(_client: MammotionClient, _name: str, *, completed: asyncio.Event, **_: object) -> bool:
        completed.set()
        return True

    with patch.object(MammotionClient, "start_mow_path_saga", autospec=True, side_effect=_fetch):
        fetched = await asyncio.wait_for(client.fetch_planned_mow_path(_NAME), 5)

    assert fetched == 0
    assert device.map.line_root_hashlist == []


async def test_the_fetch_hands_its_signal_to_the_saga_queue() -> None:
    """The queue sets it when the saga ends, failed or not; unset, the caller waits out its whole timeout."""
    client, _ = await _client_with_planned_route()
    completed = asyncio.Event()

    with (
        patch.object(DeviceHandle, "is_transport_connected", autospec=True, return_value=True),
        patch.object(DeviceHandle, "enqueue_saga", autospec=True) as enqueue,
    ):
        started = await client.start_mow_path_saga(_NAME, zone_hashs=[], skip_planning=True, completed=completed)

    assert started is True
    assert enqueue.call_args.kwargs["done"] is completed


async def test_a_plan_cleared_by_an_idle_report_is_found_by_the_reports_hash() -> None:
    """A mower that planned but did not start reports no job, which empties the plan reply's settings."""
    client, device = await _client_with_planned_route()
    device.work.path_hash = 0
    device.report_data.work.path_hash = _planned_hash()
    device.map.invalidate_mow_path(0)
    _no_line_route(device)

    fetched = await asyncio.wait_for(client.fetch_planned_mow_path(_NAME), 5)

    assert fetched == _planned_hash()
