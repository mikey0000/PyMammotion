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


# ---------------------------------------------------------------------------
# Yuka device — mow path generation from real device data
# ---------------------------------------------------------------------------


def _load_yuka_fixture() -> dict:
    return _load_fixture("yuka_fixture.json")


def _build_yuka_hash_list(fixture: dict) -> HashList:
    """Build a HashList with mow path data from the Yuka fixture."""
    hash_list = HashList()
    hash_list.area_name = [
        AreaHashNameList(name=a["name"], hash=a["hash"]) for a in fixture["area_names"]
    ]
    for raw_frame in fixture["mow_path_frames"]:
        mow_path = _make_mow_path(raw_frame)
        hash_list.update_mow_path(mow_path)
    return hash_list


def test_yuka_complete_mow_path_populates_current_mow_path() -> None:
    """Yuka: update_mow_path populates current_mow_path keyed by transaction_id."""
    fixture = _load_yuka_fixture()
    hash_list = _build_yuka_hash_list(fixture)

    transaction_id = fixture["mow_path_frames"][0]["transaction_id"]
    assert transaction_id in hash_list.current_mow_path
    frames = hash_list.current_mow_path[transaction_id]
    assert len(frames) == 2, "Expected 2 frames for the transaction"
    assert 1 in frames and 2 in frames


def test_yuka_mow_path_generates_geojson() -> None:
    """Yuka: complete mow path frames produce valid generated_mow_path_geojson."""
    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])
    hash_list = _build_yuka_hash_list(fixture)

    result = hash_list.generate_mowing_geojson(rtk)

    assert result["type"] == "FeatureCollection"
    assert result["name"] == "Mowing Lawn Areas"
    assert len(result["features"]) > 0, "Expected at least one mow path feature"

    # Verify the stored geojson was also updated
    assert hash_list.generated_mow_path_geojson == result


def test_yuka_mow_path_geojson_has_correct_properties() -> None:
    """Yuka: generated mow path feature has expected metadata properties."""
    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])
    hash_list = _build_yuka_hash_list(fixture)

    result = hash_list.generate_mowing_geojson(rtk)

    feature = result["features"][0]
    props = feature["properties"]
    assert props["type_name"] == "mow_path"
    assert props["transaction_id"] == fixture["mow_path_frames"][0]["transaction_id"]
    assert props["total_path_num"] == fixture["mow_path_frames"][0]["total_path_num"]
    assert "length" in props
    assert "area" in props
    assert "color" in props


def test_yuka_mow_path_geojson_has_linestring_coordinates() -> None:
    """Yuka: generated mow path feature contains a LineString with real lon/lat coordinates."""
    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])
    hash_list = _build_yuka_hash_list(fixture)

    result = hash_list.generate_mowing_geojson(rtk)

    feature = result["features"][0]
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
    """Yuka: when only 1 of 2 frames is present, no features are generated."""
    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])

    hash_list = HashList()
    # Only add the first frame
    frame1 = _make_mow_path(fixture["mow_path_frames"][0])
    hash_list.update_mow_path(frame1)

    result = hash_list.generate_mowing_geojson(rtk)

    assert result["type"] == "FeatureCollection"
    assert result["features"] == [], "Expected no features when mow path is incomplete"


def test_yuka_empty_current_mow_path_empty_geojson() -> None:
    """Yuka: empty current_mow_path produces empty GeoJSON."""
    fixture = _load_yuka_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])

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
    """_apply_mow_path_geojson generates and stores geojson on MowingDevice after saga completes."""
    from pymammotion.client import _apply_mow_path_geojson
    from pymammotion.data.model.device import MowingDevice

    fixture = _load_yuka_fixture()
    device = MowingDevice(name=fixture["device_name"])

    # Set RTK location from fixture
    device.location.RTK.latitude = fixture["rtk"]["latitude"]
    device.location.RTK.longitude = fixture["rtk"]["longitude"]

    # Populate current_mow_path (simulating what MowPathSaga does)
    for raw_frame in fixture["mow_path_frames"]:
        mow_path = _make_mow_path(raw_frame)
        device.map.update_mow_path(mow_path)

    assert device.map.current_mow_path, "current_mow_path should be populated before apply"
    assert not device.map.generated_mow_path_geojson, "generated_mow_path_geojson should be empty before apply"

    # This is what _on_mow_path_complete calls
    _apply_mow_path_geojson(device)

    result = device.map.generated_mow_path_geojson
    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) > 0, "Expected mow path features after apply"

    feature = result["features"][0]
    assert feature["geometry"]["type"] == "LineString"
    assert feature["properties"]["type_name"] == "mow_path"

    # Verify coordinates are in expected real-world range
    for lon, lat in feature["geometry"]["coordinates"]:
        assert 175.0 < lon < 176.0
        assert -39.0 < lat < -37.0
