"""CommonDataSaga — fetches a single multi-frame toapp_get_commondata_ack response."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.data.model.hash_list import CommDataCouple
from pymammotion.messaging.saga import Saga
from pymammotion.transport.base import CommandTimeoutError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.messaging.broker import DeviceMessageBroker

_logger = logging.getLogger(__name__)


class CommonDataSaga(Saga):
    """Fetch a multi-frame ``toapp_get_commondata_ack`` response from the device.

    Covers any ``NavGetCommData`` request that returns CommonData frames —
    for example the live dynamics line (``action=8, type=18``) or the area
    transfer data (``action=8, type=3``).

    The saga:

    1. Subscribes to unsolicited ``toapp_get_commondata_ack`` messages filtered
       by the requested ``type``, then sends the request command.
    2. Accumulates incoming frames (each carries a ``data_couple`` list of
       ``CommDataCouple`` x/y points) into a per-frame dict.
    3. Stops once ``current_frame == total_frame`` for all collected frames.
    4. Assembles frames in ascending frame-number order into ``self.result``.

    Frame 1 of a dynamics-line response signals a new mowing session on the
    device; the caller (``MammotionClient.get_dynamics_line``) replaces the
    stored ``device.map.dynamics_line`` list with the assembled result.

    Attributes:
        result: Assembled list of ``CommDataCouple`` points from all frames,
                in frame order.  Empty until the saga completes successfully.

    """

    name = "common_data_fetch"
    max_attempts = 3
    step_timeout = 5.0

    def __init__(
        self,
        command_builder: Any,
        send_command: Callable[[bytes], Awaitable[None]],
        *,
        action: int,
        type: int,
        hash_num: int = 0,
    ) -> None:
        """Initialise the saga.

        Args:
            command_builder: Navigation command builder that exposes
                             ``get_common_data(action, type, hash_num)``.
            send_command:    Async callable that transmits raw bytes to the device.
            action:          NavGetCommData ``action`` field (e.g. 8 = fetch/sync).
            type:            ``PathType`` value identifying the requested data
                             (e.g. ``PathType.DYNAMICS_LINE = 18``).
            hash_num:        Optional hash ID.  Pass 0 (default) for requests
                             that are not hash-specific (dynamics line, area
                             transfer).

        """
        self._command_builder = command_builder
        self._send_command = send_command
        self._action = action
        self._type = type
        self._hash_num = hash_num
        self.result: list[CommDataCouple] = []

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Execute the saga.  Clears partial state at the start of each attempt."""
        self.result = []
        frames: dict[int, list[CommDataCouple]] = {}
        total_frame: int | None = None

        frame_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _collect(msg: Any) -> None:
            frame = self.extract_nav_frame(msg, "toapp_get_commondata_ack")
            if frame is not None and frame[1].type == self._type:
                frame_queue.put_nowait(msg)

        with broker.subscribe_unsolicited(_collect):
            cmd = self._command_builder.get_common_data(action=self._action, type=self._type, hash_num=self._hash_num)
            await self._send_command(cmd)

            while True:
                try:
                    msg = await asyncio.wait_for(frame_queue.get(), timeout=self.step_timeout)
                except TimeoutError:
                    raise CommandTimeoutError("toapp_get_commondata_ack", 1) from None

                _, nav_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                ack = nav_val.toapp_get_commondata_ack
                total_frame = ack.total_frame
                frames[ack.current_frame] = [CommDataCouple(x=p.x, y=p.y) for p in ack.data_couple]

                _logger.debug(
                    "CommonDataSaga(action=%d type=%d): frame %d/%d  points=%d",
                    self._action,
                    self._type,
                    ack.current_frame,
                    total_frame,
                    len(frames[ack.current_frame]),
                )

                if len(frames) >= total_frame:
                    break

        # Assemble frames in ascending order
        for i in range(1, (total_frame or 0) + 1):
            self.result.extend(frames.get(i, []))

        _logger.debug(
            "CommonDataSaga(action=%d type=%d): complete — %d total points across %d frame(s)",
            self._action,
            self._type,
            len(self.result),
            total_frame or 0,
        )
