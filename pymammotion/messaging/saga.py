"""Saga base class for multi-step, restartable device operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import logging

from pymammotion.messaging.broker import CommandTimeoutError, DeviceMessageBroker

_logger = logging.getLogger(__name__)


class SagaInterruptedError(Exception):
    """Raised when a saga step times out after all retries.

    The saga executor catches this and restarts _run() from the beginning.
    Subclasses must clear partial state at the start of each _run() call.
    """


class SagaFailedError(Exception):
    """Raised when a saga exhausts all restart attempts."""

    def __init__(self, name: str, attempts: int) -> None:
        """Initialise with the saga name and total attempts made."""
        self.name = name
        self.attempts = attempts
        super().__init__(f"Saga '{name}' failed after {attempts} attempt(s)")


class Saga(ABC):
    """Base class for multi-step, exclusive device operations.

    Sagas represent sequences of request/response exchanges that must run
    atomically from the device's perspective. If a step times out (SagaInterruptedError
    or CommandTimeoutError), the entire saga restarts from _run() because the device
    state machine may have reset.

    Subclasses must:
    - Set class-level `name`
    - Implement `_run(broker)` — clear any partial state at the start
    """

    name: str = "unnamed_saga"
    max_attempts: int = 3
    step_timeout: float = 15.0

    @abstractmethod
    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Execute all saga steps. May be called multiple times on restart.

        Implementors MUST clear partial state (e.g. incomplete map data)
        at the start of this method so restarts begin clean.
        """

    async def execute(self, broker: DeviceMessageBroker) -> None:
        """Run the saga with automatic restart on interruption.

        Raises:
            SagaFailedError: All restart attempts were exhausted.

        """
        for attempt in range(1, self.max_attempts + 1):
            try:
                await self._run(broker)
            except (SagaInterruptedError, CommandTimeoutError) as exc:
                if attempt >= self.max_attempts:
                    raise SagaFailedError(self.name, self.max_attempts) from exc
                _logger.warning(
                    "Saga '%s' interrupted on attempt %d/%d: %s. Restarting in 1s.",
                    self.name,
                    attempt,
                    self.max_attempts,
                    exc,
                )
                await asyncio.sleep(1.0)
            else:
                _logger.debug("Saga '%s' completed on attempt %d", self.name, attempt)
                return
