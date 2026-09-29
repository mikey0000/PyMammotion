"""MowPathSaga — line hash list collection and the cover-path requests built from it."""

from __future__ import annotations

import asyncio

import pytest

from pymammotion.data.model import GenerateRouteInformation
from pymammotion.data.model.hash_list import HashList
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.mow_path_saga import MowPathSaga
from tests.unit.messaging._fakes import FakeHashListDevice

_SAGA_TIMEOUT = 5.0


@pytest.mark.regression
async def test_saga_acks_every_line_hash_list_frame_and_requests_every_line_hash() -> None:
    """The sub_cmd=3 stream must be acked frame by frame, and every hash requested.

    ``ack_stream`` was handed ``field="toapp_gethash_ack(sub_cmd=3)"``, which is no
    protobuf leaf, so every frame the collector queued failed to unwrap.  With
    ``allow_empty=True`` that read as "no breakpoint lines": frame 1 was never
    acked, the device never sent frame 2, and ``get_line_info_list`` went out
    with only the first frame's hashes.
    """
    broker = DeviceMessageBroker()
    _map = HashList()
    line_a, line_b = 5000000000000000001, 5000000000000000002
    device = FakeHashListDevice(broker, _map, hash_lists={3: [[line_a], [line_b]]})
    saga = MowPathSaga(
        command_builder=device.command_builder,
        send_command=device.send,
        get_map=lambda: _map,
        zone_hashs=[line_a],
        route_info=GenerateRouteInformation(one_hashs=[line_a]),
        skip_planning=True,
        device_name="Luba-Test",
    )

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert device.hash_list_acks == [(3, 1, 2), (3, 2, 2)]
    assert device.line_info_requests == [[line_a, line_b]]


def _retry_saga(device: FakeHashListDevice, _map: HashList, line: int) -> MowPathSaga:
    saga = MowPathSaga(
        command_builder=device.command_builder,
        send_command=device.send,
        get_map=lambda: _map,
        zone_hashs=[line],
        route_info=GenerateRouteInformation(one_hashs=[line]),
        skip_planning=True,
        device_name="Luba-Test",
    )
    # The APK's 6 s / 4 s timers, shrunk so the retry path runs in milliseconds.
    saga.first_frame_timeout = saga.next_frame_timeout = saga.residual_frame_timeout = 0.01
    return saga


async def test_saga_re_requests_missing_lines_until_the_device_answers() -> None:
    broker = DeviceMessageBroker()
    _map = HashList()
    line = 5000000000000000001
    device = FakeHashListDevice(broker, _map, hash_lists={3: [[line]]}, ignore_line_requests=2)
    saga = _retry_saga(device, _map, line)

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert device.line_info_requests == [[line], [line], [line]]
    assert not saga.failed
    assert _map.has_mow_path_for_hash(line)


async def test_saga_gives_up_after_ten_retries_without_raising() -> None:
    """Matches the APK's numberLine >= 10 cut-off: one request plus ten retries, then stop."""
    broker = DeviceMessageBroker()
    _map = HashList()
    line = 5000000000000000001
    device = FakeHashListDevice(broker, _map, hash_lists={3: [[line]]}, ignore_line_requests=1000)
    saga = _retry_saga(device, _map, line)

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert len(device.line_info_requests) == 1 + saga.max_cover_path_retries
    assert saga.failed
    assert _map.current_mow_path == {}


async def test_saga_skips_lines_already_cached() -> None:
    """Lines cached before the fetch (e.g. from another client's request) are not asked for again."""
    broker = DeviceMessageBroker()
    _map = HashList()
    cached, missing = 5000000000000000001, 5000000000000000002
    device = FakeHashListDevice(broker, _map, hash_lists={3: [[cached, missing]]})
    await device.send(("line_info", [cached], 1))
    device.line_info_requests.clear()
    saga = _retry_saga(device, _map, cached)

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert device.line_info_requests == [[missing]]


def _planning_saga(device: FakeHashListDevice, _map: HashList, route_info: GenerateRouteInformation) -> MowPathSaga:
    return MowPathSaga(
        command_builder=device.command_builder,
        send_command=device.send,
        get_map=lambda: _map,
        zone_hashs=list(route_info.one_hashs),
        route_info=route_info,
        device_name="Luba-Test",
    )


@pytest.mark.regression
async def test_planning_saga_sends_the_route_it_was_given() -> None:
    """``route_info`` is the route to plan, not proof that one already exists.

    ``_route_val`` was seeded from ``route_info``, so step 2 saw a route as already
    confirmed and skipped ``generate_route_information`` — ``async_plan_route``, which always
    passes ``route_info``, never planned anything and only fetched whatever line list the device
    already held.
    """
    broker = DeviceMessageBroker()
    _map = HashList()
    route_info = GenerateRouteInformation(one_hashs=[7])
    device = FakeHashListDevice(broker, _map, hash_lists={3: [[5000000000000000001]]})

    await asyncio.wait_for(_planning_saga(device, _map, route_info).execute(broker), timeout=_SAGA_TIMEOUT)

    assert device.route_requests == [route_info]


@pytest.mark.regression
async def test_planning_saga_fetches_the_line_list_the_planned_route_produced() -> None:
    """The line list is requested after the route reply, as the APK does (routeResponse → getLineHashList).

    Asking first returned the device's pre-plan route, whose cover paths were then fetched and
    kept for a route that no longer existed.
    """
    broker = DeviceMessageBroker()
    _map = HashList()
    old_line, new_a, new_b = 5000000000000000001, 5000000000000000002, 5000000000000000003
    device = FakeHashListDevice(
        broker, _map, hash_lists={3: [[old_line]]}, hash_lists_after_route={3: [[new_a, new_b]]}
    )
    saga = _planning_saga(device, _map, GenerateRouteInformation(one_hashs=[7]))

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert device.events == ["route", "hash_list:3"], f"line list requested out of order: {device.events}"
    assert device.line_info_requests == [[new_a, new_b]]
    assert _map.line_root_hashlist == [new_a, new_b]


async def test_skip_planning_saga_does_not_send_a_route_request() -> None:
    """A running job's route is already known: only its line list and cover paths are fetched."""
    broker = DeviceMessageBroker()
    _map = HashList()
    device = FakeHashListDevice(broker, _map, hash_lists={3: [[5000000000000000001]]})
    saga = MowPathSaga(
        command_builder=device.command_builder,
        send_command=device.send,
        get_map=lambda: _map,
        zone_hashs=[7],
        route_info=GenerateRouteInformation(one_hashs=[7]),
        skip_planning=True,
        device_name="Luba-Test",
    )

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert device.events == ["hash_list:3"]
