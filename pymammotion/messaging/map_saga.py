"""MapFetchSaga — fetches the complete device map atomically."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from pymammotion.data.model.hash_list import AreaHashNameList, HashList
from pymammotion.messaging.saga import Saga
from pymammotion.transport.base import CommandTimeoutError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.messaging.broker import DeviceMessageBroker

_logger = logging.getLogger(__name__)


class MapFetchSaga(Saga):
    """Fetches the full device map: area names (non-Luba1), hash list, and all chunk data.

    Execution order:
      1. Area names (non-Luba1) — re-requested on every run including retries.
      2-3. Root hash list frames (all sub_cmd=0 hashes)
      4. Boundary/obstacle/path data for every hash ID in the list

    Steps 2-4 use subscribe_unsolicited so that device-pushed frames are never
    dropped due to a race between receiving and registering a send_and_wait.

    The saga relies entirely on the device's HashList (via ``get_map``) as the
    source of truth.  The StateReducer applies every incoming message to
    device.map before the saga's queue handlers fire, so checking
    ``get_map().missing_hashlist()`` after a ``comm_queue.get()`` already
    reflects the newly received frame — no separate internal tracking needed.

    The root hash list is always re-fetched on every run; the device must
    receive get_all_boundary_hash_list before it will serve comm data frames,
    so skipping it causes step 4 to time out.  Each incoming frame is acked
    with get_hash_response which tells the device to send the next one.
    get_hash_response is never sent proactively — only in response to an
    incoming frame.
    """

    name = "map_fetch"
    max_attempts = 2
    # 5 s matches the APK's HandlerType.handlerType_12333 timeout (5000 ms).
    # SVG tile responses can take ~4 s over MQTT, and the device may broadcast
    # stale frames for already-complete hashes between the request and the reply.
    step_timeout = 5.0

    # SubNavMsg leaf fields the step-4 comm-data loop collects and acks.
    _COMM_FIELDS = ("toapp_get_commondata_ack", "toapp_svg_msg")

    def __init__(
        self,
        device_id: str,
        device_name: str,
        *,
        is_luba1: bool,
        command_builder: Any,  # Navigation instance — typed as Any to avoid tight coupling
        send_command: Callable[[bytes], Awaitable[None]],
        get_map: Callable[[], HashList],
        get_bol_hash: Callable[[], int] | None = None,
        sync_type: int = 3,
        skip_area_names: bool = False,
    ) -> None:
        """Initialise the saga with device info and transport helpers.

        *get_map* must return the device's current ``HashList`` (e.g.
        ``lambda: handle.snapshot.raw.map``).  The saga never creates its
        own HashList — it operates directly on the device state so that
        partial data is preserved across retries without any extra bookkeeping.

        *get_bol_hash* returns the device's most recently reported ``bol_hash``
        (``report_data.locations[0].bol_hash``), used for the start-of-run
        staleness check.  Defaults to a getter that returns 0 (no check) so
        callers/tests that don't supply it behave as before.

        *skip_area_names* suppresses step 1 (``get_area_name_list``) without
        implying the full Luba-1 profile.  Use this for incremental updates
        during mowing where area names haven't changed and the device may not
        respond to the area-name query while busy.
        """
        self._device_id = device_id
        self._device_name = device_name
        self._is_luba1 = is_luba1
        self._skip_area_names = skip_area_names
        self._command_builder = command_builder
        self._send_command = send_command
        self._get_map = get_map
        self._get_bol_hash = get_bol_hash or (lambda: 0)
        self._sync_type = sync_type  # 2 = BLE, 3 = IoT/MQTT

        # Result — set on success, None until then
        self.result: HashList | None = None

    async def _send_ble_sync(self) -> None:
        """Send a ``todev_ble_sync`` to keep the device in the synced/responsive state.

        The device only serves hash-list and common-data frames while it considers the
        app "synced", and that state lapses after a few seconds (the APK re-sends sync
        every ~1.5 s for the whole connection).  We send one immediately before each
        major fetch step — the root hash-list request and the per-hash data request — so
        the device is freshly synced when those commands arrive, rather than relying on a
        single sync at the top of the run that can be stale by the time (e.g. after the
        area-name step) the request actually goes out.  See the ``ble_loop`` heartbeat for
        the background keep-alive that covers the gaps between fetch steps.
        """
        _logger.debug("MapFetchSaga[%s]: sending todev_ble_sync(%d)", self._device_name, self._sync_type)
        await self._send_command(self._command_builder.send_todev_ble_sync(sync_type=self._sync_type))

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Execute all saga steps.  Uses device.map (via get_map) as the source of truth."""
        self.result = None
        self._reset_attempt_counter = False

        # Start-of-run staleness check: if the device's reported bol_hash no longer
        # matches our stored root manifest, the map was edited device-side since we
        # last synced.  invalidate_maps() only wipes root_hash_lists when the hashes
        # actually mismatch, so an in-sync map (or a mid-fetch resume) is left intact
        # and only a genuinely stale manifest is dropped — forcing steps 2-3 to
        # rebuild it to match the device's CURRENT boundary list.  Guard on a known
        # (non-zero) bol_hash so a device that hasn't reported one yet is never wiped.
        # This is the manual-"sync maps" safety net: the report-driven invalidate in
        # MowingDevice already handles the watcher-triggered path.
        self._get_map().invalidate_maps(self._get_bol_hash())

        await self._send_ble_sync()

        # ------------------------------------------------------------------
        # Step 1: Fetch area names (non-Luba1, non-incremental only).
        # ------------------------------------------------------------------
        if not self._is_luba1 and not self._skip_area_names:
            _logger.debug("MapFetchSaga[%s]: fetching area names", self._device_name)
            cmd = self._command_builder.get_area_name_list(self._device_id)
            # will raise a CommandTimeoutError if it fails
            response = await broker.send_and_wait(
                send_fn=lambda: self._send_command(cmd),
                expected_field="toapp_all_hash_name",
                send_timeout=self.step_timeout,
            )

            _area_frame = self.extract_nav_frame(response, "toapp_all_hash_name")
            area_hash_name_msg = _area_frame[1] if _area_frame is not None else None
            if (
                area_hash_name_msg is not None
                and hasattr(area_hash_name_msg, "hashnames")
                and area_hash_name_msg.hashnames
            ):
                self._get_map().area_name = [
                    AreaHashNameList(name=item.name, hash=item.hash) for item in area_hash_name_msg.hashnames
                ]
            _logger.debug("MapFetchSaga[%s]: got %d area names", self._device_name, len(self._get_map().area_name))

        # ------------------------------------------------------------------
        # Steps 2-3: Root hash list frames.
        # Subscribe before sending so no frame is dropped if the device
        # pushes multiple frames at once before we can register a second
        # send_and_wait.
        #
        # get_all_boundary_hash_list is always sent; every incoming frame is
        # acked via get_hash_response which tells the device to send the next
        # one.  get_hash_response is never sent proactively — only as an ack
        # to an incoming frame.  This matches HashDataManager.setHashList in
        # the APK (line 1173).
        # ------------------------------------------------------------------
        _logger.debug("MapFetchSaga[%s]: requesting hash list", self._device_name)

        # Filter to sub_cmd=0: an interrupted MowPathSaga can leave the device
        # retransmitting unacked sub_cmd=3 line-hash frames, and an unfiltered
        # collector would accept one as the root list — ending this loop early
        # and completing the saga with an empty/stale map.
        with self._collect_frames(broker, "toapp_gethash_ack", lambda v: v.sub_cmd == 0) as hash_frame_queue:
            # Re-sync immediately before the root-list request: the area-name step above can
            # take several seconds, staling the run's initial sync, and an unsynced device
            # returns no toapp_gethash_ack.
            await self._send_ble_sync()
            cmd = self._command_builder.get_all_boundary_hash_list(sub_cmd=0)
            await self._send_command(cmd)

            # Ack-driven loop: every frame received from the device is
            # acked via get_hash_response, which tells the device to send
            # the next one.  We never call get_hash_response proactively.
            while True:
                response = await self._next_frame(hash_frame_queue, "toapp_gethash_ack")

                _hash_frame = self.extract_nav_frame(response, "toapp_gethash_ack")
                if _hash_frame is None:
                    raise CommandTimeoutError("toapp_gethash_ack", 1)
                hash_ack = _hash_frame[1]

                # Ack this frame (device interprets as "send me the next one").
                ack_cmd = self._command_builder.get_hash_response(
                    total_frame=hash_ack.total_frame, current_frame=hash_ack.current_frame
                )
                await self._send_command(ack_cmd)

                if hash_ack.current_frame >= hash_ack.total_frame:
                    break

        _logger.debug(
            "MapFetchSaga[%s]: hash list complete — %d hash IDs to fetch",
            self._device_name,
            len(self._get_map().hashlist),
        )

        # ------------------------------------------------------------------
        # Step 4: Fetch boundary/obstacle/path data for every hash ID.
        # Same unsolicited-subscription pattern: subscribe before first send
        # so rapid multi-frame responses are never lost.
        #
        # The StateReducer already applies each toapp_get_commondata_ack /
        # toapp_svg_msg to device.map before the saga's queue handler fires,
        # so get_map().missing_hashlist(0) reflects the up-to-date state after
        # every comm_queue.get().
        #
        # Protocol for each hash:
        #   1. Send synchronize_hash_data(hash) — device starts streaming frames.
        #   2. Ack each received frame with get_regional_data(current_frame=received)
        #      so the device sends the next frame.
        #   3. Once missing_frame() is empty for the received data, check whether
        #      the whole hash is done via find_incomplete_hashes.
        #   4. Only send synchronize_hash_data again when moving to a NEW hash —
        #      never re-send for the hash already being streamed, or the device
        #      restarts from frame 1.
        # ------------------------------------------------------------------
        with self._collect_frames(broker, self._COMM_FIELDS) as comm_queue:
            _no_progress_limit = 10
            no_progress = 0

            # ``find_incomplete_hashes`` includes BOTH never-started hashes AND
            # key-present-but-missing-frames hashes.  This is critical for saga
            # resume — a previous run that got interrupted mid-area will have
            # added a partial FrameList to ``device.map.area[hash]``; the saga
            # must re-send ``synchronize_hash_data`` so the device re-streams
            # the missing frames from scratch.
            missing_hashes = self._get_map().find_incomplete_hashes(0)
            current_hash: int | None = None
            # Saga-local tracker of hashes whose `current_frame == total_frame`
            # transaction we've observed.  Used to advance current_hash even
            # when ``find_incomplete_hashes`` doesn't realise a hash is done
            # (e.g. radar-only types like 23 that have no PathType entry).
            addressed_hashes: set[int] = set()

            if missing_hashes:
                # Re-sync before the first per-hash request for the same reason as the
                # root-list step — keep the device responsive when step 4 begins.
                await self._send_ble_sync()
                current_hash = missing_hashes[0]
                _logger.debug("MapFetchSaga[%s]: fetching data for hash %d", self._device_name, current_hash)
                cmd = self._command_builder.synchronize_hash_data(hash_num=current_hash)
                await self._send_command(cmd)

            while missing_hashes:
                response = await self._next_frame(
                    comm_queue, f"toapp_get_commondata_ack or toapp_svg_msg {current_hash}"
                )

                # State reducer has already applied this frame to device.map.
                _comm_frame = self.extract_nav_frame(response, self._COMM_FIELDS)
                if _comm_frame is None:
                    continue
                leaf_name, leaf_val = _comm_frame

                # Ack every received frame, unconditionally and before any advancement
                # logic — the ack tells the device "got this frame, send the next", so
                # acking is what keeps the stream flowing regardless of which hash the
                # frame is for.  Unlike the APK (HashDataManager.setRegionalData :1218
                # suppresses the ack for a frame already in ``areaListMap``) we do NOT
                # dedup — re-acking is idempotent, and acking unrelated/stale frames
                # (dynamics_line type=18 mid-fetch, leftovers from a previous request)
                # drains them so the device stops retransmitting with an incrementing
                # ``dataHash`` and flooding MQTT.
                await self._send_command(self._ack_frame(leaf_name, leaf_val))

                # Ignore frames for hashes we aren't fetching right now (the device
                # replays old data while processing our request, which would reset the
                # step timeout without progress — APK setRegionalData :1245).
                if not self._in_scope(leaf_name, leaf_val, missing_hashes, current_hash):
                    continue

                # Track per-hash completion locally so the advancement decision doesn't
                # rely solely on find_incomplete_hashes (which can miss radar/unknown
                # types — see addressed_hashes init comment).
                frame_hash, parent_hash = self._frame_scope_hashes(leaf_name, leaf_val)
                if leaf_val.current_frame >= leaf_val.total_frame and leaf_val.total_frame > 0:
                    addressed_hashes.add(frame_hash)
                    if leaf_name == "toapp_svg_msg":
                        addressed_hashes.add(parent_hash)

                if self._get_map().missing_frame(leaf_val):
                    # More frames still needed for this transaction — the device sends
                    # the next one in response to the ack above.
                    continue

                # Data item complete.  Drain any sibling frames for current_hash already
                # queued (area boundary + SVG tiles arrive together) so area completion
                # doesn't advance current_hash before the SVG tile is processed.
                await self._drain_current_hash_frames(comm_queue, current_hash)

                # Check whether the whole hash is done.  Filter find_incomplete_hashes by
                # addressed_hashes so a hash whose only frame had an unknown type (e.g.
                # radar type=23) doesn't keep us pinned to the same current_hash.
                new_missing = [h for h in self._get_map().find_incomplete_hashes(0) if h not in addressed_hashes]
                if len(new_missing) < len(missing_hashes):
                    no_progress = 0
                    self._reset_attempt_counter = True  # genuine map progress — refresh attempt budget
                else:
                    no_progress += 1
                    if no_progress >= _no_progress_limit:
                        raise CommandTimeoutError("map_sync_stall", no_progress)
                missing_hashes = new_missing
                # Only send synchronize_hash_data when moving to a new hash.
                # Re-sending for the current hash would restart device streaming from frame 1.
                if missing_hashes and missing_hashes[0] != current_hash:
                    current_hash = missing_hashes[0]
                    _logger.debug("MapFetchSaga[%s]: fetching data for hash %d", self._device_name, current_hash)
                    cmd = self._command_builder.synchronize_hash_data(hash_num=current_hash)
                    await self._send_command(cmd)

        # If the device never returned area names and no names have been set yet,
        # fill in fallbacks from fetched area hashes.
        current_map = self._get_map()
        if not current_map.area_name and current_map.area:
            current_map.area_name = [
                AreaHashNameList(name=f"area {i + 1}", hash=h) for i, h in enumerate(sorted(current_map.area.keys()))
            ]
            _logger.debug(
                "MapFetchSaga[%s]: generated %d fallback area name(s) after full sync",
                self._device_name,
                len(current_map.area_name),
            )

        _logger.debug(
            "MapFetchSaga[%s]: map fetch complete — areas=%d obstacles=%d paths=%d",
            self._device_name,
            len(current_map.area),
            len(current_map.obstacle),
            len(current_map.path),
        )
        self.result = current_map

    def _ack_frame(self, leaf_name: str, leaf_val: Any) -> bytes:
        """Build the per-frame ack for a comm-data (get_regional_data) or SVG (send_svg_response) frame."""
        if leaf_name == "toapp_svg_msg":
            return self._command_builder.send_svg_response(
                total_frame=leaf_val.total_frame,
                current_frame=leaf_val.current_frame,
                data_hash=leaf_val.data_hash,
                paternal_hash_a=leaf_val.paternal_hash_a,
            )
        return self._command_builder.get_regional_data(regional_data=self._region_data(leaf_val))

    @staticmethod
    def _frame_scope_hashes(leaf_name: str, leaf_val: Any) -> tuple[int, int]:
        """Return ``(frame_hash, parent_hash)`` used for scope checks.

        SVG tiles carry their own ``data_hash``; the link back to the requesting
        area is ``paternal_hash_a``.  Comm-data frames use their area ``hash``
        directly and have no parent (returned as 0).
        """
        if leaf_name == "toapp_svg_msg":
            return int(leaf_val.data_hash), int(leaf_val.paternal_hash_a)
        return int(leaf_val.hash), 0

    def _in_scope(self, leaf_name: str, leaf_val: Any, missing_hashes: list[int], current_hash: int | None) -> bool:
        """Return True when this frame belongs to a hash we're still fetching.

        SVG tiles are accepted when either the tile's own ``data_hash`` or its
        ``paternal_hash_a`` is in scope.
        """
        frame_hash, parent_hash = self._frame_scope_hashes(leaf_name, leaf_val)
        in_scope = frame_hash in missing_hashes or frame_hash == current_hash
        if leaf_name == "toapp_svg_msg":
            in_scope = in_scope or parent_hash in missing_hashes or parent_hash == current_hash
        return in_scope

    async def _drain_current_hash_frames(self, comm_queue: asyncio.Queue[Any], current_hash: int | None) -> None:
        """Ack and discard already-queued frames belonging to *current_hash*.

        The device sends area boundary data and SVG tiles for the same hash in
        quick succession; draining (and acking) them here stops area completion
        from advancing ``current_hash`` before the SVG tile is processed.  Frames
        for other hashes are pushed back and left for the main loop.
        """
        while not comm_queue.empty():
            try:
                queued_msg = comm_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            q_frame = self.extract_nav_frame(queued_msg, self._COMM_FIELDS)
            if q_frame is None:
                comm_queue.put_nowait(queued_msg)
                break
            q_name, q_val = q_frame
            q_hash, q_parent = self._frame_scope_hashes(q_name, q_val)
            if current_hash not in (q_hash, q_parent):
                comm_queue.put_nowait(queued_msg)
                break
            # Always ack drained frames (the device retransmits unacked frames indefinitely).
            await self._send_command(self._ack_frame(q_name, q_val))
