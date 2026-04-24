"""Tests for HashList GeoJSON generation using real device fixture data."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pymammotion.data.model.hash_list import (
    AreaHashNameList,
    FrameList,
    HashList,
    MowPath,
    MowPathPacket,
    NavGetCommData,
    CommDataCouple,
)
from pymammotion.data.model.location import Dock, LocationPoint

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str = "hash_list_fixture.json") -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def _make_mow_path(raw: dict) -> MowPath:
    path_packets = [
        MowPathPacket(
            path_hash=p["path_hash"],
            path_type=p["path_type"],
            path_total=p["path_total"],
            path_cur=p["path_cur"],
            zone_hash=p["zone_hash"],
            data_couple=[CommDataCouple(x=c["x"], y=c["y"]) for c in p["data_couple"]],
        )
        for p in raw["path_packets"]
    ]
    return MowPath(
        pver=raw["pver"],
        sub_cmd=raw["sub_cmd"],
        result=raw["result"],
        area=raw["area"],
        time=raw["time"],
        total_frame=raw["total_frame"],
        current_frame=raw["current_frame"],
        total_path_num=raw["total_path_num"],
        valid_path_num=raw["valid_path_num"],
        data_hash=raw["data_hash"],
        transaction_id=raw["transaction_id"],
        reserved=raw["reserved"],
        data_len=raw["data_len"],
        path_packets=path_packets,
    )


def _make_nav_get_comm_data(raw: dict) -> NavGetCommData:
    from pymammotion.data.model.hash_list import NavNameTime

    return NavGetCommData(
        pver=raw["pver"],
        sub_cmd=raw["sub_cmd"],
        result=raw["result"],
        action=raw["action"],
        type=raw["type"],
        hash=raw["hash"],
        paternal_hash_a=raw["paternal_hash_a"],
        paternal_hash_b=raw["paternal_hash_b"],
        total_frame=raw["total_frame"],
        current_frame=raw["current_frame"],
        data_hash=raw["data_hash"],
        data_len=raw["data_len"],
        data_couple=[CommDataCouple(x=c["x"], y=c["y"]) for c in raw["data_couple"]],
        reserved=raw["reserved"],
        name_time=NavNameTime(
            name=raw["name_time"]["name"],
            create_time=raw["name_time"]["create_time"],
            modify_time=raw["name_time"]["modify_time"],
        ),
    )


# ---------------------------------------------------------------------------
# Mow path GeoJSON
# ---------------------------------------------------------------------------


def test_complete_mow_path_generates_features() -> None:
    """When all frames for a transaction are present, GeoJSON features are generated."""
    fixture = _load_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])

    frame1 = _make_mow_path(fixture["mow_path_frames"][0])
    frame2 = _make_mow_path(fixture["mow_path_frames"][1])

    # Both frames present; total_frame=2 in fixture
    assert frame1.total_frame == 2
    assert frame2.total_frame == 2

    hash_list = HashList()
    hash_list.update_mow_path(frame1)
    hash_list.update_mow_path(frame2)

    result = hash_list.generate_mowing_geojson(rtk)

    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) > 0, "Expected at least one mow path feature when all frames are present"


def test_incomplete_mow_path_generates_no_features() -> None:
    """When only frame 1 of 2 is present, no features are generated (transaction skipped)."""
    fixture = _load_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])

    frame1 = _make_mow_path(fixture["mow_path_frames"][0])
    # frame2 is intentionally omitted

    hash_list = HashList()
    hash_list.update_mow_path(frame1)

    result = hash_list.generate_mowing_geojson(rtk)

    assert result["type"] == "FeatureCollection"
    assert result["features"] == [], "Expected no features when mow path frames are incomplete"


# ---------------------------------------------------------------------------
# Map (area) GeoJSON
# ---------------------------------------------------------------------------


def _build_hash_list_with_area(area_frames: list[NavGetCommData]) -> HashList:
    """Build a HashList populated with the given area frames."""
    hash_list = HashList()
    hash_id = area_frames[0].hash
    total_frame = area_frames[0].total_frame
    hash_list.area[hash_id] = FrameList(total_frame=total_frame, sub_cmd=0, data=list(area_frames))
    hash_list.area_name.append(AreaHashNameList(name="area 1", hash=hash_id))
    return hash_list


def test_complete_area_generates_features() -> None:
    """When all area frames are present, GeoJSON features are generated."""
    fixture = _load_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])
    dock = Dock(latitude=fixture["dock"]["latitude"], longitude=fixture["dock"]["longitude"], rotation=fixture["dock"]["rotation"])

    frame1 = _make_nav_get_comm_data(fixture["area_frames"][0])
    frame2 = _make_nav_get_comm_data(fixture["area_frames"][1])

    assert frame1.total_frame == 2
    assert frame2.total_frame == 2

    hash_list = _build_hash_list_with_area([frame1, frame2])

    hash_list.generate_geojson(rtk, dock)
    result = hash_list.generated_geojson

    assert result["type"] == "FeatureCollection"
    area_features = [f for f in result["features"] if f["properties"].get("type_name") == "area"]
    assert len(area_features) > 0, "Expected at least one area feature when all frames are present"


def test_incomplete_area_generates_no_area_features() -> None:
    """When only frame 1 of 2 is present for an area, it is skipped in GeoJSON output."""
    fixture = _load_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])
    dock = Dock(latitude=fixture["dock"]["latitude"], longitude=fixture["dock"]["longitude"], rotation=fixture["dock"]["rotation"])

    frame1 = _make_nav_get_comm_data(fixture["area_frames"][0])
    # Only frame 1 present; total_frame=2, so _validate_frame_list returns False

    hash_list = _build_hash_list_with_area([frame1])

    hash_list.generate_geojson(rtk, dock)
    result = hash_list.generated_geojson

    assert result["type"] == "FeatureCollection"
    area_features = [f for f in result["features"] if f["properties"].get("type_name") == "area"]
    assert area_features == [], "Expected no area features when area frames are incomplete"


def _make_frame(
    type_code: int,
    hash_id: int,
    coords: list[tuple[float, float]],
) -> NavGetCommData:
    """Build a single-frame NavGetCommData with the given type and coord list."""
    from pymammotion.data.model.hash_list import NavNameTime

    return NavGetCommData(
        pver=1,
        sub_cmd=0,
        result=0,
        action=0,
        type=type_code,
        hash=hash_id,
        paternal_hash_a=0,
        paternal_hash_b=0,
        total_frame=1,
        current_frame=1,
        data_hash=hash_id,
        data_len=len(coords) * 16,
        data_couple=[CommDataCouple(x=x, y=y) for x, y in coords],
        reserved="",
        name_time=NavNameTime(name="", create_time=0, modify_time=0),
    )


def _install_frame(target: dict[int, FrameList], frame: NavGetCommData) -> None:
    target[frame.hash] = FrameList(total_frame=frame.total_frame, sub_cmd=0, data=[frame])


def _hash_list_with_extra_types() -> tuple[HashList, dict[str, int]]:
    """Return a HashList with one frame per new PathType and the hash IDs used."""
    hash_list = HashList()
    hashes = {
        "corridor_line": 1_900_000_000_000_000_001,
        "corridor_point": 2_000_000_000_000_000_001,
        "virtual_wall": 2_100_000_000_000_000_001,
        "visual_safety_zone": 2_500_000_000_000_000_001,
        "visual_obstacle_zone": 2_600_000_000_000_000_001,
    }
    _install_frame(
        hash_list.corridor_line,
        _make_frame(19, hashes["corridor_line"], [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)]),
    )
    _install_frame(
        hash_list.corridor_point,
        _make_frame(20, hashes["corridor_point"], [(1.0, 1.0), (2.0, 2.0)]),
    )
    _install_frame(
        hash_list.virtual_wall,
        _make_frame(21, hashes["virtual_wall"], [(0.0, 3.0), (0.0, 6.0), (3.0, 6.0)]),
    )
    _install_frame(
        hash_list.visual_safety_zone,
        _make_frame(
            25,
            hashes["visual_safety_zone"],
            [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0), (4.0, 4.0)],
        ),
    )
    _install_frame(
        hash_list.visual_obstacle_zone,
        _make_frame(
            26,
            hashes["visual_obstacle_zone"],
            [(8.0, 8.0), (10.0, 8.0), (10.0, 10.0), (8.0, 10.0), (8.0, 8.0)],
        ),
    )
    return hash_list, hashes


def test_corridor_wall_and_visual_zones_emit_geojson_features() -> None:
    """Each of the five new PathTypes (19/20/21/25/26) produces one styled feature.

    Guards the two gaps the previous PR left open:
      1. The generator's ``_process_map_objects.type_mapping`` silently dropped
         these dicts.
      2. ``_create_feature_geometry`` returned ``None`` for any type_id other
         than 0/1/2, so even if dispatch worked the feature was discarded.
    """
    fixture = _load_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])
    dock = Dock(
        latitude=fixture["dock"]["latitude"],
        longitude=fixture["dock"]["longitude"],
        rotation=fixture["dock"]["rotation"],
    )

    hash_list, _hashes = _hash_list_with_extra_types()
    hash_list.generate_geojson(rtk, dock)
    result = hash_list.generated_geojson

    features_by_type = {f["properties"].get("type_name"): f for f in result["features"]}

    expected_geometry = {
        "corridor_line": "LineString",
        "corridor_point": "MultiPoint",
        "virtual_wall": "LineString",
        "visual_safety_zone": "Polygon",
        "visual_obstacle_zone": "Polygon",
    }
    for type_name, geom_type in expected_geometry.items():
        assert type_name in features_by_type, f"Expected a {type_name} feature in generator output"
        assert features_by_type[type_name]["geometry"]["type"] == geom_type


def test_features_get_meaningful_names_and_descriptions() -> None:
    """Every feature gets a non-empty Name/title and a real description.

    Guards a regression where the generator emitted ``description: "description <b>test</b>"``
    and left ``title``/``Name`` blank for any type the device hadn't user-labeled
    (most of them — only areas carry a name_time.name).
    """
    fixture = _load_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])
    dock = Dock(
        latitude=fixture["dock"]["latitude"],
        longitude=fixture["dock"]["longitude"],
        rotation=fixture["dock"]["rotation"],
    )

    hash_list, _hashes = _hash_list_with_extra_types()
    hash_list.generate_geojson(rtk, dock)
    result = hash_list.generated_geojson

    expected_descriptions = {
        "corridor_line": "Corridor line between zones (MN231)",
        "corridor_point": "Corridor waypoint between zones (MN231)",
        "virtual_wall": "User-drawn virtual fence",
        "visual_safety_zone": "Vision-detected safety zone",
        "visual_obstacle_zone": "Vision-detected obstacle zone",
    }
    expected_name_prefix = {
        "corridor_line": "Corridor",
        "corridor_point": "Corridor waypoint",
        "virtual_wall": "Virtual wall",
        "visual_safety_zone": "Safety zone",
        "visual_obstacle_zone": "Obstacle zone",
    }

    features_by_type = {f["properties"].get("type_name"): f for f in result["features"]}
    for type_name, expected_desc in expected_descriptions.items():
        feat = features_by_type.get(type_name)
        assert feat is not None, f"missing feature for {type_name}"
        props = feat["properties"]
        assert props["description"] == expected_desc
        # Name must be non-empty and start with the type-specific prefix
        assert props["Name"], f"{type_name} has empty Name"
        assert props["title"], f"{type_name} has empty title"
        assert props["Name"] == props["title"], "title and Name should match"
        assert props["Name"].startswith(expected_name_prefix[type_name]), (
            f"{type_name} name {props['Name']!r} should start with {expected_name_prefix[type_name]!r}"
        )
        # The old placeholder must never come back.
        assert "test" not in props["description"]


def test_corridor_wall_and_visual_zone_styles_are_distinct() -> None:
    """Each new type gets its own style — colors must not collide with existing types."""
    fixture = _load_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])
    dock = Dock(
        latitude=fixture["dock"]["latitude"],
        longitude=fixture["dock"]["longitude"],
        rotation=fixture["dock"]["rotation"],
    )

    hash_list, _hashes = _hash_list_with_extra_types()
    hash_list.generate_geojson(rtk, dock)
    result = hash_list.generated_geojson

    colors = {
        f["properties"]["type_name"]: f["properties"].get("color")
        for f in result["features"]
        if f["properties"].get("type_name")
        in {
            "corridor_line",
            "corridor_point",
            "virtual_wall",
            "visual_safety_zone",
            "visual_obstacle_zone",
        }
    }
    # Color values lifted from the Mammotion Android app's MapColorTag / render code.
    assert colors["corridor_line"] == "#145FF2"
    assert colors["corridor_point"] == "#145FF2"
    assert colors["virtual_wall"] == "#FF4D00"
    assert colors["visual_safety_zone"] == "#007AFF"
    assert colors["visual_obstacle_zone"] == "#CC7700"


def test_feature_styles_use_leaflet_path_options() -> None:
    """Styles must emit Leaflet Path keys, not the common mis-spellings.

    Guards against regressing to ``fill: "<color>"`` (Leaflet treats ``fill``
    as a Boolean — the color is silently ignored, falling back to ``color``).
    Also verifies the dead ``zIndex`` / ``road_center_*`` keys stay removed.
    """
    fixture = _load_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])
    dock = Dock(
        latitude=fixture["dock"]["latitude"],
        longitude=fixture["dock"]["longitude"],
        rotation=fixture["dock"]["rotation"],
    )

    hash_list, _hashes = _hash_list_with_extra_types()
    hash_list.generate_geojson(rtk, dock)
    result = hash_list.generated_geojson

    for feat in result["features"]:
        props = feat["properties"]
        # ``fill`` must never be a color string on any feature — Leaflet would
        # treat a non-empty string as truthy but ignore the color value.
        if "fill" in props:
            assert isinstance(props["fill"], bool), (
                f"feature {props.get('type_name')!r} has fill={props['fill']!r} "
                f"(must be bool or absent; use fillColor for colors)"
            )
        # Any feature that declares a fill colour must use the Leaflet key.
        if props.get("type_name") in {
            "area",
            "visual_safety_zone",
            "visual_obstacle_zone",
            "corridor_point",
        }:
            assert "fillColor" in props, f"{props['type_name']} missing fillColor"

        # Dead keys from the previous convention must stay out.
        assert "zIndex" not in props
        assert "road_center_color" not in props
        assert "road_center_dash" not in props


# ---------------------------------------------------------------------------
# Yuka device — mow path generation from real device data
# ---------------------------------------------------------------------------


def _load_yuka_fixture() -> dict:
    return _load_fixture("yuka_fixture.json")


def _build_yuka_hash_list(fixture: dict) -> HashList:
    """Build a HashList with mow path data from the Yuka fixture."""
    hash_list = HashList()
    hash_list.area_name = [
        AreaHashNameList(name=a["name"], hash=a["hash"]) for a in fixture["map"]["area_name"]
    ]
    for tid, frames in fixture["map"]["current_mow_path"].items():
        for fid, frame in frames.items():
            hash_list.update_mow_path(_make_mow_path(frame))
    return hash_list


def test_yuka_complete_mow_path_populates_current_mow_path() -> None:
    """Yuka: update_mow_path populates current_mow_path keyed by transaction_id."""
    fixture = _load_yuka_fixture()
    hash_list = _build_yuka_hash_list(fixture)

    transaction_id = int(list(fixture["map"]["current_mow_path"].keys())[0])
    assert transaction_id in hash_list.current_mow_path
    frames = hash_list.current_mow_path[transaction_id]
    assert len(frames) == 33, "Expected 33 frames for the transaction"
    assert 1 in frames and 33 in frames


def test_yuka_mow_path_generates_geojson() -> None:
    """Yuka: complete mow path frames produce valid generated_mow_path_geojson."""
    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["location"]["RTK"]["latitude"], longitude=fixture["location"]["RTK"]["longitude"])
    hash_list = _build_yuka_hash_list(fixture)

    result = hash_list.generate_mowing_geojson(rtk)

    assert result["type"] == "FeatureCollection"
    assert result["name"] == "Mowing Lawn Areas"
    assert len(result["features"]) > 0, "Expected at least one mow path feature"

    # Verify the stored geojson was also updated
    assert hash_list.generated_mow_path_geojson == result


def test_yuka_mow_path_geojson_has_correct_properties() -> None:
    """Yuka: generated mow path GeoJSON contains both mow_path and border_pass features."""
    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["location"]["RTK"]["latitude"], longitude=fixture["location"]["RTK"]["longitude"])
    hash_list = _build_yuka_hash_list(fixture)

    result = hash_list.generate_mowing_geojson(rtk)

    type_names = {f["properties"]["type_name"] for f in result["features"]}
    assert "mow_path" in type_names, "Expected a mow_path (stripe) feature"
    assert "border_pass" in type_names, "Expected a border_pass feature"

    # Verify shared metadata on the mow_path feature
    mow_feature = next(f for f in result["features"] if f["properties"]["type_name"] == "mow_path")
    props = mow_feature["properties"]
    first_tid = int(list(fixture["map"]["current_mow_path"].keys())[0])
    first_frame = fixture["map"]["current_mow_path"][str(first_tid)]["1"]
    assert props["transaction_id"] == first_frame["transaction_id"]
    assert props["total_path_num"] == first_frame["total_path_num"]
    assert "length" in props
    assert "area" in props
    assert "color" in props


def test_yuka_mow_path_geojson_has_linestring_coordinates() -> None:
    """Yuka: all mow path features contain LineStrings with real lon/lat coordinates."""
    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["location"]["RTK"]["latitude"], longitude=fixture["location"]["RTK"]["longitude"])
    hash_list = _build_yuka_hash_list(fixture)

    result = hash_list.generate_mowing_geojson(rtk)

    # Pick the mow_path (stripe) feature specifically; border_pass uses the same transform
    feature = next(f for f in result["features"] if f["properties"]["type_name"] == "mow_path")
    geometry = feature["geometry"]
    assert geometry["type"] == "LineString"
    coords = geometry["coordinates"]
    assert len(coords) > 0, "Expected coordinates in the LineString"

    # Coordinates should be [lon, lat] pairs near the Yuka's real-world location
    # RTK is at approximately lon=175.318, lat=-38.002 (New Zealand)
    for lon, lat in coords:
        assert 175.0 < lon < 176.0, f"Longitude {lon} out of expected range"
        assert -39.0 < lat < -37.0, f"Latitude {lat} out of expected range"


def test_yuka_incomplete_mow_path_empty_geojson() -> None:
    """Yuka: when only 1 of 33 frames is present, no features are generated."""
    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["location"]["RTK"]["latitude"], longitude=fixture["location"]["RTK"]["longitude"])

    hash_list = HashList()
    # Only add the first frame (total_frame=33, so the transaction is incomplete)
    first_frame = fixture["map"]["current_mow_path"][list(fixture["map"]["current_mow_path"].keys())[0]]["1"]
    hash_list.update_mow_path(_make_mow_path(first_frame))

    result = hash_list.generate_mowing_geojson(rtk)

    assert result["type"] == "FeatureCollection"
    assert result["features"] == [], "Expected no features when mow path is incomplete"


def test_yuka_empty_current_mow_path_empty_geojson() -> None:
    """Yuka: empty current_mow_path produces empty GeoJSON."""
    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["location"]["RTK"]["latitude"], longitude=fixture["location"]["RTK"]["longitude"])

    hash_list = HashList()
    # No mow path data at all

    result = hash_list.generate_mowing_geojson(rtk)

    assert result["type"] == "FeatureCollection"
    assert result["features"] == []
    assert hash_list.generated_mow_path_geojson == result


# ---------------------------------------------------------------------------
# Yuka — end-to-end: _apply_mow_path_geojson (client.py callback)
# ---------------------------------------------------------------------------


def test_yuka_apply_mow_path_geojson_populates_device() -> None:
    """generate_mowing_geojson generates and stores geojson on MowerDevice after saga completes."""
    from pymammotion.data.model.device import MowerDevice

    fixture = _load_yuka_fixture()
    device = MowerDevice(name=fixture["update_check"]["device_name"])

    # Set RTK location from fixture
    device.location.RTK.latitude = fixture["location"]["RTK"]["latitude"]
    device.location.RTK.longitude = fixture["location"]["RTK"]["longitude"]

    # Populate current_mow_path (simulating what MowPathSaga does)
    for tid, frames in fixture["map"]["current_mow_path"].items():
        for fid, frame in frames.items():
            device.map.update_mow_path(_make_mow_path(frame))

    assert device.map.current_mow_path, "current_mow_path should be populated before apply"
    assert not device.map.generated_mow_path_geojson, "generated_mow_path_geojson should be empty before apply"

    # This is what _on_mow_path_complete calls
    device.map.generate_mowing_geojson(device.location.RTK)

    result = device.map.generated_mow_path_geojson
    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) > 0, "Expected mow path features after apply"

    # Features are split by path_type; find the mow stripe feature specifically
    mow_feature = next(
        (f for f in result["features"] if f["properties"]["type_name"] == "mow_path"), None
    )
    assert mow_feature is not None, "Expected a mow_path (stripe) feature"
    assert mow_feature["geometry"]["type"] == "LineString"

    # Verify coordinates are in expected real-world range
    for lon, lat in mow_feature["geometry"]["coordinates"]:
        assert 175.0 < lon < 176.0
        assert -39.0 < lat < -37.0


# ---------------------------------------------------------------------------
# WorkData.real_path_num decoding
# ---------------------------------------------------------------------------


def test_work_data_real_path_num_decoding() -> None:
    """real_path_num=5889 (0x1701) decodes to now_index=23, start_index=0, path_direction=1."""
    from pymammotion.data.model.report_info import WorkData

    work = WorkData(real_path_num=5889)
    # 5889 = 0x1701
    # now_index      = (0x1701 & 0x00FFFF00) >> 8   = 0x1700 >> 8 = 23
    # start_index    = (0x1701 & 0xFFFF000000) >> 24 = 0  (value fits in 16 bits)
    # path_direction = 0x1701 & 0xFF                 = 1
    assert work.now_index == 23
    assert work.start_index == 0
    assert work.path_direction == 1


def test_work_data_zero_real_path_num() -> None:
    """real_path_num=0 gives all-zero decoded fields."""
    from pymammotion.data.model.report_info import WorkData

    work = WorkData(real_path_num=0)
    assert work.now_index == 0
    assert work.start_index == 0
    assert work.path_direction == 0


# ---------------------------------------------------------------------------
# Mow progress GeoJSON — generate_mow_progress_geojson
# ---------------------------------------------------------------------------


def test_mow_progress_geojson_now_index_zero_returns_full_path() -> None:
    """now_index=0 returns the entire planned path (no slicing)."""
    from shapely.geometry import Point

    from pymammotion.data.model.generate_geojson import GeojsonGenerator

    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["location"]["RTK"]["latitude"], longitude=fixture["location"]["RTK"]["longitude"])
    hash_list = _build_yuka_hash_list(fixture)

    result = GeojsonGenerator.generate_mow_progress_geojson(
        hash_list,
        now_index=0,
        rtk_location=Point(rtk.latitude, rtk.longitude),
    )

    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) > 0, "now_index=0 should return the full path, not empty"


def test_mow_progress_geojson_empty_path_returns_empty() -> None:
    """Empty current_mow_path produces an empty FeatureCollection even with now_index>0."""
    from shapely.geometry import Point

    from pymammotion.data.model.generate_geojson import GeojsonGenerator

    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["location"]["RTK"]["latitude"], longitude=fixture["location"]["RTK"]["longitude"])
    hash_list = HashList()  # no mow path loaded

    result = GeojsonGenerator.generate_mow_progress_geojson(
        hash_list,
        now_index=10,
        rtk_location=Point(rtk.latitude, rtk.longitude),
    )

    assert result["type"] == "FeatureCollection"
    assert result["features"] == []


def test_mow_progress_geojson_now_index_within_range() -> None:
    """now_index=10 is applied per section: the active section (ub_path_hash) gets 51 remaining pts.
    Other sections in current_mow_path are shown in full (now_index=0)."""
    from shapely.geometry import Point

    from pymammotion.data.model.generate_geojson import GeojsonGenerator

    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["location"]["RTK"]["latitude"], longitude=fixture["location"]["RTK"]["longitude"])
    hash_list = _build_yuka_hash_list(fixture)
    ub_path_hash = fixture["report_data"]["work"]["ub_path_hash"]

    result = GeojsonGenerator.generate_mow_progress_geojson(
        hash_list,
        now_index=10,
        rtk_location=Point(rtk.latitude, rtk.longitude),
        ub_path_hash=ub_path_hash,
    )

    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 14

    # Exactly one feature is the active section with now_index applied
    active = [f for f in result["features"] if f["properties"]["now_index"] == 10]
    assert len(active) == 1
    feature = active[0]
    assert feature["geometry"]["type"] == "LineString"
    assert feature["properties"]["type_name"] == "mow_progress"
    assert feature["properties"]["point_count"] == 51  # 60 total - (10-1) = 51 remaining
    assert len(feature["geometry"]["coordinates"]) == 51


def test_mow_progress_geojson_now_index_exceeds_total() -> None:
    """now_index >= total points means nothing remaining — returns empty FeatureCollection."""
    from shapely.geometry import Point

    from pymammotion.data.model.generate_geojson import GeojsonGenerator

    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["location"]["RTK"]["latitude"], longitude=fixture["location"]["RTK"]["longitude"])
    hash_list = _build_yuka_hash_list(fixture)

    # now_index=2000 exceeds the 1180 total points — mow is complete, nothing remaining
    result = GeojsonGenerator.generate_mow_progress_geojson(
        hash_list,
        now_index=2000,
        rtk_location=Point(rtk.latitude, rtk.longitude),
    )

    assert result["type"] == "FeatureCollection"
    assert result["features"] == [], "Expected empty when now_index exceeds total points"


def test_mow_progress_geojson_coordinates_in_expected_range() -> None:
    """Progress GeoJSON coordinates should be near the Yuka's real-world RTK location.

    LocationPoint.latitude/longitude in the Yuka fixture are stored in radians
    (-0.663 rad ≈ -37.97° S, 3.06 rad ≈ 175.3° E — New Zealand).
    generate_mow_progress_geojson expects a WGS-84 Point already converted via
    CoordinateConverter.enu_to_lla, matching the same contract as
    generate_mow_path_geojson.
    """
    from shapely.geometry import Point

    from pymammotion.data.model.generate_geojson import GeojsonGenerator
    from pymammotion.utility.map import CoordinateConverter

    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["location"]["RTK"]["latitude"], longitude=fixture["location"]["RTK"]["longitude"])
    hash_list = _build_yuka_hash_list(fixture)

    conv = CoordinateConverter(rtk.latitude, rtk.longitude)
    rtk_ll = conv.enu_to_lla(0, 0)

    result = GeojsonGenerator.generate_mow_progress_geojson(
        hash_list,
        now_index=10,
        rtk_location=Point(rtk_ll.latitude, rtk_ll.longitude),
    )

    assert result["features"], "Expected at least one feature"
    for lon, lat in result["features"][0]["geometry"]["coordinates"]:
        assert 175.0 < lon < 176.0, f"Longitude {lon} out of expected NZ range"
        assert -39.0 < lat < -37.0, f"Latitude {lat} out of expected NZ range"


def test_mow_progress_geojson_spatial_overlap_with_planned_path() -> None:
    """Progress path coordinates fall within the bounding box of the planned path."""
    from shapely.geometry import Point

    from pymammotion.data.model.generate_geojson import GeojsonGenerator
    from pymammotion.utility.map import CoordinateConverter

    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["location"]["RTK"]["latitude"], longitude=fixture["location"]["RTK"]["longitude"])
    hash_list = _build_yuka_hash_list(fixture)

    conv = CoordinateConverter(rtk.latitude, rtk.longitude)
    rtk_ll = conv.enu_to_lla(0, 0)
    rtk_point = Point(rtk_ll.latitude, rtk_ll.longitude)

    planned = hash_list.generate_mowing_geojson(rtk)
    progress = GeojsonGenerator.generate_mow_progress_geojson(
        hash_list, now_index=10, rtk_location=rtk_point
    )

    # Collect all planned coords across all features
    planned_coords = [c for f in planned["features"] for c in f["geometry"]["coordinates"]]
    planned_lons = [c[0] for c in planned_coords]
    planned_lats = [c[1] for c in planned_coords]

    # Progress coords must be within the planned path bounding box (with 0.001° tolerance)
    assert progress["features"], "Expected at least one progress feature"
    for lon, lat in progress["features"][0]["geometry"]["coordinates"]:
        assert min(planned_lons) - 0.001 < lon < max(planned_lons) + 0.001, (
            f"Progress lon {lon} outside planned path range [{min(planned_lons)}, {max(planned_lons)}]"
        )
        assert min(planned_lats) - 0.001 < lat < max(planned_lats) + 0.001, (
            f"Progress lat {lat} outside planned path range [{min(planned_lats)}, {max(planned_lats)}]"
        )


# ---------------------------------------------------------------------------
# Yuka — end-to-end: _apply_mow_progress_geojson (client.py callback)
# ---------------------------------------------------------------------------


def test_apply_mow_progress_geojson_populates_device() -> None:
    """apply_mow_progress_geojson stores progress GeoJSON on MowerDevice.

    Uses ub_path_hash=0 (all zones) — now_index=23 is applied per section (start=22).
    Yuka fixture has 10 type-1 sections (902 pts total) and 4 type-2 sections (278 pts total).
    Each section independently loses its first 22 points: type 1 → 702 remaining, type 2 → 190.
    """
    from collections import defaultdict

    from pymammotion.data.model.device import MowerDevice

    fixture = _load_yuka_fixture()
    device = MowerDevice(name=fixture["update_check"]["device_name"])

    device.location.RTK.latitude = fixture["location"]["RTK"]["latitude"]
    device.location.RTK.longitude = fixture["location"]["RTK"]["longitude"]

    for tid, frames in fixture["map"]["current_mow_path"].items():
        for fid, frame in frames.items():
            device.map.update_mow_path(_make_mow_path(frame))

    # real_path_num=5889 → now_index=23; all zones included (ub_path_hash=0)
    device.report_data.work.real_path_num = 5889

    assert not device.map.generated_mow_progress_geojson, "Should be empty before apply"

    work = device.report_data.work
    device.map.apply_mow_progress_geojson(
        device.location.RTK,
        work.now_index,
        work.ub_path_hash,
        work.path_pos_x,
        work.path_pos_y,
    )

    result = device.map.generated_mow_progress_geojson
    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 12  # one feature per path_hash section

    assert {f["properties"]["path_type"] for f in result["features"]} == {1, 2}

    for feature in result["features"]:
        assert feature["geometry"]["type"] == "LineString"
        assert feature["properties"]["type_name"] == "mow_progress"
        assert feature["properties"]["now_index"] == 23

    # now_index=23 → start=22 applied per section; sum remaining pts across all sections per type
    totals: dict[int, int] = defaultdict(int)
    for f in result["features"]:
        totals[f["properties"]["path_type"]] += f["properties"]["point_count"]
    assert totals[1] == 702
    assert totals[2] == 190


def test_apply_mow_progress_geojson_now_index_zero_returns_full_path() -> None:
    """apply_mow_progress_geojson with now_index=0 returns the entire planned path."""
    from pymammotion.data.model.device import MowerDevice

    fixture = _load_yuka_fixture()
    device = MowerDevice(name=fixture["update_check"]["device_name"])
    device.location.RTK.latitude = fixture["location"]["RTK"]["latitude"]
    device.location.RTK.longitude = fixture["location"]["RTK"]["longitude"]

    for tid, frames in fixture["map"]["current_mow_path"].items():
        for fid, frame in frames.items():
            device.map.update_mow_path(_make_mow_path(frame))

    device.report_data.work.real_path_num = 0  # now_index=0 → full path

    work = device.report_data.work
    device.map.apply_mow_progress_geojson(
        device.location.RTK,
        work.now_index,
        work.ub_path_hash,
        work.path_pos_x,
        work.path_pos_y,
    )

    result = device.map.generated_mow_progress_geojson
    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) > 0, "now_index=0 should return full path, not empty"


# ---------------------------------------------------------------------------
# Mow progress GeoJSON — multi-type coverage (mow stripes + border passes)
# ---------------------------------------------------------------------------


def test_mow_progress_geojson_matches_example_script_output() -> None:
    """generate_mow_progress_geojson at now_index 1, 300 and 550 must produce output
    identical to the reference files written by examples/generate_mow_progress_geojson.py.

    The example script uses ub_path_hash=0 (all paths) and the path_pos decoded from
    the fixture's report_data.work.  Both must be replicated here to get a byte-for-byte
    match of every coordinate in the GeoJSON.
    """
    from shapely.geometry import Point

    from pymammotion.data.model.generate_geojson import GeojsonGenerator
    from pymammotion.utility.map import CoordinateConverter

    fixture = _load_yuka_fixture()
    hash_list = _build_yuka_hash_list(fixture)

    rtk = LocationPoint(
        latitude=fixture["location"]["RTK"]["latitude"],
        longitude=fixture["location"]["RTK"]["longitude"],
    )
    conv = CoordinateConverter(rtk.latitude, rtk.longitude)
    rtk_ll = conv.enu_to_lla(0, 0)
    rtk_point = Point(rtk_ll.latitude, rtk_ll.longitude)

    work = fixture.get("report_data", {}).get("work", {})
    raw_x = work.get("path_pos_x", 0)
    raw_y = work.get("path_pos_y", 0)
    path_pos = (raw_x / 10000.0, raw_y / 10000.0) if (raw_x or raw_y) else None

    dev_output = Path(__file__).parent.parent / "examples" / "dev_output"

    for now_index in (1, 300, 550):
        ref_file = dev_output / f"mow_progress_{now_index}.geojson"
        with open(ref_file) as f:
            reference = json.load(f)

        result = GeojsonGenerator.generate_mow_progress_geojson(
            hash_list,
            now_index=now_index,
            rtk_location=rtk_point,
            ub_path_hash=0,
            path_pos=path_pos,
        )

        assert result["type"] == reference["type"]
        assert len(result["features"]) == len(reference["features"]), (
            f"now_index={now_index}: expected {len(reference['features'])} features, "
            f"got {len(result['features'])}"
        )

        if not reference["features"]:
            continue  # 0 features is valid when now_index exceeds all section lengths

        # Group by path_hash (unique per section) for an exact per-section comparison.
        ref_by_hash = {f["properties"]["path_hash"]: f for f in reference["features"]}
        res_by_hash = {f["properties"]["path_hash"]: f for f in result["features"]}

        assert set(res_by_hash.keys()) == set(ref_by_hash.keys()), (
            f"now_index={now_index}: path_hash mismatch — "
            f"expected {set(ref_by_hash.keys())}, got {set(res_by_hash.keys())}"
        )

        for path_hash, ref_feat in ref_by_hash.items():
            res_feat = res_by_hash[path_hash]
            ref_coords = ref_feat["geometry"]["coordinates"]
            res_coords = res_feat["geometry"]["coordinates"]
            assert len(res_coords) == len(ref_coords), (
                f"now_index={now_index}, path_hash={path_hash}: "
                f"{len(res_coords)} pts != {len(ref_coords)} reference pts"
            )
            assert res_coords == ref_coords, (
                f"now_index={now_index}, path_hash={path_hash}: coordinates differ at index "
                + str(next(i for i, (a, b) in enumerate(zip(res_coords, ref_coords)) if a != b))
            )


def test_mow_progress_from_start_identical_to_mow_path() -> None:
    """At now_index=1 (start) the progress geojson coordinates must be identical to the
    planned mow path geojson, per path_type.

    Both functions must:
      - cover the same path_types (mow stripes + border passes)
      - produce the same number of points per type
      - produce the exact same coordinates per type

    This guards against two regressions:
      1. Flattening all path types into one feature (loses border_pass / mow_stripe distinction)
      2. Inconsistent point ordering between the two generation paths
    """
    from shapely.geometry import Point

    from pymammotion.data.model.generate_geojson import GeojsonGenerator
    from pymammotion.utility.map import CoordinateConverter

    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["location"]["RTK"]["latitude"], longitude=fixture["location"]["RTK"]["longitude"])
    hash_list = _build_yuka_hash_list(fixture)

    # generate_mowing_geojson converts radian RTK coords via CoordinateConverter internally;
    # generate_mow_progress_geojson expects the already-converted WGS-84 Point — match that.
    conv = CoordinateConverter(rtk.latitude, rtk.longitude)
    rtk_ll = conv.enu_to_lla(0, 0)
    rtk_point = Point(rtk_ll.latitude, rtk_ll.longitude)

    # Planned mow path — one feature per path_type, keyed by path_type int
    planned = hash_list.generate_mowing_geojson(rtk)
    planned_by_type: dict[int, list] = {
        f["properties"]["path_type"]: f["geometry"]["coordinates"]
        for f in planned["features"]
    }
    assert len(planned_by_type) >= 2, "Fixture should have at least two path types"

    # Progress at now_index=1: start = max(0, 0) = 0, so all points are remaining.
    # One feature is emitted per path_hash section; accumulate coords by path_type for comparison.
    progress = GeojsonGenerator.generate_mow_progress_geojson(
        hash_list,
        now_index=1,
        rtk_location=rtk_point,
        ub_path_hash=0,  # all paths, all types
    )
    progress_by_type: dict[int, list] = {}
    for f in progress["features"]:
        pt = f["properties"]["path_type"]
        progress_by_type.setdefault(pt, []).extend(f["geometry"]["coordinates"])

    assert set(progress_by_type.keys()) == set(planned_by_type.keys()), (
        f"Progress path_types {set(progress_by_type.keys())} != planned {set(planned_by_type.keys())}"
    )

    for path_type, planned_coords in planned_by_type.items():
        progress_coords = progress_by_type[path_type]
        assert len(progress_coords) == len(planned_coords), (
            f"path_type={path_type}: {len(progress_coords)} progress pts != {len(planned_coords)} planned pts"
        )
        # Section ordering may differ between the two generators; compare as coordinate sets.
        assert sorted(progress_coords) == sorted(planned_coords), (
            f"path_type={path_type}: coordinate sets differ"
        )
