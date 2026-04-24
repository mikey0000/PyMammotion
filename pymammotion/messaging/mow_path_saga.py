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

    Execution order — planning mode (skip_planning=False):
      1. Send get_all_boundary_hash_list(sub_cmd=3) and collect all hash frames,
         acknowledging each with get_hash_response.
      2. Send generate_route_information (bidire_reqconver_path, sub_cmd=0)
         and wait for the device's sub_cmd=0 confirmation.
      3. Send get_line_info_list with each frame's hashes + a timestamp transaction_id.
      4. Collect all cover_path_upload frames until none are missing.

    Execution order — running task mode (skip_planning=True):
      1. Same as planning mode step 1.
      2. Send query_generate_route_information (bidire_reqconver_path, sub_cmd=2)
         to retrieve the currently running job's route configuration (zone hashes).
      3–4. Same as planning mode steps 3–4.

    result is a dict[transaction_id, dict[frame_num, MowPath]] on success,
    empty dict until then.
    """

    name = "mow_path_fetch"
    max_attempts = 3
    step_timeout = 3.0

    def __init__(
        self,
        command_builder: Any,
        send_command: Callable[[bytes], Awaitable[None]],
        get_map: Callable[[], HashList],
        zone_hashs: list[int],
        route_info: GenerateRouteInformation | None = None,
        *,
        skip_planning: bool = False,
        device_name: str = "",
    ) -> None:
        """Initialise the saga.

        Args:
            command_builder: Navigation command builder (MammotionCommand or similar).
            send_command: Async callable that transmits raw bytes to the device.
            get_map: Returns the device's current HashList (e.g.
                     ``lambda: handle.snapshot.raw.map``).  Used as the source of
                     truth for received cover-path frames across retries.
            zone_hashs: Area/zone hash IDs to mow (from HashList.area.keys()).
                        Used as fallback when the device returns an empty line hash list.
            route_info: Optional pre-built GenerateRouteInformation; defaults are
                        used if not supplied.
            skip_planning: When True, skip generate_route_information and instead query
                           the currently running job's route info (sub_cmd=2) to obtain
                           the zone hashes before fetching the line hash list.

        """
        self._command_builder = command_builder
        self._send_command = send_command
        self._get_map = get_map
        self._zone_hashs = zone_hashs
        self._route_info = route_info
        self._skip_planning = skip_planning
        self._device_name = device_name
        self.result: dict[int, dict[int, MowPath]] = {}
        self._route_val: GenerateRouteInformation | None = (
            route_info  # persists across retries to skip step 2 if already fetched
        )

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Execute all saga steps."""
        self.result = {}
        self._get_map().current_mow_path = {}

        # ------------------------------------------------------------------
        # Step 1: Request the line hash list (sub_cmd=3), collect all frames,
        # send get_hash_response acks for each.
        # ------------------------------------------------------------------
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

        _current_frame = 1
        _total_frame = 0
        with broker.subscribe_unsolicited(_collect_hash_ack):
            _logger.debug("MowPathSaga: requesting line hash list (sub_cmd=3)")
            cmd = self._command_builder.get_all_boundary_hash_list(sub_cmd=3)
            await self._send_command(cmd)

            while True:
                try:
                    ack_response = await asyncio.wait_for(hash_ack_queue.get(), timeout=self.step_timeout)
                except TimeoutError:
                    if _total_frame == 0:
                        _logger.warning(
                            "MowPathSaga [%s]: no response to line hash list request (sub_cmd=3)",
                            self._device_name,
                        )
                    else:
                        _logger.warning(
                            "MowPathSaga [%s]: line hash list interrupted at frame %d/%d",
                            self._device_name,
                            _current_frame,
                            _total_frame,
                        )
                    raise CommandTimeoutError("toapp_gethash_ack(sub_cmd=3)", 1) from None

                ack = ack_response.nav.toapp_gethash_ack
                _current_frame = ack.current_frame
                _total_frame = ack.total_frame
                self._reset_attempt_counter = True
                _logger.debug("MowPathSaga: line hash frame %d/%d", _current_frame, _total_frame)

                # Acknowledge every frame, including the last one.
                ack_cmd = self._command_builder.get_hash_response(
                    total_frame=ack.total_frame, current_frame=ack.current_frame
                )
                await self._send_command(ack_cmd)

                if ack.current_frame == ack.total_frame:
                    break

        # ------------------------------------------------------------------
        # Step 2: Get route information (skip if already cached from a prior attempt).
        # ------------------------------------------------------------------
        if self._route_val is None:
            if not self._skip_planning:
                # planning mode: send generate_route_information, wait for sub_cmd=0 confirmation
                route_info = self._route_info or GenerateRouteInformation(one_hashs=self._zone_hashs)
                _logger.debug("MowPathSaga: sending generate_route_information for %d zone(s)", len(self._zone_hashs))
                cmd = self._command_builder.generate_route_information(route_info)
                response = await broker.send_and_wait(
                    send_fn=lambda: self._send_command(cmd),
                    expected_field="bidire_reqconver_path",
                    send_timeout=self.step_timeout,
                )
                _, self._route_val = betterproto2.which_one_of(response.nav, "SubNavMsg")
                _logger.debug(
                    "MowPathSaga: route confirmed — sub_cmd=%d  path_hash=%d",
                    self._route_val.sub_cmd,
                    self._route_val.path_hash,
                )
            else:
                # running task mode: query the currently running job's route info (sub_cmd=2)
                return
        else:
            _logger.debug("MowPathSaga: reusing cached route info — skipping step 2")

        # Use get_map() as the source of truth for the received line hash frames.
        # Combine all frames' hashes into one flat list, then split into batches of 20.
        _sub3 = next((r for r in self._get_map().root_hash_lists if r.sub_cmd == 3), None)
        if _sub3 is None or not _sub3.data:
            confirmed_zone_hashs = (
                [h for h in self._route_val.zone_hashs if h != 0] if self._route_val is not None else []
            ) or self._zone_hashs
            _logger.warning(
                "MowPathSaga: no sub_cmd=3 hash list in map — falling back to zone_hashs=%s",
                confirmed_zone_hashs,
            )
            all_hashes = confirmed_zone_hashs
        else:
            all_hashes = [
                h for frame in sorted(_sub3.data, key=lambda d: d.current_frame) for h in frame.data_couple if h != 0
            ]
            _logger.debug("MowPathSaga: %d total hash(es) from map", len(all_hashes))

        _BATCH_SIZE = 20
        hash_batches = [all_hashes[i : i + _BATCH_SIZE] for i in range(0, len(all_hashes), _BATCH_SIZE)]
        _logger.debug(
            "MowPathSaga: %d batch(es) of up to %d hash(es) each",
            len(hash_batches),
            _BATCH_SIZE,
        )

        # ------------------------------------------------------------------
        # Step 3–4: For each batch of up to 20 hashes, request cover paths and
        # collect all cover_path_upload frames before moving to the next batch.
        # ------------------------------------------------------------------
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

        current_run_tx_ids: set[int] = set()

        with broker.subscribe_unsolicited(_collect_path):
            for batch_idx, batch_hashes in enumerate(hash_batches):
                transaction_id = int(time.time() * 1000)
                current_run_tx_ids.add(transaction_id)
                _logger.debug(
                    "MowPathSaga: requesting cover path batch %d/%d — transaction_id=%d  hashes=%s",
                    batch_idx + 1,
                    len(hash_batches),
                    transaction_id,
                    batch_hashes,
                )
                cmd = self._command_builder.get_line_info_list(batch_hashes, transaction_id)
                await self._send_command(cmd)

                while True:
                    try:
                        frame_response = await asyncio.wait_for(path_queue.get(), timeout=self.step_timeout)
                    except TimeoutError:
                        raise CommandTimeoutError("cover_path_upload", 1) from None

                    self._reset_attempt_counter = True
                    _, path_val = betterproto2.which_one_of(frame_response.nav, "SubNavMsg")
                    mow_path = MowPath.from_dict(path_val.to_dict(casing=betterproto2.Casing.SNAKE))

                    if mow_path.transaction_id not in current_run_tx_ids:
                        _logger.debug(
                            "MowPathSaga: dropping residual frame tx=%d (current run tx_ids=%s)",
                            mow_path.transaction_id,
                            current_run_tx_ids,
                        )
                        self._get_map().current_mow_path.pop(mow_path.transaction_id, None)
                        continue

                    _logger.debug(
                        "MowPathSaga: got cover_path_upload frame %d/%d  tx=%d  batch=%d/%d",
                        mow_path.current_frame,
                        mow_path.total_frame,
                        mow_path.transaction_id,
                        batch_idx + 1,
                        len(hash_batches),
                    )

                    if not self._get_map().find_missing_mow_path_frames():
                        break

        self.result = self._get_map().current_mow_path
        total_packets = sum(len(frames) for frames in self.result.values())
        _logger.debug("MowPathSaga: complete — %d transaction(s)  %d total frame(s)", len(self.result), total_packets)
        self._route_val = None
