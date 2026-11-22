"""MapFetchSaga step 4 when the device leaves a ``synchronize_hash_data`` unanswered.

The device is ``FakeHashListDevice``, which answers synchronously inside the send, so
the saga's ``step_timeout`` is shrunk to a few milliseconds: every wait that expires is
a wait the device was never going to answer.
"""
from __future__ import annotations

import asyncio

import pytest

from pymammotion.data.model.hash_list import HashList
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.transport.base import SagaFailedError
from tests.unit.messaging._fakes import FakeHashListDevice
from tests.unit.messaging._helpers import make_fast_map_saga

_SAGA_TIMEOUT = 5.0
_SILENT_FOREVER = 1_000
_AREA_A, _AREA_B, _AREA_C = 5000000000000000001, 5000000000000000002, 5000000000000000003


def _make_device(
    broker: DeviceMessageBroker,
    device_map: HashList,
    hashes: list[int],
    ignore_sync_requests: dict[int, int] | None = None,
) -> FakeHashListDevice:
    return FakeHashListDevice(
        broker,
        device_map,
        hash_lists={0: [hashes]},
        comm_types=dict.fromkeys(hashes, 0),
        ignore_sync_requests=ignore_sync_requests,
    )


@pytest.mark.regression
async def test_an_ignored_hash_request_is_resent_without_refetching_the_root_list() -> None:
    """One unanswered ``synchronize_hash_data`` restarted the whole saga.

    The step timeout raised out of ``_run``, so ``_retry_loop`` re-ran every step:
    the root hash list was requested again (one ack per frame), all to recover a
    single reply the device dropped.  The APK re-sends the same hash instead.
    """
    broker, device_map = DeviceMessageBroker(), HashList()
    device = _make_device(broker, device_map, [_AREA_A, _AREA_B], ignore_sync_requests={_AREA_B: 1})
    saga = make_fast_map_saga(device.command_builder, device.send, device_map)

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert device.events.count("hash_list:0") == 1, f"root list requested again: {device.events}"
    assert device.sync_requests.count(_AREA_B) == 2
    assert saga.result is not None
    assert set(saga.result.area) == {_AREA_A, _AREA_B}


@pytest.mark.regression
async def test_a_hash_the_device_never_serves_is_deferred_and_the_rest_of_the_map_completes() -> None:
    """One permanently unanswered hash cost the user the whole map.

    Each timeout restarted the saga until its attempts ran out, and since the map is
    only published when the saga completes, the areas that had arrived were never
    shown.  The saga must give up on that one hash after a bounded number of sends,
    finish the others, and leave the map unsynced so a later sync retries it.
    """
    broker, device_map = DeviceMessageBroker(), HashList()
    device = _make_device(
        broker, device_map, [_AREA_A, _AREA_B, _AREA_C], ignore_sync_requests={_AREA_B: _SILENT_FOREVER}
    )
    saga = make_fast_map_saga(device.command_builder, device.send, device_map)

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert saga.result is not None
    assert set(saga.result.area) == {_AREA_A, _AREA_C}
    assert device.sync_requests.count(_AREA_B) == 3, "an unserved hash is sent at most three times"
    assert not device_map.is_map_synced(device_map.computed_bol_hash)


async def test_a_deferred_hash_is_recorded_as_unserved() -> None:
    broker, device_map = DeviceMessageBroker(), HashList()
    device = _make_device(broker, device_map, [_AREA_A, _AREA_B], ignore_sync_requests={_AREA_B: _SILENT_FOREVER})

    await asyncio.wait_for(make_fast_map_saga(device.command_builder, device.send, device_map).execute(broker), timeout=_SAGA_TIMEOUT)

    assert device_map.unserved_hashes == {_AREA_B}


async def test_a_sync_that_serves_every_hash_clears_the_unserved_record() -> None:
    broker, device_map = DeviceMessageBroker(), HashList()
    device_map.unserved_hashes = {_AREA_B}
    device = _make_device(broker, device_map, [_AREA_A, _AREA_B])

    await asyncio.wait_for(make_fast_map_saga(device.command_builder, device.send, device_map).execute(broker), timeout=_SAGA_TIMEOUT)

    assert device_map.unserved_hashes == set()


async def test_a_resumed_sync_defers_a_silent_hash_when_the_map_already_holds_areas() -> None:
    """Steps 1-3 answered, so the device is up; one silent hash is that hash's problem."""
    broker, device_map = DeviceMessageBroker(), HashList()
    device = _make_device(broker, device_map, [_AREA_A, _AREA_B])
    await asyncio.wait_for(make_fast_map_saga(device.command_builder, device.send, device_map).execute(broker), timeout=_SAGA_TIMEOUT)
    device_map.area.pop(_AREA_B)
    silent = _make_device(broker, device_map, [_AREA_A, _AREA_B], ignore_sync_requests={_AREA_B: _SILENT_FOREVER})
    saga = make_fast_map_saga(silent.command_builder, silent.send, device_map)

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert saga.result is not None
    assert device_map.unserved_hashes == {_AREA_B}


@pytest.mark.parametrize(
    ("hashes", "silent"),
    [
        ([_AREA_A], [_AREA_A]),
        ([_AREA_A, _AREA_B, _AREA_C], [_AREA_B, _AREA_C]),
    ],
    ids=["the_only_hash_of_an_empty_map", "two_hashes_in_a_row"],
)
async def test_a_device_that_stops_answering_hash_requests_fails_the_sync(hashes: list[int], silent: list[int]) -> None:
    """Total silence is the device going away, not one bad hash: fail rather than publish an empty or gutted map."""
    broker, device_map = DeviceMessageBroker(), HashList()
    device = _make_device(broker, device_map, hashes, ignore_sync_requests=dict.fromkeys(silent, _SILENT_FOREVER))
    saga = make_fast_map_saga(device.command_builder, device.send, device_map)

    with pytest.raises(SagaFailedError):
        await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert saga.result is None
    assert device_map.unserved_hashes == set()
