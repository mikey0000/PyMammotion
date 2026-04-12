"""PlanFetchSaga — reads all stored schedule plans from the device."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.data.model.hash_list import Plan
from pymammotion.messaging.saga import Saga
from pymammotion.transport.base import CommandTimeoutError

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
    step_timeout = 3.0

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

        plan_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _collect_plan(msg: Any) -> None:
            try:
                sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                if sub_name == "nav":
                    leaf_name, _ = betterproto2.which_one_of(sub_val, "SubNavMsg")
                    if leaf_name == "todev_planjob_set":
                        plan_queue.put_nowait(msg)
            except Exception:  # noqa: BLE001
                pass

        with broker.subscribe_unsolicited(_collect_plan):
            # Request first plan (index 0)
            cmd = self._command_builder.read_plan(sub_cmd=2, plan_index=0)
            await self._send_command(cmd)

            try:
                response = await asyncio.wait_for(plan_queue.get(), timeout=self.step_timeout)
            except TimeoutError:
                raise CommandTimeoutError("todev_planjob_set", 1) from None

            _, leaf_val = betterproto2.which_one_of(response.nav, "SubNavMsg")
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

                try:
                    response = await asyncio.wait_for(plan_queue.get(), timeout=self.step_timeout)
                except TimeoutError:
                    raise CommandTimeoutError("todev_planjob_set", 1) from None

                _, leaf_val = betterproto2.which_one_of(response.nav, "SubNavMsg")
                plan = Plan.from_dict(leaf_val.to_dict(casing=betterproto2.Casing.SNAKE))
                if plan.plan_id:
                    self.result[plan.plan_id] = plan

        _logger.debug("PlanFetchSaga: fetched %d plan(s)", len(self.result))
