"""Tests for DeviceCommandQueue."""
from __future__ import annotations

import asyncio

import pytest

from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_queue import DeviceCommandQueue, Priority
from pymammotion.messaging.saga import Saga
from pymammotion.transport.base import SagaFailedError, SessionExpiredError, TransportType


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
    await asyncio.sleep(0.1)

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
    await asyncio.sleep(0.1)

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
    await asyncio.sleep(0.2)

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


def _session_expired() -> SessionExpiredError:
    return SessionExpiredError(TransportType.CLOUD_ALIYUN, "identityId is blank (29003) — token refresh required")


async def test_session_expired_refreshes_and_retries() -> None:
    """A SessionExpiredError triggers one credential refresh and a retry of the same command."""
    q = DeviceCommandQueue()
    q.start()
    attempts: list[int] = []
    refreshes: list[SessionExpiredError] = []

    async def flaky_work() -> None:
        attempts.append(1)
        if len(attempts) == 1:
            raise _session_expired()

    async def on_session_expired(exc: SessionExpiredError) -> bool:
        refreshes.append(exc)
        return True

    q.on_session_expired = on_session_expired
    await q.enqueue(flaky_work)
    await asyncio.sleep(0.1)

    assert len(attempts) == 2
    assert len(refreshes) == 1
    await q.stop()


async def test_session_expired_failed_refresh_drops_command() -> None:
    """When the credential refresh fails the command is dropped and reported as critical."""
    q = DeviceCommandQueue()
    q.start()
    attempts: list[int] = []
    critical: list[Exception] = []

    async def work() -> None:
        attempts.append(1)
        raise _session_expired()

    async def on_session_expired(exc: SessionExpiredError) -> bool:
        return False

    async def on_critical(exc: Exception) -> None:
        critical.append(exc)

    q.on_session_expired = on_session_expired
    q.on_critical_error = on_critical
    await q.enqueue(work)
    await asyncio.sleep(0.1)

    assert len(attempts) == 1
    assert len(critical) == 1
    assert isinstance(critical[0], SessionExpiredError)
    await q.stop()


async def test_session_expired_retries_only_once() -> None:
    """A second SessionExpiredError after the refresh drops the command — no refresh loop."""
    q = DeviceCommandQueue()
    q.start()
    attempts: list[int] = []
    refreshes: list[int] = []
    critical: list[Exception] = []

    async def always_expired() -> None:
        attempts.append(1)
        raise _session_expired()

    async def on_session_expired(exc: SessionExpiredError) -> bool:
        refreshes.append(1)
        return True

    async def on_critical(exc: Exception) -> None:
        critical.append(exc)

    q.on_session_expired = on_session_expired
    q.on_critical_error = on_critical
    await q.enqueue(always_expired)
    await asyncio.sleep(0.1)

    assert len(attempts) == 2
    assert len(refreshes) == 1
    assert len(critical) == 1
    await q.stop()


async def test_session_expired_without_callback_keeps_previous_behaviour() -> None:
    """Without a wired refresh callback the command is dropped and reported as critical."""
    q = DeviceCommandQueue()
    q.start()
    attempts: list[int] = []
    critical: list[Exception] = []

    async def work() -> None:
        attempts.append(1)
        raise _session_expired()

    async def on_critical(exc: Exception) -> None:
        critical.append(exc)

    q.on_critical_error = on_critical
    await q.enqueue(work)
    await asyncio.sleep(0.1)

    assert len(attempts) == 1
    assert len(critical) == 1
    await q.stop()
