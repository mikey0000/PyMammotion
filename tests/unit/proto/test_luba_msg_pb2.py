"""Wire values of the ``luba_msg.proto`` additions from app 2.3.20.30."""

from __future__ import annotations

from pymammotion.proto import LubaMsg, MsgCmdType


def test_luba_msg_reads_command_type_252_as_pdt_pb() -> None:
    # msgtype is field 1 varint; 252 -> 0xFC 0x01.
    assert LubaMsg().parse(b"\x08\xfc\x01").msgtype is MsgCmdType.PDT_PB
