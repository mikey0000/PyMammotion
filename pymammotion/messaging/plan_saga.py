"""PlanFetchSaga — sends a mow plan and waits for device acknowledgement."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pymammotion.messaging.saga import Saga

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.messaging.broker import DeviceMessageBroker

_logger = logging.getLogger(__name__)


class PlanFetchSaga(Saga):
    """Sends a Plan to the device and waits for acknowledgement.

    Used when starting a mow job or updating a plan. If the ack times out,
    the saga restarts (resends the plan).
    """

    name = "plan_fetch"
    max_attempts = 3
    step_timeout = 15.0

    def __init__(
        self,
        plan: Any,  # Plan dataclass from hash_list.py
        command_builder: Any,
        send_command: Callable[[bytes], Awaitable[None]],
    ) -> None:
        """Initialise the saga with a plan, command builder, and transport callable."""
        self._plan = plan
        self._command_builder = command_builder
        self._send_command = send_command

        # Set to True once ack is received
        self.success: bool = False

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Send the plan and wait for the device to acknowledge it."""
        # Clear state at the start of each attempt
        self.success = False

        _logger.debug("PlanFetchSaga: sending plan %s", getattr(self._plan, "plan_id", "<unknown>"))
        cmd = self._command_builder.send_plan(self._plan)
        await broker.send_and_wait(
            send_fn=lambda: self._send_command(cmd),
            expected_field="todev_planjob_set",
            send_timeout=self.step_timeout,
        )
        self.success = True
        _logger.debug("PlanFetchSaga: plan acknowledged")
