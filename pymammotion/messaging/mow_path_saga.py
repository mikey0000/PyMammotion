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

    Execution order (mirrors APK MACommandHelper / HashDataManager flow):
      1. Send generate_route_information (bidire_reqconver_path, sub_cmd=0)
         and wait for the device's sub_cmd=0 confirmation.
      2. Send get_all_boundary_hash_list(sub_cmd=3) to request the list of
         generated line/path hashes from the device.
      3. Wait for toapp_gethash_ack (sub_cmd=3) carrying the line hash list.
         Send get_hash_response acknowledgement frames as they arrive.
      4. Send get_line_info_list with those line hashes + a timestamp transaction_id.
      5. Collect all cover_path_upload frames until none are missing.

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
        *,
        skip_planning: bool = False,
    ) -> None:
        """Initialise the saga.

        Args:
            command_builder: Navigation command builder (MammotionCommand or similar).
            send_command: Async callable that transmits raw bytes to the device.
            zone_hashs: Area/zone hash IDs to mow (from HashList.area.keys()).
            route_info: Optional pre-built GenerateRouteInformation; defaults are
                        used if not supplied.
            skip_planning: When True, skip the generate_route_information step (step 1).
                           Use this when the device is already working and you only
                           want to fetch the current cover path.

        """
        self._command_builder = command_builder
        self._send_command = send_command
        self._zone_hashs = zone_hashs
        self._route_info = route_info
        self._skip_planning = skip_planning
        self.result: dict[int, dict[int, MowPath]] = {}

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Execute all saga steps. Clears partial state at the start."""
        self.result = {}
        hash_list = HashList()
        route_val: Any = None

        if not self._skip_planning:
            # ------------------------------------------------------------------
            # Step 1: Send generate_route_information, wait for sub_cmd=0 confirm.
            # Subscribe before sending to avoid a race with a fast response.
            # ------------------------------------------------------------------
            route_info = self._route_info or GenerateRouteInformation(one_hashs=self._zone_hashs)
            _logger.debug("MowPathSaga: sending generate_route_information for %d zone(s)", len(self._zone_hashs))
            route_queue: asyncio.Queue[Any] = asyncio.Queue()

            async def _collect_route(msg: Any) -> None:
                try:
                    sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                    if sub_name == "nav":
                        leaf_name, leaf_val = betterproto2.which_one_of(sub_val, "SubNavMsg")
                        if leaf_name == "bidire_reqconver_path" and leaf_val.sub_cmd == 0:
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

            _logger.debug(
                "MowPathSaga: route confirmed — sub_cmd=%d  path_hash=%d",
                route_val.sub_cmd,
                route_val.path_hash,
            )
        else:
            _logger.debug("MowPathSaga: skip_planning=True — skipping generate_route_information")

        # ------------------------------------------------------------------
        # Step 2–3: Request the line hash list (sub_cmd=3), collect all frames,
        # send get_hash_response acks for each, build the line hash list.
        # This mirrors APK: routeResponse() → getLineHashList() →
        #   getAllBoundaryHashList(3) → setHashList(subCmd=3) → lineHashList
        # ------------------------------------------------------------------
        _logger.debug("MowPathSaga: requesting line hash list (sub_cmd=3)")
        hash_ack_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _collect_hash_ack(msg: Any) -> None:
            try:
                sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                if sub_name == "nav":
                    leaf_name, leaf_val = betterproto2.which_one_of(sub_val, "SubNavMsg")
                    if leaf_name == "toapp_gethash_ack" and leaf_val.sub_cmd == 3:
                        hash_ack_queue.put_nowait(msg)
            except Exception:  # noqa: BLE001
                pass

        line_hashs: list[int] = []
        with broker.subscribe_unsolicited(_collect_hash_ack):
            cmd = self._command_builder.get_all_boundary_hash_list(sub_cmd=3)
            await self._send_command(cmd)

            # Collect potentially multi-frame hash list response
            while True:
                try:
                    ack_response = await asyncio.wait_for(hash_ack_queue.get(), timeout=self.step_timeout)
                except TimeoutError:
                    raise CommandTimeoutError("toapp_gethash_ack(sub_cmd=3)", 1) from None

                ack = ack_response.nav.toapp_gethash_ack
                line_hashs.extend(h for h in ack.data_couple if h != 0)

                # Acknowledge this frame
                ack_cmd = self._command_builder.get_hash_response(
                    total_frame=ack.total_frame, current_frame=ack.current_frame
                )
                await self._send_command(ack_cmd)

                _logger.debug(
                    "MowPathSaga: line hash frame %d/%d — %d hashes so far",
                    ack.current_frame,
                    ack.total_frame,
                    len(line_hashs),
                )

                if ack.current_frame >= ack.total_frame:
                    break

        if not line_hashs:
            # Fallback: use confirmed zone hashes if the device sent an empty list
            confirmed_zone_hashs = (
                [h for h in route_val.zone_hashs if h != 0] if route_val is not None else []
            ) or self._zone_hashs
            _logger.warning(
                "MowPathSaga: line hash list was empty — falling back to zone_hashs=%s",
                confirmed_zone_hashs,
            )
            line_hashs = confirmed_zone_hashs

        _logger.debug("MowPathSaga: line hash list — %d hash(es): %s", len(line_hashs), line_hashs)

        # ------------------------------------------------------------------
        # Step 4–5: Request the cover path and collect all frames.
        # ------------------------------------------------------------------
        transaction_id = int(time.time() * 1000)
        _logger.debug("MowPathSaga: requesting cover path — transaction_id=%d  hashes=%s", transaction_id, line_hashs)

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
            cmd = self._command_builder.get_line_info_list(line_hashs, transaction_id)
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
