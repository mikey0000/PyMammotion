"""Tests for ConnectionWatchdog and CircuitBreaker."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.transport.base import AuthError, ReLoginRequiredError, TransportAvailability, TransportType
from pymammotion.transport.watchdog import CircuitBreaker, CircuitState, ConnectionWatchdog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_transport(*, is_connected: bool = False) -> MagicMock:
    """Return a mock that looks like a Transport."""
    transport = MagicMock()
    transport.is_connected = is_connected
    transport.connect = AsyncMock()
    transport.disconnect = AsyncMock()
    transport.send = AsyncMock()
    transport.transport_type = TransportType.BLE
    return transport


def make_token_manager() -> MagicMock:
    """Return a mock that looks like a TokenManager."""
    tm = MagicMock()
    tm.force_refresh = AsyncMock()
    return tm


# ---------------------------------------------------------------------------
# CircuitBreaker unit tests
# ---------------------------------------------------------------------------


def test_circuit_breaker_opens_after_failures() -> None:
    """Recording failure_threshold failures should open the circuit."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
    assert cb.state is CircuitState.CLOSED

    cb.record_failure()
    cb.record_failure()
    assert cb.state is CircuitState.CLOSED  # not yet

    cb.record_failure()
    assert cb.state is CircuitState.OPEN


def test_circuit_breaker_half_open_after_timeout() -> None:
    """An OPEN circuit should transition to HALF_OPEN once recovery_timeout elapses."""
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
    cb.record_failure()
    assert cb.state is CircuitState.OPEN

    # Simulate time passing beyond the recovery timeout
    with patch("pymammotion.transport.watchdog.time") as mock_time:
        mock_time.monotonic.return_value = cb._tripped_at + 11.0  # noqa: SLF001
        result = cb.allow_request()

    assert result is True
    assert cb.state is CircuitState.HALF_OPEN


def test_circuit_breaker_closes_on_success() -> None:
    """Recording success from HALF_OPEN should reset to CLOSED."""
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
    cb.record_failure()
    # Manually set to HALF_OPEN to simulate probe window
    cb._state = CircuitState.HALF_OPEN  # noqa: SLF001

    cb.record_success()

    assert cb.state is CircuitState.CLOSED
    assert cb._failure_count == 0  # noqa: SLF001


# ---------------------------------------------------------------------------
# ConnectionWatchdog unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchdog_reconnects_disconnected_transport() -> None:
    """When the transport is disconnected, the watchdog should call connect()."""
    transport = make_transport(is_connected=False)
    tm = make_token_manager()

    watchdog = ConnectionWatchdog(
        transport,
        tm,
        heartbeat_interval=0.05,
        reconnect_delay=0.0,
        failure_threshold=3,
        recovery_timeout=60.0,
    )

    connect_called = asyncio.Event()
    original_connect = transport.connect

    async def _spy_connect() -> None:
        connect_called.set()
        await original_connect()

    transport.connect = _spy_connect

    watchdog.start()
    try:
        await asyncio.wait_for(connect_called.wait(), timeout=2.0)
    finally:
        await watchdog.stop()

    assert connect_called.is_set(), "transport.connect() was never called"


@pytest.mark.asyncio
async def test_watchdog_auth_error_triggers_force_refresh() -> None:
    """When connect() raises AuthError, force_refresh() should be called."""
    transport = make_transport(is_connected=False)
    tm = make_token_manager()

    # First call raises AuthError; second (after refresh) succeeds.
    call_count = 0

    async def _connect_raises_once() -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise AuthError("bad credentials")

    transport.connect = _connect_raises_once

    refresh_called = asyncio.Event()
    original_refresh = tm.force_refresh

    async def _spy_refresh() -> None:
        refresh_called.set()
        await original_refresh()

    tm.force_refresh = _spy_refresh

    watchdog = ConnectionWatchdog(
        transport,
        tm,
        heartbeat_interval=0.05,
        reconnect_delay=0.0,
        failure_threshold=3,
        recovery_timeout=60.0,
    )

    watchdog.start()
    try:
        await asyncio.wait_for(refresh_called.wait(), timeout=2.0)
    finally:
        await watchdog.stop()

    assert refresh_called.is_set(), "token_manager.force_refresh() was never called"


@pytest.mark.asyncio
async def test_watchdog_stop_cancels_task() -> None:
    """start() followed by stop() should result in a done/cancelled task."""
    transport = make_transport(is_connected=True)  # connected → no connect() called
    tm = make_token_manager()

    watchdog = ConnectionWatchdog(
        transport,
        tm,
        heartbeat_interval=100.0,  # very long so the task just sleeps
        failure_threshold=3,
        recovery_timeout=60.0,
    )

    watchdog.start()
    assert watchdog._task is not None  # noqa: SLF001
    assert not watchdog._task.done()  # noqa: SLF001

    await watchdog.stop()

    assert watchdog._task is None  # noqa: SLF001
