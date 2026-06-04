"""Tests for DeviceMessageBroker."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.transport.base import CommandTimeoutError, ConcurrentRequestError


def make_mock_message(field_name: str) -> MagicMock:
    msg = MagicMock()
    return msg


async def test_solicited_response_resolves_future() -> None:
    broker = DeviceMessageBroker()
    received: list[object] = []

    async def send_fn() -> None:
        pass

    with patch("betterproto2.which_one_of", return_value=("toapp_gethash_ack", MagicMock())):

        async def deliver() -> None:
            await asyncio.sleep(0.01)
            await broker.on_message(make_mock_message("toapp_gethash_ack"))

        task = asyncio.get_running_loop().create_task(deliver())
        result = await broker.send_and_wait(send_fn, "toapp_gethash_ack", send_timeout=1.0, retries=1)
        assert result is not None
        await task


async def test_unsolicited_goes_to_event_bus() -> None:
    broker = DeviceMessageBroker()
    received: list[object] = []

    async def handler(msg: object) -> None:
        received.append(msg)

    broker.subscribe_unsolicited(handler)
    msg = make_mock_message("some_event")

    with patch("betterproto2.which_one_of", return_value=("some_event", MagicMock())):
        await broker.on_message(msg)

    assert len(received) == 1


async def test_timeout_retries_correct_count() -> None:
    broker = DeviceMessageBroker()
    send_count = 0

    async def send_fn() -> None:
        nonlocal send_count
        send_count += 1

    with patch("betterproto2.which_one_of", return_value=("never_field", MagicMock())):
        with pytest.raises(CommandTimeoutError):
            await broker.send_and_wait(send_fn, "missing_field", send_timeout=0.05, retries=3)

    assert send_count == 3


async def test_concurrent_request_raises() -> None:
    broker = DeviceMessageBroker()

    async def slow_send() -> None:
        await asyncio.sleep(5)

    task = asyncio.get_running_loop().create_task(
        broker.send_and_wait(slow_send, "toapp_gethash_ack", send_timeout=0.01, retries=1)
    )
    await asyncio.sleep(0.001)  # let first request register

    with pytest.raises(ConcurrentRequestError):
        await broker.send_and_wait(slow_send, "toapp_gethash_ack", send_timeout=0.01, retries=1)

    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, CommandTimeoutError):
        pass


async def test_pending_cleared_after_timeout() -> None:
    broker = DeviceMessageBroker()

    async def send_fn() -> None:
        pass

    with pytest.raises(CommandTimeoutError):
        await broker.send_and_wait(send_fn, "some_field", send_timeout=0.05, retries=1)

    assert "some_field" not in broker._pending


async def test_close_cancels_pending_futures() -> None:
    broker = DeviceMessageBroker()

    async def send_fn() -> None:
        pass

    loop = asyncio.get_running_loop()
    future: asyncio.Future[object] = loop.create_future()
    from pymammotion.messaging.broker import PendingRequest
    import time

    broker._pending["test_field"] = PendingRequest(
        expected_field="test_field",
        future=future,
        sent_at=time.monotonic(),
        resend=send_fn,
    )

    await broker.close()
    assert future.cancelled()
    assert len(broker._pending) == 0
