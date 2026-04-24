"""MapFetchSaga — fetches the complete device map atomically."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.data.model.hash_list import AreaHashNameList, HashList
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
         If the device returns no names, fallback labels are generated from
         known area hashes (``existing_area_hashes`` or post-step-4 area data).
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
    max_attempts = 3
    step_timeout = 3.0  # map fetch steps can be slow

    def __init__(
        self,
        device_id: str,
        device_name: str,
        *,
        is_luba1: bool,
        command_builder: Any,  # Navigation instance — typed as Any to avoid tight coupling
        send_command: Callable[[bytes], Awaitable[None]],
        get_map: Callable[[], HashList],
        area_names_only: bool = False,
        existing_area_hashes: list[int] | None = None,
    ) -> None:
        """Initialise the saga with device info and transport helpers.

        *get_map* must return the device's current ``HashList`` (e.g.
        ``lambda: handle.snapshot.raw.map``).  The saga never creates its
        own HashList — it operates directly on the device state so that
        partial data is preserved across retries without any extra bookkeeping.

        When *area_names_only* is True the saga only executes step 1 (area
        name fetch) and skips the expensive hash-list + chunk steps.  Use this
        when the map data is already valid but area names were not populated.

        *existing_area_hashes* is used in *area_names_only* mode: if the device
        returns no names (user has never named their areas), fallback names
        "area 1", "area 2", … are generated from these hash IDs so that HA
        always has something to display.
        """
        self._device_id = device_id
        self._device_name = device_name
        self._is_luba1 = is_luba1
        self._command_builder = command_builder
        self._send_command = send_command
        self._get_map = get_map
        self._area_names_only = area_names_only
        self._existing_area_hashes: list[int] = existing_area_hashes or []

        # Result — set on success, None until then
        self.result: HashList | None = None

    async def _run(self, broker: DeviceMessageBroker) -> None:  # noqa: C901
        """Execute all saga steps.  Uses device.map (via get_map) as the source of truth."""
        self.result = None
        self._reset_attempt_counter = False

        # ------------------------------------------------------------------
        # Step 1: Fetch area names (non-Luba1 only, always fresh — re-requested
        # on every run so names stay current even after a mid-saga restart).
        # ------------------------------------------------------------------
        if not self._is_luba1:
            _logger.debug("MapFetchSaga[%s]: fetching area names", self._device_name)
            cmd = self._command_builder.get_area_name_list(self._device_id)
            response = await broker.send_and_wait(
                send_fn=lambda: self._send_command(cmd),
                expected_field="toapp_all_hash_name",
                send_timeout=self.step_timeout,
            )
            area_hash_name_msg = getattr(response.nav, "toapp_all_hash_name", None)
            if (
                area_hash_name_msg is not None
                and hasattr(area_hash_name_msg, "hashnames")
                and area_hash_name_msg.hashnames
            ):
                self._get_map().area_name = [
                    AreaHashNameList(name=item.name, hash=item.hash) for item in area_hash_name_msg.hashnames
                ]
            elif self._existing_area_hashes:
                # Device returned no names — generate fallbacks from known area hashes
                self._get_map().area_name = [
                    AreaHashNameList(name=f"area {i + 1}", hash=h)
                    for i, h in enumerate(sorted(self._existing_area_hashes))
                ]
                _logger.debug(
                    "MapFetchSaga[%s]: device returned no area names — generated %d fallback name(s)",
                    self._device_name,
                    len(self._get_map().area_name),
                )
            _logger.debug("MapFetchSaga[%s]: got %d area names", self._device_name, len(self._get_map().area_name))

        if self._area_names_only:
            _logger.debug("MapFetchSaga[%s]: area-names-only mode — skipping hash list fetch", self._device_name)
            self.result = self._get_map()
            return

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
            try:
                sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                if sub_name == "nav":
                    leaf_name, _ = betterproto2.which_one_of(sub_val, "SubNavMsg")
                    if leaf_name == "toapp_gethash_ack":
                        hash_frame_queue.put_nowait(msg)
            except Exception:  # noqa: BLE001, S110
                pass

        with broker.subscribe_unsolicited(_collect_hash_frame):
            partial_root = next((r for r in self._get_map().root_hash_lists if r.sub_cmd == 0), None)
            root_list_complete = (
                partial_root is not None
                and partial_root.total_frame > 0
                and len(partial_root.data) >= partial_root.total_frame
            )

            if root_list_complete:
                assert partial_root is not None  # noqa: S101
                self._reset_attempt_counter = True
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

                    hash_ack = getattr(response.nav, "toapp_gethash_ack", None)
                    if hash_ack is None:
                        raise CommandTimeoutError("toapp_gethash_ack", 1)

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
        # ------------------------------------------------------------------
        comm_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _collect_comm_data(msg: Any) -> None:
            try:
                sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                if sub_name == "nav":
                    leaf_name, _ = betterproto2.which_one_of(sub_val, "SubNavMsg")
                    if leaf_name in ("toapp_get_commondata_ack", "toapp_svg_msg"):
                        comm_queue.put_nowait(msg)
            except Exception:  # noqa: BLE001, S110
                pass

        with broker.subscribe_unsolicited(_collect_comm_data):
            _no_progress_limit = 10
            no_progress = 0

            # ``find_incomplete_hashes`` includes BOTH never-started hashes AND
            # key-present-but-missing-frames hashes.  This is critical for saga
            # resume — a previous run that got interrupted mid-area will have
            # added a partial FrameList to ``device.map.area[hash]``; the saga
            # must re-send ``synchronize_hash_data`` so the device re-streams
            # the missing frames from scratch (``get_hash_response`` is only a
            # per-frame ack, not a request-to-resume).
            missing_hashes = self._get_map().find_incomplete_hashes(0)
            if missing_hashes:
                _logger.debug("MapFetchSaga[%s]: fetching data for hash %d", self._device_name, missing_hashes[0])
                cmd = self._command_builder.synchronize_hash_data(hash_num=missing_hashes[0])
                await self._send_command(cmd)

            while missing_hashes:
                try:
                    response = await asyncio.wait_for(comm_queue.get(), timeout=self.step_timeout)
                except TimeoutError:
                    raise CommandTimeoutError("toapp_get_commondata_ack", 1) from None

                # State reducer has already applied this frame to device.map.
                leaf_name, leaf_val = betterproto2.which_one_of(response.nav, "SubNavMsg")

                current_map = self._get_map()
                missing_frames = current_map.missing_frame(leaf_val)
                if missing_frames:
                    # More frames needed — request the first missing one.
                    current_frame = leaf_val.current_frame
                    if current_frame != missing_frames[0] - 1:
                        current_frame = missing_frames[0] - 1
                    region_data = self._make_region_data(leaf_name, leaf_val, current_frame)
                    cmd = self._command_builder.get_regional_data(regional_data=region_data)
                    await self._send_command(cmd)
                else:
                    # Hash is complete — chain to first still-incomplete hash.
                    new_missing = current_map.find_incomplete_hashes(0)
                    if len(new_missing) < len(missing_hashes):
                        no_progress = 0
                    else:
                        no_progress += 1
                        if no_progress >= _no_progress_limit:
                            raise CommandTimeoutError("map_sync_stall", no_progress)
                    missing_hashes = new_missing
                    if missing_hashes:
                        _logger.debug(
                            "MapFetchSaga[%s]: fetching data for hash %d", self._device_name, missing_hashes[0]
                        )
                        cmd = self._command_builder.synchronize_hash_data(hash_num=missing_hashes[0])
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
    def _make_region_data(leaf_name: str, leaf_val: Any, current_frame: int) -> RegionData:
        """Build a RegionData request for the next missing frame."""
        region_data = RegionData()
        region_data.total_frame = leaf_val.total_frame
        region_data.current_frame = current_frame
        region_data.sub_cmd = leaf_val.sub_cmd
        region_data.type = leaf_val.type
        if leaf_name == "toapp_svg_msg":
            region_data.hash = leaf_val.data_hash
            region_data.action = 0
        else:
            region_data.hash = leaf_val.hash
            region_data.action = leaf_val.action
        return region_data
