"""Tests for SVG positioning utilities — verified against APK SvgDataBean / MACommandHelper.

Protocol constants confirmed from APK source:
  sub_cmd=1  ADD    — new tile, data_hash=0 (device assigns)
  sub_cmd=2  ACK    — app acknowledges device-pushed frame, no svg_message body
  sub_cmd=3  UPDATE — replace existing tile using device-assigned hash
  sub_cmd=6  DELETE — remove tile by device-assigned hash

Frame counting: single-frame messages use total_frame=0, current_frame=0.
Pixel dims:     base_width_pix / base_height_pix are always 0 (APK behaviour).
name_count:     must equal len(svg_file_name) (APK: svgFileName.length()).
data_hash ADD:  must be 0 — device assigns the real hash on receipt.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from pymammotion.data.model.hash_list import CommDataCouple, FrameList, HashList, NavGetCommData, SvgMessage
from pymammotion.utility.svg import (
    area_centroid,
    build_svg_ack,
    build_svg_delete,
    build_svg_for_area,
    build_svg_update,
)

# tests/unit/render/ → repo tests/ is parents[2].
FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"

_SIMPLE_SQUARE = [
    CommDataCouple(x=0.0, y=0.0),
    CommDataCouple(x=4.0, y=0.0),
    CommDataCouple(x=4.0, y=6.0),
    CommDataCouple(x=0.0, y=6.0),
]
_SIMPLE_SVG = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="1"/></svg>'
_SVG_NAME = "pattern.svg"


# ---------------------------------------------------------------------------
# area_centroid
# ---------------------------------------------------------------------------


def test_centroid_square():
    cx, cy = area_centroid(_SIMPLE_SQUARE)
    assert cx == pytest.approx(2.0, abs=1e-6)
    assert cy == pytest.approx(3.0, abs=1e-6)


def test_centroid_single_point():
    assert area_centroid([CommDataCouple(x=5.0, y=7.0)]) == (5.0, 7.0)


def test_centroid_empty():
    assert area_centroid([]) == (0.0, 0.0)


def test_centroid_triangle():
    pts = [
        CommDataCouple(x=0.0, y=0.0),
        CommDataCouple(x=3.0, y=0.0),
        CommDataCouple(x=0.0, y=3.0),
    ]
    cx, cy = area_centroid(pts)
    assert cx == pytest.approx(1.0, abs=1e-6)
    assert cy == pytest.approx(1.0, abs=1e-6)


def test_centroid_degenerate_collinear():
    pts = [CommDataCouple(x=float(i), y=0.0) for i in range(5)]
    cx, cy = area_centroid(pts)
    assert cx == pytest.approx(2.0, abs=1e-6)
    assert cy == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# ADD — build_svg_for_area
# Verified against APK PlanMapLandFragment + MACommandHelper.sendSvgDate()
# ---------------------------------------------------------------------------


def test_add_sub_cmd_is_1():
    """APK always sends subCmd=1 for ADD operations."""
    msg = build_svg_for_area(12345, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.sub_cmd == 1


def test_add_data_hash_is_zero():
    """APK sets dataHash=0L on ADD — device assigns the real hash on receipt."""
    msg = build_svg_for_area(12345, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.data_hash == 0


def test_add_paternal_hash_is_area_hash():
    """paternalHashA links the tile to its parent mowing area."""
    area_hash = 8323694340871879373
    msg = build_svg_for_area(area_hash, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.paternal_hash_a == area_hash


def test_add_pver_is_1():
    msg = build_svg_for_area(1, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.pver == 1


def test_add_type_is_13():
    """SVG tiles use type=13 (PathType.SVG)."""
    msg = build_svg_for_area(1, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.type == 13


def test_add_result_is_0():
    msg = build_svg_for_area(1, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.result == 0


def test_add_frame_counts_are_zero():
    """APK uses total_frame=0, current_frame=0 for single-frame SVG messages."""
    msg = build_svg_for_area(1, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.total_frame == 0
    assert msg.current_frame == 0


def test_add_pixel_dims_are_zero():
    """APK sends base_width_pix=0, base_height_pix=0 — device derives from metres."""
    msg = build_svg_for_area(1, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.svg_message.base_width_pix == 0
    assert msg.svg_message.base_height_pix == 0


def test_add_name_count_equals_filename_length():
    """APK: svgDataBean.setName_count(svgFileName.length())."""
    msg = build_svg_for_area(1, _SIMPLE_SQUARE, _SIMPLE_SVG, svg_file_name="circle.svg")
    assert msg.svg_message.name_count == len("circle.svg")


def test_add_data_count_is_zero():
    """APK always sends data_count=0."""
    msg = build_svg_for_area(1, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.svg_message.data_count == 0


def test_add_centre_matches_centroid():
    """x_move/y_move are the polygon centroid, rounded to 3 dp."""
    msg = build_svg_for_area(1, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.svg_message.x_move == pytest.approx(2.0, abs=0.001)
    assert msg.svg_message.y_move == pytest.approx(3.0, abs=0.001)


def test_add_position_rounded_to_3dp():
    """APK uses BaseUtil.keepf(value, 3) — 3 decimal places."""
    pts = [
        CommDataCouple(x=0.0, y=0.0),
        CommDataCouple(x=1.0, y=0.0),
        CommDataCouple(x=1.0, y=1.0),
        CommDataCouple(x=0.0, y=1.0),
    ]
    msg = build_svg_for_area(1, pts, _SIMPLE_SVG)
    # 0.5 is exact; verify no extra precision leaks through
    assert str(msg.svg_message.x_move) == "0.5"
    assert str(msg.svg_message.y_move) == "0.5"


def test_add_svg_content_and_filename_preserved():
    msg = build_svg_for_area(1, _SIMPLE_SQUARE, _SIMPLE_SVG, svg_file_name="star.svg")
    assert msg.svg_message.svg_file_data == _SIMPLE_SVG
    assert msg.svg_message.svg_file_name == "star.svg"


def test_add_scale_and_rotate():
    msg = build_svg_for_area(1, _SIMPLE_SQUARE, _SIMPLE_SVG, scale=2.5, rotate=math.pi / 4)
    assert msg.svg_message.scale == pytest.approx(2.5)
    assert msg.svg_message.rotate == pytest.approx(math.pi / 4)


def test_add_base_dimensions():
    msg = build_svg_for_area(1, _SIMPLE_SQUARE, _SIMPLE_SVG, base_width_m=4.0, base_height_m=4.0)
    assert msg.svg_message.base_width_m == pytest.approx(4.0)
    assert msg.svg_message.base_height_m == pytest.approx(4.0)


def test_add_default_base_dimensions_are_2_5m():
    """Default tile size is 2.5 m (Yuka / Luba 1)."""
    msg = build_svg_for_area(1, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.svg_message.base_width_m == pytest.approx(2.5)
    assert msg.svg_message.base_height_m == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# ACK — build_svg_ack
# APK MACommandHelper.sendResponseSvgDate(): always sub_cmd=2, no svg_message body
# ---------------------------------------------------------------------------

def _make_device_svg_push(data_hash: int = 999, paternal: int = 555, total: int = 3, current: int = 2) -> SvgMessage:
    """Simulate an SVG frame the device pushes to the app."""
    return SvgMessage(
        pver=1,
        sub_cmd=0,  # incoming from device
        total_frame=total,
        current_frame=current,
        data_hash=data_hash,
        paternal_hash_a=paternal,
        type=13,
        result=1,  # device signals ACK required
    )


def test_ack_sub_cmd_is_2():
    """APK sendResponseSvgDate always uses subCmd=2 (fixed)."""
    push = _make_device_svg_push()
    ack = build_svg_ack(push)
    assert ack.sub_cmd == 2


def test_ack_echoes_data_hash():
    push = _make_device_svg_push(data_hash=42)
    assert build_svg_ack(push).data_hash == 42


def test_ack_echoes_paternal_hash():
    push = _make_device_svg_push(paternal=777)
    assert build_svg_ack(push).paternal_hash_a == 777


def test_ack_echoes_frame_counts():
    push = _make_device_svg_push(total=5, current=3)
    ack = build_svg_ack(push)
    assert ack.total_frame == 5
    assert ack.current_frame == 3


def test_ack_has_no_svg_content():
    """ACK carries no svg_message body — APK does not call setSvgMessage()."""
    push = _make_device_svg_push()
    ack = build_svg_ack(push)
    assert ack.svg_message.svg_file_data == ""
    assert ack.svg_message.svg_file_name == ""
    assert ack.svg_message.x_move == 0.0
    assert ack.svg_message.y_move == 0.0


def test_ack_pver_and_type():
    push = _make_device_svg_push()
    ack = build_svg_ack(push)
    assert ack.pver == 1
    assert ack.type == 13
    assert ack.result == 0


# ---------------------------------------------------------------------------
# UPDATE — build_svg_update
# ---------------------------------------------------------------------------


def test_update_sub_cmd_is_3():
    msg = build_svg_update(device_hash=888, area_hash=1, boundary=_SIMPLE_SQUARE, svg_file_data=_SIMPLE_SVG)
    assert msg.sub_cmd == 3


def test_update_uses_device_hash():
    """UPDATE uses the hash the device assigned, not 0."""
    device_hash = 0xDEADBEEF
    msg = build_svg_update(device_hash=device_hash, area_hash=1, boundary=_SIMPLE_SQUARE, svg_file_data=_SIMPLE_SVG)
    assert msg.data_hash == device_hash


def test_update_paternal_hash_preserved():
    area_hash = 99999
    msg = build_svg_update(device_hash=1, area_hash=area_hash, boundary=_SIMPLE_SQUARE, svg_file_data=_SIMPLE_SVG)
    assert msg.paternal_hash_a == area_hash


def test_update_name_count():
    msg = build_svg_update(1, 1, _SIMPLE_SQUARE, _SIMPLE_SVG, svg_file_name="new.svg")
    assert msg.svg_message.name_count == len("new.svg")


def test_update_frame_counts_zero():
    msg = build_svg_update(1, 1, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.total_frame == 0
    assert msg.current_frame == 0


def test_update_recomputes_centroid():
    msg = build_svg_update(1, 1, _SIMPLE_SQUARE, _SIMPLE_SVG)
    assert msg.svg_message.x_move == pytest.approx(2.0, abs=0.001)
    assert msg.svg_message.y_move == pytest.approx(3.0, abs=0.001)


# ---------------------------------------------------------------------------
# DELETE — build_svg_delete
# ---------------------------------------------------------------------------


def test_delete_sub_cmd_is_6():
    msg = build_svg_delete(device_hash=123, area_hash=456)
    assert msg.sub_cmd == 6


def test_delete_uses_device_hash():
    msg = build_svg_delete(device_hash=0xCAFEBABE, area_hash=1)
    assert msg.data_hash == 0xCAFEBABE


def test_delete_paternal_hash_preserved():
    msg = build_svg_delete(device_hash=1, area_hash=77777)
    assert msg.paternal_hash_a == 77777


def test_delete_has_no_svg_content():
    """DELETE carries no svg_message content — just the hash to remove."""
    msg = build_svg_delete(device_hash=1, area_hash=1)
    assert msg.svg_message.svg_file_data == ""
    assert msg.svg_message.svg_file_name == ""
    assert msg.svg_message.x_move == 0.0


def test_delete_frame_counts_zero():
    msg = build_svg_delete(device_hash=1, area_hash=1)
    assert msg.total_frame == 0
    assert msg.current_frame == 0


def test_delete_type_and_pver():
    msg = build_svg_delete(device_hash=1, area_hash=1)
    assert msg.pver == 1
    assert msg.type == 13


# ---------------------------------------------------------------------------
# Proto serialisation round-trip
# ---------------------------------------------------------------------------


def test_add_serialises_to_proto_bytes():
    """build_svg_for_area output can be serialised to proto bytes without error."""
    from pymammotion.proto import MctlNav, SvgMessageAckT, SvgMessageT

    msg = build_svg_for_area(12345, _SIMPLE_SQUARE, _SIMPLE_SVG, svg_file_name="circle.svg")

    proto_msg = MctlNav(
        todev_svg_msg=SvgMessageAckT(
            pver=msg.pver,
            sub_cmd=msg.sub_cmd,
            total_frame=msg.total_frame,
            current_frame=msg.current_frame,
            data_hash=msg.data_hash,
            paternal_hash_a=msg.paternal_hash_a,
            result=msg.result,
            svg_message=SvgMessageT(
                x_move=msg.svg_message.x_move,
                y_move=msg.svg_message.y_move,
                scale=msg.svg_message.scale,
                rotate=msg.svg_message.rotate,
                svg_file_name=msg.svg_message.svg_file_name,
                svg_file_data=msg.svg_message.svg_file_data,
                name_count=msg.svg_message.name_count,
                data_count=msg.svg_message.data_count,
                base_width_m=msg.svg_message.base_width_m,
                base_height_m=msg.svg_message.base_height_m,
                base_width_pix=msg.svg_message.base_width_pix,
                base_height_pix=msg.svg_message.base_height_pix,
            ),
        )
    )
    raw = proto_msg.SerializeToString()
    assert len(raw) > 0

    # Round-trip: deserialise and check key fields
    decoded = MctlNav().parse(raw)
    svg = decoded.todev_svg_msg
    assert svg.sub_cmd == 1
    assert svg.data_hash == 0
    assert svg.paternal_hash_a == 12345
    assert svg.svg_message.name_count == len("circle.svg")
    assert svg.svg_message.x_move == pytest.approx(2.0, abs=0.001)
    assert svg.svg_message.y_move == pytest.approx(3.0, abs=0.001)


def test_delete_serialises_to_proto_bytes():
    from pymammotion.proto import MctlNav, SvgMessageAckT

    msg = build_svg_delete(device_hash=0xDEADBEEF, area_hash=99)
    proto_msg = MctlNav(
        todev_svg_msg=SvgMessageAckT(
            pver=msg.pver,
            sub_cmd=msg.sub_cmd,
            total_frame=msg.total_frame,
            current_frame=msg.current_frame,
            data_hash=msg.data_hash,
            paternal_hash_a=msg.paternal_hash_a,
            result=msg.result,
        )
    )
    raw = proto_msg.SerializeToString()
    decoded = MctlNav().parse(raw)
    assert decoded.todev_svg_msg.sub_cmd == 6
    assert decoded.todev_svg_msg.data_hash == 0xDEADBEEF


# ---------------------------------------------------------------------------
# Integration: real fixture area
# ---------------------------------------------------------------------------


def _load_yuka_hash_list() -> HashList:
    raw = json.loads((FIXTURES_DIR / "yuka_fixture.json").read_text())
    return HashList.from_dict(raw["map"])


def test_svg_centred_in_real_area_correct_fields():
    """Full integration check against real Yuka fixture data."""
    hl = _load_yuka_hash_list()
    area_hash_str, frame_list = next(iter(hl.area.items()))
    area_hash = int(area_hash_str)

    boundary: list[CommDataCouple] = []
    for frame in frame_list.data:
        if isinstance(frame, NavGetCommData):
            boundary.extend(frame.data_couple)

    msg = build_svg_for_area(area_hash, boundary, _SIMPLE_SVG, svg_file_name=_SVG_NAME)

    # Protocol contract
    assert msg.sub_cmd == 1
    assert msg.data_hash == 0
    assert msg.paternal_hash_a == area_hash
    assert msg.pver == 1
    assert msg.type == 13
    assert msg.result == 0
    assert msg.total_frame == 0
    assert msg.current_frame == 0

    # Pixel dims
    assert msg.svg_message.base_width_pix == 0
    assert msg.svg_message.base_height_pix == 0

    # name_count matches filename
    assert msg.svg_message.name_count == len(_SVG_NAME)

    # Centroid inside bounding box
    xs = [p.x for p in boundary]
    ys = [p.y for p in boundary]
    assert min(xs) <= msg.svg_message.x_move <= max(xs)
    assert min(ys) <= msg.svg_message.y_move <= max(ys)


def test_ack_for_real_area_svg():
    """ACK for a device-pushed SVG echoes frame fields, carries no content."""
    push = _make_device_svg_push(data_hash=42, paternal=88, total=2, current=1)
    ack = build_svg_ack(push)

    assert ack.sub_cmd == 2
    assert ack.data_hash == 42
    assert ack.paternal_hash_a == 88
    assert ack.total_frame == 2
    assert ack.current_frame == 1
    assert ack.svg_message.svg_file_data == ""
    assert ack.svg_message.name_count == 0
