"""Tests for DeviceCommandQueue."""
from __future__ import annotations

import asyncio

import pytest

from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_queue import DeviceCommandQueue, Priority
from pymammotion.messaging.saga import Saga
from pymammotion.transport.base import SagaFailedError


async def test_is_saga_active_false_initially() -> None:
    q = DeviceCommandQueue()
    assert q.is_saga_active is False


async def test_skip_if_saga_active_drops_item() -> None:
    q = DeviceCommandQueue()
    q._exclusive_active.clear()  # simulate saga running
    called = []

    async def work() -> None:
        called.append(1)

    await q.enqueue(work, priority=Priority.NORMAL, skip_if_saga_active=True)
    assert q._queue.empty()
    assert called == []
    q._exclusive_active.set()


async def test_emergency_never_skipped() -> None:
    q = DeviceCommandQueue()
    q._exclusive_active.clear()  # simulate saga running
    called = []

    async def work() -> None:
        called.append(1)

    # EMERGENCY should always enqueue even when saga active
    await q.enqueue(work, priority=Priority.EMERGENCY, skip_if_saga_active=True)
    assert not q._queue.empty()
    q._exclusive_active.set()


async def test_exclusive_active_set_after_saga() -> None:
    q = DeviceCommandQueue()
    broker = DeviceMessageBroker()
    q.start()

    class QuickSaga(Saga):
        name = "quick"

        async def _run(self, b: DeviceMessageBroker) -> None:
            pass

    await q.enqueue_saga(QuickSaga(), broker)
    await asyncio.sleep(0.1)
    assert q.is_saga_active is False
    await q.stop()


async def test_stop_releases_exclusive_lock() -> None:
    q = DeviceCommandQueue()
    q._exclusive_active.clear()  # simulate stuck saga
    await q.stop()
    assert q._exclusive_active.is_set()


async def test_exception_in_work_does_not_crash_queue() -> None:
    q = DeviceCommandQueue()
    q.start()
    executed = []

    async def bad_work() -> None:
        raise RuntimeError("boom")

    async def good_work() -> None:
        executed.append(1)

    await q.enqueue(bad_work)
    await q.enqueue(good_work)
    await asyncio.sleep(0.1)
    assert executed == [1]
    await q.stop()


async def test_fifo_within_same_priority() -> None:
    q = DeviceCommandQueue()
    q.start()
    order: list[int] = []

    for i in range(3):
        n = i

        async def work(n: int = n) -> None:
            order.append(n)

        await q.enqueue(work, priority=Priority.NORMAL)

    await asyncio.sleep(0.1)
    assert order == [0, 1, 2]
    await q.stop()
