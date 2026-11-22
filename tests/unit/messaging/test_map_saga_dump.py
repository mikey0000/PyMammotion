"""MapFetchSaga and dump (grass-collection point, type 12) elements.

Saved dump points are listed in the ordinary sub_cmd=0 manifest and fetched like any
other element; the sub_cmd=4 list names only the temporary points of an in-progress
dump-setup session, so a map sync never requests it.
"""
from __future__ import annotations

import asyncio

import pytest

from pymammotion.data.model.hash_list import HashList, NavGetHashListData
from pymammotion.messaging.broker import DeviceMessageBroker
from tests.unit.messaging._fakes import FakeHashListDevice
from tests.unit.messaging._helpers import make_fast_map_saga

_SAGA_TIMEOUT = 5.0
_AREA, _DUMP, _TEMPORARY_DUMP = 4000000000000000001, 4000000000000000002, 4000000000000000003


async def test_a_dump_point_listed_in_the_area_manifest_lands_in_dump() -> None:
    broker, device_map = DeviceMessageBroker(), HashList()
    device = FakeHashListDevice(broker, device_map, hash_lists={0: [[_AREA, _DUMP]]}, comm_types={_AREA: 0, _DUMP: 12})
    saga = make_fast_map_saga(device.command_builder, device.send, device_map)

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert saga.result is not None
    assert set(saga.result.area) == {_AREA}
    assert set(saga.result.dump) == {_DUMP}


@pytest.mark.regression
async def test_a_stored_temporary_dump_list_does_not_hold_up_the_sync() -> None:
    """The saga requested the sub_cmd=4 dump list on every run and fetched its hashes.

    That list names only uncommitted points of a dump-setup session, which the app
    requests from the drawing page alone and never fetches; a mower may never answer
    them, so a sync stalled on them (and before deferral, failed outright).
    """
    broker, device_map = DeviceMessageBroker(), HashList()
    device_map.update_root_hash_list(
        NavGetHashListData(pver=1, sub_cmd=4, total_frame=1, current_frame=1, data_couple=[_TEMPORARY_DUMP])
    )
    device = FakeHashListDevice(
        broker,
        device_map,
        hash_lists={0: [[_AREA]], 4: [[_TEMPORARY_DUMP]]},
        comm_types={_AREA: 0},
        ignore_sync_requests={_TEMPORARY_DUMP: 1_000},
    )
    saga = make_fast_map_saga(device.command_builder, device.send, device_map)

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert "hash_list:4" not in device.events, f"dump list requested: {device.events}"
    assert _TEMPORARY_DUMP not in device.sync_requests
    assert device_map.unserved_hashes == set()
