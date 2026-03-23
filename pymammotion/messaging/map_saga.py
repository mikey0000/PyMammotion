"""MapFetchSaga — fetches the complete device map atomically."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pymammotion.data.model.hash_list import AreaHashNameList, HashList, NavGetHashListData
from pymammotion.messaging.broker import CommandTimeoutError, DeviceMessageBroker
from pymammotion.messaging.saga import Saga

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_logger = logging.getLogger(__name__)


class MapFetchSaga(Saga):
    """Fetches the full device map: area names (non-Luba1), hash list, and all chunks.

    Area names are fetched first (for non-Luba1 devices) because they must be
    present in the HashList before boundary data is processed. Area names are
    cached after the first successful fetch and reused on saga restarts.

    If any step times out (CommandTimeoutError), the saga sets SagaInterruptedError
    which causes Saga.execute() to restart _run() from scratch. Partial state
    (hash list, chunks) is cleared at the start of each _run() call.
    Area names are NOT cleared on restart — they are cached in _cached_area_names.
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

        # Step 1: Fetch area names (non-Luba1 only, cached after first fetch)
        if not self._is_luba1 and self._cached_area_names is None:
            _logger.debug("MapFetchSaga[%s]: fetching area names", self._device_name)
            cmd = self._command_builder.get_area_name_list(self._device_id)
            response = await broker.send_and_wait(
                send_fn=lambda: self._send_command(cmd),
                expected_field="toapp_all_hash_name",
                send_timeout=self.step_timeout,
            )
            # Parse the AppGetAllAreaHashName response
            nav_msg = response.nav
            area_hash_name_msg = getattr(nav_msg, "toapp_all_hash_name", None)
            if area_hash_name_msg is not None and hasattr(area_hash_name_msg, "hashnames"):
                self._cached_area_names = [
                    AreaHashNameList(name=item.name, hash=item.hash)
                    for item in area_hash_name_msg.hashnames
                ]
            else:
                self._cached_area_names = []
            _logger.debug(
                "MapFetchSaga[%s]: got %d area names", self._device_name, len(self._cached_area_names)
            )

        # Apply cached area names to the hash list being assembled
        if self._cached_area_names is not None:
            hash_list.area_name = list(self._cached_area_names)

        # Step 2: Request the root hash list (first frame)
        _logger.debug("MapFetchSaga[%s]: requesting hash list", self._device_name)
        cmd = self._command_builder.get_all_boundary_hash_list(sub_cmd=1)
        response = await broker.send_and_wait(
            send_fn=lambda: self._send_command(cmd),
            expected_field="toapp_gethash_ack",
            send_timeout=self.step_timeout,
        )

        nav_msg = response.nav
        hash_list_ack = getattr(nav_msg, "toapp_gethash_ack", None)
        if hash_list_ack is None:
            _logger.warning("MapFetchSaga[%s]: hash list ack was None", self._device_name)
            field = "toapp_gethash_ack"
            raise CommandTimeoutError(field, 0)

        # Decode first frame
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
        current_frame = hash_list_ack.current_frame

        # Step 3: Fetch any remaining hash list frames
        received_frames = {current_frame}
        all_frames = set(range(1, total_frame + 1))

        while received_frames != all_frames:
            missing = sorted(all_frames - received_frames)
            next_frame = missing[0]
            _logger.debug(
                "MapFetchSaga[%s]: requesting hash frame %d/%d", self._device_name, next_frame, total_frame
            )
            chunk_cmd = self._command_builder.get_hash_response(
                total_frame=total_frame, current_frame=next_frame
            )
            chunk_response = await broker.send_and_wait(
                send_fn=lambda: self._send_command(chunk_cmd),  # noqa: B023
                expected_field="toapp_gethash_ack",
                send_timeout=self.step_timeout,
            )
            chunk_nav = chunk_response.nav
            chunk_ack = getattr(chunk_nav, "toapp_gethash_ack", None)
            if chunk_ack is None:
                field = "toapp_gethash_ack"
                raise CommandTimeoutError(field, 0)

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
            "MapFetchSaga[%s]: map fetch complete, %d hash IDs",
            self._device_name,
            len(hash_list.hashlist),
        )
        self.result = hash_list
