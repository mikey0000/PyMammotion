"""MowPathSaga — plan a route and collect the mowing path from the device."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.data.model import GenerateRouteInformation
from pymammotion.messaging.saga import Saga
from pymammotion.transport.base import CommandTimeoutError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.data.model.hash_list import HashList, MowPath
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

    The saga uses the device's HashList (via ``get_map``) as the source of truth
    for received cover-path frames.  The StateReducer applies each
    ``cover_path_upload`` message to ``device.map.current_mow_path`` before the
    saga's queue handlers fire.

    result is a dict[transaction_id, dict[frame_num, MowPath]] on success,
    empty dict until then.

    Resume behaviour on restart:
      If steps 1-3 completed before an interruption, the saga stores the
      line hash list and transaction_id and skips straight to step 4 on the
      next attempt.  It probes by re-sending get_line_info_list; if the device
      responds the attempt counter is reset and frame collection resumes.
      If the probe times out, all partial state is cleared and the saga restarts
      from step 1 (or step 2 when skip_planning=True).
    """

    name = "mow_path_fetch"
    max_attempts = 3
    step_timeout = 30.0

    def __init__(
        self,
        command_builder: Any,
        send_command: Callable[[bytes], Awaitable[None]],
        get_map: Callable[[], HashList],
        zone_hashs: list[int],
        route_info: GenerateRouteInformation | None = None,
        *,
        skip_planning: bool = False,
    ) -> None:
        """Initialise the saga.

        Args:
            command_builder: Navigation command builder (MammotionCommand or similar).
            send_command: Async callable that transmits raw bytes to the device.
            get_map: Returns the device's current HashList (e.g.
                     ``lambda: handle.snapshot.raw.map``).  Used as the source of
                     truth for received cover-path frames across retries.
            zone_hashs: Area/zone hash IDs to mow (from HashList.area.keys()).
            route_info: Optional pre-built GenerateRouteInformation; defaults are
                        used if not supplied.
            skip_planning: When True, skip the generate_route_information step (step 1).
                           Use this when the device is already working and you only
                           want to fetch the current cover path.

        """
        self._command_builder = command_builder
        self._send_command = send_command
        self._get_map = get_map
        self._zone_hashs = zone_hashs
        self._route_info = route_info
        self._skip_planning = skip_planning
        self.result: dict[int, dict[int, MowPath]] = {}

        # State that survives between _run() calls to allow frame-level resume.
        # line_hashs / transaction_id are set after steps 1-3 complete so that
        # a restarted run can skip straight to frame collection.
        # Reset to None only when a resume probe times out.
        self._line_hashs: list[int] | None = None
        self._transaction_id: int | None = None

    async def _run(self, broker: DeviceMessageBroker) -> None:  # noqa: C901
        """Execute all saga steps.  Resumes from partial state when available."""
        self.result = {}
        self._reset_attempt_counter = False

        # ------------------------------------------------------------------
        # Fast-path: steps 1-3 completed in a previous interrupted run.
        # Probe by re-sending get_line_info_list with the same transaction_id.
        # On success → resume frame collection.
        # On timeout  → reset state and fall through to full restart.
        # ------------------------------------------------------------------
        if self._line_hashs is not None and self._transaction_id is not None:
            transaction_id = self._transaction_id
            line_hashs = self._line_hashs
            _logger.debug(
                "MowPathSaga: resuming from partial state — probing cover_path_upload " "(tx=%d  hashes=%s)",
                transaction_id,
                line_hashs,
            )

            path_probe_queue: asyncio.Queue[Any] = asyncio.Queue()

            async def _collect_path_probe(msg: Any) -> None:
                try:
                    sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                    if sub_name == "nav":
                        leaf_name, _ = betterproto2.which_one_of(sub_val, "SubNavMsg")
                        if leaf_name == "cover_path_upload":
                            path_probe_queue.put_nowait(msg)
                except Exception:  # noqa: BLE001, S110
                    pass

            with broker.subscribe_unsolicited(_collect_path_probe):
                cmd = self._command_builder.get_line_info_list(line_hashs, transaction_id)
                await self._send_command(cmd)

                try:
                    await asyncio.wait_for(path_probe_queue.get(), timeout=self.step_timeout)
                    # Probe succeeded — state reducer already stored this frame.
                    self._reset_attempt_counter = True
                    _logger.debug("MowPathSaga: resume probe succeeded")

                    # Collect remaining frames in the same subscription context.
                    while self._get_map().find_missing_mow_path_frames():
                        path_cmd = path_probe_queue.get()
                        try:
                            await asyncio.wait_for(path_cmd, timeout=self.step_timeout)
                        except TimeoutError:
                            raise CommandTimeoutError("cover_path_upload", 1) from None

                except TimeoutError:
                    # Probe timed out — clear stale transaction_id but keep line hashes;
                    # the full path below will skip the hash-list re-fetch if get_map() shows
                    # the sub_cmd=3 root hash list is already complete.
                    _logger.debug(
                        "MowPathSaga: resume probe timed out — clearing transaction_id, retaining line hashes"
                    )
                    self._transaction_id = None
                    # Fall through to the full execution path below by not returning here.
                else:
                    # Resume completed successfully.
                    self.result = self._get_map().current_mow_path
                    total_packets = sum(len(frames) for frames in self.result.values())
                    _logger.debug(
                        "MowPathSaga: complete (resumed) — %d transaction(s)  %d total frame(s)",
                        len(self.result),
                        total_packets,
                    )
                    self._line_hashs = None
                    self._transaction_id = None
                    return

        # Full execution path (first run or resume probe failed).
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
                except Exception:  # noqa: BLE001, S110
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
        #
        # Skip if get_map() already holds a complete sub_cmd=3 root hash list
        # (state reducer persists it across restarts), or if _line_hashs was
        # retained from a previous run's probe timeout.
        # ------------------------------------------------------------------
        line_hashs: list[int] = []

        _sub3 = next((r for r in self._get_map().root_hash_lists if r.sub_cmd == 3), None)
        _sub3_complete = _sub3 is not None and len(_sub3.data) >= _sub3.total_frame

        if _sub3_complete:
            assert _sub3 is not None  # noqa: S101
            line_hashs = list(dict.fromkeys(h for obj in _sub3.data for h in obj.data_couple if h != 0))
            _logger.debug(
                "MowPathSaga: line hash list already complete in map — skipping re-fetch (%d hash(es))",
                len(line_hashs),
            )
        elif self._line_hashs is not None:
            line_hashs = self._line_hashs
            _logger.debug(
                "MowPathSaga: reusing retained line hash list — skipping re-fetch (%d hash(es))",
                len(line_hashs),
            )
        else:
            _logger.debug("MowPathSaga: requesting line hash list (sub_cmd=3)")
            hash_ack_queue: asyncio.Queue[Any] = asyncio.Queue()

            async def _collect_hash_ack(msg: Any) -> None:
                try:
                    sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                    if sub_name == "nav":
                        leaf_name, leaf_val = betterproto2.which_one_of(sub_val, "SubNavMsg")
                        if leaf_name == "toapp_gethash_ack" and leaf_val.sub_cmd == 3:
                            hash_ack_queue.put_nowait(msg)
                except Exception:  # noqa: BLE001, S110
                    pass

            _seen_hashes: set[int] = set()
            with broker.subscribe_unsolicited(_collect_hash_ack):
                cmd = self._command_builder.get_all_boundary_hash_list(sub_cmd=3)
                await self._send_command(cmd)

                while True:
                    try:
                        ack_response = await asyncio.wait_for(hash_ack_queue.get(), timeout=self.step_timeout)
                    except TimeoutError:
                        raise CommandTimeoutError("toapp_gethash_ack(sub_cmd=3)", 1) from None

                    ack = ack_response.nav.toapp_gethash_ack
                    for h in ack.data_couple:
                        if h != 0 and h not in _seen_hashes:
                            _seen_hashes.add(h)
                            line_hashs.append(h)

                    _logger.debug(
                        "MowPathSaga: line hash frame %d/%d — %d hashes so far",
                        ack.current_frame,
                        ack.total_frame,
                        len(line_hashs),
                    )

                    if ack.current_frame >= ack.total_frame:
                        break

                    # Request the next frame
                    ack_cmd = self._command_builder.get_hash_response(
                        total_frame=ack.total_frame, current_frame=ack.current_frame
                    )
                    await self._send_command(ack_cmd)

        if not line_hashs:
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
        # Persist line_hashs + transaction_id so a restart can skip steps 1-3.
        # ------------------------------------------------------------------
        transaction_id = int(time.time() * 1000)
        self._line_hashs = line_hashs
        self._transaction_id = transaction_id
        _logger.debug("MowPathSaga: requesting cover path — transaction_id=%d  hashes=%s", transaction_id, line_hashs)

        path_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _collect_path(msg: Any) -> None:
            try:
                sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                if sub_name == "nav":
                    leaf_name, _ = betterproto2.which_one_of(sub_val, "SubNavMsg")
                    if leaf_name == "cover_path_upload":
                        path_queue.put_nowait(msg)
            except Exception:  # noqa: BLE001, S110
                pass

        with broker.subscribe_unsolicited(_collect_path):
            cmd = self._command_builder.get_line_info_list(line_hashs, transaction_id)
            await self._send_command(cmd)

            # Collect frames until all present.  State reducer applies each frame to
            # device.map.current_mow_path before the queue handler fires, so
            # get_map().find_missing_mow_path_frames() reflects current state.
            while True:
                path_cmd = path_queue.get()
                try:
                    await asyncio.wait_for(path_cmd, timeout=self.step_timeout)
                except TimeoutError:
                    # _line_hashs and _transaction_id are set — next attempt can fast-path probe and resume.
                    self._reset_attempt_counter = True
                    raise CommandTimeoutError("cover_path_upload", 1) from None

                if not self._get_map().find_missing_mow_path_frames():
                    break

        self.result = self._get_map().current_mow_path
        total_packets = sum(len(frames) for frames in self.result.values())
        _logger.debug("MowPathSaga: complete — %d transaction(s)  %d total frame(s)", len(self.result), total_packets)
        self._line_hashs = None
        self._transaction_id = None
