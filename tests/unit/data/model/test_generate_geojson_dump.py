"""GeoJSON output for PathType 12 (DUMP / grass-collection point)."""
from __future__ import annotations

import json
from pathlib import Path

from pymammotion.data.model.generate_geojson import GeojsonGenerator, apply_area_geojson
from pymammotion.data.model.hash_list import (
    CommDataCouple,
    FrameList,
    HashList,
    NavGetCommData,
    NavNameTime,
)
from pymammotion.data.model.location import Dock, LocationPoint

# tests/unit/data/model/ → repo tests/ is parents[3].
FIXTURES_DIR = Path(__file__).parents[3] / "fixtures"


def _load_fixture(name: str = "hash_list_fixture.json") -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def _hash_list_with_dump_type() -> tuple[HashList, int]:
    """Return a HashList with one type=12 (DUMP / grass-collection point) frame and its hash ID."""
    hash_list = HashList()
    dump_hash = 1_200_000_000_000_000_001
    frame = NavGetCommData(
        pver=1,
        sub_cmd=0,
        result=0,
        action=0,
        type=12,
        hash=dump_hash,
        paternal_hash_a=0,
        paternal_hash_b=0,
        total_frame=1,
        current_frame=1,
        data_hash=dump_hash,
        data_len=16,
        data_couple=[CommDataCouple(x=2.0, y=3.0)],
        reserved="",
        name_time=NavNameTime(name="", create_time=1, modify_time=1),
    )
    hash_list.dump[dump_hash] = FrameList(total_frame=1, sub_cmd=0, data=[frame])
    return hash_list, dump_hash


def test_dump_type_emits_a_point_geojson_feature() -> None:
    """PathType 12 (DUMP / grass-collection point): I.40 wired this into both the
    ``type_mapping`` dispatch (already present) and ``_create_feature_geometry``
    (previously missing — every dump frame was silently dropped, returning None).
    """
    fixture = _load_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])
    dock = Dock(
        latitude=fixture["dock"]["latitude"],
        longitude=fixture["dock"]["longitude"],
        rotation=fixture["dock"]["rotation"],
    )

    hash_list, dump_hash = _hash_list_with_dump_type()
    apply_area_geojson(hash_list, rtk, dock)
    result = hash_list.generated_geojson

    dump_features = [f for f in result["features"] if f["properties"].get("type_name") == "dump"]
    assert len(dump_features) == 1
    feature = dump_features[0]
    assert feature["geometry"]["type"] == "Point"
    assert len(feature["geometry"]["coordinates"]) == 2  # a single [lon, lat] pair, not nested
    assert feature["properties"]["hash"] == dump_hash
    assert feature["properties"]["type_id"] == 12


def test_dump_feature_gets_meaningful_name_and_description() -> None:
    fixture = _load_fixture()
    rtk = LocationPoint(latitude=fixture["rtk"]["latitude"], longitude=fixture["rtk"]["longitude"])
    dock = Dock(
        latitude=fixture["dock"]["latitude"],
        longitude=fixture["dock"]["longitude"],
        rotation=fixture["dock"]["rotation"],
    )

    hash_list, _dump_hash = _hash_list_with_dump_type()
    apply_area_geojson(hash_list, rtk, dock)
    result = hash_list.generated_geojson

    feature = next(f for f in result["features"] if f["properties"].get("type_name") == "dump")
    props = feature["properties"]
    assert props["description"] == "Clippings dump zone"
    assert props["Name"] == props["title"] == "Dump zone 1"


def test_dump_type_with_no_coordinates_returns_no_feature() -> None:
    """An empty data_couple (no position at all) must be dropped, not crash on
    an out-of-range coordinate index."""
    geometry = GeojsonGenerator._create_feature_geometry(12, [], {})  # noqa: SLF001
    assert geometry is None
