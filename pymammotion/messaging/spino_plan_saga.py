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

import logging
from typing import TYPE_CHECKING, Any

from pymammotion.messaging.saga import Saga
from pymammotion.messaging.transfers import indexed_fetch

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.messaging.broker import DeviceMessageBroker
    from pymammotion.proto import PlanJobSet

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
    #: One 10 s shot, matching the APK's uniform request timeout — see PlanFetchSaga.
    max_attempts = 1
    step_timeout = 10.0

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

        with self._collect_frames(broker, "plan_job_set", envelope="ctrl") as plan_queue:

            async def _request(index: int) -> None:
                await self._send_command(self._command_builder.read_spino_plan(plan_index=index))

            async for wire in indexed_fetch(
                plan_queue,
                field="plan_job_set",
                envelope="ctrl",
                request=_request,
                total_of=lambda f: f.totalplannum,
                timeout=self.step_timeout,
            ):
                if wire.jobid:
                    self.result[wire.jobid] = wire

        _logger.debug("SpinoPlanFetchSaga: fetched %d plan(s)", len(self.result))
