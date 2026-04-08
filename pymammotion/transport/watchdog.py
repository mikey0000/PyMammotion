"""ConnectionWatchdog — per-transport health monitor with circuit breaker."""

from __future__ import annotations

import asyncio
import contextlib
from enum import Enum
import logging
import time
from typing import TYPE_CHECKING

from pymammotion.transport.base import AuthError, ReLoginRequiredError, Transport, TransportAvailability, TransportError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.auth.token_manager import TokenManager

_logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """States of the circuit breaker."""

    CLOSED = "closed"  # normal — transport in use
    OPEN = "open"  # tripped — reconnect attempts cooling off
    HALF_OPEN = "half_open"  # probing — one reconnect attempt allowed


class CircuitBreaker:
    """Circuit breaker that trips after repeated failures and recovers after a timeout."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0) -> None:
        """Initialise the circuit breaker with threshold and recovery timeout.

        Args:
            failure_threshold: Number of failures before the circuit opens.
            recovery_timeout: Seconds to wait in OPEN state before probing.

        """
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count: int = 0
        self._state: CircuitState = CircuitState.CLOSED
        self._tripped_at: float = 0.0

    @property
    def state(self) -> CircuitState:
        """Return the current circuit breaker state."""
        return self._state

    def record_success(self) -> None:
        """Reset failure count and transition to CLOSED."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Increment failure count; open the circuit if threshold is reached."""
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            self._tripped_at = time.monotonic()
            _logger.warning(
                "Circuit breaker opened after %d failure(s) (threshold=%d)",
                self._failure_count,
                self._failure_threshold,
            )

    def allow_request(self) -> bool:
        """Return True if a connection attempt should be allowed.

        - CLOSED: always True.
        - OPEN: False unless recovery_timeout has elapsed, then transition to HALF_OPEN and return True.
        - HALF_OPEN: True (one probe attempt).

        """
        if self._state is CircuitState.CLOSED:
            return True
        if self._state is CircuitState.OPEN:
            elapsed = time.monotonic() - self._tripped_at
            if elapsed >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                _logger.info("Circuit breaker moved to HALF_OPEN after %.1f s", elapsed)
                return True
            return False
        # HALF_OPEN: allow one probe
        return True


class ConnectionWatchdog:
    """Monitors a single Transport, reconnects it on failure, trips a circuit breaker.

    When the endpoint is persistently unreachable the circuit breaker opens to
    prevent a reconnect storm.

    Auth errors (AuthError / ReLoginRequiredError) trigger TokenManager.force_refresh()
    instead of tripping the circuit breaker — credentials may just be stale.

    The watchdog runs as a background asyncio task. Call start() after creating
    the transport; call stop() on cleanup.
    """

    def __init__(
        self,
        transport: Transport,
        token_manager: TokenManager,
        *,
        heartbeat_interval: float = 30.0,
        reconnect_delay: float = 5.0,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ) -> None:
        """Create a ConnectionWatchdog for the given transport.

        Args:
            transport: The transport to monitor.
            token_manager: Used to refresh credentials on auth errors.
            heartbeat_interval: Seconds between health-check iterations.
            reconnect_delay: Seconds to wait before retrying a failed connect.
            failure_threshold: Failures before the circuit breaker opens.
            recovery_timeout: Seconds before OPEN circuit moves to HALF_OPEN.

        """
        self._transport = transport
        self._token_manager = token_manager
        self._heartbeat_interval = heartbeat_interval
        self._reconnect_delay = reconnect_delay
        self._circuit = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        self._task: asyncio.Task[None] | None = None
        self._last_availability: TransportAvailability | None = None

        #: Optional callback invoked when transport availability changes.
        self.on_state_change: Callable[[TransportAvailability], Awaitable[None]] | None = None

    def start(self) -> None:
        """Schedule the background monitoring task."""
        if self._task is not None and not self._task.done():
            _logger.debug("ConnectionWatchdog already running — ignoring start()")
            return
        self._task = asyncio.ensure_future(self._run())
        _logger.debug("ConnectionWatchdog started for transport %s", type(self._transport).__name__)

    async def stop(self) -> None:
        """Cancel the background task and wait for it to finish."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        _logger.debug("ConnectionWatchdog stopped")

    async def _run(self) -> None:
        """Run the main monitoring loop until cancelled."""
        while True:
            try:
                if self._transport.is_connected:
                    await self._ping()
                    await self._notify_availability(TransportAvailability.CONNECTED)
                else:
                    await self._notify_availability(TransportAvailability.DISCONNECTED)
                    if self._circuit.allow_request():
                        await self._attempt_connect()
                    else:
                        _logger.debug(
                            "Circuit breaker OPEN — skipping reconnect for transport %s",
                            type(self._transport).__name__,
                        )

                await asyncio.sleep(self._heartbeat_interval)
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("Unexpected error in ConnectionWatchdog._run()")
                await asyncio.sleep(self._heartbeat_interval)

    async def _attempt_connect(self) -> None:
        """Try to connect the transport, handling auth errors and circuit breaker updates."""
        await self._notify_availability(TransportAvailability.CONNECTING)
        try:
            await self._transport.connect()
            self._circuit.record_success()
            _logger.info("Transport %s connected successfully", type(self._transport).__name__)
        except ReLoginRequiredError:
            _logger.warning("Re-login required for transport %s — notifying caller", type(self._transport).__name__)
            # Cannot recover autonomously; let the circuit stay as-is and surface to caller.
            raise
        except AuthError:
            _logger.warning(
                "Auth error on transport %s — forcing token refresh and retrying once",
                type(self._transport).__name__,
            )
            try:
                await self._token_manager.force_refresh(self._transport.transport_type)
                await self._transport.connect()
                self._circuit.record_success()
                _logger.info("Transport %s connected after token refresh", type(self._transport).__name__)
            except AuthError:
                _logger.error(
                    "Auth error persisted after token refresh on transport %s",
                    type(self._transport).__name__,
                )
                self._circuit.record_failure()
            except TransportError:
                self._circuit.record_failure()
        except TransportError:
            _logger.warning(
                "Transport error on %s — recording failure in circuit breaker",
                type(self._transport).__name__,
            )
            self._circuit.record_failure()

    async def _ping(self) -> None:
        """No-op heartbeat placeholder. Subclasses may override to send a real ping.

        If the ping fails, call self._circuit.record_failure() and optionally
        disconnect the transport so the next loop iteration attempts reconnect.
        """

    async def _notify_availability(self, availability: TransportAvailability) -> None:
        """Fire on_state_change if the availability has changed."""
        if availability == self._last_availability:
            return
        self._last_availability = availability
        if self.on_state_change is not None:
            try:
                await self.on_state_change(availability)
            except Exception:
                _logger.exception("on_state_change callback raised an unhandled exception")
