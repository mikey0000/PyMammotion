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
from pymammotion.messaging.transfers import ack_stream
from pymammotion.transport.base import SagaFailedError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.messaging.broker import DeviceMessageBroker

_logger = logging.getLogger(__name__)

#: Consecutive non-advancing frames treated as a stall, like a timer expiry.
_NO_PROGRESS_LIMIT = 10


class MowPathSaga(Saga):
    """Plan a mowing route and collect the resulting cover-path frames.

    Execution order — planning mode (skip_planning=False):
      1. Send get_all_boundary_hash_list(sub_cmd=3) and collect all hash frames,
         acknowledging each with get_hash_response.
      2. Send generate_route_information (bidire_reqconver_path, sub_cmd=0)
         and wait for the device's sub_cmd=0 confirmation.
      3. Send get_line_info_list (app_request_cover_paths) for up to 20 of the lines
         not yet cached, with a timestamp transaction_id.
      4. Collect that request's cover_path_upload frames, then repeat 3–4 until every
         line is cached.  A stall re-requests the missing lines (see
         ``first_frame_timeout``); after ``max_cover_path_retries`` the saga ends
         with ``failed`` set instead of raising.

    Execution order — running task mode (skip_planning=True):
      1. Same as planning mode step 1.
      2. Send query_generate_route_information (bidire_reqconver_path, sub_cmd=2)
         to retrieve the currently running job's route configuration (zone hashes).
      3–4. Same as planning mode steps 3–4.

    result is a dict[transaction_id, dict[frame_num, MowPath]] on success,
    empty dict until then.
    """

    name = "mow_path_fetch"
    max_attempts = 1
    #: Matches the Android app's per-frame watchdog for the same fetch
    #: (HashDataManager.handlerType_12333, armed at 3000 ms after each
    #: getRegionalData and cancelled on every received frame).
    #:
    #: Must stay comfortably *above* the device's own ~1 s frame-retransmit
    #: interval.  At 1.0 s this raced it exactly: the device re-sends an unacked
    #: frame after 1.000 s, so the saga could time out at the very moment the
    #: retransmit was in flight and abandon a run that was about to succeed —
    #: and with ``max_attempts = 1`` there is no retry to cover for it.
    step_timeout = 3.0
    #: Cover-path request timer, from HashDataManager's handlerType_100001: armed for
    #: 6 s after each app_request_cover_paths, re-armed for 4 s by every frame and for
    #: 10 s by a frame left over from an older request.  Each expiry re-requests the
    #: lines still missing; after ``max_cover_path_retries`` of them the fetch gives up.
    first_frame_timeout = 6.0
    next_frame_timeout = 4.0
    residual_frame_timeout = 10.0
    max_cover_path_retries = 10
    #: Line hashes per app_request_cover_paths, as in the APK's getNoLineHash().
    cover_path_batch_size = 20

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
        sync_type: int = 3,
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
        self._sync_type = sync_type  # 2 = BLE, 3 = IoT/MQTT
        self.result: dict[int, dict[int, MowPath]] = {}
        #: True when the cover-path fetch gave up after ``max_cover_path_retries``.
        #: The saga still completes normally so partial lines stay usable.
        self.failed = False
        self._route_val: GenerateRouteInformation | None = (
            route_info  # persists across retries to skip step 2 if already fetched
        )

    async def progress(self) -> Any:
        """Route resolution plus banked cover-path frames.

        Drives the base class's attempt-budget refresh.  Replaces both the manual
        ``_reset_attempt_counter`` and the ``_budget_reset_granted`` one-shot that
        guarded it: a value derived from state only changes when the fetch really
        advances, so it cannot refresh the budget on every run the way a flag set
        inside ``_run`` did.
        """
        frames = sum(len(f) for f in self._get_map().current_mow_path.values())
        return (self._route_val is not None, frames)

    async def _send_ble_sync(self) -> None:
        """Keep the device in its synced/responsive state before a major fetch request.

        The device only serves hash-list / route / cover-path frames while it considers the
        app "synced", and that state lapses after a few seconds.  We re-sync immediately
        before each major request (line hash list, route info, cover-path fetch) so the
        device is freshly synced when the command arrives, rather than relying on a single
        sync at the top of the run that goes stale across the intervening frame loops.
        """
        _logger.debug("MowPathSaga[%s]: sending todev_ble_sync(%d)", self._device_name, self._sync_type)
        await self._send_command(self._command_builder.send_todev_ble_sync(sync_type=self._sync_type))

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Execute all saga steps."""
        self.result = {}
        self.failed = False
        # Do NOT wipe current_mow_path here — invalidate_mow_path() handles
        # clearing the cache when the device reports path_hash 0/1.  Wiping here
        # defeats the per-hash skip logic below and forces a full re-fetch on
        # every retry, mirroring what the APK's HashDataManager avoids.

        # start with ble sync (immediately precedes the step-1 line-hash-list request below)
        await self._send_ble_sync()

        # ------------------------------------------------------------------
        # Step 1: Request the line hash list (sub_cmd=3), collect all frames,
        # send get_hash_response acks for each.
        # ------------------------------------------------------------------
        with self._collect_frames(broker, "toapp_gethash_ack", lambda v: v.sub_cmd == 3) as hash_ack_queue:
            _logger.debug("MowPathSaga: requesting line hash list (sub_cmd=3)")
            cmd = self._command_builder.get_all_boundary_hash_list(sub_cmd=3)
            await self._send_command(cmd)

            async def _ack(ack: Any) -> None:
                # Acknowledge every frame, including the last one.
                await self._send_command(
                    self._command_builder.get_hash_response(
                        total_frame=ack.total_frame, current_frame=ack.current_frame
                    )
                )

            # allow_empty: no response at all means the device has no active
            # breakpoint lines — a legitimate empty answer, not a failure.  We then
            # fall through to the zone_hashs fallback at the sub_cmd=3 check below.
            # Silence *mid*-stream still raises, since that is a real interruption.
            line_frames = await ack_stream(
                hash_ack_queue,
                field="toapp_gethash_ack",
                ack=_ack,
                timeout=self.step_timeout,
                allow_empty=True,
            )
            if not line_frames:
                _logger.debug(
                    "collecting mow path [%s]: no response to line hash list request (sub_cmd=3)"
                    " — treating as empty and continuing",
                    self._device_name,
                )

        # ------------------------------------------------------------------
        # Step 2: Get route information (skip if already cached from a prior attempt).
        # ------------------------------------------------------------------
        if self._route_val is None:
            if not self._skip_planning:
                # planning mode: send generate_route_information, wait for sub_cmd=0 confirmation
                route_info = self._route_info or GenerateRouteInformation(one_hashs=self._zone_hashs)
                _logger.debug("MowPathSaga: sending generate_route_information for %d zone(s)", len(self._zone_hashs))
                # Re-sync before the route request — the step-1 frame loop above can stale
                # the run's initial sync.
                await self._send_ble_sync()
                cmd = self._command_builder.generate_route_information(route_info)
                response = await broker.send_and_wait(
                    send_fn=lambda: self._send_command(cmd),
                    expected_field="bidire_reqconver_path",
                    send_timeout=self.step_timeout,
                )
                route_frame = self.extract_nav_frame(response, "bidire_reqconver_path")
                assert route_frame is not None  # noqa: S101 — send_and_wait already matched this field
                self._route_val = route_frame[1]
                _logger.debug(
                    "MowPathSaga: route confirmed — sub_cmd=%d  path_hash=%d",
                    self._route_val.sub_cmd,
                    self._route_val.path_hash,
                )
            else:
                # skip_planning=True: a running job's route info should already be cached.
                # If it isn't, the saga cannot fetch cover paths — fail loudly instead of
                # returning silently (which left the caller with empty MowPath data).
                _logger.warning("MowPathSaga: skip_planning=True but no _route_val available — failing saga")
                raise SagaFailedError(self.name, self.max_attempts)
        else:
            _logger.debug("MowPathSaga: reusing cached route info — skipping step 2")

        line_hashes = [h for h in self._get_map().line_root_hashlist if h != 0]
        if not line_hashes:
            _logger.debug("MowPathSaga: no sub_cmd=3 line hashes — no cover path to fetch")
            self._route_val = None
            return
        _logger.debug("MowPathSaga: %d line hash(es) from map", len(line_hashes))

        # ------------------------------------------------------------------
        # Step 3–4: request the lines still missing (up to 20 per request) and
        # collect their cover_path_upload frames, re-requesting on a stall the
        # way the APK's handlerType_100001 timer does.
        # ------------------------------------------------------------------
        current_run_tx_ids: set[int] = set()
        retries = 0

        with self._collect_frames(broker, "cover_path_upload") as path_queue:
            while True:
                # Re-derived before every request, matching getHashLineNew(): lines already
                # cached (by us, a prior run, or another client's fetch) are never re-asked for.
                current_map = self._get_map()
                missing_hashes = [h for h in line_hashes if not current_map.has_mow_path_for_hash(h)]
                if not missing_hashes:
                    break
                batch_hashes = missing_hashes[: self.cover_path_batch_size]
                transaction_id = int(time.time() * 1000)
                current_run_tx_ids.add(transaction_id)
                _logger.debug(
                    "MowPathSaga: requesting %d of %d missing line(s) — transaction_id=%d  retry=%d  hashes=%s",
                    len(batch_hashes),
                    len(missing_hashes),
                    transaction_id,
                    retries,
                    batch_hashes,
                )
                # Re-sync before each request — the frame loop can stale the previous sync.
                await self._send_ble_sync()
                await self._send_command(self._command_builder.get_line_info_list(batch_hashes, transaction_id))

                if not await self._collect_transaction(path_queue, transaction_id, current_run_tx_ids):
                    retries += 1
                    if retries > self.max_cover_path_retries:
                        _logger.warning(
                            "MowPathSaga[%s]: cover path still missing %d line(s) after %d retries — giving up",
                            self._device_name,
                            len(missing_hashes),
                            self.max_cover_path_retries,
                        )
                        self.failed = True
                        break
                    _logger.debug(
                        "MowPathSaga: no complete reply for tx=%d — retry %d/%d",
                        transaction_id,
                        retries,
                        self.max_cover_path_retries,
                    )

        # Requests abandoned for a retry leave half-filled transactions behind; their
        # lines were re-requested, and the GeoJSON builders skip incomplete ones anyway.
        self._get_map().prune_incomplete_mow_paths()
        self.result = self._get_map().current_mow_path
        total_packets = sum(len(frames) for frames in self.result.values())
        _logger.debug(
            "MowPathSaga: %s — %d transaction(s)  %d total frame(s)",
            "failed" if self.failed else "complete",
            len(self.result),
            total_packets,
        )
        self._route_val = None

    async def _collect_transaction(
        self, path_queue: asyncio.Queue[Any], transaction_id: int, current_run_tx_ids: set[int]
    ) -> bool:
        """Collect frames for *transaction_id* until it is complete; False on a timeout or stall.

        Timeouts follow the APK: 6 s for the first frame after a request, 4 s between
        frames, and 10 s after a frame left over from an older request.
        """
        timeout = self.first_frame_timeout
        no_progress = 0
        prev_missing = self._missing_frame_count()
        while True:
            try:
                frame_response = await asyncio.wait_for(path_queue.get(), timeout=timeout)
            except TimeoutError:
                return False

            path_frame = self.extract_nav_frame(frame_response, "cover_path_upload")
            assert path_frame is not None  # noqa: S101 — the collector already filtered on this field
            mow_path = MowPath.from_dict(path_frame[1].to_dict(casing=betterproto2.Casing.SNAKE))

            if mow_path.transaction_id not in current_run_tx_ids:
                _logger.debug(
                    "MowPathSaga: dropping residual frame tx=%d (current run tx_ids=%s)",
                    mow_path.transaction_id,
                    current_run_tx_ids,
                )
                self._get_map().current_mow_path.pop(mow_path.transaction_id, None)
                timeout = self.residual_frame_timeout
                continue

            _logger.debug(
                "MowPathSaga: got cover_path_upload frame %d/%d  tx=%d",
                mow_path.current_frame,
                mow_path.total_frame,
                mow_path.transaction_id,
            )
            timeout = self.next_frame_timeout

            # Frames that arrive but never shrink the missing set (duplicates, a device
            # stuck re-sending) would otherwise re-arm the timer forever.
            new_missing = self._missing_frame_count()
            if new_missing < prev_missing:
                no_progress = 0
            else:
                no_progress += 1
                if no_progress >= _NO_PROGRESS_LIMIT:
                    return False
            prev_missing = new_missing

            current_map = self._get_map()
            if transaction_id in current_map.current_mow_path and (
                transaction_id not in current_map.find_missing_mow_path_frames()
            ):
                return True

    def _missing_frame_count(self) -> int:
        return sum(len(v) for v in self._get_map().find_missing_mow_path_frames().values())
