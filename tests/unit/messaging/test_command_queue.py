"""Tests for DeviceCommandQueue."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
import logging
import time
from unittest.mock import AsyncMock, patch

import pytest

from pymammotion.messaging import command_queue
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_queue import _COMMAND_TTL, DeviceCommandQueue, Priority
from pymammotion.messaging.saga import Saga
from tests._helpers import wait_until

_DRAIN_TIMEOUT = 2.0


class _OffsetClock:
    """Stands in for the queue module's ``time``: real monotonic plus a test-controlled offset."""

    def __init__(self) -> None:
        self.offset = 0.0

    def monotonic(self) -> float:
        return time.monotonic() + self.offset


def _work_mock() -> AsyncMock:
    async def work() -> None: ...

    return AsyncMock(spec=work)


async def _hold_one_item(
    q: DeviceCommandQueue, hold: Callable[[], None], enqueue: Callable[[], Awaitable[None]]
) -> None:
    """Close a gate via *hold*, enqueue, and return once the processor has dequeued the item.

    ``_process`` runs from ``get()`` to the first unset Event without yielding, so an empty
    queue means the item passed the dequeue TTL check and is parked on that Event.
    """
    hold()
    q.start()
    await enqueue()
    await wait_until(q._queue.empty, message="the processor never dequeued the item")


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


@pytest.mark.parametrize("priority", [Priority.EMERGENCY, Priority.USER])
async def test_direct_priorities_are_refused_by_the_queue(priority: Priority) -> None:
    """These are dispatched on the caller's task; queueing one reinstates the waiting.

    The queue used to accept EMERGENCY and merely exempt it from some gates, which
    could not deliver preemption: the processor is sequential, so the item still sat
    behind whatever work() was already running.
    """
    q = DeviceCommandQueue()

    async def work() -> None:
        pass

    with pytest.raises(ValueError, match="direct-send priority"):
        await q.enqueue(work, priority=priority)

    assert q._queue.empty()


async def test_exclusive_active_set_after_saga() -> None:
    q = DeviceCommandQueue()
    broker = DeviceMessageBroker()
    q.start()

    class QuickSaga(Saga):
        name = "quick"

        async def _run(self, b: DeviceMessageBroker) -> None:
            pass

    await q.enqueue_saga(QuickSaga(), broker)
    await wait_until(lambda: q.is_saga_active is False, message="saga never released the exclusive lock")
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
    await wait_until(lambda: executed == [1], message="the queue stopped after the failing work item")
    assert executed == [1]
    await q.stop()


async def test_enqueue_saga_on_complete_called_on_success() -> None:
    """on_complete must be called once after a successful saga."""
    q = DeviceCommandQueue()
    broker = DeviceMessageBroker()
    q.start()

    class QuickSaga(Saga):
        name = "quick"

        async def _run(self, b: DeviceMessageBroker) -> None:
            pass

    completed: list[int] = []

    async def on_complete() -> None:
        completed.append(1)

    await q.enqueue_saga(QuickSaga(), broker, on_complete=on_complete)
    await wait_until(lambda: completed == [1], message="on_complete never fired")

    assert completed == [1]
    await q.stop()


async def test_enqueue_saga_on_complete_not_called_on_failure() -> None:
    """on_complete must NOT be called when the saga fails (exhausts retries)."""
    q = DeviceCommandQueue()
    broker = DeviceMessageBroker()
    q.start()

    class FailingSaga(Saga):
        name = "failing"
        max_attempts = 1

        async def _run(self, b: DeviceMessageBroker) -> None:
            raise RuntimeError("saga failure")

    completed: list[int] = []

    async def on_complete() -> None:
        completed.append(1)

    await q.enqueue_saga(FailingSaga(), broker, on_complete=on_complete)
    await wait_until(lambda: q.is_saga_active is False, message="the failing saga never released the lock")

    assert completed == []
    await q.stop()


async def test_enqueue_saga_on_complete_error_does_not_crash_queue() -> None:
    """A failing on_complete callback must not stop subsequent queue items."""
    q = DeviceCommandQueue()
    broker = DeviceMessageBroker()
    q.start()

    class QuickSaga(Saga):
        name = "quick"

        async def _run(self, b: DeviceMessageBroker) -> None:
            pass

    async def bad_on_complete() -> None:
        raise RuntimeError("callback error")

    executed: list[int] = []

    async def next_work() -> None:
        executed.append(1)

    await q.enqueue_saga(QuickSaga(), broker, on_complete=bad_on_complete)
    await q.enqueue(next_work)
    await wait_until(lambda: executed == [1], message="a raising on_complete stalled the queue")

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

    await wait_until(lambda: len(order) == 3, message=f"only {order} ran")
    assert order == [0, 1, 2]
    await q.stop()


