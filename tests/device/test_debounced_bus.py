"""Tests for _DebouncedBus in DeviceHandle."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.device.handle import _DebouncedBus
from pymammotion.state.device_state import DeviceAvailability, DeviceConnectionState, DeviceSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_snapshot(seq: int = 1, battery: int = 80) -> DeviceSnapshot:
    """Build a minimal DeviceSnapshot for testing."""
    device = MagicMock()
    device.online = True
    device.enabled = True
    device.report_data.dev.battery_val = battery
    device.report_data.dev.sys_status = "idle"
    device.report_data.work.knife_height = 50
    from datetime import UTC, datetime

    return DeviceSnapshot(
        sequence=seq,
        timestamp=datetime.now(tz=UTC),
        connection_state=DeviceConnectionState.CONNECTED,
        online=True,
        enabled=True,
        battery_level=battery,
        mowing_activity="idle",
        blade_height=50,
        raw=device,
    )


# ---------------------------------------------------------------------------
# Test 1: debounce_interval=0 — immediate emission, no coalescing
# ---------------------------------------------------------------------------


async def test_no_debounce_emits_immediately() -> None:
    """With debounce_interval=0, each emit() calls handlers immediately."""
    bus = _DebouncedBus(debounce_interval=0.0)
    handler = AsyncMock()
    bus.subscribe(handler)

    snap1 = make_snapshot(seq=1)
    snap2 = make_snapshot(seq=2)
    snap3 = make_snapshot(seq=3)

    await bus.emit(snap1)
    await bus.emit(snap2)
    await bus.emit(snap3)

    # All 3 snapshots emitted, handler called 3 times
    assert handler.await_count == 3
    # Each call got the corresponding snapshot
    assert handler.call_args_list[0].args[0] is snap1
    assert handler.call_args_list[1].args[0] is snap2
    assert handler.call_args_list[2].args[0] is snap3


# ---------------------------------------------------------------------------
# Test 2: debounce_interval>0 — rapid emits coalesce to the last snapshot
# ---------------------------------------------------------------------------


async def test_debounce_coalesces_rapid_emits() -> None:
    """3 rapid emits with debounce_interval=0.05 should coalesce to 1 handler call."""
    bus = _DebouncedBus(debounce_interval=0.05, max_debounce_wait=2.0)
    handler = AsyncMock()
    bus.subscribe(handler)

    snap1 = make_snapshot(seq=1, battery=10)
    snap2 = make_snapshot(seq=2, battery=20)
    snap3 = make_snapshot(seq=3, battery=30)

    # Emit 3 times rapidly (no await between)
    await bus.emit(snap1)
    await bus.emit(snap2)
    await bus.emit(snap3)

    # Handler should NOT have been called yet
    assert handler.await_count == 0

    # Wait for debounce to fire
    await asyncio.sleep(0.15)

    # Only 1 call with the last snapshot
    assert handler.await_count == 1
    assert handler.call_args_list[0].args[0] is snap3


# ---------------------------------------------------------------------------
# Test 3: max_debounce_wait forces emission during continuous rapid events
# ---------------------------------------------------------------------------


async def test_max_debounce_wait_forces_emission() -> None:
    """max_debounce_wait shortens the debounce interval during a long burst.

    With debounce_interval=0.5 and max_debounce_wait=0.08:
    - First emit starts the burst clock.
    - After 0.06s, the second emit finds remaining_max=0.02s, so the
      debounce task sleeps only 0.02s instead of 0.5s.
    - Handler fires well before the full 0.5s debounce_interval.
    """
    bus = _DebouncedBus(debounce_interval=0.5, max_debounce_wait=0.08)
    handler = AsyncMock()
    bus.subscribe(handler)

    snap1 = make_snapshot(seq=1, battery=10)
    snap2 = make_snapshot(seq=2, battery=20)

    # First emit: starts the burst
    await bus.emit(snap1)
    assert handler.await_count == 0

    # Wait long enough that remaining_max is very small (< debounce_interval)
    await asyncio.sleep(0.06)

    # Second emit: remaining_max ≈ 0.02s < 0.5s (debounce_interval)
    # → debounce task sleeps only ~0.02s, not 0.5s
    await bus.emit(snap2)

    # The task should fire within 0.05s (0.02s sleep + margin)
    await asyncio.sleep(0.06)

    # Handler should have been called exactly once with the last snapshot
    assert handler.await_count == 1
    assert handler.call_args_list[0].args[0] is snap2


# ---------------------------------------------------------------------------
# Test 4: stop() cancels pending task without calling handler
# ---------------------------------------------------------------------------


async def test_stop_cancels_pending_task_without_calling_handler() -> None:
    """stop() cancels the pending debounce task; handler must NOT be called."""
    bus = _DebouncedBus(debounce_interval=1.0, max_debounce_wait=5.0)
    handler = AsyncMock()
    bus.subscribe(handler)

    snap = make_snapshot(seq=1)
    await bus.emit(snap)

    # Task is pending but hasn't fired (1s sleep)
    assert bus._debounce_task is not None
    assert not bus._debounce_task.done()

    await bus.stop()

    # After stop, the task is done (cancelled) and handler was NOT called
    assert handler.await_count == 0
    assert bus._pending_snapshot is None
