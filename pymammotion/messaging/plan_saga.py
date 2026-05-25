"""PlanFetchSaga — reads all stored schedule plans from the device."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.data.model.hash_list import Plan
from pymammotion.messaging.saga import Saga

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
        self.result: dict[str, Plan] = {}

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Request all plans from the device and collect responses."""
        self.result = {}

        with self._collect_frames(broker, "todev_planjob_set") as plan_queue:
            # Request first plan (index 0)
            cmd = self._command_builder.read_plan(sub_cmd=2, plan_index=0)
            await self._send_command(cmd)

            response = await self._next_frame(plan_queue, "todev_planjob_set")

            _, leaf_val = betterproto2.which_one_of(response.nav, "SubNavMsg")
            assert leaf_val is not None
            plan = Plan.from_dict(leaf_val.to_dict(casing=betterproto2.Casing.SNAKE))

            total = plan.total_plan_num
            if total == 0:
                _logger.debug("PlanFetchSaga: device has no stored plans")
                return

            if plan.plan_id:
                self.result[plan.plan_id] = plan

            # Collect remaining plans one index at a time
            for next_index in range(1, total):
                _logger.debug("PlanFetchSaga: requesting plan %d/%d", next_index + 1, total)
                cmd = self._command_builder.read_plan(sub_cmd=2, plan_index=next_index)
                await self._send_command(cmd)

                response = await self._next_frame(plan_queue, "todev_planjob_set")

                _, leaf_val = betterproto2.which_one_of(response.nav, "SubNavMsg")
                assert leaf_val is not None
                plan = Plan.from_dict(leaf_val.to_dict(casing=betterproto2.Casing.SNAKE))
                if plan.plan_id:
                    self.result[plan.plan_id] = plan

        _logger.debug("PlanFetchSaga: fetched %d plan(s)", len(self.result))