class _RecordingSaga(Saga):
    name = "recording"

    def __init__(self) -> None:
        super().__init__()
        self.ran = False

    async def _run(self, b: DeviceMessageBroker) -> None:
        self.ran = True


@pytest.fixture
async def queue() -> AsyncIterator[DeviceCommandQueue]:
    q = DeviceCommandQueue(device_name="dev")
    yield q
    await q.stop()


@pytest.fixture
def clock() -> Iterator[_OffsetClock]:
    c = _OffsetClock()
    with patch.object(command_queue, "time", c):
        yield c


@pytest.mark.regression
@pytest.mark.parametrize("priority", [Priority.NORMAL, Priority.BACKGROUND])
async def test_command_held_at_reconnect_gate_past_ttl_is_dropped(
    priority: Priority, queue: DeviceCommandQueue, clock: _OffsetClock, caplog: pytest.LogCaptureFixture
) -> None:
    """A queued command that outlives the TTL while parked on the reconnect gate must not run.

    The age was checked only at dequeue, before the gate wait, so an item dequeued fresh
    and held through a reconnect longer than the TTL was dispatched on resume anyway.
    """
    work = _work_mock()
    await _hold_one_item(queue, queue.pause_for_reconnect, lambda: queue.enqueue(work, priority=priority))
    clock.offset = _COMMAND_TTL + 1
    with caplog.at_level(logging.DEBUG, logger=command_queue.__name__):
        queue.resume_after_reconnect()
        await asyncio.wait_for(queue._queue.join(), _DRAIN_TIMEOUT)

    work.assert_not_awaited()
    assert any("command expired" in r.getMessage() for r in caplog.records), "expiry was not logged"


@pytest.mark.parametrize("priority", [Priority.NORMAL, Priority.BACKGROUND])
async def test_command_held_at_reconnect_gate_within_ttl_runs(
    priority: Priority, queue: DeviceCommandQueue, clock: _OffsetClock
) -> None:
    work = _work_mock()
    await _hold_one_item(queue, queue.pause_for_reconnect, lambda: queue.enqueue(work, priority=priority))
    clock.offset = _COMMAND_TTL - 1
    queue.resume_after_reconnect()
    await asyncio.wait_for(queue._queue.join(), _DRAIN_TIMEOUT)

    work.assert_awaited_once()


async def test_command_stale_at_dequeue_is_dropped_without_parking_at_the_gate(
    queue: DeviceCommandQueue, clock: _OffsetClock
) -> None:
    """An item already past the TTL when dequeued is dropped there, so it cannot hold the processor at a closed gate."""
    work = _work_mock()
    queue.pause_for_reconnect()
    await queue.enqueue(work, priority=Priority.NORMAL)
    clock.offset = _COMMAND_TTL + 1
    queue.start()

    await asyncio.wait_for(queue._queue.join(), _DRAIN_TIMEOUT)

    work.assert_not_awaited()
    assert not queue._transport_gate.is_set(), "the queue drained only because the gate was opened"


async def test_saga_held_at_reconnect_gate_past_ttl_still_runs(queue: DeviceCommandQueue, clock: _OffsetClock) -> None:
    """Sagas are TTL-exempt: dropping one means on_complete never fires and the sync silently never happens."""
    saga = _RecordingSaga()
    await _hold_one_item(queue, queue.pause_for_reconnect, lambda: queue.enqueue_saga(saga, DeviceMessageBroker()))
    clock.offset = _COMMAND_TTL + 1
    queue.resume_after_reconnect()
    await asyncio.wait_for(queue._queue.join(), _DRAIN_TIMEOUT)

    assert saga.ran


@pytest.mark.regression
async def test_command_held_behind_exclusive_slot_past_ttl_is_dropped(
    queue: DeviceCommandQueue, clock: _OffsetClock
) -> None:
    """The exclusive-slot wait sits between the dequeue check and dispatch too.

    An item that aged past the TTL waiting for the slot was dispatched once it freed.
    """
    work = _work_mock()
    # Private: a real saga runs on the processor task, so nothing can be dequeued behind it publicly.
    await _hold_one_item(queue, queue._exclusive_active.clear, lambda: queue.enqueue(work, priority=Priority.NORMAL))
    clock.offset = _COMMAND_TTL + 1
    queue._exclusive_active.set()
    await asyncio.wait_for(queue._queue.join(), _DRAIN_TIMEOUT)

    work.assert_not_awaited()
