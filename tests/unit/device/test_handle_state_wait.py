"""``DeviceHandle.wait_for`` — wait until the device reports a state a host is waiting on.

Built on the state-changed bus, so it sees exactly what every subscriber sees.  The
``refresh`` hook stands in for the user-priority report request; it is the boundary
the waiter drives, so asserting on its awaits is the contract.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.device.handle import DeviceHandle, DeviceStateTimeoutError
from pymammotion.utility.constant.device_enums import WorkMode
from tests._helpers import wait_until
from tests.unit._helpers import is_ready, make_sys_status_report

_TIMEOUT = 2.0


def _handle() -> DeviceHandle:
    return DeviceHandle(device_id="dev-s", device_name="Luba-Wait", initial_device=MowerDevice(name="Luba-Wait"))


async def test_wait_for_returns_the_current_state_without_requesting_a_report_when_it_already_matches() -> None:
    handle = _handle()
    await handle.on_raw_message(make_sys_status_report(WorkMode.MODE_READY))
    refresh = AsyncMock()

    device = await handle.wait_for(is_ready, timeout=_TIMEOUT, refresh=refresh)

    assert is_ready(device)
    refresh.assert_not_awaited()


async def test_wait_for_requests_a_report_and_returns_the_state_it_brings() -> None:
    handle = _handle()

    async def _device_answers() -> None:
        await handle.on_raw_message(make_sys_status_report(WorkMode.MODE_READY))

    refresh = AsyncMock(side_effect=_device_answers)

    device = await handle.wait_for(is_ready, timeout=_TIMEOUT, refresh=refresh)

    assert is_ready(device)
    refresh.assert_awaited_once()


async def test_wait_for_resolves_on_a_later_report_that_matches() -> None:
    handle = _handle()

    async def _device_still_paused() -> None:
        await handle.on_raw_message(make_sys_status_report(WorkMode.MODE_PAUSE))

    refresh = AsyncMock(side_effect=_device_still_paused)

    waiter = asyncio.create_task(handle.wait_for(is_ready, timeout=_TIMEOUT, refresh=refresh))
    await wait_until(lambda: refresh.await_count == 1)
    assert not waiter.done(), "a non-matching report must not end the wait"
    await handle.on_raw_message(make_sys_status_report(WorkMode.MODE_READY))

    device = await asyncio.wait_for(waiter, _TIMEOUT)
    assert is_ready(device)


async def test_wait_for_does_not_request_a_report_while_the_device_is_already_reporting() -> None:
    """A fresh report means the device is talking; a one-shot RPT_START would reconfigure its stream."""
    handle = _handle()
    await handle.on_raw_message(make_sys_status_report(WorkMode.MODE_PAUSE))
    refresh = AsyncMock()

    waiter = asyncio.create_task(handle.wait_for(is_ready, timeout=_TIMEOUT, refresh=refresh, poll_interval=60.0))
    await asyncio.sleep(0)  # one turn: the waiter subscribes and parks without a refresh
    await handle.on_raw_message(make_sys_status_report(WorkMode.MODE_READY))

    await asyncio.wait_for(waiter, _TIMEOUT)
    refresh.assert_not_awaited()


async def test_wait_for_requests_again_when_no_report_arrives_within_the_poll_interval() -> None:
    handle = _handle()
    refresh = AsyncMock()

    waiter = asyncio.create_task(handle.wait_for(is_ready, timeout=_TIMEOUT, refresh=refresh, poll_interval=0.01))
    await wait_until(lambda: refresh.await_count >= 2, message="the wait never re-requested a report")
    await handle.on_raw_message(make_sys_status_report(WorkMode.MODE_READY))

    await asyncio.wait_for(waiter, _TIMEOUT)


async def test_wait_for_raises_a_timeout_error_naming_the_device_when_the_state_never_arrives() -> None:
    handle = _handle()

    with pytest.raises(DeviceStateTimeoutError) as exc_info:
        await handle.wait_for(is_ready, timeout=0.01, refresh=AsyncMock(), poll_interval=60.0)

    assert isinstance(exc_info.value, TimeoutError), "hosts already catch TimeoutError"
    assert exc_info.value.device_name == "Luba-Wait"


async def test_wait_for_unsubscribes_from_the_state_bus_when_it_returns() -> None:
    handle = _handle()
    await handle.on_raw_message(make_sys_status_report(WorkMode.MODE_READY))
    before = len(handle._state_changed_bus._bus._handlers)

    await handle.wait_for(is_ready, timeout=_TIMEOUT, refresh=AsyncMock())

    assert len(handle._state_changed_bus._bus._handlers) == before


async def test_wait_for_propagates_a_failed_report_request_and_releases_its_subscription() -> None:
    handle = _handle()
    before = len(handle._state_changed_bus._bus._handlers)
    refresh = AsyncMock(side_effect=ConnectionError("no route"))

    with pytest.raises(ConnectionError):
        await handle.wait_for(is_ready, timeout=_TIMEOUT, refresh=refresh)

    assert len(handle._state_changed_bus._bus._handlers) == before
