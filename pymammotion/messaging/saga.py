"""Saga base class for multi-step, restartable device operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from pymammotion.aliyun.exceptions import GatewayTimeoutException
from pymammotion.data.model.region_data import RegionData
from pymammotion.messaging import transfers
from pymammotion.transport.base import CommandTimeoutError, SagaFailedError, SagaInterruptedError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

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

    Subclasses that can bank partial work should override `progress()` to report it.
    Any advance resets the attempt budget, so `max_attempts` caps *consecutive
    fruitless* attempts rather than total runs — see `_retry_loop`.

    ``total_timeout`` is a hard wall-clock limit on the entire execute() call.  If the
    saga has not completed within that many seconds (across all attempts and resets),
    it raises SagaFailedError regardless of remaining attempts.  Defaults to 5 minutes.
    """

    name: str = "unnamed_saga"
    #: Consecutive attempts allowed without any progress.  Progress resets this.
    max_attempts: int = 3
    step_timeout: float = 15.0
    total_timeout: float = 300.0  # 5-minute hard limit across all attempts
    device_name: str = ""

    @staticmethod
    def extract_frame(
        msg: Any,
        expected: str | tuple[str, ...] | frozenset[str],
        *,
        envelope: str = "nav",
    ) -> tuple[str, Any] | None:
        """Return ``(frame_name, frame_value)`` for a matching frame, else ``None``.

        Delegates to :func:`pymammotion.messaging.transfers.extract_frame` so the
        transfer helpers and the sagas share one implementation; exposed here
        because call sites read better as ``self.extract_frame(...)``.
        """
        return transfers.extract_frame(msg, expected, envelope=envelope)

    @staticmethod
    def extract_nav_frame(
        msg: Any,
        expected: str | tuple[str, ...] | frozenset[str],
    ) -> tuple[str, Any] | None:
        """Return ``(frame_name, frame_value)`` for a matching ``nav`` frame, else ``None``.

        Thin alias for :meth:`extract_frame` with the default envelope; kept
        because most sagas only ever speak ``nav`` and reading ``extract_nav_frame``
        at the call site is clearer than passing the default explicitly.
        """
        return transfers.extract_frame(msg, expected)

    @contextlib.contextmanager
    def _collect_frames(
        self,
        broker: DeviceMessageBroker,
        field: str | tuple[str, ...],
        predicate: Callable[[Any], bool] | None = None,
        *,
        envelope: str = "nav",
    ) -> Iterator[asyncio.Queue[Any]]:
        """Subscribe to unsolicited frames matching *field* and queue them.

        Yields an ``asyncio.Queue`` fed with every message whose *envelope* leaf is
        in *field* and, when *predicate* is given, whose frame value satisfies it.
        Subscribing before the caller's first send avoids the race where the device
        replies before a handler is registered; the subscription is removed on
        context exit (RAII).

        *envelope* selects the ``LubaSubMsg`` member — ``"nav"`` for mower traffic,
        ``"ctrl"`` for Spino.  Both leaf shapes are handled by
        :meth:`extract_frame`, so a device speaking a different envelope needs an
        entry in :data:`transfers.LEAF_GROUPS`, not a subclass override of this method.
        """
        if envelope not in transfers.LEAF_GROUPS:
            msg = f"unknown envelope {envelope!r} — add it to transfers.LEAF_GROUPS"
            raise ValueError(msg)

        queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _collect(msg: Any) -> None:
            frame = self.extract_frame(msg, field, envelope=envelope)
            if frame is not None and (predicate is None or predicate(frame[1])):
                queue.put_nowait(msg)

        with broker.subscribe_unsolicited(_collect):
            yield queue

    async def _next_frame(self, queue: asyncio.Queue[Any], field: str, current_frame: int = 1) -> Any:
        """Await the next queued frame, or raise ``CommandTimeoutError`` after ``step_timeout``.

        Wraps the ``asyncio.wait_for(queue.get(), step_timeout)`` →
        ``CommandTimeoutError`` pattern every ack-driven saga step shares.
        """
        try:
            return await asyncio.wait_for(queue.get(), timeout=self.step_timeout)
        except TimeoutError:
            raise CommandTimeoutError(field, current_frame) from None

    @staticmethod
    def _region_data(frame: Any) -> RegionData:
        """Build a ``RegionData`` echo-ack for a received comm-data / region frame.

        The device waits for this echo (``get_regional_data``) before sending the
        next frame; it mirrors back action/type/hash/total/current/sub_cmd.
        """
        region_data = RegionData()
        region_data.total_frame = frame.total_frame
        region_data.current_frame = frame.current_frame
        region_data.sub_cmd = frame.sub_cmd
        region_data.type = frame.type
        region_data.hash = frame.hash
        region_data.action = frame.action
        return region_data

    @abstractmethod
    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Execute all saga steps. May be called multiple times on restart.

        Partial state (e.g. partially-fetched frames) may be preserved between calls
        to allow resuming from the interrupted frame rather than restarting from scratch.
        Report that banked work from :meth:`progress` so an interrupted-but-advancing
        run earns another attempt.
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

    async def progress(self) -> Any:
        """Return an opaque marker of how much work this saga has banked.

        Compared (by inequality) between attempts: any change means the last run
        advanced before it was interrupted, so it earns a fresh attempt budget.
        Return ``None`` — the default — for sagas with nothing meaningful to
        measure; they simply cap out at :attr:`max_attempts`.

        This replaces the manual ``_reset_attempt_counter`` flag that map- and
        mow-path fetches used to set by hand.  Deriving it from state rather than
        having ``_run`` announce it removes the failure mode that forced
        MowPathSaga's one-shot ``_budget_reset_granted`` guard: a flag set on
        every run made ``max_attempts`` meaningless, whereas a value that stops
        changing when the device stalls does not.
        """
        return None

    async def _retry_loop(self, broker: DeviceMessageBroker) -> None:
        """Re-enter ``_run`` while it keeps making progress; give up when it stops.

        Whole-run restart is the wrong granularity for this protocol: the device
        retransmits unacked frames, so an interruption at frame 47 of 50 is a blip,
        not a reason to discard 46 banked frames.  Attempts are therefore only
        counted while :meth:`progress` is *not* advancing.

        ``GatewayTimeoutException`` is handled here as an interruption rather than
        propagated.  If we let it escape, ``DeviceCommandQueue._process`` would
        catch it and replay the entire saga work-item up to 3x — multiplying every
        cloud invoke the saga has already made.

        ``total_timeout`` (enforced by :meth:`execute`) is the backstop that bounds
        a saga whose progress advances indefinitely.
        """
        attempt = 0
        last_progress = await self.progress()
        while True:
            attempt += 1
            try:
                await self._run(broker)
            except (SagaInterruptedError, CommandTimeoutError, GatewayTimeoutException) as exc:
                current = await self.progress()
                if current is not None and current != last_progress:
                    _logger.debug(
                        "Saga '%s'[%s] advanced before interruption (%s -> %s) — refreshing budget",
                        self.name,
                        self.device_name,
                        last_progress,
                        current,
                    )
                    last_progress = current
                    attempt = 0
                    await asyncio.sleep(0.5)
                    continue
                if attempt >= self.max_attempts:
                    raise SagaFailedError(self.name, self.max_attempts) from exc
                _logger.warning(
                    "Saga '%s'[%s] interrupted with no progress on attempt %d/%d: %s. Restarting in 0.5s.",
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
