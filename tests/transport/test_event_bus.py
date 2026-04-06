"""Tests for EventBus and Subscription."""
import asyncio
import pytest
from pymammotion.transport.base import EventBus, Subscription


async def test_subscribe_and_emit() -> None:
    bus: EventBus[int] = EventBus()
    received: list[int] = []

    async def handler(val: int) -> None:
        received.append(val)

    bus.subscribe(handler)
    await bus.emit(42)
    assert received == [42]


async def test_multiple_subscribers_all_called() -> None:
    bus: EventBus[str] = EventBus()
    log: list[str] = []

    async def h1(v: str) -> None:
        log.append(f"h1:{v}")

    async def h2(v: str) -> None:
        log.append(f"h2:{v}")

    bus.subscribe(h1)
    bus.subscribe(h2)
    await bus.emit("x")
    assert "h1:x" in log
    assert "h2:x" in log


async def test_handler_exception_does_not_abort_others() -> None:
    bus: EventBus[int] = EventBus()
    called: list[str] = []

    async def bad(v: int) -> None:
        raise ValueError("boom")

    async def good(v: int) -> None:
        called.append("good")

    bus.subscribe(bad)
    bus.subscribe(good)
    await bus.emit(1)  # should not raise
    assert called == ["good"]


async def test_cancel_removes_handler() -> None:
    bus: EventBus[int] = EventBus()
    called: list[int] = []

    async def handler(v: int) -> None:
        called.append(v)

    sub = bus.subscribe(handler)
    sub.cancel()
    await bus.emit(99)
    assert called == []


async def test_context_manager_cancels_on_exit() -> None:
    bus: EventBus[int] = EventBus()
    called: list[int] = []

    async def handler(v: int) -> None:
        called.append(v)

    with bus.subscribe(handler) as sub:
        await bus.emit(1)
    await bus.emit(2)
    assert called == [1]


async def test_unique_subscription_ids() -> None:
    bus: EventBus[int] = EventBus()

    async def noop(v: int) -> None:
        pass

    sub1 = bus.subscribe(noop)
    sub2 = bus.subscribe(noop)
    assert sub1._sub_id != sub2._sub_id


async def test_len_reflects_active_subscribers() -> None:
    bus: EventBus[int] = EventBus()

    async def noop(v: int) -> None:
        pass

    assert len(bus) == 0
    sub = bus.subscribe(noop)
    assert len(bus) == 1
    sub.cancel()
    assert len(bus) == 0


async def test_unsubscribe_during_emit_is_safe() -> None:
    bus: EventBus[int] = EventBus()
    sub_ref: list[Subscription] = []
    called: list[int] = []

    async def self_removing(v: int) -> None:
        called.append(v)
        sub_ref[0].cancel()

    sub = bus.subscribe(self_removing)
    sub_ref.append(sub)
    await bus.emit(7)  # must not raise
    assert called == [7]
    await bus.emit(8)  # handler removed, no second call
    assert called == [7]
