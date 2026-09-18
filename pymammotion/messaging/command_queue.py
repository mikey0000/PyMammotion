"""Priority command queue with exclusive slots for saga operations."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from enum import IntEnum
import logging
import time
from typing import TYPE_CHECKING

from pymammotion.aliyun.exceptions import (
    DeviceOfflineException,
    DeviceUnboundException,
    GatewayTimeoutException,
    TooManyRequestsException,
)
from pymammotion.transport import TransportError
from pymammotion.transport.base import AuthError, NoTransportAvailableError, SagaFailedError, TransportRateLimitedError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.messaging.broker import DeviceMessageBroker
    from pymammotion.messaging.saga import Saga

_logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """Command execution priority. Lower value = higher priority.

    The two highest levels never enter this queue at all — ``MammotionClient``
    dispatches them on the caller's own task (see :attr:`is_direct`).  That is the
    only way to get true preemption: the processor is strictly sequential, so an
    item enqueued while an EXCLUSIVE saga is mid-flight would still have to wait
    for that saga's ``work()`` to return no matter how it was ranked.
    """

    EMERGENCY = 0  # e-stop — direct send, outranks everything
    USER = 1  # human-initiated action — direct send, never queued or dropped
    EXCLUSIVE = 2  # sagas (map/plan fetch) — holds processor until complete
    NORMAL = 3  # regular HA commands — waits for exclusive slot
    BACKGROUND = 4  # low-urgency polling — waits for exclusive slot

    @property
    def is_direct(self) -> bool:
        """True for the priorities that bypass this queue entirely."""
        return self <= Priority.USER


#: Commands that have not been dispatched within this window are silently dropped.
_COMMAND_TTL = 120.0  # 2 minutes


#: Attempts allowed for a work item that keeps hitting a cloud gateway timeout.
_GATEWAY_TIMEOUT_MAX = 3


async def execute_command(
    work: Callable[[], Awaitable[None]],
    *,
    device_name: str,
    on_critical_error: Callable[[Exception], Awaitable[None]] | None = None,
    reraise: bool = False,
) -> None:
    """Run *work* with the gateway-timeout retry and the standard error buckets.

    The single home for "should this exception be treated as expected?".  Both the
    queue processor and ``MammotionClient``'s direct send path go through here, so a
    user-initiated command is classified, logged and escalated exactly as a queued
    one is.

    *reraise* is the only difference between the two callers: the queue swallows,
    because there is nobody left to tell, while a direct send propagates so the host
    learns the command did not land.  ``asyncio.CancelledError`` always propagates.
    """
    for attempt in range(1, _GATEWAY_TIMEOUT_MAX + 1):
        try:
            await work()
            return
        except GatewayTimeoutException:
            if attempt < _GATEWAY_TIMEOUT_MAX:
                _logger.warning(
                    "DeviceCommandQueue[%s]: gateway timeout (attempt %d/%d) — retrying",
                    device_name,
                    attempt,
                    _GATEWAY_TIMEOUT_MAX,
                )
                continue
            _logger.warning(
                "DeviceCommandQueue[%s]: gateway timeout after %d attempts — dropping command",
                device_name,
                attempt,
            )
            if reraise:
                raise
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Expected during transport churn — quiet by default.  Recovery
            # is automatic: mqtt_reported_offline clears on inbound frames,
            # BLE rearms via the availability listener.  No retry loop or
            # caller-side gate needed; just don't pollute the log.
            if isinstance(exc, (NoTransportAvailableError, DeviceOfflineException, DeviceUnboundException)):
                _logger.debug("DeviceCommandQueue[%s]: %s", device_name, exc)
            elif isinstance(
                exc,
                (
                    AuthError,  # includes ReLoginRequiredError
                    SagaFailedError,
                    TooManyRequestsException,
                    TransportRateLimitedError,
                    TransportError,
                ),
            ):
                _logger.warning("DeviceCommandQueue[%s]: %s", device_name, exc)
            else:
                _logger.exception("DeviceCommandQueue[%s]: unhandled error in work item", device_name)
            if on_critical_error is not None and isinstance(exc, (AuthError, SagaFailedError)):
                try:
                    await on_critical_error(exc)
                except Exception:
                    _logger.exception("on_critical_error callback failed")
            if reraise:
                raise
            return


@dataclass(order=True)
class _QueueItem:
    priority: int
    sequence: int
    work: Callable[[], Awaitable[None]] = field(compare=False)
    skip_if_saga_active: bool = field(compare=False, default=False)
    dedup_key: str | None = field(compare=False, default=None)
    enqueued_at: float = field(compare=False, default_factory=time.monotonic)


class DeviceCommandQueue:
    """Priority command queue with exclusive slots for sagas.

    EXCLUSIVE items (sagas) hold the queue processor until the saga finishes.
    NORMAL/BACKGROUND items marked skip_if_saga_active=True are silently
    dropped while a saga is running — used by HA coordinator update() calls
    to prevent accumulation during long map/plan fetches.

    Only the queued priorities reach here.  EMERGENCY and USER are dispatched
    directly by ``MammotionClient`` and :meth:`enqueue` rejects them.
    """

    def __init__(self, device_name: str = "") -> None:
        """Initialise queue, exclusive-slot event, and sequence counter."""
        self._queue: asyncio.PriorityQueue[_QueueItem] = asyncio.PriorityQueue()
        self._exclusive_active = asyncio.Event()
        self._exclusive_active.set()  # set = free (no saga running)
        # Gate cleared while the active MQTT transport is reconnecting (CONNECTING state)
        # and no BLE fallback is available.  Queued items wait here so we don't
        # dispatch commands whose responses we cannot receive (MQTT subscription inactive).
        # DeviceHandle manages the gate via pause_for_reconnect() / resume_after_reconnect().
        self._transport_gate: asyncio.Event = asyncio.Event()
        self._transport_gate.set()  # set = open (no reconnection in progress)
        self._seq = 0
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._device_name = device_name
        self._pending_dedup_keys: set[str] = set()
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

    def pause_for_reconnect(self) -> None:
        """Block command dispatch while the MQTT transport is reconnecting.

        Called by DeviceHandle when the active MQTT transport transitions to
        CONNECTING state and no BLE fallback is available.  Commands accumulate
        in the queue but are not dispatched until resume_after_reconnect() is
        called (transport becomes CONNECTED, or BLE connects as a fallback).
        Direct-send commands never touch this gate — they don't use the queue.
        """
        self._transport_gate.clear()

    def resume_after_reconnect(self) -> None:
        """Unblock command dispatch after transport reconnection completes."""
        self._transport_gate.set()

    async def stop(self) -> None:
        """Stop the queue processor and release any held exclusive lock."""
        self._running = False
        self._exclusive_active.set()  # release any waiters
        self._transport_gate.set()  # release any gate-blocked waiters
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._task = None

    async def enqueue(
        self,
        work: Callable[[], Awaitable[None]],
        priority: Priority = Priority.NORMAL,
        *,
        skip_if_saga_active: bool = False,
        dedup_key: str | None = None,
    ) -> None:
        """Add work to the queue.

        If skip_if_saga_active=True and a saga is active, the item is dropped
        silently. This is correct for HA coordinator polls — they must not
        accumulate during a multi-minute map sync.

        If dedup_key is given and an item with that key is already pending,
        the new item is silently dropped. Use for idempotent commands like
        RPT_START that should only be queued once at a time.

        Raises:
            ValueError: if *priority* is a direct-send level.  EMERGENCY and USER
                are dispatched by ``MammotionClient`` on the caller's task; queueing
                one would reintroduce exactly the waiting it exists to avoid.

        """
        if priority.is_direct:
            msg = f"{priority.name} is a direct-send priority and must not be queued"
            raise ValueError(msg)

        if skip_if_saga_active and self.is_saga_active and priority > Priority.EXCLUSIVE:
            return

        if dedup_key is not None and dedup_key in self._pending_dedup_keys:
            return

        self._seq += 1
        item = _QueueItem(
            priority=int(priority),
            sequence=self._seq,
            work=work,
            skip_if_saga_active=skip_if_saga_active,
            dedup_key=dedup_key,
        )
        if dedup_key is not None:
            self._pending_dedup_keys.add(dedup_key)
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
            saga_exception: BaseException | None = None
            try:
                if self.on_saga_start is not None:
                    try:
                        await self.on_saga_start()
                    except Exception:
                        _logger.exception("on_saga_start callback failed for saga '%s'", saga.name)
                saga.device_name = self._device_name
                try:
                    await saga.execute(broker)
                except asyncio.CancelledError:
                    saga_exception = asyncio.CancelledError()
                    raise
                except Exception as exc:
                    saga_exception = exc
                    # GatewayTimeoutException and DeviceOfflineException are
                    # expected operational errors handled by the _process retry
                    # loop — logging them here as "unhandled" is misleading noise.
                    if not isinstance(
                        exc, (GatewayTimeoutException, DeviceOfflineException, NoTransportAvailableError)
                    ):
                        _logger.exception("Saga '%s' raised an unhandled exception", saga.name)
                    raise
            finally:
                # Always release the exclusive lock and clear the work-task pointer,
                # even on cancellation or unhandled exception — otherwise the queue deadlocks.
                self._exclusive_active.set()
                if self.on_saga_end is not None:
                    try:
                        await self.on_saga_end()
                    except Exception:
                        _logger.exception("on_saga_end callback failed for saga '%s'", saga.name)
            if saga_exception is None and on_complete is not None:
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
                # Release dedup slot as soon as item is dequeued
                if item.dedup_key is not None:
                    self._pending_dedup_keys.discard(item.dedup_key)

                # Drop commands that have waited longer than _COMMAND_TTL without being
                # dispatched.  Checked here — before any lock/gate waits — so stale
                # commands don't execute after a long reconnect or saga pause.
                # EXCLUSIVE sagas are exempt: a queued map/plan sync routinely waits
                # out a multi-minute saga ahead of it, and silently dropping it means
                # on_complete never fires and nothing upstream learns the sync
                # didn't happen.
                if item.priority > Priority.EXCLUSIVE:
                    age = time.monotonic() - item.enqueued_at
                    if age > _COMMAND_TTL:
                        _logger.debug(
                            "DeviceCommandQueue[%s]: command expired after %.0fs — dropping",
                            self._device_name,
                            age,
                        )
                        continue

                # Queued items yield to an active exclusive op
                if item.priority > Priority.EXCLUSIVE:
                    await self._exclusive_active.wait()

                # Re-check skip condition after waiting
                if item.skip_if_saga_active and self.is_saga_active and item.priority > Priority.EXCLUSIVE:
                    continue

                # Hold here while the MQTT transport is reconnecting, so we don't
                # dispatch commands whose responses can't be received because the
                # MQTT subscription isn't active yet.  Nothing bypasses this gate:
                # the priorities that used to (EMERGENCY) no longer reach the queue.
                await self._transport_gate.wait()

                await execute_command(
                    item.work,
                    device_name=self._device_name,
                    on_critical_error=self.on_critical_error,
                )
            except asyncio.CancelledError:
                # stop() sets _running=False before cancelling the processor task,
                # so CancelledError here always means we are shutting down.
                break
            except Exception:
                # execute_command classifies everything the work item raises, so
                # reaching here means the loop machinery itself failed.  Log and keep
                # going: a dead processor silently stops every command for this device.
                _logger.exception("DeviceCommandQueue[%s]: queue processor error", self._device_name)
            finally:
                with contextlib.suppress(ValueError):
                    self._queue.task_done()
