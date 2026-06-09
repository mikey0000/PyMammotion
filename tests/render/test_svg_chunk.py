"""Unit tests for pymammotion.utility.svg.chunk_svg_messages.

Edge cases covered
------------------
* Empty svg_file_data → single frame (total_frame=0, current_frame=0).
* Data ≤ chunk_size → single frame.
* Data exactly == chunk_size → single frame (boundary).
* Data == chunk_size + 1 → two frames.
* Data fits exactly N * chunk_size → N frames, last frame full.
* Data spans N * chunk_size + remainder → N+1 frames, last frame short.
* Single-frame: total_frame=0, current_frame=0 (APK convention).
* Multi-frame: 1-based current_frame, total_frame == len(result).
* data_count set to chunk_size on every frame.
* All non-data fields preserved unchanged across every frame.
* Input SvgMessage is never mutated.
* Re-joining all frame svg_file_data reproduces the original string.
* Custom chunk_size parameter is respected.
"""

from __future__ import annotations

import dataclasses

import pytest

from pymammotion.data.model.hash_list import SvgMessage, SvgMessageData
from pymammotion.utility.svg import _SVG_CHUNK_SIZE, chunk_svg_messages


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msg(data: str = "", *, chunk_size_hint: int = _SVG_CHUNK_SIZE) -> SvgMessage:
    """Return an SvgMessage with the given svg_file_data and sentinel fields."""
    return SvgMessage(
        pver=1,
        sub_cmd=1,
        total_frame=0,
        current_frame=0,
        data_hash=0,
        paternal_hash_a=999,
        type=13,
        result=0,
        svg_message=SvgMessageData(
            x_move=1.5,
            y_move=2.5,
            scale=1.0,
            rotate=0.5,
            base_width_m=2.5,
            base_height_m=2.5,
            base_width_pix=0,
            base_height_pix=0,
            name_count=11,
            data_count=0,
            svg_file_name="pattern.svg",
            svg_file_data=data,
        ),
    )


def _sentinel_fields_preserved(original: SvgMessage, frame: SvgMessage) -> None:
    """Assert all non-chunking fields are unchanged on *frame*."""
    assert frame.pver == original.pver
    assert frame.sub_cmd == original.sub_cmd
    assert frame.data_hash == original.data_hash
    assert frame.paternal_hash_a == original.paternal_hash_a
    assert frame.type == original.type
    assert frame.result == original.result
    assert frame.svg_message.x_move == original.svg_message.x_move
    assert frame.svg_message.y_move == original.svg_message.y_move
    assert frame.svg_message.scale == original.svg_message.scale
    assert frame.svg_message.rotate == original.svg_message.rotate
    assert frame.svg_message.base_width_m == original.svg_message.base_width_m
    assert frame.svg_message.base_height_m == original.svg_message.base_height_m
    assert frame.svg_message.name_count == original.svg_message.name_count
    assert frame.svg_message.svg_file_name == original.svg_message.svg_file_name


# ---------------------------------------------------------------------------
# Tests: single-frame cases
# ---------------------------------------------------------------------------


class TestSingleFrame:
    def test_empty_data_is_single_frame(self) -> None:
        msg = _make_msg("")
        result = chunk_svg_messages(msg)
        assert len(result) == 1

    def test_empty_data_frame_convention(self) -> None:
        result = chunk_svg_messages(_make_msg(""))
        assert result[0].total_frame == 0
        assert result[0].current_frame == 0

    def test_short_data_is_single_frame(self) -> None:
        result = chunk_svg_messages(_make_msg("x" * 100))
        assert len(result) == 1

    def test_data_exactly_chunk_size_is_single_frame(self) -> None:
        result = chunk_svg_messages(_make_msg("a" * _SVG_CHUNK_SIZE))
        assert len(result) == 1

    def test_single_frame_has_zero_total_and_current(self) -> None:
        result = chunk_svg_messages(_make_msg("hello"))
        assert result[0].total_frame == 0
        assert result[0].current_frame == 0

    def test_single_frame_data_count_is_chunk_size(self) -> None:
        result = chunk_svg_messages(_make_msg("hello"))
        assert result[0].svg_message.data_count == _SVG_CHUNK_SIZE

    def test_single_frame_svg_file_data_unchanged(self) -> None:
        data = "short svg"
        result = chunk_svg_messages(_make_msg(data))
        assert result[0].svg_message.svg_file_data == data

    def test_single_frame_sentinel_fields_preserved(self) -> None:
        msg = _make_msg("tiny")
        _sentinel_fields_preserved(msg, chunk_svg_messages(msg)[0])


