"""Tests for EventBus and Subscription."""
import asyncio
import time
from unittest.mock import patch
import pytest
from pymammotion.transport.base import EventBus, Subscription, Transport, TransportAvailability, TransportType


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


# ---------------------------------------------------------------------------
# The Transport base holds only what every link kind has.  Send quota and auth
# flags live on CloudTransport (tests/unit/transport/test_cloud.py); BLE gating
# lives on BLETransport (tests/unit/transport/test_ble.py).
# ---------------------------------------------------------------------------


def _make_concrete_transport() -> Transport:
    """Return a minimal concrete Transport (abstract methods stubbed out)."""

    class _Stub(Transport):
        @property
        def transport_type(self) -> TransportType:
            return TransportType.BLE

        @property
        def is_connected(self) -> bool:
            return True

        @property
        def availability(self) -> TransportAvailability:
            return TransportAvailability.CONNECTED

        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def send(self, payload: bytes, iot_id: str = "", firmware_version: str = "1.0.0.0") -> None:
            pass

    return _Stub()


def test_base_is_usable_defaults_to_true() -> None:
    """A link with no extra preconditions is usable whenever it is registered.

    The default used to be computed from the cloud auth flags, so BLE had to override
    it to say anything at all.
    """
    assert _make_concrete_transport().is_usable is True


def test_base_transport_has_no_cloud_surface() -> None:
    """The quota and broker-auth API must not be reachable from a non-cloud transport.

    This is the regression guard for the split: re-adding any of these to ``Transport``
    puts them back on ``BLETransport``, which uses none of them.
    """
    t = _make_concrete_transport()
    for name in (
        "is_rate_limited",
        "set_rate_limited",
        "is_send_blocked",
        "record_send",
        "sends_in_window",
        "seconds_until_send_available",
        "version_is_rate_limited",
        "mark_auth_failed",
        "mark_unrecoverable_auth_failure",
        "is_unrecoverable_auth_failure",
        "on_auth_failure",
        "on_fatal_auth_error",
        "on_device_status",
        "on_device_event",
        "on_device_properties",
        "on_device_mammotion_properties",
    ):
        assert not hasattr(t, name), f"Transport still carries the cloud-only member {name!r}"


def test_records_inbound_and_outbound_activity() -> None:
    """Both timestamps are shared: every transport kind reports activity for poll cadence."""
    t = _make_concrete_transport()
    assert t.last_received_monotonic == 0.0
    assert t.last_send_monotonic == 0.0
    t._mark_received()  # noqa: SLF001
    assert t.last_received_monotonic > 0.0


def test_error_window_counts_recent_errors() -> None:
    t = _make_concrete_transport()
    assert t.errors_in_window() == 0
    t.record_error()
    t.record_error()
    assert t.errors_in_window() == 2
