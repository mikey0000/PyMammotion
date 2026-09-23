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
        route_info=GenerateRouteInformation(one_hashs=[line_a]),  # skips route planning
        device_name="Luba-Test",
    )

    await asyncio.wait_for(saga.execute(broker), timeout=_SAGA_TIMEOUT)

    assert device.hash_list_acks == [(3, 1, 2), (3, 2, 2)]
    assert device.line_info_requests == [[line_a, line_b]]
