"""Saga base class for multi-step, restartable device operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import logging
from typing import TYPE_CHECKING

from pymammotion.transport.base import CommandTimeoutError, SagaFailedError, SagaInterruptedError

if TYPE_CHECKING:
    from pymammotion.messaging.broker import DeviceMessageBroker

_logger = logging.getLogger(__name__)


class Saga(ABC):
    """Base class for multi-step, exclusive device operations.

    Sagas represent sequences of request/response exchanges that must run
    atomically from the device's perspective. If a step times out (SagaInterruptedError
    or CommandTimeoutError), the entire saga restarts from _run() because the device
    state machine may have reset.

    Subclasses must:
    - Set class-level `name`
    - Implement `_run(broker)` — partial state may be preserved between runs for resume

    Subclasses may set `self._reset_attempt_counter = True` inside `_run()` when they
    successfully resume from a previously interrupted frame, signalling that the attempt
    counter should be reset so the resumed run gets a fresh set of max_attempts.

    ``total_timeout`` is a hard wall-clock limit on the entire execute() call.  If the
    saga has not completed within that many seconds (across all attempts and resets),
    it raises SagaFailedError regardless of remaining attempts.  Defaults to 5 minutes.
    """

    name: str = "unnamed_saga"
    max_attempts: int = 3
    step_timeout: float = 15.0
    total_timeout: float = 300.0  # 5-minute hard limit across all attempts
    device_name: str = ""
    _reset_attempt_counter: bool = False

    @abstractmethod
    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Execute all saga steps. May be called multiple times on restart.

        Partial state (e.g. partially-fetched frames) may be preserved between calls
        to allow resuming from the interrupted frame rather than restarting from scratch.
        Set self._reset_attempt_counter = True when a successful resume probe indicates
        the device is still responsive at the interrupted frame.
        """

    async def execute(self, broker: DeviceMessageBroker) -> None:
        """Run the saga with automatic restart on interruption.

        Raises:
            SagaFailedError: All restart attempts were exhausted or total_timeout elapsed.

        """
        try:
            await asyncio.wait_for(self._retry_loop(broker), timeout=self.total_timeout)
        except TimeoutError:
            _logger.warning(
                "Saga '%s'[%s] exceeded total timeout of %.0fs — giving up",
                self.name,
                self.device_name,
                self.total_timeout,
            )
            raise SagaFailedError(self.name, self.max_attempts) from None

    async def _retry_loop(self, broker: DeviceMessageBroker) -> None:
        """Inner retry loop — runs until success or max_attempts exhausted."""
        attempt = 0
        while True:
            attempt += 1
            self._reset_attempt_counter = False
            try:
                await self._run(broker)
            except (SagaInterruptedError, CommandTimeoutError) as exc:
                if self._reset_attempt_counter:
                    # The subclass successfully resumed from a partial frame — give it a
                    # fresh set of attempts so the resumed run is not penalised for the
                    # prior interruption.
                    _logger.debug(
                        "Saga '%s'[%s] resumed from partial state — resetting attempt counter",
                        self.name,
                        self.device_name,
                    )
                    attempt = 0
                    await asyncio.sleep(0.5)
                    continue
                if attempt >= self.max_attempts:
                    raise SagaFailedError(self.name, self.max_attempts) from exc
                _logger.warning(
                    "Saga '%s'[%s] interrupted on attempt %d/%d: %s. Restarting in 0.5s.",
                    self.name,
                    self.device_name,
                    attempt,
                    self.max_attempts,
                    exc,
                )
                await asyncio.sleep(0.5)
            else:
                _logger.debug("Saga '%s'[%s] completed on attempt %d", self.name, self.device_name, attempt)
                return