# ---------------------------------------------------------------------------
# Tests: multi-frame cases
# ---------------------------------------------------------------------------


class TestMultiFrame:
    def test_chunk_size_plus_one_gives_two_frames(self) -> None:
        result = chunk_svg_messages(_make_msg("z" * (_SVG_CHUNK_SIZE + 1)))
        assert len(result) == 2

    def test_exact_multiple_gives_correct_count(self) -> None:
        result = chunk_svg_messages(_make_msg("a" * (_SVG_CHUNK_SIZE * 3)))
        assert len(result) == 3

    def test_partial_last_chunk_counted(self) -> None:
        result = chunk_svg_messages(_make_msg("b" * (_SVG_CHUNK_SIZE * 2 + 1)))
        assert len(result) == 3

    def test_current_frame_is_one_based(self) -> None:
        result = chunk_svg_messages(_make_msg("c" * (_SVG_CHUNK_SIZE + 1)))
        assert result[0].current_frame == 1
        assert result[1].current_frame == 2

    def test_total_frame_equals_frame_count(self) -> None:
        n = 4
        result = chunk_svg_messages(_make_msg("d" * (_SVG_CHUNK_SIZE * n - 1)))
        for frame in result:
            assert frame.total_frame == len(result)

    def test_data_count_is_chunk_size_on_every_frame(self) -> None:
        result = chunk_svg_messages(_make_msg("e" * (_SVG_CHUNK_SIZE * 3 + 7)))
        for frame in result:
            assert frame.svg_message.data_count == _SVG_CHUNK_SIZE

    def test_reassembled_data_matches_original(self) -> None:
        original = "f" * (_SVG_CHUNK_SIZE * 2 + 250)
        result = chunk_svg_messages(_make_msg(original))
        reassembled = "".join(f.svg_message.svg_file_data for f in result)
        assert reassembled == original

    def test_last_frame_may_be_shorter(self) -> None:
        remainder = 123
        result = chunk_svg_messages(_make_msg("g" * (_SVG_CHUNK_SIZE + remainder)))
        assert len(result[-1].svg_message.svg_file_data) == remainder

    def test_all_non_data_fields_preserved_on_every_frame(self) -> None:
        msg = _make_msg("h" * (_SVG_CHUNK_SIZE * 3))
        result = chunk_svg_messages(msg)
        for frame in result:
            _sentinel_fields_preserved(msg, frame)

    def test_five_frames_sequential_numbering(self) -> None:
        result = chunk_svg_messages(_make_msg("i" * (_SVG_CHUNK_SIZE * 5)))
        numbers = [f.current_frame for f in result]
        assert numbers == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Tests: immutability
# ---------------------------------------------------------------------------


class TestNoMutation:
    def test_input_message_not_mutated_single_frame(self) -> None:
        msg = _make_msg("original data")
        original_data = msg.svg_message.svg_file_data
        original_data_count = msg.svg_message.data_count
        _ = chunk_svg_messages(msg)
        assert msg.svg_message.svg_file_data == original_data
        assert msg.svg_message.data_count == original_data_count

    def test_input_message_not_mutated_multi_frame(self) -> None:
        data = "x" * (_SVG_CHUNK_SIZE * 2 + 100)
        msg = _make_msg(data)
        _ = chunk_svg_messages(msg)
        assert msg.svg_message.svg_file_data == data
        assert msg.total_frame == 0
        assert msg.current_frame == 0
        assert msg.svg_message.data_count == 0


# ---------------------------------------------------------------------------
# Tests: custom chunk_size
# ---------------------------------------------------------------------------


class TestCustomChunkSize:
    def test_custom_small_chunk_size(self) -> None:
        result = chunk_svg_messages(_make_msg("abcdefghij"), chunk_size=3)
        # 10 chars / 3 = 3 full + 1 remainder = 4 frames
        assert len(result) == 4

    def test_custom_chunk_size_used_as_data_count(self) -> None:
        result = chunk_svg_messages(_make_msg("hello world"), chunk_size=4)
        for frame in result:
            assert frame.svg_message.data_count == 4

    def test_custom_chunk_reassembles_correctly(self) -> None:
        original = "abcdefghijklmnopqrstuvwxyz"
        result = chunk_svg_messages(_make_msg(original), chunk_size=7)
        reassembled = "".join(f.svg_message.svg_file_data for f in result)
        assert reassembled == original

    def test_single_frame_when_data_fits_custom_size(self) -> None:
        result = chunk_svg_messages(_make_msg("hi"), chunk_size=10)
        assert len(result) == 1
        assert result[0].total_frame == 0
        assert result[0].current_frame == 0
