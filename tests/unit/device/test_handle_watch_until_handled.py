"""``DeviceHandle.watch_until_handled`` — a change stays pending until its handler says it acted.

Mirrors the APK's ``updateTotalHash``, which only records a new ``path_hash`` once its gate is
open, so a change seen while the gate is shut is retried on every later report.  ``watch_field``
fires once per change and cannot do that.
"""

from __future__ import annotations

import asyncio
import itertools
from unittest.mock import AsyncMock

from pymammotion.data.model.device import MowerDevice
from pymammotion.device.handle import DeviceHandle
from pymammotion.proto import LubaMsg, MctlSys, ReportInfoData, RptWork
from pymammotion.state.device_state import DeviceSnapshot

_TIMEOUT = 2.0


def _handle() -> DeviceHandle:
    return DeviceHandle(device_id="dev-w", device_name="Luba-Watch", initial_device=MowerDevice(name="Luba-Watch"))


def _path_hash(snapshot: DeviceSnapshot) -> int:
    return snapshot.raw.report_data.work.path_hash  # type: ignore[attr-defined]


_position = itertools.count(1)


def _report(path_hash: int) -> bytes:
    """A report that always changes state: an unchanged frame emits no snapshot, so it could not fail a test."""
    work = RptWork(path_hash=path_hash, path_pos_x=next(_position))
    return bytes(LubaMsg(sys=MctlSys(toapp_report_data=ReportInfoData(work=work))))


async def _seeded(handler: AsyncMock) -> DeviceHandle:
    handle = _handle()
    handle.watch_until_handled(_path_hash, handler)
    await handle.on_raw_message(_report(1))
    return handle


async def test_the_first_snapshot_only_seeds_the_watcher() -> None:
    handler = AsyncMock(return_value=True)

    await _seeded(handler)

    handler.assert_not_awaited()


async def test_a_refused_change_is_retried_on_the_next_snapshot_with_the_same_value() -> None:
    handler = AsyncMock(side_effect=[False, False, True])
    handle = await _seeded(handler)

    for _ in range(3):
        await handle.on_raw_message(_report(5))

    assert handler.await_count == 3
    assert [call.args[0] for call in handler.await_args_list] == [5, 5, 5]


async def test_an_accepted_change_is_not_offered_again() -> None:
    handler = AsyncMock(return_value=True)
    handle = await _seeded(handler)

    await handle.on_raw_message(_report(5))
    await handle.on_raw_message(_report(5))

    handler.assert_awaited_once_with(5)


async def test_a_new_value_is_offered_after_an_accepted_one() -> None:
    handler = AsyncMock(return_value=True)
    handle = await _seeded(handler)

    await handle.on_raw_message(_report(5))
    await handle.on_raw_message(_report(6))

    assert [call.args[0] for call in handler.await_args_list] == [5, 6]


async def test_a_handler_that_raises_is_not_retried_for_the_same_value() -> None:
    """One failed attempt per change, like the APK: retrying a raising handler on every report would storm."""
    handler = AsyncMock(side_effect=RuntimeError("saga failed to start"))
    handle = await _seeded(handler)

    await handle.on_raw_message(_report(5))
    await handle.on_raw_message(_report(5))

    handler.assert_awaited_once_with(5)


async def test_a_snapshot_arriving_mid_handler_does_not_start_a_second_attempt() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def _slow(_value: int) -> bool:
        entered.set()
        await release.wait()
        return True

    handler = AsyncMock(side_effect=_slow)
    handle = await _seeded(handler)

    first = asyncio.create_task(handle.on_raw_message(_report(5)))
    await asyncio.wait_for(entered.wait(), _TIMEOUT)
    await asyncio.wait_for(handle.on_raw_message(_report(5)), _TIMEOUT)
    release.set()
    await asyncio.wait_for(first, _TIMEOUT)

    handler.assert_awaited_once_with(5)


async def test_cancelling_the_subscription_stops_the_watcher() -> None:
    handler = AsyncMock(return_value=True)
    handle = _handle()
    subscription = handle.watch_until_handled(_path_hash, handler)
    await handle.on_raw_message(_report(1))

    subscription.cancel()
    await handle.on_raw_message(_report(5))

    handler.assert_not_awaited()
