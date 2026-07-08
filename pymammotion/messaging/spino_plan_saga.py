"""SpinoPlanFetchSaga — reads all stored cleaning plans from a Spino device.

Mirror of :class:`pymammotion.messaging.plan_saga.PlanFetchSaga` for the
Spino pool cleaner.  Differences from the mower path:

* Spino plans arrive via ``LubaMsg.ctrl.plan_job_set`` (not
  ``LubaMsg.nav.todev_planjob_set``).
* Plans are keyed by 64-bit ``jobid`` (not by a 21-char string id).
* ``enable`` on the wire is inverted; this saga delegates to
  :class:`PoolStateReducer` for that conversion via the reducer pipeline,
  so the saga itself stores raw wire dicts.

See ``docs/tasks_and_schedules.md`` § 3 for the fetch protocol.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.messaging.saga import Saga
from pymammotion.proto import PlanJobSet

if TYPE_CHECKING:
    from collections.abc import Iterator
    from collections.abc import Awaitable, Callable

    from pymammotion.messaging.broker import DeviceMessageBroker

_logger = logging.getLogger(__name__)


class SpinoPlanFetchSaga(Saga):
    """Reads all stored Spino cleaning plans from the device.

    Sends ``read_spino_plan(plan_index=0)`` then collects every
    ``plan_job_set`` response until ``totalplannum`` plans are received.

    The saga subscribes to unsolicited messages BEFORE the first send so
    no plan frame is lost if the device responds faster than we can
    register the next request — same race fix as ``PlanFetchSaga``.

    ``result`` is a ``dict[int, PlanJobSet]`` keyed by ``jobid``, set on
    success.  The reducer also applies each frame to
    ``PoolCleanerDevice.plans`` independently, so callers typically read
    from there rather than this attribute.
    """

    name = "spino_plan_fetch"
    max_attempts = 3
    step_timeout = 2.0

    def __init__(
        self,
        command_builder: Any,
        send_command: Callable[[bytes], Awaitable[None]],
    ) -> None:
        """Initialise the saga with a command builder and transport callable."""
        self._command_builder = command_builder
        self._send_command = send_command
        self.result: dict[int, PlanJobSet] = {}

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Request all Spino plans from the device and collect responses."""
        self.result = {}

        with self._collect_frames(broker, "plan_job_set") as plan_queue:
            cmd = self._command_builder.read_spino_plan(plan_index=0)
            await self._send_command(cmd)

            response = await self._next_frame(plan_queue, "plan_job_set")
            wire = self._extract_plan_job_set(response)

            total = wire.totalplannum
            if total == 0:
                _logger.debug("SpinoPlanFetchSaga: device has no stored plans")
                return

            if wire.jobid:
                self.result[wire.jobid] = wire

            for next_index in range(1, total):
                _logger.debug(
                    "SpinoPlanFetchSaga: requesting plan %d/%d",
                    next_index + 1,
                    total,
                )
                cmd = self._command_builder.read_spino_plan(plan_index=next_index)
                await self._send_command(cmd)

                response = await self._next_frame(plan_queue, "plan_job_set")
                wire = self._extract_plan_job_set(response)
                if wire.jobid:
                    self.result[wire.jobid] = wire

        _logger.debug("SpinoPlanFetchSaga: fetched %d plan(s)", len(self.result))

    @contextlib.contextmanager
    def _collect_frames(  # type: ignore[override]
        self,
        broker: Any,
        field: str | tuple[str, ...],
        predicate: Any = None,
    ) -> Iterator[asyncio.Queue[Any]]:
        """Spino-specific frame collector — subscribes on ``LubaMsg.ctrl.plan_job_set``.

        The base class's ``_collect_frames`` is hard-wired to the ``nav``
        envelope; Spino plans arrive via ``ctrl`` (``SpinoCtrl``), so we
        override to dispatch on that group instead. Same RAII shape as the
        base — subscription is released on context exit.
        """
        queue: asyncio.Queue[Any] = asyncio.Queue()
        expected = (field,) if isinstance(field, str) else field

        async def _collect(msg: Any) -> None:
            try:
                sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                if sub_name != "ctrl" or sub_val is None:
                    return
                # SpinoCtrl currently has only one populated child:
                # plan_job_set.  We could grow this to a oneof later — for
                # now an optional-field check is enough.
                if "plan_job_set" not in expected:
                    return
                if sub_val.plan_job_set is None:
                    return
            except Exception:  # noqa: BLE001 — malformed frames are noise
                return
            if predicate is None or predicate(sub_val.plan_job_set):
                queue.put_nowait(msg)

        with broker.subscribe_unsolicited(_collect):
            yield queue

    @staticmethod
    def _extract_plan_job_set(luba_msg: Any) -> PlanJobSet:
        """Pull the ``plan_job_set`` payload out of a LubaMsg frame.

        Mirror of :meth:`_collect_frames` — once the queue delivers a
        ``LubaMsg`` we know carries a ``ctrl.plan_job_set``, this helper
        descends back through the envelope so the saga's main loop can
        use the inner ``PlanJobSet`` directly.
        """
        _, ctrl = betterproto2.which_one_of(luba_msg, "LubaSubMsg")
        assert ctrl is not None and ctrl.plan_job_set is not None
        return ctrl.plan_job_set
