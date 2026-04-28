"""EdgeMappingSaga — collects edge/boundary points streamed by the device during edgewise mapping."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.data.model.hash_list import CommDataCouple, EdgePoints
from pymammotion.messaging.saga import Saga
from pymammotion.transport.base import CommandTimeoutError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.messaging.broker import DeviceMessageBroker

_logger = logging.getLogger(__name__)


class EdgeMappingSaga(Saga):
    """Collect edge/boundary point frames pushed by the device during live border walking.

    Workflow (mirrors APK MACarDataManager case TOAPP_EDGE_POINTS):
      1. (Optional) Send ``along_border()`` to tell the device to start edge mapping.
         Skip with ``skip_start=True`` if edge mapping is already in progress.
      2. Subscribe to unsolicited ``toapp_edge_points`` frames.
      3. For each frame, send a ``toapp_edge_points_ack`` back so the device
         continues sending (mirrors APK ``responseEdgewiseMapping()``).
      4. Collect frames until ``current_frame >= total_frame`` for the hash.

    ``result`` is a dict[hash, EdgePoints] on success, empty dict until then.
    """

    name = "edge_mapping"
    max_attempts = 3
    step_timeout = 60.0  # edge mapping can take a while on large properties

    def __init__(
        self,
        command_builder: Any,
        send_command: Callable[[bytes], Awaitable[None]],
        *,
        skip_start: bool = False,
    ) -> None:
        """Initialise the saga.

        Args:
            command_builder: Navigation command builder (provides ``along_border()``
                             and ``response_edgewise_mapping()``).
            send_command: Async callable that transmits raw bytes to the device.
            skip_start: When True, skip sending ``along_border()`` — useful when
                        the device has already been told to start.

        """
        self._command_builder = command_builder
        self._send_command = send_command
        self._skip_start = skip_start
        self.result: dict[int, EdgePoints] = {}

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Execute the edge mapping collection. Clears partial state at the start."""
        self.result = {}
        collected: dict[int, EdgePoints] = {}  # hash → EdgePoints

        frame_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _collect_frame(msg: Any) -> None:
            if self.extract_nav_frame(msg, "toapp_edge_points") is not None:
                frame_queue.put_nowait(msg)

        with broker.subscribe_unsolicited(_collect_frame):
            if not self._skip_start:
                _logger.debug("EdgeMappingSaga: sending along_border to start edge mapping")
                cmd = self._command_builder.along_border()
                await self._send_command(cmd)

            # Collect frames — the device streams them until current_frame >= total_frame
            _expected_field = "toapp_edge_points"
            while True:
                try:
                    frame_msg = await asyncio.wait_for(frame_queue.get(), timeout=self.step_timeout)
                except TimeoutError:
                    raise CommandTimeoutError(_expected_field, 1) from None

                _, nav_val = betterproto2.which_one_of(frame_msg, "LubaSubMsg")
                edge_msg = nav_val.toapp_edge_points
                hash_key: int = edge_msg.hash

                # Accumulate into collected EdgePoints
                existing = collected.get(hash_key)
                if existing is None:
                    existing = EdgePoints(
                        hash=hash_key,
                        action=edge_msg.action,
                        type=edge_msg.type,
                        total_frame=edge_msg.total_frame,
                    )
                    collected[hash_key] = existing
                else:
                    existing.total_frame = edge_msg.total_frame

                points = [CommDataCouple(x=p.x, y=p.y) for p in edge_msg.data_couple]
                existing.frames[edge_msg.current_frame] = points

                _logger.debug(
                    "EdgeMappingSaga: frame %d/%d  hash=%d  points=%d",
                    edge_msg.current_frame,
                    edge_msg.total_frame,
                    hash_key,
                    len(points),
                )

                # Ack this frame so the device sends the next one
                ack_cmd = self._command_builder.response_edgewise_mapping(
                    action=edge_msg.action,
                    hash_num=hash_key,
                    result=0,
                    type=edge_msg.type,
                    total_frame=edge_msg.total_frame,
                    current_frame=edge_msg.current_frame,
                )
                await self._send_command(ack_cmd)

                # Done when all frames for this hash are received
                if edge_msg.current_frame >= edge_msg.total_frame and existing.is_complete:
                    _logger.debug(
                        "EdgeMappingSaga: complete — hash=%d  %d frames  %d total points",
                        hash_key,
                        len(existing.frames),
                        len(existing.all_points),
                    )
                    break

        self.result = collected
