"""Builders shared by the ``tests/unit/data/model`` test modules."""

from __future__ import annotations

import betterproto2

from pymammotion.data.model.work import CurrentTaskSettings
from pymammotion.proto import NavReqCoverPath


def make_wire_field(field_number: int, wire_type: int, payload: bytes) -> bytes:
    """Encode one protobuf field by hand, so a test can send a wire form the proto would not produce."""

    def varint(n: int) -> bytes:
        out = bytearray()
        while True:
            b = n & 0x7F
            n >>= 7
            out.append(b | (0x80 if n else 0))
            if not n:
                return bytes(out)

    return varint((field_number << 3) | wire_type) + payload


def make_task_settings(frame: bytes) -> CurrentTaskSettings:
    """Decode a ``NavReqCoverPath`` frame the way the state reducer does."""
    return CurrentTaskSettings.from_dict(NavReqCoverPath().parse(frame).to_dict(casing=betterproto2.Casing.SNAKE))
