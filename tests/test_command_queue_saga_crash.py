"""Regression tests for C2: saga crash / cancellation must release the exclusive lock.

If `saga.execute(broker)` raises an unhandled exception, OR the saga task is
cancelled before the `finally` runs, ``_exclusive_active`` must still be set
again so subsequent commands can run on the same device queue.
"""

from __future__ import annotations

import asyncio

from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_queue import DeviceCommandQueue, Priority
from pymammotion.messaging.saga import Saga


class _CrashingSaga(Saga):
    """Saga whose ``execute()`` raises immediately via ``_run``."""

    name = "crashing"
    max_attempts = 1
    total_timeout = 5.0

    async def _run(self, broker: DeviceMessageBroker) -> None:
        raise RuntimeError("boom")


class _SlowSaga(Saga):
    """Saga that sleeps long enough to be cancelled mid-execution."""

    name = "slow"
    max_attempts = 1
    total_timeout = 60.0

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()

    async def _run(self, broker: DeviceMessageBroker) -> None:
        self.started.set()
        await asyncio.sleep(60.0)


async def test_saga_exception_releases_exclusive_lock() -> None:
    """A saga that raises inside execute() must not leave the queue blocked."""
    q = DeviceCommandQueue(device_name="dev-crash")
    broker = DeviceMessageBroker()
    q.start()
    try:
        ran: list[int] = []

        async def follow_up() -> None:
            ran.append(1)

        await q.enqueue_saga(_CrashingSaga(), broker)
        # Give the queue processor a chance to run the (failing) saga.
        await asyncio.sleep(0.2)

        # Lock must be released even though the saga raised.
        assert q.is_saga_active is False, "exclusive lock not released after saga crash"
        assert q._current_work_task is None, "_current_work_task not cleared after saga crash"

        # A subsequent NORMAL command must execute (proves queue is not stuck).
        await q.enqueue(follow_up, priority=Priority.NORMAL)
        await asyncio.sleep(0.2)
        assert ran == [1], "follow-up command did not run — queue is deadlocked"
    finally:
        await q.stop()


async def test_saga_cancellation_releases_exclusive_lock() -> None:
    """If the saga work-task is cancelled mid-flight, the lock must still release."""
    q = DeviceCommandQueue(device_name="dev-cancel")
    broker = DeviceMessageBroker()
    q.start()
    try:
        slow = _SlowSaga()
        await q.enqueue_saga(slow, broker)

        # Wait until the saga has actually started running before cancelling.
        await asyncio.wait_for(slow.started.wait(), timeout=2.0)
        assert q.is_saga_active is True

        # Cancel the in-flight work task — simulates a transport teardown
        # racing the saga's `finally` block.
        current = q._current_work_task
        assert current is not None
        current.cancel()

        # Wait until cancellation has propagated.
        await asyncio.sleep(0.2)

        assert q.is_saga_active is False, "exclusive lock not released after cancellation"
        assert q._current_work_task is None, "_current_work_task not cleared after cancellation"

        # Verify follow-up commands actually run.
        ran: list[int] = []

        async def follow_up() -> None:
            ran.append(1)

        await q.enqueue(follow_up, priority=Priority.NORMAL)
        await asyncio.sleep(0.2)
        assert ran == [1], "follow-up command did not run — queue is deadlocked"
    finally:
        await q.stop()


async def test_on_saga_start_cancellation_releases_exclusive_lock() -> None:
    """If on_saga_start is cancelled (CancelledError), the lock must still release.

    on_saga_start is awaited *after* `_exclusive_active.clear()` but *outside*
    the try/finally that re-sets it. CancelledError in that window would
    deadlock the queue.
    """
    q = DeviceCommandQueue(device_name="dev-cb-cancel")
    broker = DeviceMessageBroker()

    class _QuickSaga(Saga):
        name = "quick"

        async def _run(self, b: DeviceMessageBroker) -> None:
            return None

    async def cancelling_start() -> None:
        raise asyncio.CancelledError

    q.on_saga_start = cancelling_start
    q.start()
    try:
        await q.enqueue_saga(_QuickSaga(), broker)
        await asyncio.sleep(0.2)

        assert q.is_saga_active is False, "exclusive lock not released after on_saga_start cancel"
        assert q._current_work_task is None
    finally:
        await q.stop()
