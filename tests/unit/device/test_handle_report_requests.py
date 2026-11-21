"""``DeviceHandle``'s queued report requests: the burst a host asks for after a command, and stream keep-alives.

The cloud transport's ``send`` stands in for the device, answering each request with
a report frame, so one request is exactly one send and the send count is the contract.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from pymammotion.data.model.device import MowingDevice
from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import TransportType
from tests._helpers import make_mock_handle, make_mock_transport
from tests.unit._helpers import make_answering_send

_DRAIN_TIMEOUT = 2.0


@pytest.fixture
async def handle() -> AsyncIterator[DeviceHandle]:
    """A cloud handle whose queue is not running yet, so whatever is requested stays queued."""
    handle = make_mock_handle(device=MowingDevice())
    await handle.add_transport(make_mock_transport(TransportType.CLOUD_ALIYUN))
    handle.get_transport(TransportType.CLOUD_ALIYUN).send = make_answering_send(handle)
    yield handle
    await handle.queue.stop()


async def _drain(handle: DeviceHandle) -> None:
    handle.queue.start()
    await asyncio.wait_for(handle.queue.join(), _DRAIN_TIMEOUT)


@pytest.mark.regression
async def test_request_reports_leaves_a_live_ble_stream_alone(handle: DeviceHandle) -> None:
    """A burst request replaced the continuous subscription the BLE loop renews.

    ``MammotionClient.request_reports`` promised to skip while the stream is live, but
    the handle sent its count=N ``RPT_START`` anyway, reconfiguring that stream.
    """
    handle.ble_stream_active = True

    await handle.request_reports(count=5)
    await _drain(handle)

    handle.get_transport(TransportType.CLOUD_ALIYUN).send.assert_not_awaited()


@pytest.mark.regression
async def test_request_reports_twice_before_it_runs_sends_once(handle: DeviceHandle) -> None:
    """Every call queued its own request, so commands sent back to back each paid for a burst."""
    await handle.request_reports(count=5)
    await handle.request_reports(count=5)
    await _drain(handle)

    handle.get_transport(TransportType.CLOUD_ALIYUN).send.assert_awaited_once()


@pytest.mark.regression
async def test_send_report_stream_keep_twice_before_it_runs_sends_once(handle: DeviceHandle) -> None:
    """Each call queued its own RPT_KEEP, so a dashboard re-arming the stream paid one send per call."""
    await handle.send_report_stream_keep()
    await handle.send_report_stream_keep()
    await _drain(handle)

    handle.get_transport(TransportType.CLOUD_ALIYUN).send.assert_awaited_once()
