"""MowPathSaga — plan a route and collect the mowing path from the device."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.data.model import GenerateRouteInformation
from pymammotion.data.model.hash_list import HashList, MowPath
from pymammotion.messaging.saga import Saga
from pymammotion.transport.base import CommandTimeoutError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.messaging.broker import DeviceMessageBroker

_logger = logging.getLogger(__name__)


class MowPathSaga(Saga):
    """Plan a mowing route and collect the resulting cover-path frames.

    Execution order:
      1. Send generate_route_information (bidire_reqconver_path, sub_cmd=0)
         and wait for the device's confirmation response.
      2. Send get_line_info_list with the zone hashes from the confirmation
         and a timestamp-based transaction_id.
      3. Collect all cover_path_upload frames until none are missing.

    result is a dict[transaction_id, dict[frame_num, MowPath]] on success,
    empty dict until then.
    """

    name = "mow_path_fetch"
    max_attempts = 3
    step_timeout = 30.0

    def __init__(
        self,
        command_builder: Any,
        send_command: Callable[[bytes], Awaitable[None]],
        zone_hashs: list[int],
        route_info: GenerateRouteInformation | None = None,
    ) -> None:
        """Initialise the saga.

        Args:
            command_builder: Navigation command builder (MammotionCommand or similar).
            send_command: Async callable that transmits raw bytes to the device.
            zone_hashs: Area/zone hash IDs to mow (from HashList.area.keys()).
            route_info: Optional pre-built GenerateRouteInformation; defaults are
                        used if not supplied.

        """
        self._command_builder = command_builder
        self._send_command = send_command
        self._zone_hashs = zone_hashs
        self._route_info = route_info
        self.result: dict[int, dict[int, MowPath]] = {}

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Execute all saga steps. Clears partial state at the start."""
        self.result = {}
        hash_list = HashList()

        route_info = self._route_info or GenerateRouteInformation(one_hashs=self._zone_hashs)

        # ------------------------------------------------------------------
        # Step 1: Send generate_route_information, wait for confirmation.
        # Subscribe before sending to avoid race with a fast response.
        # ------------------------------------------------------------------
        _logger.debug("MowPathSaga: sending generate_route_information for %d zone(s)", len(self._zone_hashs))
        route_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _collect_route(msg: Any) -> None:
            try:
                sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                if sub_name == "nav":
                    leaf_name, _ = betterproto2.which_one_of(sub_val, "SubNavMsg")
                    if leaf_name == "bidire_reqconver_path":
                        route_queue.put_nowait(msg)
            except Exception:  # noqa: BLE001
                pass

        with broker.subscribe_unsolicited(_collect_route):
            cmd = self._command_builder.generate_route_information(route_info)
            await self._send_command(cmd)

            try:
                response = await asyncio.wait_for(route_queue.get(), timeout=self.step_timeout)
            except TimeoutError:
                raise CommandTimeoutError("bidire_reqconver_path", 1) from None

            _, route_val = betterproto2.which_one_of(response.nav, "SubNavMsg")
            # Use the zone_hashs echoed by the device; fall back to ours if empty
            confirmed_zone_hashs: list[int] = list(route_val.zone_hashs) or self._zone_hashs

        _logger.debug(
            "MowPathSaga: route confirmed — sub_cmd=%d  zone_hashs=%s",
            route_val.sub_cmd,
            confirmed_zone_hashs,
        )

        # ------------------------------------------------------------------
        # Step 2 & 3: Request the cover path and collect all frames.
        # ------------------------------------------------------------------
        transaction_id = int(time.time() * 1000)
        _logger.debug("MowPathSaga: requesting cover path — transaction_id=%d", transaction_id)

        path_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _collect_path(msg: Any) -> None:
            try:
                sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                if sub_name == "nav":
                    leaf_name, _ = betterproto2.which_one_of(sub_val, "SubNavMsg")
                    if leaf_name == "cover_path_upload":
                        path_queue.put_nowait(msg)
            except Exception:  # noqa: BLE001
                pass

        with broker.subscribe_unsolicited(_collect_path):
            cmd = self._command_builder.get_line_info_list(confirmed_zone_hashs, transaction_id)
            await self._send_command(cmd)

            # Collect frames until all present (device sends them sequentially)
            while True:
                try:
                    frame_response = await asyncio.wait_for(path_queue.get(), timeout=self.step_timeout)
                except TimeoutError:
                    raise CommandTimeoutError("cover_path_upload", 1) from None

                _, path_val = betterproto2.which_one_of(frame_response.nav, "SubNavMsg")
                mow_path = MowPath.from_dict(path_val.to_dict(casing=betterproto2.Casing.SNAKE))
                hash_list.update_mow_path(mow_path)
                _logger.debug(
                    "MowPathSaga: got cover_path_upload frame %d/%d  tx=%d",
                    mow_path.current_frame,
                    mow_path.total_frame,
                    mow_path.transaction_id,
                )

                if not hash_list.find_missing_mow_path_frames():
                    break

        self.result = hash_list.current_mow_path
        total_packets = sum(len(frames) for frames in self.result.values())
        _logger.debug("MowPathSaga: complete — %d transaction(s)  %d total frame(s)", len(self.result), total_packets)
