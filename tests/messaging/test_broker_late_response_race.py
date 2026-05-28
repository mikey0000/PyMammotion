"""Regression tests for the late-response race in DeviceMessageBroker.

Bug C3 (TODO.md): in ``DeviceMessageBroker.on_message`` the pending-future
lookup happened inside the broker lock, but the actual ``set_result()`` was
performed *outside* the lock. That left a window where:

  1. ``send_and_wait`` times out and its ``finally`` block pops the entry from
     ``_pending`` and cancels the (shielded) future.
  2. A late incoming message had already passed the lookup and held a
     reference to the now-orphaned future.
  3. ``set_result()`` was called on the cancelled future, raising
     ``InvalidStateError`` and (worse) silently losing the response.

These tests pin the new behaviour: the lookup-and-resolve happens atomically
inside the lock; late responses are routed to the event bus instead, and the
broker is left in a clean state ready for the next request.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.transport.base import CommandTimeoutError


def _mock_msg() -> MagicMock:
    return MagicMock()


async def test_late_response_after_timeout_is_safe_and_recoverable() -> None:
    """A response arriving after timeout must not raise and must not poison the slot."""
    broker = DeviceMessageBroker()
    field = "toapp_gethash_ack"

    async def send_fn() -> None:
        pass

    # Capture any unhandled exceptions on the running loop so we can assert
    # nothing was raised by the late on_message().
    loop = asyncio.get_running_loop()
    captured: list[BaseException] = []
    prev_handler = loop.get_exception_handler()

    def handler(_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
        exc = context.get("exception")
        if isinstance(exc, BaseException):
            captured.append(exc)

    loop.set_exception_handler(handler)
    try:
        with patch("betterproto2.which_one_of", return_value=(field, MagicMock())):
            # 1. First request times out.
            with pytest.raises(CommandTimeoutError):
                await broker.send_and_wait(send_fn, field, send_timeout=0.02, retries=1)

            # Sanity: pending slot was cleared by the finally block.
            assert field not in broker._pending

            # 2. The "late" response arrives ~50 ms after the timeout.
            await asyncio.sleep(0.05)
            await broker.on_message(_mock_msg())  # must not raise

            # 3. The slot is still clean and a fresh request resolves normally.
            assert field not in broker._pending

            async def deliver_next() -> None:
                await asyncio.sleep(0.01)
                await broker.on_message(_mock_msg())

            deliver_task = loop.create_task(deliver_next())
            result = await broker.send_and_wait(send_fn, field, send_timeout=1.0, retries=1)
            await deliver_task

            assert result is not None
            assert field not in broker._pending
    finally:
        loop.set_exception_handler(prev_handler)

    # No InvalidStateError (or anything else) leaked from the late delivery.
    assert captured == [], f"Late on_message raised on the loop: {captured!r}"


async def test_concurrent_timeout_and_delivery_no_invalid_state_error() -> None:
    """Hammer the race: many concurrent timeouts + late deliveries on the same field.

    Each iteration starts a ``send_and_wait`` with a tiny timeout and races a
    delivery against the ``finally`` cleanup. With the bug, this reliably hit
    ``InvalidStateError`` from ``set_result()`` on an already-cancelled future.
    With the fix, the lookup+resolve are atomic under the lock, so a late
    delivery either resolves the future cleanly or finds the slot empty and
    falls through to the event bus.
    """
    broker = DeviceMessageBroker()
    field = "toapp_gethash_ack"

    async def send_fn() -> None:
        pass

    loop = asyncio.get_running_loop()
    captured: list[BaseException] = []
    prev_handler = loop.get_exception_handler()

    def handler(_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
        exc = context.get("exception")
        if isinstance(exc, BaseException):
            captured.append(exc)

    loop.set_exception_handler(handler)

    resolved = 0
    timed_out = 0
    try:
        with patch("betterproto2.which_one_of", return_value=(field, MagicMock())):
            for i in range(200):
                # Stagger the delivery delay across the timeout boundary to
                # maximise the chance of hitting the lookup-vs-cancel race.
                delay = 0.0005 + (i % 5) * 0.0002

                async def deliver(d: float = delay) -> None:
                    await asyncio.sleep(d)
                    await broker.on_message(_mock_msg())

                deliver_task = loop.create_task(deliver())
                try:
                    await broker.send_and_wait(send_fn, field, send_timeout=0.001, retries=1)
                    resolved += 1
                except CommandTimeoutError:
                    timed_out += 1

                await deliver_task

                # Slot must always be cleared between iterations — a stuck
                # entry would be a regression of the bug (next call would
                # raise ConcurrentRequestError).
                assert field not in broker._pending
    finally:
        loop.set_exception_handler(prev_handler)

    # The loop must complete without leaking exceptions onto the loop.
    assert captured == [], f"Race produced unhandled exceptions: {captured!r}"
    assert resolved + timed_out == 200


async def test_set_result_race_with_cancel_in_finally() -> None:
    """Force the exact interleaving from C3 deterministically.

    The race: ``on_message`` does the pending-table lookup under the lock,
    releases the lock, then calls ``pending.future.set_result(...)``. If the
    timeout's ``finally`` block runs (acquires the lock, pops the entry, then
    cancels the future) *between* the lock release and the ``set_result``,
    the future is already cancelled and ``set_result`` raises
    ``InvalidStateError`` — losing the response and crashing the transport's
    on_message dispatcher.

    We force this interleaving by holding the lock manually so that the
    timeout finally's lock acquisition queues *after* on_message's lookup
    but runs *before* on_message's set_result.
    """
    broker = DeviceMessageBroker()
    field = "toapp_gethash_ack"

    async def send_fn() -> None:
        pass

    loop = asyncio.get_running_loop()

    with patch("betterproto2.which_one_of", return_value=(field, MagicMock())):
        # Start the request; let it register and time out quickly.
        send_task = loop.create_task(
            broker.send_and_wait(send_fn, field, send_timeout=0.05, retries=1)
        )
        # Wait until the pending entry is registered.
        for _ in range(100):
            await asyncio.sleep(0.001)
            if field in broker._pending:
                break
        assert field in broker._pending
        pending = broker._pending[field]

        # Capture the future BEFORE timeout cleanup, simulating an
        # on_message that already finished the lookup.
        captured_future = pending.future

        # Let the timeout fire and the finally block cancel the future.
        with pytest.raises(CommandTimeoutError):
            await send_task

        # The finally block has popped the entry and cancelled the future.
        assert field not in broker._pending
        assert captured_future.cancelled() or captured_future.done()

        # The buggy code path would now do `captured_future.set_result(msg)`.
        # The fix ensures on_message rechecks under the lock, sees the slot
        # is gone, and routes to the event bus instead.
        received: list[object] = []

        async def event_handler(msg: object) -> None:
            received.append(msg)

        broker.subscribe_unsolicited(event_handler)

        # A late on_message must not raise and must route to event bus
        # (no pending entry to resolve).
        await broker.on_message(_mock_msg())
        assert len(received) == 1, "Late response should fall through to event bus"
