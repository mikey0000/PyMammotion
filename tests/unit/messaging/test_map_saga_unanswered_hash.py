"""MapFetchSaga step 4 when the device leaves a ``synchronize_hash_data`` unanswered.

The device is ``FakeHashListDevice``, which answers synchronously inside the send, so
the saga's ``step_timeout`` is shrunk to a few milliseconds: every wait that expires is
a wait the device was never going to answer.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pymammotion.data.model.hash_list import HashList
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.transport.base import SagaFailedError
from tests.unit.messaging._fakes import FakeHashListDevice
from tests.unit.messaging._helpers import apply_msg_to_map, comm_data_frame, make_fast_map_saga

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


async def _sync(device: FakeHashListDevice, device_map: HashList, broker: DeviceMessageBroker) -> None:
    await asyncio.wait_for(
        make_fast_map_saga(device.command_builder, device.send, device_map).execute(broker), timeout=_SAGA_TIMEOUT
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

    await _sync(device, device_map, broker)

    assert device_map.unserved_hashes == {_AREA_B}


async def test_a_sync_that_serves_every_hash_clears_the_unserved_record() -> None:
    broker, device_map = DeviceMessageBroker(), HashList()
    device_map.unserved_hashes = {_AREA_B}
    device = _make_device(broker, device_map, [_AREA_A, _AREA_B])

    await _sync(device, device_map, broker)

    assert device_map.unserved_hashes == set()


async def test_a_resumed_sync_defers_a_silent_hash_when_the_map_already_holds_areas() -> None:
    """Steps 1-3 answered, so the device is up; one silent hash is that hash's problem."""
    broker, device_map = DeviceMessageBroker(), HashList()
    device = _make_device(broker, device_map, [_AREA_A, _AREA_B])
    await _sync(device, device_map, broker)
    device_map.area.pop(_AREA_B)
    silent = _make_device(broker, device_map, [_AREA_A, _AREA_B], ignore_sync_requests={_AREA_B: _SILENT_FOREVER})
    saga = make_fast_map_saga(silent.command_builder, silent.send, device_map)

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert saga.result is not None
    assert device_map.unserved_hashes == {_AREA_B}


async def test_the_only_hash_of_an_empty_map_going_unanswered_fails_the_sync() -> None:
    """Deferring it would publish an empty map; an absent device must fail like any other silence."""
    broker, device_map = DeviceMessageBroker(), HashList()
    device = _make_device(broker, device_map, [_AREA_A], ignore_sync_requests={_AREA_A: _SILENT_FOREVER})

    with pytest.raises(SagaFailedError):
        await _sync(device, device_map, broker)

    assert device_map.unserved_hashes == set()


async def test_two_hashes_in_a_row_going_unanswered_fails_the_sync() -> None:
    """The map holds a served area, so only the consecutive-deferral cap can fail this run."""
    broker, device_map = DeviceMessageBroker(), HashList()
    device = _make_device(
        broker,
        device_map,
        [_AREA_A, _AREA_B, _AREA_C],
        ignore_sync_requests={_AREA_B: _SILENT_FOREVER, _AREA_C: _SILENT_FOREVER},
    )

    with pytest.raises(SagaFailedError):
        await _sync(device, device_map, broker)

    assert set(device_map.area) == {_AREA_A}
    assert device_map.unserved_hashes == set()


async def test_a_served_hash_between_two_silent_ones_resets_the_consecutive_deferral_count() -> None:
    broker, device_map = DeviceMessageBroker(), HashList()
    device = _make_device(
        broker,
        device_map,
        [_AREA_A, _AREA_B, _AREA_C],
        ignore_sync_requests={_AREA_A: _SILENT_FOREVER, _AREA_C: _SILENT_FOREVER},
    )

    await _sync(device, device_map, broker)

    assert device_map.unserved_hashes == {_AREA_A, _AREA_C}


async def test_a_deferred_hash_whose_data_arrives_later_in_the_run_is_not_recorded_as_unserved() -> None:
    broker, device_map = DeviceMessageBroker(), HashList()
    device = _make_device(broker, device_map, [_AREA_A, _AREA_B], ignore_sync_requests={_AREA_A: _SILENT_FOREVER})
    late_frame = comm_data_frame(_AREA_A, type_code=0)

    async def send_with_late_reply(cmd: Any) -> None:
        if cmd == ("sync_hash", _AREA_B):
            apply_msg_to_map(late_frame, device_map)
            await broker.on_message(late_frame)
        await device.send(cmd)

    saga = make_fast_map_saga(device.command_builder, send_with_late_reply, device_map)
    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert set(device_map.area) == {_AREA_A, _AREA_B}
    assert device_map.unserved_hashes == set()
