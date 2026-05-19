"""MapFetchSaga — fetches the complete device map atomically."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from pymammotion.data.model.hash_list import AreaHashNameList, HashList, RootHashList
from pymammotion.data.model.region_data import RegionData
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

    Resume behaviour on restart:
      * Root list complete → skip to step 4.
      * Otherwise → call get_all_boundary_hash_list once; the device starts
        streaming, and each incoming frame is acked with get_hash_response
        which tells the device to send the next one.  get_hash_response is
        never sent proactively — only in response to an incoming frame.
    """

    name = "map_fetch"
    max_attempts = 2
    # 5 s matches the APK's HandlerType.handlerType_12333 timeout (5000 ms).
    # SVG tile responses can take ~4 s over MQTT, and the device may broadcast
    # stale frames for already-complete hashes between the request and the reply.
    step_timeout = 5.0

    def __init__(
        self,
        device_id: str,
        device_name: str,
        *,
        is_luba1: bool,
        command_builder: Any,  # Navigation instance — typed as Any to avoid tight coupling
        send_command: Callable[[bytes], Awaitable[None]],
        get_map: Callable[[], HashList],
    ) -> None:
        """Initialise the saga with device info and transport helpers.

        *get_map* must return the device's current ``HashList`` (e.g.
        ``lambda: handle.snapshot.raw.map``).  The saga never creates its
        own HashList — it operates directly on the device state so that
        partial data is preserved across retries without any extra bookkeeping.
        """
        self._device_id = device_id
        self._device_name = device_name
        self._is_luba1 = is_luba1
        self._command_builder = command_builder
        self._send_command = send_command
        self._get_map = get_map

        # Result — set on success, None until then
        self.result: HashList | None = None

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Execute all saga steps.  Uses device.map (via get_map) as the source of truth."""
        self.result = None
        self._reset_attempt_counter = False

        # Pre-check root hash list completion so step 1 can be skipped on
        # retry paths where only step 4 remains (saves one round-trip).
        partial_root: RootHashList | None = None
        root_list_complete = False

        cmd = self._command_builder.send_todev_ble_sync(sync_type=3)
        await self._send_command(cmd)

        partial_root = next((r for r in self._get_map().root_hash_lists if r.sub_cmd == 0), None)
        root_list_complete = (
            partial_root is not None
            and partial_root.total_frame > 0
            and len(partial_root.data) >= partial_root.total_frame
        )

        # ------------------------------------------------------------------
        # Step 1: Fetch area names (non-Luba1 only).
        # Skipped when root hash list already complete — we're resuming step 4
        # and names from the first run are still valid.  Always fetched in
        # area_names_only mode (that mode exists solely to refresh names).
        # ------------------------------------------------------------------
        if not self._is_luba1 and not root_list_complete:
            _logger.debug("MapFetchSaga[%s]: fetching area names", self._device_name)
            cmd = self._command_builder.get_area_name_list(self._device_id)
            try:
                response = await broker.send_and_wait(
                    send_fn=lambda: self._send_command(cmd),
                    expected_field="toapp_all_hash_name",
                    send_timeout=self.step_timeout,
                )
            except CommandTimeoutError:
                raise

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
        elif not self._is_luba1:
            _logger.debug(
                "MapFetchSaga[%s]: root hash list already complete — skipping area name re-fetch",
                self._device_name,
            )

        # ------------------------------------------------------------------
        # Steps 2-3: Root hash list frames.
        # Subscribe before sending so no frame is dropped if the device
        # pushes multiple frames at once before we can register a second
        # send_and_wait.
        #
        # Resume logic:
        #   a) Root list already complete  → skip straight to step 4.
        #   b) Otherwise                   → get_all_boundary_hash_list once;
        #      every incoming frame is acked via get_hash_response which also
        #      requests the next frame.  get_hash_response is never sent
        #      proactively — only as an ack to an incoming frame.  This matches
        #      HashDataManager.setHashList in the APK (line 1173).
        # ------------------------------------------------------------------
        _logger.debug("MapFetchSaga[%s]: requesting hash list", self._device_name)

        hash_frame_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _collect_hash_frame(msg: Any) -> None:
            if self.extract_nav_frame(msg, "toapp_gethash_ack") is not None:
                hash_frame_queue.put_nowait(msg)

        with broker.subscribe_unsolicited(_collect_hash_frame):
            if root_list_complete:
                assert partial_root is not None  # noqa: S101
                _logger.debug(
                    "MapFetchSaga[%s]: root hash list already complete (%d frame(s)) — skipping to comm data",
                    self._device_name,
                    partial_root.total_frame,
                )
            else:
                cmd = self._command_builder.get_all_boundary_hash_list(sub_cmd=0)
                await self._send_command(cmd)

                # Ack-driven loop: every frame received from the device is
                # acked via get_hash_response, which tells the device to send
                # the next one.  We never call get_hash_response proactively.
                while True:
                    try:
                        response = await asyncio.wait_for(hash_frame_queue.get(), timeout=self.step_timeout)
                    except TimeoutError:
                        raise CommandTimeoutError("toapp_gethash_ack", 1) from None

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
        comm_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _collect_comm_data(msg: Any) -> None:
            if self.extract_nav_frame(msg, ("toapp_get_commondata_ack", "toapp_svg_msg")) is not None:
                comm_queue.put_nowait(msg)

        with broker.subscribe_unsolicited(_collect_comm_data):
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
            if missing_hashes:
                current_hash = missing_hashes[0]
                _logger.debug("MapFetchSaga[%s]: fetching data for hash %d", self._device_name, current_hash)
                cmd = self._command_builder.synchronize_hash_data(hash_num=current_hash)
                await self._send_command(cmd)

            while missing_hashes:
                try:
                    response = await asyncio.wait_for(comm_queue.get(), timeout=self.step_timeout)
                except TimeoutError:
                    raise CommandTimeoutError("toapp_get_commondata_ack", 1) from None

                # State reducer has already applied this frame to device.map.
                _comm_frame = self.extract_nav_frame(response, ("toapp_get_commondata_ack", "toapp_svg_msg"))
                if _comm_frame is None:
                    continue
                leaf_name, leaf_val = _comm_frame

                # APK guard: ignore frames for hashes we are not currently
                # waiting on (device replays old data while processing our
                # request, which would reset the step_timeout without making
                # any progress — see HashDataManager.setRegionalData line 1267).
                frame_hash = int(leaf_val.data_hash) if leaf_name == "toapp_svg_msg" else int(leaf_val.hash)
                if frame_hash not in missing_hashes and frame_hash != current_hash:
                    continue

                current_map = self._get_map()
                missing_frames = current_map.missing_frame(leaf_val)
                if missing_frames:
                    # More frames needed — ack the received frame so the device sends the next.
                    # SVG uses todev_svg_msg (sub_cmd=2); comm data uses todev_get_commondata.
                    if leaf_name == "toapp_svg_msg":
                        cmd = self._command_builder.send_svg_response(
                            total_frame=leaf_val.total_frame,
                            current_frame=leaf_val.current_frame,
                            data_hash=leaf_val.data_hash,
                            paternal_hash_a=leaf_val.paternal_hash_a,
                        )
                    else:
                        region_data = self._make_region_data(leaf_val)
                        cmd = self._command_builder.get_regional_data(regional_data=region_data)
                    await self._send_command(cmd)
                else:
                    # This data item is complete — check whether the whole hash is done.
                    new_missing = current_map.find_incomplete_hashes(0)
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

    @staticmethod
    def _make_region_data(leaf_val: Any) -> RegionData:
        """Build a RegionData ack for a received toapp_get_commondata_ack frame."""
        region_data = RegionData()
        region_data.total_frame = leaf_val.total_frame
        region_data.current_frame = leaf_val.current_frame
        region_data.sub_cmd = leaf_val.sub_cmd
        region_data.type = leaf_val.type
        region_data.hash = leaf_val.hash
        region_data.action = leaf_val.action
        return region_data
