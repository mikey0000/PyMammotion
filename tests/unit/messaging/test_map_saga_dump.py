"""MapFetchSaga and the sub_cmd=4 dump (grass-collection point) hash list.

A second root list the saga must request and fetch alongside sub_cmd=0,
tolerating silence when the device has no dumping spots configured.
"""
from __future__ import annotations

import asyncio

from pymammotion.data.model.hash_list import HashList
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.map_saga import MapFetchSaga
from tests.unit.messaging._helpers import (
    comm_data_frame as _comm_data_msg,
    hash_list_msg as _hash_list_msg,
    make_command_builder as _make_command_builder,
    run_saga_with_messages as _run_saga_with_messages,
)


async def test_saga_fetches_dump_hash_list_and_stores_type_12() -> None:
    """A sub_cmd=4 hash list entry is requested, fetched via step 4 like any
    other hash, and its type=12 (DUMP) comm-data frame lands in ``.dump``."""
    broker = DeviceMessageBroker()

    async def send_command(_cmd: bytes) -> None:
        pass

    _map = HashList()
    saga = MapFetchSaga(
        device_id="dev-dump",
        device_name="Luba-Test",
        is_luba1=True,  # skip area names
        command_builder=_make_command_builder(),
        send_command=send_command,
        get_map=lambda: _map,
    )

    area_hash = 4000000000000000001
    dump_hash = 4000000000000000002

    await asyncio.wait_for(
        _run_saga_with_messages(
            broker,
            saga,
            messages=[
                _hash_list_msg([area_hash], sub_cmd=0),
                _hash_list_msg([dump_hash], sub_cmd=4),
                _comm_data_msg(area_hash, type_code=0),  # PathType.AREA
                _comm_data_msg(dump_hash, type_code=12),  # PathType.DUMP
            ],
            map_update=_map,
        ),
        timeout=5.0,
    )

    assert saga.result is not None
    assert area_hash in saga.result.area
    assert dump_hash in saga.result.dump
    assert dump_hash not in saga.result.area

    names = [c[0] for c in saga._command_builder.mock_calls if c[0]]  # noqa: SLF001
    sub_cmd_kwargs = [c.kwargs.get("sub_cmd") for c in saga._command_builder.mock_calls if c[0] == "get_all_boundary_hash_list"]  # noqa: SLF001
    assert 0 in sub_cmd_kwargs
    assert 4 in sub_cmd_kwargs
    assert names.index("get_all_boundary_hash_list") < names.index("synchronize_hash_data")


async def test_saga_completes_when_device_has_no_dumping_spots() -> None:
    """A device with no grass-collection points configured answers the sub_cmd=4
    request with nothing at all — the saga must not hang or fail waiting for it,
    and must still complete the sub_cmd=0 fetch normally."""
    broker = DeviceMessageBroker()

    async def send_command(_cmd: bytes) -> None:
        pass

    _map = HashList()
    saga = MapFetchSaga(
        device_id="dev-no-dump",
        device_name="Luba-Test",
        is_luba1=True,
        command_builder=_make_command_builder(),
        send_command=send_command,
        get_map=lambda: _map,
    )

    area_hash = 4000000000000000003

    # No sub_cmd=4 message is injected at all — silence, not an empty frame.
    await asyncio.wait_for(
        _run_saga_with_messages(
            broker,
            saga,
            messages=[
                _hash_list_msg([area_hash], sub_cmd=0),
                _comm_data_msg(area_hash, type_code=0),
            ],
            map_update=_map,
        ),
        timeout=5.0,  # would hang/timeout-fail without allow_empty=True on the sub_cmd=4 step
    )

    assert saga.result is not None
    assert area_hash in saga.result.area
    assert saga.result.dump == {}
