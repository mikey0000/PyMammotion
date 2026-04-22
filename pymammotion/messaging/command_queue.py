"""Priority command queue with exclusive slots for saga operations."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from enum import IntEnum
import logging
from typing import TYPE_CHECKING

from pymammotion.transport import TransportError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.messaging.broker import DeviceMessageBroker
    from pymammotion.messaging.saga import Saga

_logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """Command execution priority. Lower value = higher priority."""

    EMERGENCY = 0  # estop, return-to-dock — never skipped, bypasses saga block
    EXCLUSIVE = 1  # sagas (map/plan fetch) — holds processor until complete
    NORMAL = 2  # regular HA commands — waits for exclusive slot
    BACKGROUND = 3  # low-urgency polling — waits for exclusive slot


@dataclass(order=True)
class _QueueItem:
    priority: int
    sequence: int
    work: Callable[[], Awaitable[None]] = field(compare=False)
    skip_if_saga_active: bool = field(compare=False, default=False)


class DeviceCommandQueue:
    """Priority command queue with exclusive slots for sagas.

    EXCLUSIVE items (sagas) hold the queue processor until the saga finishes.
    NORMAL/BACKGROUND items marked skip_if_saga_active=True are silently
    dropped while a saga is running — used by HA coordinator update() calls
    to prevent accumulation during long map/plan fetches.
    EMERGENCY items always execute and are never skipped.
    """

    def __init__(self, device_name: str = "") -> None:
        """Initialise queue, exclusive-slot event, and sequence counter."""
        self._queue: asyncio.PriorityQueue[_QueueItem] = asyncio.PriorityQueue()
        self._exclusive_active = asyncio.Event()
        self._exclusive_active.set()  # set = free (no saga running)
        self._seq = 0
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._current_work_task: asyncio.Task[None] | None = None
        self._device_name = device_name
        #: Called on critical errors (AuthError, SagaFailedError) so DeviceHandle can propagate them.
        self.on_critical_error: Callable[[Exception], Awaitable[None]] | None = None
        #: Fired when an exclusive saga is about to start.  Clients use this to pause the
        #: rapid-report subscription so it doesn't fight the saga for the MQTT channel.
        self.on_saga_start: Callable[[], Awaitable[None]] | None = None
        #: Fired once the saga returns (success or failure).  Pair with ``on_saga_start``
        #: to restart the subscription after the saga yields the channel.
        self.on_saga_end: Callable[[], Awaitable[None]] | None = None

    @property
    def is_saga_active(self) -> bool:
        """True when an exclusive saga is currently running."""
        return not self._exclusive_active.is_set()

    def start(self) -> None:
        """Start the background queue processor task."""
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.get_running_loop().create_task(self._process())

    async def stop(self) -> None:
        """Stop the queue processor and release any held exclusive lock."""
        self._running = False
        self._exclusive_active.set()  # release any waiters
        if self._current_work_task is not None and not self._current_work_task.done():
            self._current_work_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._current_work_task
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None

    async def enqueue(
        self,
        work: Callable[[], Awaitable[None]],
        priority: Priority = Priority.NORMAL,
        *,
        skip_if_saga_active: bool = False,
    ) -> None:
        """Add work to the queue.

        If skip_if_saga_active=True and a saga is active, the item is dropped
        silently. This is correct for HA coordinator polls — they must not
        accumulate during a multi-minute map sync.
        """
        # EMERGENCY is never skipped or blocked
        if priority == Priority.EMERGENCY:
            skip_if_saga_active = False

        if skip_if_saga_active and self.is_saga_active and priority > Priority.EXCLUSIVE:
            return

        self._seq += 1
        item = _QueueItem(
            priority=int(priority),
            sequence=self._seq,
            work=work,
            skip_if_saga_active=skip_if_saga_active,
        )
        await self._queue.put(item)

    async def enqueue_saga(
        self,
        saga: Saga,
        broker: DeviceMessageBroker,
        on_complete: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Enqueue a saga as an exclusive blocking operation."""

        async def _run() -> None:
            self._exclusive_active.clear()
            if self.on_saga_start is not None:
                try:
                    await self.on_saga_start()
                except Exception:
                    _logger.exception("on_saga_start callback failed for saga '%s'", saga.name)
            try:
                saga.device_name = self._device_name
                await saga.execute(broker)
            finally:
                self._exclusive_active.set()
                if self.on_saga_end is not None:
                    try:
                        await self.on_saga_end()
                    except Exception:
                        _logger.exception("on_saga_end callback failed for saga '%s'", saga.name)
            if on_complete is not None:
                try:
                    await on_complete()
                except Exception:
                    _logger.exception("on_complete callback failed for saga '%s'", saga.name)

        await self.enqueue(_run, priority=Priority.EXCLUSIVE)

    async def _process(self) -> None:
        """Queue processor loop — runs as an asyncio background task."""
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=0.4)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                # Non-emergency items yield to an active exclusive op
                if item.priority > Priority.EXCLUSIVE:
                    await self._exclusive_active.wait()

                # Re-check skip condition after waiting
                if item.skip_if_saga_active and self.is_saga_active and item.priority > Priority.EXCLUSIVE:
                    continue

                from pymammotion.aliyun.exceptions import GatewayTimeoutException

                _gateway_timeout_max = 3
                for _attempt in range(1, _gateway_timeout_max + 1):
                    self._current_work_task = asyncio.get_running_loop().create_task(
                        item.work()  # type: ignore[arg-type]
                    )
                    try:
                        await self._current_work_task
                        break  # success — exit retry loop
                    except GatewayTimeoutException:
                        if _attempt < _gateway_timeout_max:
                            _logger.warning(
                                "DeviceCommandQueue[%s]: gateway timeout (attempt %d/%d) — retrying in 1s",
                                self._device_name,
                                _attempt,
                                _gateway_timeout_max,
                            )
                            await asyncio.sleep(1.0)
                        else:
                            _logger.warning(
                                "DeviceCommandQueue[%s]: gateway timeout after %d attempts — dropping command",
                                self._device_name,
                                _attempt,
                            )
                    finally:
                        self._current_work_task = None
            except asyncio.CancelledError:
                break
            except Exception as exc:
                from pymammotion.aliyun.exceptions import DeviceOfflineException
                from pymammotion.transport.base import AuthError, NoTransportAvailableError, SagaFailedError

                if isinstance(
                    exc, (AuthError, SagaFailedError, DeviceOfflineException, NoTransportAvailableError, TransportError)
                ):
                    _logger.warning("DeviceCommandQueue[%s]: %s", self._device_name, exc)
                else:
                    _logger.exception("DeviceCommandQueue[%s]: unhandled error in work item", self._device_name)
                if self.on_critical_error is not None and isinstance(exc, (AuthError, SagaFailedError)):
                    try:
                        await self.on_critical_error(exc)
                    except Exception:
                        _logger.exception("on_critical_error callback failed")
            finally:
                with contextlib.suppress(ValueError):
                    self._queue.task_done()
