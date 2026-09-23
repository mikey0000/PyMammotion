"""Hand-written fakes for saga tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import create_autospec

from pymammotion.data.model.hash_list import HashList
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.proto import CoverPathPacketT, CoverPathUploadT, LubaMsg, MctlNav
from tests.unit.messaging._helpers import apply_msg_to_map, comm_data_frame, hash_list_msg


class FakeHashListDevice:
    """Mower that streams hash lists the way firmware does: frame N+1 only after frame N is acked.

    ``hash_lists`` maps each ``get_all_boundary_hash_list`` sub_cmd to its frames
    (one list of hash IDs per frame); a sub_cmd absent from it is answered with
    silence.  ``comm_types`` gives the ``type`` returned for each hash on
    ``synchronize_hash_data``.  ``get_line_info_list`` is answered with one
    single-frame cover path per request.  Every frame is applied to ``device_map``
    before the broker sees it, standing in for the StateReducer.
    """

    def __init__(
        self,
        broker: DeviceMessageBroker,
        device_map: HashList,
        hash_lists: dict[int, list[list[int]]],
        *,
        comm_types: dict[int, int] | None = None,
    ) -> None:
        self._broker = broker
        self._map = device_map
        self._hash_lists = hash_lists
        self._comm_types = comm_types or {}
        self._streaming_sub_cmd: int | None = None
        self.hash_list_acks: list[tuple[int, int, int]] = []
        """``(sub_cmd, current_frame, total_frame)`` for every get_hash_response received."""
        self.line_info_requests: list[list[int]] = []

        self.command_builder = create_autospec(MammotionCommand, instance=True)
        cb = self.command_builder
        cb.send_todev_ble_sync.return_value = b""
        cb.get_regional_data.return_value = b""
        cb.get_all_boundary_hash_list.side_effect = lambda sub_cmd: ("hash_list", sub_cmd)
        cb.get_hash_response.side_effect = lambda total_frame, current_frame: (
            "hash_ack",
            current_frame,
            total_frame,
        )
        cb.synchronize_hash_data.side_effect = lambda hash_num: ("sync_hash", hash_num)
        cb.get_line_info_list.side_effect = lambda hash_list, transaction_id: (
            "line_info",
            list(hash_list),
            transaction_id,
        )

    async def send(self, cmd: Any) -> None:
        """``send_command`` for the saga under test."""
        if not isinstance(cmd, tuple):
            return
        match cmd:
            case ("hash_list", sub_cmd):
                self._streaming_sub_cmd = sub_cmd
                await self._emit_hash_frame(sub_cmd, 1)
            case ("hash_ack", current, total):
                assert self._streaming_sub_cmd is not None, "hash list ack with no stream open"
                self.hash_list_acks.append((self._streaming_sub_cmd, current, total))
                if current < total:
                    await self._emit_hash_frame(self._streaming_sub_cmd, current + 1)
            case ("sync_hash", hash_num):
                await self._deliver(comm_data_frame(hash_num, type_code=self._comm_types[hash_num]))
            case ("line_info", hashes, transaction_id):
                self.line_info_requests.append(hashes)
                await self._deliver(_cover_path_msg(hashes[0], transaction_id))

    async def _emit_hash_frame(self, sub_cmd: int, current_frame: int) -> None:
        if not (frames := self._hash_lists.get(sub_cmd)):
            return
        await self._deliver(
            hash_list_msg(
                frames[current_frame - 1],
                sub_cmd=sub_cmd,
                current_frame=current_frame,
                total_frame=len(frames),
            )
        )

    async def _deliver(self, msg: LubaMsg) -> None:
        apply_msg_to_map(msg, self._map)
        await self._broker.on_message(msg)


def _cover_path_msg(path_hash: int, transaction_id: int) -> LubaMsg:
    return LubaMsg(
        nav=MctlNav(
            cover_path_upload=CoverPathUploadT(
                total_frame=1,
                current_frame=1,
                transaction_id=transaction_id,
                path_packets=[CoverPathPacketT(path_hash=path_hash)],
            )
        )
    )
