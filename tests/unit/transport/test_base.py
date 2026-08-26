"""Tests for EventBus and Subscription."""
import asyncio
import time
from unittest.mock import patch
import pytest
from pymammotion.device.mqtt_loop import _RATE_LIMITED_BACKOFF
from pymammotion.transport.base import EventBus, Subscription, Transport, TransportType


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
# Rate limiting / send quota — owned by the Transport base class
# (moved here from tests/unit/device/test_handle.py; these exercise Transport,
# not DeviceHandle)
# ---------------------------------------------------------------------------


def _make_concrete_transport() -> Transport:
    """Return a minimal concrete Transport (abstract methods stubbed out)."""

    class _Stub(Transport):
        @property
        def transport_type(self) -> TransportType:
            return TransportType.CLOUD_ALIYUN

        @property
        def is_connected(self) -> bool:
            return True

        @property
        def availability(self):  # type: ignore[override]
            from pymammotion.transport.base import TransportAvailability
            return TransportAvailability.CONNECTED

        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def send(self, payload: bytes, iot_id: str = "") -> None:
            pass

    return _Stub()


def test_transport_not_rate_limited_initially() -> None:
    """A freshly created Transport is not rate-limited."""
    t = _make_concrete_transport()
    assert t.is_rate_limited is False


def test_transport_set_rate_limited_blocks_for_duration() -> None:
    """After set_rate_limited(), is_rate_limited is True until the ban expires."""
    t = _make_concrete_transport()
    t.set_rate_limited()
    assert t.is_rate_limited is True


def test_transport_rate_limit_expires_after_12_hours() -> None:
    """is_rate_limited returns False once _rate_limited_until is in the past."""
    t = _make_concrete_transport()
    t.set_rate_limited()
    assert t.is_rate_limited is True

    # Simulate the 12-hour ban having expired.
    t._rate_limited_until = time.monotonic() - 1  # noqa: SLF001
    assert t.is_rate_limited is False


def test_transport_rate_limit_duration_is_12_hours() -> None:
    """set_rate_limited() sets a ban of exactly _RATE_LIMIT_DURATION seconds."""
    t = _make_concrete_transport()
    before = time.monotonic()
    t.set_rate_limited()
    after = time.monotonic()

    # Ban should expire roughly 12 hours from now.
    expected = 43200.0  # 12 h
    assert before + expected <= t._rate_limited_until <= after + expected  # noqa: SLF001


def test_transport_rate_limit_constant_matches_handle_backoff() -> None:
    """Transport._RATE_LIMIT_DURATION and handle._RATE_LIMITED_BACKOFF must agree."""
    t = _make_concrete_transport()
    assert t._RATE_LIMIT_DURATION == _RATE_LIMITED_BACKOFF  # noqa: SLF001


def test_quota_block_self_clears_when_window_slides_under_limit() -> None:
    """The self-imposed send-quota must release the instant the rolling window drops back
    under the limit — no fixed-duration ban (that is reserved for cloud 429s)."""
    from unittest.mock import patch

    t = _make_concrete_transport()
    limit = t._SEND_LIMIT  # noqa: SLF001
    window = t._SEND_WINDOW  # noqa: SLF001
    clock = {"now": 100_000.0}

    with patch("pymammotion.transport.base.time.monotonic", side_effect=lambda: clock["now"]):
        for _ in range(limit):
            t.record_send()

        # Quota exhausted — blocked — but NO fixed cloud ban was imposed.
        assert t.is_rate_limited is True
        assert t._rate_limited_until == 0.0  # noqa: SLF001 — quota path must not set the cloud timer
        # Release is exactly one window after the oldest send.
        assert t.seconds_until_send_available() == window

        # Slide the window so the oldest send ages out → count drops to limit-1.
        clock["now"] += window + 1.0
        assert t.is_rate_limited is False
        assert t.seconds_until_send_available() == 0.0


def test_seconds_until_send_available_is_max_of_cloud_ban_and_quota() -> None:
    """When both a cloud ban and the quota are active, the longer release time wins."""
    from unittest.mock import patch

    t = _make_concrete_transport()
    clock = {"now": 0.0}

    with patch("pymammotion.transport.base.time.monotonic", side_effect=lambda: clock["now"]):
        t._rate_limited_until = 100.0  # noqa: SLF001 — short cloud ban
        for _ in range(t._SEND_LIMIT):  # noqa: SLF001 — full window, release a whole window away
            t.record_send()

        # Quota release (_SEND_WINDOW) dominates the 100 s cloud ban.
        assert t.seconds_until_send_available() == t._SEND_WINDOW  # noqa: SLF001

        # Clear the quota; the cloud ban now dominates.
        t._send_timestamps.clear()  # noqa: SLF001
        assert t.seconds_until_send_available() == 100.0
        assert t.is_rate_limited is True  # cloud ban still active



def test_is_send_blocked_applies_firmware_exemption() -> None:
    """is_send_blocked() must exempt firmware >= RATE_LIMIT_REMOVED_VERSION."""
    t = _make_concrete_transport()
    t.set_rate_limited()
    assert t.is_rate_limited is True

    # Pre-removal firmware: blocked.
    assert t.is_send_blocked("1.11.5.0") is True
    # Post-removal firmware (e.g. Luba Mini 2.x): exempt.
    assert t.is_send_blocked("2.3.27.16") is False
    # Unknown / unparseable version: fail closed (blocked).
    assert t.is_send_blocked("") is True

    # Not rate-limited at all: never blocked, regardless of firmware.
    t._rate_limited_until = time.monotonic() - 1  # noqa: SLF001
    assert t.is_send_blocked("1.11.5.0") is False
