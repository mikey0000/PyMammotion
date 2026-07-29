"""PlanFetchSaga — reads all stored schedule plans from the device."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.data.model.hash_list import Plan
from pymammotion.messaging.saga import Saga
from pymammotion.messaging.transfers import indexed_fetch

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.messaging.broker import DeviceMessageBroker

_logger = logging.getLogger(__name__)


class PlanFetchSaga(Saga):
    """Reads all stored schedule plans from the device.

    Sends read_plan(sub_cmd=2, plan_index=0) then collects every
    todev_planjob_set response until total_plan_num plans are received.

    The device sends plans one at a time.  We subscribe to unsolicited
    messages before the first send so no plan frame is lost if the device
    responds faster than we can register the next request.

    result is a dict[plan_id, Plan] set on success, empty dict until then.
    """

    name = "plan_fetch"
    #: One 10 s shot, matching the APK's uniform request timeout (CommandManager
    #: safeFetchCallbackFun default 10000L, no retry).  2 s was under a cloud
    #: round-trip plus the device's ~1 s frame retransmit.
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
        self.result: dict[str, Plan] = {}

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Request all plans from the device and collect responses."""
        self.result = {}

        with self._collect_frames(broker, "todev_planjob_set") as plan_queue:

            async def _request(index: int) -> None:
                await self._send_command(self._command_builder.read_plan(sub_cmd=2, plan_index=index))

            async for wire in indexed_fetch(
                plan_queue,
                field="todev_planjob_set",
                request=_request,
                total_of=lambda f: Plan.from_dict(f.to_dict(casing=betterproto2.Casing.SNAKE)).total_plan_num,
                timeout=self.step_timeout,
            ):
                plan = Plan.from_dict(wire.to_dict(casing=betterproto2.Casing.SNAKE))
                if plan.plan_id:
                    self.result[plan.plan_id] = plan

        _logger.debug("PlanFetchSaga: fetched %d plan(s)", len(self.result))
