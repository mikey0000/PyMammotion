"""MapFetchSaga — fetches the complete device map atomically."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.data.model.hash_list import AreaHashNameList, HashList, NavGetCommData, NavGetHashListData, SvgMessage
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
      1. Area names (non-Luba1, cached across restarts)
      2-3. Root hash list frames (all sub_cmd=0 hashes)
      4. Boundary/obstacle/path data for every hash ID in the list

    Steps 2-4 use subscribe_unsolicited so that device-pushed frames are never
    dropped due to a race between receiving and registering a send_and_wait.

    Area names are NOT cleared on restart — they are cached in _cached_area_names.
    All other partial state is cleared at the start of each _run() call.
    """

    name = "map_fetch"
    max_attempts = 3
    step_timeout = 30.0  # map fetch steps can be slow

    def __init__(
        self,
        device_id: str,
        device_name: str,
        *,
        is_luba1: bool,
        command_builder: Any,  # Navigation instance — typed as Any to avoid tight coupling
        send_command: Callable[[bytes], Awaitable[None]],
    ) -> None:
        """Initialise the saga with device info and transport helpers."""
        self._device_id = device_id
        self._device_name = device_name
        self._is_luba1 = is_luba1
        self._command_builder = command_builder
        self._send_command = send_command

        # Cached area names — NOT cleared on restart
        self._cached_area_names: list[Any] | None = None

        # Result — set on success, None until then
        self.result: HashList | None = None

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Execute all saga steps. Clears partial state at the start."""
        # Clear partial state — but NOT _cached_area_names
        self.result = None
        hash_list = HashList()

        # ------------------------------------------------------------------
        # Step 1: Fetch area names (non-Luba1 only, mandatory — saga will not
        # proceed past this point until a toapp_all_hash_name response arrives).
        # ------------------------------------------------------------------
        if not self._is_luba1:
            if self._cached_area_names is None:
                _logger.debug("MapFetchSaga[%s]: fetching area names", self._device_name)
                cmd = self._command_builder.get_area_name_list(self._device_id)
                response = await broker.send_and_wait(
                    send_fn=lambda: self._send_command(cmd),
                    expected_field="toapp_all_hash_name",
                    send_timeout=self.step_timeout,
                )
                area_hash_name_msg = getattr(response.nav, "toapp_all_hash_name", None)
                if area_hash_name_msg is not None and hasattr(area_hash_name_msg, "hashnames"):
                    self._cached_area_names = [
                        AreaHashNameList(name=item.name, hash=item.hash) for item in area_hash_name_msg.hashnames
                    ]
                else:
                    self._cached_area_names = []
                _logger.debug("MapFetchSaga[%s]: got %d area names", self._device_name, len(self._cached_area_names))
            else:
                _logger.debug(
                    "MapFetchSaga[%s]: using %d cached area names (retry)",
                    self._device_name,
                    len(self._cached_area_names),
                )
            hash_list.area_name = list(self._cached_area_names)

        # ------------------------------------------------------------------
        # Steps 2-3: Root hash list frames.
        # Subscribe before sending so no frame is dropped if the device
        # pushes multiple frames at once before we can register a second
        # send_and_wait.
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
            except Exception:  # noqa: BLE001
                pass

        with broker.subscribe_unsolicited(_collect_hash_frame):
            cmd = self._command_builder.get_all_boundary_hash_list(sub_cmd=0)
            await self._send_command(cmd)

            try:
                response = await asyncio.wait_for(hash_frame_queue.get(), timeout=self.step_timeout)
            except TimeoutError:
                raise CommandTimeoutError("toapp_gethash_ack", 1) from None

            hash_list_ack = getattr(response.nav, "toapp_gethash_ack", None)
            if hash_list_ack is None:
                raise CommandTimeoutError("toapp_gethash_ack", 1)

            hash_list.update_root_hash_list(
                NavGetHashListData(
                    pver=hash_list_ack.pver,
                    sub_cmd=hash_list_ack.sub_cmd,
                    total_frame=hash_list_ack.total_frame,
                    current_frame=hash_list_ack.current_frame,
                    data_hash=hash_list_ack.data_hash,
                    hash_len=hash_list_ack.hash_len,
                    result=hash_list_ack.result,
                    data_couple=list(hash_list_ack.data_couple),
                )
            )

            total_frame = hash_list_ack.total_frame
            received_frames = {hash_list_ack.current_frame}
            all_frames = set(range(1, total_frame + 1))

            while received_frames != all_frames:
                missing = sorted(all_frames - received_frames)
                next_frame = missing[0]
                _logger.debug(
                    "MapFetchSaga[%s]: requesting hash frame %d/%d", self._device_name, next_frame, total_frame
                )
                chunk_cmd = self._command_builder.get_hash_response(total_frame=total_frame, current_frame=next_frame)
                await self._send_command(chunk_cmd)

                try:
                    chunk_response = await asyncio.wait_for(hash_frame_queue.get(), timeout=self.step_timeout)
                except TimeoutError:
                    raise CommandTimeoutError("toapp_gethash_ack", 1) from None

                chunk_ack = getattr(chunk_response.nav, "toapp_gethash_ack", None)
                if chunk_ack is None:
                    raise CommandTimeoutError("toapp_gethash_ack", 1)

                hash_list.update_root_hash_list(
                    NavGetHashListData(
                        pver=chunk_ack.pver,
                        sub_cmd=chunk_ack.sub_cmd,
                        total_frame=chunk_ack.total_frame,
                        current_frame=chunk_ack.current_frame,
                        data_hash=chunk_ack.data_hash,
                        hash_len=chunk_ack.hash_len,
                        result=chunk_ack.result,
                        data_couple=list(chunk_ack.data_couple),
                    )
                )
                received_frames.add(chunk_ack.current_frame)

        _logger.debug(
            "MapFetchSaga[%s]: hash list complete — %d hash IDs to fetch",
            self._device_name,
            len(hash_list.hashlist),
        )

        # ------------------------------------------------------------------
        # Step 4: Fetch boundary/obstacle/path data for every hash ID.
        # Same unsolicited-subscription pattern: subscribe before first send
        # so rapid multi-frame responses are never lost.
        # ------------------------------------------------------------------
        comm_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _collect_comm_data(msg: Any) -> None:
            try:
                sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                if sub_name == "nav":
                    leaf_name, _ = betterproto2.which_one_of(sub_val, "SubNavMsg")
                    if leaf_name in ("toapp_get_commondata_ack", "toapp_svg_msg"):
                        comm_queue.put_nowait(msg)
            except Exception:  # noqa: BLE001
                pass

        with broker.subscribe_unsolicited(_collect_comm_data):
            # Mirrors commdata_response / datahash_response in mower_device.py:
            # receive any message → store it → if missing frames request them,
            # else chain to the first item in missing_hashlist (same hash or next).
            #
            # Circuit breaker: if no hash is removed from missing_hashes after
            # _NO_PROGRESS_LIMIT consecutive responses the device is stuck —
            # raise CommandTimeoutError so the Saga base retries (max_attempts=3).
            _NO_PROGRESS_LIMIT = 10
            no_progress = 0

            missing_hashes = hash_list.missing_hashlist(0)
            if missing_hashes:
                _logger.debug("MapFetchSaga[%s]: fetching data for hash %d", self._device_name, missing_hashes[0])
                cmd = self._command_builder.synchronize_hash_data(hash_num=missing_hashes[0])
                await self._send_command(cmd)

            while missing_hashes:
                try:
                    response = await asyncio.wait_for(comm_queue.get(), timeout=self.step_timeout)
                except TimeoutError:
                    raise CommandTimeoutError("toapp_get_commondata_ack", 1) from None

                leaf_name, leaf_val = betterproto2.which_one_of(response.nav, "SubNavMsg")
                self._apply_comm_data(hash_list, leaf_name, leaf_val)

                missing_frames = hash_list.missing_frame(leaf_val)
                if missing_frames:
                    # Request the next missing frame for the received hash (mirrors commdata_response else-branch)
                    region_data = self._make_region_data(leaf_name, leaf_val, missing_frames[0] - 1)
                    cmd = self._command_builder.get_regional_data(regional_data=region_data)
                    await self._send_command(cmd)
                else:
                    # Received hash is complete — chain to first still-missing hash (mirrors commdata_response)
                    new_missing = hash_list.missing_hashlist(0)
                    if len(new_missing) < len(missing_hashes):
                        no_progress = 0
                    else:
                        no_progress += 1
                        if no_progress >= _NO_PROGRESS_LIMIT:
                            raise CommandTimeoutError("map_sync_stall", no_progress)
                    missing_hashes = new_missing
                    if missing_hashes:
                        _logger.debug(
                            "MapFetchSaga[%s]: fetching data for hash %d", self._device_name, missing_hashes[0]
                        )
                        cmd = self._command_builder.synchronize_hash_data(hash_num=missing_hashes[0])
                        await self._send_command(cmd)

        _logger.debug(
            "MapFetchSaga[%s]: map fetch complete — areas=%d obstacles=%d paths=%d",
            self._device_name,
            len(hash_list.area),
            len(hash_list.obstacle),
            len(hash_list.path),
        )
        self.result = hash_list

    @staticmethod
    def _apply_comm_data(hash_list: HashList, leaf_name: str, leaf_val: Any) -> None:
        """Convert a protobuf comm-data message to a model object and store it."""
        if leaf_name == "toapp_get_commondata_ack":
            hash_list.update(NavGetCommData.from_dict(leaf_val.to_dict(casing=betterproto2.Casing.SNAKE)))
        elif leaf_name == "toapp_svg_msg":
            hash_list.update(SvgMessage.from_dict(leaf_val.to_dict(casing=betterproto2.Casing.SNAKE)))

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
