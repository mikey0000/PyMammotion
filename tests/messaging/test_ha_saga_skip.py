"""Tests for HA saga-skip behaviour and stop() saga cancellation."""
from __future__ import annotations

import asyncio

import pytest

from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_queue import DeviceCommandQueue, Priority
from pymammotion.messaging.saga import Saga


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _BlockingSaga(Saga):
    """Saga that blocks until its internal event is set."""

    name = "blocking_saga"
    max_attempts = 1

    def __init__(self) -> None:
        self._release = asyncio.Event()

    def release(self) -> None:
        self._release.set()

    async def _run(self, broker: DeviceMessageBroker) -> None:
        await self._release.wait()


class _InstantSaga(Saga):
    """Saga that returns immediately."""

    name = "instant_saga"
    max_attempts = 1

    async def _run(self, broker: DeviceMessageBroker) -> None:
        pass


# ---------------------------------------------------------------------------
# Test 1: skip_if_saga_active=True drops a NORMAL command while saga active
# ---------------------------------------------------------------------------


async def test_skip_if_saga_active_true_drops_normal_command() -> None:
    """NORMAL item with skip_if_saga_active=True must be dropped when saga is running."""
    q = DeviceCommandQueue()
    # Simulate a saga holding the exclusive slot
    q._exclusive_active.clear()
    called: list[int] = []

    async def normal_work() -> None:
        called.append(1)

    await q.enqueue(normal_work, priority=Priority.NORMAL, skip_if_saga_active=True)

    # Item must have been dropped — queue still empty, work never scheduled
    assert q._queue.empty()
    assert called == []

    # Cleanup
    q._exclusive_active.set()


# ---------------------------------------------------------------------------
# Test 2: skip_if_saga_active=False queues item and it runs after saga
# ---------------------------------------------------------------------------


async def test_skip_if_saga_active_false_queues_command() -> None:
    """NORMAL item with skip_if_saga_active=False must wait and eventually execute."""
    q = DeviceCommandQueue()
    broker = DeviceMessageBroker()
    saga = _BlockingSaga()
    q.start()

    await q.enqueue_saga(saga, broker)

    # Give the processor time to pick up the saga
    await asyncio.sleep(0.05)
    assert q.is_saga_active is True

    executed: list[int] = []

    async def normal_work() -> None:
        executed.append(1)

    # skip_if_saga_active=False — must NOT be dropped
    await q.enqueue(normal_work, priority=Priority.NORMAL, skip_if_saga_active=False)

    # Still running — work should not have executed yet
    assert executed == []

    # Release the saga so the normal work can proceed
    saga.release()
    await asyncio.sleep(0.15)

    assert executed == [1]
    await q.stop()


# ---------------------------------------------------------------------------
# Test 3: EMERGENCY always runs even while saga is active
# ---------------------------------------------------------------------------


async def test_emergency_runs_during_saga() -> None:
    """EMERGENCY priority items must be enqueued (not dropped) and run after the current work item.

    EMERGENCY bypasses the skip_if_saga_active drop and the exclusive-slot wait,
    so the item IS placed on the queue.  The single-threaded processor finishes
    its current work task first, then picks up the EMERGENCY item — so we need
    to release the saga before asserting execution.
    """
    q = DeviceCommandQueue()
    broker = DeviceMessageBroker()
    saga = _BlockingSaga()
    q.start()

    await q.enqueue_saga(saga, broker)
    await asyncio.sleep(0.05)
    assert q.is_saga_active is True

    emergency_called: list[int] = []

    async def emergency_work() -> None:
        emergency_called.append(1)

    # EMERGENCY with skip_if_saga_active=True must still be enqueued (not dropped)
    await q.enqueue(emergency_work, priority=Priority.EMERGENCY, skip_if_saga_active=True)
    assert not q._queue.empty(), "EMERGENCY item must not have been dropped"

    # Release the saga so the processor can move on to the EMERGENCY item
    saga.release()
    await asyncio.sleep(0.15)
    assert emergency_called == [1]

    await q.stop()


# ---------------------------------------------------------------------------
# Test 4: stop() cancels a currently-running saga task
# ---------------------------------------------------------------------------


async def test_stop_cancels_running_saga_task() -> None:
    """stop() must cancel the running work task and return cleanly."""
    q = DeviceCommandQueue()
    broker = DeviceMessageBroker()
    saga = _BlockingSaga()
    q.start()

    await q.enqueue_saga(saga, broker)
    await asyncio.sleep(0.05)
    assert q.is_saga_active is True

    # stop() should complete even though the saga is blocking
    await asyncio.wait_for(q.stop(), timeout=2.0)

    # Queue must report no active saga after stop
    assert q.is_saga_active is False


# ---------------------------------------------------------------------------
# Test 5: is_saga_active is False after stop()
# ---------------------------------------------------------------------------


async def test_is_saga_active_false_after_stop() -> None:
    """After stop(), is_saga_active must return False."""
    q = DeviceCommandQueue()
    broker = DeviceMessageBroker()
    saga = _BlockingSaga()
    q.start()

    await q.enqueue_saga(saga, broker)
    await asyncio.sleep(0.05)

    await q.stop()

    assert q.is_saga_active is False
