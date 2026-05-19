"""Regression test for SvgMessage misrouting into HashList.area.

SvgMessage.type is always 0, which matches PathType.AREA. Before the fix,
HashList.update() dispatched on type alone and stored SvgMessage frames in
self.area instead of self.svg. The fix routes all SvgMessage instances
directly to self.svg before any type-based dispatch.
"""

from __future__ import annotations

from shapely import Point

from pymammotion.data.model.generate_geojson import GeojsonGenerator
from pymammotion.data.model.hash_list import (
    CommDataCouple,
    FrameList,
    HashList,
    NavGetCommData,
    NavNameTime,
    SvgMessage,
    SvgMessageData,
)


def _make_svg_frame(data_hash: int, current_frame: int = 1, total_frame: int = 1) -> SvgMessage:
    return SvgMessage(
        sub_cmd=1,
        type=0,  # always 0 — must not drive routing
        data_hash=data_hash,
        paternal_hash_a=7095723005866681215,
        total_frame=total_frame,
        current_frame=current_frame,
        svg_message=SvgMessageData(),
    )


class TestSvgMessageRouting:
    def test_svg_frame_stored_in_svg_not_area(self) -> None:
        hl = HashList()
        frame = _make_svg_frame(data_hash=99)
        hl.update(frame)
        assert 99 in hl.svg
        assert not hl.area

    def test_svg_frame_with_zero_data_hash_stored_in_svg(self) -> None:
        """data_hash=0 was one of the bad keys appearing in area — must go to svg."""
        hl = HashList()
        frame = _make_svg_frame(data_hash=0)
        hl.update(frame)
        assert 0 in hl.svg
        assert not hl.area

    def test_svg_multiframe_accumulated_in_svg(self) -> None:
        hl = HashList()
        for i in range(1, 4):
            hl.update(_make_svg_frame(data_hash=0, current_frame=i, total_frame=3))
        assert len(hl.svg[0].data) == 3
        assert not hl.area

    def test_area_frame_still_routed_to_area(self) -> None:
        """Ensure the SvgMessage early-return does not affect NavGetCommData routing."""
        hl = HashList()
        frame = NavGetCommData(
            type=0,
            hash=42,
            total_frame=1,
            current_frame=1,
            name_time=NavNameTime(name="Front"),
            data_couple=[CommDataCouple(x=1.0, y=2.0)],
        )
        hl.update(frame)
        assert 42 in hl.area
        assert not hl.svg


SVG_HASH = 5477816201920812051
AREA_HASH = 42


def _make_svg_with_geometry(data_hash: int) -> SvgMessage:
    """Build an SvgMessage whose bounding box is non-degenerate (scale > 0, dimensions > 0)."""
    return SvgMessage(
        sub_cmd=1,
        type=0,
        data_hash=data_hash,
        paternal_hash_a=7095723005866681215,
        total_frame=1,
        current_frame=1,
        svg_message=SvgMessageData(
            x_move=10.0,
            y_move=5.0,
            scale=1.0,
            rotate=0.0,
            base_width_m=20.0,
            base_height_m=15.0,
            svg_file_name="garden.svg",
        ),
    )


def _make_area_frame(hash_val: int) -> NavGetCommData:
    return NavGetCommData(
        type=0,
        hash=hash_val,
        total_frame=1,
        current_frame=1,
        name_time=NavNameTime(name="Front"),
        data_couple=[CommDataCouple(x=1.0, y=2.0)],
    )


class TestSvgGeojsonIntegration:
    """Verify that the geojson builder reads SVG data from hash_list.svg."""

    def test_svg_in_svg_dict_produces_geojson_feature(self) -> None:
        """A valid SvgMessage in hash_list.svg must appear as a Polygon feature."""
        hl = HashList()
        hl.update(_make_svg_with_geometry(SVG_HASH))

        rtk = Point(51.5, 4.5)  # (lat, lon) — shapely Point convention used by GeojsonGenerator
        geo_json: dict = {"type": "FeatureCollection", "name": "test", "features": []}
        GeojsonGenerator._process_svg_map_objects(hl, rtk, geo_json, yaw=0.0)

        svg_features = [f for f in geo_json["features"] if f["properties"].get("type_name") == "svg"]
        assert len(svg_features) == 1
        feat = svg_features[0]
        assert feat["geometry"]["type"] == "Polygon"
        assert feat["properties"]["hash"] == SVG_HASH
        assert feat["properties"]["title"] == "garden.svg"

    def test_misrouted_svg_in_area_is_not_in_geojson_features(self) -> None:
        """An SvgMessage previously misrouted into hash_list.area must not produce an svg feature.

        _collect_frame_coordinates skips non-NavGetCommData frames, so the misrouted entry
        also won't corrupt area polygon rendering.  This test confirms the boundary.
        """
        hl = HashList()
        # Simulate old saved state: SvgMessage stored directly in area under its data_hash key
        hl.area[SVG_HASH] = FrameList(data=[_make_svg_with_geometry(SVG_HASH)])

        rtk = Point(51.5, 4.5)
        geo_json: dict = {"type": "FeatureCollection", "name": "test", "features": []}
        GeojsonGenerator._process_svg_map_objects(hl, rtk, geo_json, yaw=0.0)

        # svg dict is empty → no svg features generated
        assert not geo_json["features"]
        # area still holds the contaminated entry (cleanup is via update_hash_lists)
        assert SVG_HASH in hl.area

    def test_update_hash_lists_removes_misrouted_svg_from_area(self) -> None:
        """update_hash_lists() prunes area entries whose hash is not in the device area hashlist.

        When the real area hashlist arrives (containing only legitimate area hashes),
        the SVG hash that was incorrectly stored in area gets dropped.
        """
        hl = HashList()
        # Contaminated state: SVG hash and a real area hash both in area
        hl.area[SVG_HASH] = FrameList(data=[_make_svg_with_geometry(SVG_HASH)])
        hl.area[AREA_HASH] = FrameList(data=[_make_area_frame(AREA_HASH)])

        # Device area hashlist contains only the real area hash, not the SVG hash
        hl.update_hash_lists(hashlist=[AREA_HASH])

        assert SVG_HASH not in hl.area, "misrouted SVG entry must be purged by update_hash_lists"
        assert AREA_HASH in hl.area, "legitimate area entry must be preserved"

    def test_full_round_trip_svg_routed_correctly_produces_geojson_feature(self) -> None:
        """Full round-trip using update(): svg entry lands in svg dict and produces a geojson feature.

        The fix to HashList.update() routes SvgMessage via isinstance check before type dispatch,
        so hl.svg is populated and hl.area stays clean.  _process_svg_map_objects then reads from
        hl.svg to produce one Polygon feature per tile.
        """
        hl = HashList()
        # Real area frame alongside the svg frame — both go through update()
        hl.update(_make_area_frame(AREA_HASH))
        hl.update(_make_svg_with_geometry(SVG_HASH))

        assert SVG_HASH not in hl.area, "update() must not route SvgMessage into area"
        assert AREA_HASH in hl.area
        assert SVG_HASH in hl.svg

        rtk = Point(51.5, 4.5)
        geo_json: dict = {"type": "FeatureCollection", "name": "test", "features": []}
        GeojsonGenerator._process_svg_map_objects(hl, rtk, geo_json, yaw=0.0)

        svg_features = [f for f in geo_json["features"] if f["properties"].get("type_name") == "svg"]
        assert len(svg_features) == 1
        assert svg_features[0]["properties"]["hash"] == SVG_HASH
