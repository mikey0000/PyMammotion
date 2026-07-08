"""Round-trip tests for outbound BluFi framing/fragmentation in BleMessage.

The outbound frames produced by ``post_contains_data`` must be exactly what
the library's own inbound parser (``parseNotification`` +
``parseBlufiNotifyData``) consumes: a 4-byte header ``[type, frameCtrl,
sequence, dataLen]`` followed by the data section, where fragmented frames
(FRAG bit set) prepend a 2-byte little-endian remaining-content-length prefix
that the parser strips before reassembly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pymammotion.bluetooth.ble_message import FRAG_CONTENT_LEN, MAX_DATA_LEN, BleMessage
from pymammotion.bluetooth.data.framectrldata import FrameCtrlData

CUSTOM_DATA_TYPE = (19 << 2) | 1  # getTypeValue(1, 19) — pkgType=data, subType=custom data
HEADER_LEN = 4


def _make_sender() -> tuple[BleMessage, list[bytes]]:
    """Build a BleMessage whose GATT writes are captured instead of sent."""
    client = MagicMock()
    frames: list[bytes] = []

    async def capture(_uuid, data, _response) -> None:
        frames.append(bytes(data))

    client.write_gatt_char = AsyncMock(side_effect=capture)
    return BleMessage(client), frames


async def _reassemble(frames: list[bytes]) -> bytes | None:
    """Feed captured frames one-by-one into a receiving BleMessage and return the payload."""
    receiver = BleMessage(MagicMock())
    for frame in frames[:-1]:
        assert receiver.parseNotification(frame) == 1  # fragment received, waiting for more
    assert receiver.parseNotification(frames[-1]) == 0  # complete
    return await receiver.parseBlufiNotifyData(return_bytes=True)


async def test_large_payload_round_trips_through_inbound_parser() -> None:
    sender, frames = _make_sender()
    payload = bytes(i % 251 for i in range(700))

    await sender.post_custom_data_bytes(payload)

    assert len(frames) > 1
    assert await _reassemble(frames) == payload


async def test_small_payload_single_frame_format_unchanged() -> None:
    """A ≤255-byte payload keeps the original single-frame wire format: no FRAG bit, no prefix."""
    sender, frames = _make_sender()
    payload = bytes(range(200))

    await sender.post_custom_data_bytes(payload)

    assert len(frames) == 1
    frame = frames[0]
    assert frame[0] == CUSTOM_DATA_TYPE
    assert frame[1] == 0  # frame ctrl: no encrypt/checksum/ack and no FRAG bit
    assert not FrameCtrlData(frame[1]).hasFrag()
    assert frame[2] == 0  # first send sequence
    assert frame[3] == len(payload)
    assert frame[HEADER_LEN:] == payload  # data verbatim — no length prefix

    assert await _reassemble(frames) == payload


async def test_boundary_255_byte_payload_is_single_frame() -> None:
    sender, frames = _make_sender()
    payload = bytes(255)

    await sender.post_custom_data_bytes(payload)

    assert len(frames) == 1
    assert frames[0][3] == MAX_DATA_LEN
    assert not FrameCtrlData(frames[0][1]).hasFrag()
    assert await _reassemble(frames) == payload


async def test_large_payload_fragment_structure() -> None:
    """>255 bytes: all frames written, data-length ≤ 255, FRAG on all but the last."""
    sender, frames = _make_sender()
    total = 700
    payload = bytes(total)

    await sender.post_custom_data_bytes(payload)

    # 700 bytes → 253 + 253 + 194 content bytes → 3 frames
    assert len(frames) == 3
    for index, frame in enumerate(frames):
        data_len = frame[3]
        assert data_len <= MAX_DATA_LEN
        assert len(frame) == HEADER_LEN + data_len  # every frame fully written
        assert frame[0] == CUSTOM_DATA_TYPE
        assert frame[2] == index  # each fragment consumes its own sequence number
        if index < len(frames) - 1:
            assert FrameCtrlData(frame[1]).hasFrag()
            assert data_len == MAX_DATA_LEN
            remaining = int.from_bytes(frame[HEADER_LEN : HEADER_LEN + 2], "little")
            assert remaining == total - index * FRAG_CONTENT_LEN
        else:
            assert not FrameCtrlData(frame[1]).hasFrag()

    content_lengths = [f[3] - 2 if FrameCtrlData(f[1]).hasFrag() else f[3] for f in frames]
    assert sum(content_lengths) == total


async def test_256_byte_payload_splits_into_two_frames() -> None:
    """One byte over the single-frame limit produces exactly two frames."""
    sender, frames = _make_sender()
    payload = bytes(i % 256 for i in range(256))

    await sender.post_custom_data_bytes(payload)

    assert len(frames) == 2
    first, last = frames
    assert FrameCtrlData(first[1]).hasFrag()
    assert first[3] == MAX_DATA_LEN  # 2-byte prefix + 253 content bytes
    assert int.from_bytes(first[HEADER_LEN : HEADER_LEN + 2], "little") == 256
    assert not FrameCtrlData(last[1]).hasFrag()
    assert last[3] == 256 - FRAG_CONTENT_LEN
    assert await _reassemble(frames) == payload
