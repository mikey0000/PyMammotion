"""Generate mow-progress GeoJSON from a yuka/device fixture file.

Usage
-----
    uv run python examples/generate_mow_progress_geojson.py [FIXTURE] [NOW_INDEX] [UB_PATH_HASH] [OUTPUT]

Arguments (all optional, positional):
    FIXTURE       Path to a JSON fixture file (default: tests/fixtures/yuka_fixture.json)
    NOW_INDEX     Current path position index, e.g. from real_path_num decoding (default: 23)
    UB_PATH_HASH  Path hash to filter packets by; 0 = include all packets (default: 0)
    OUTPUT        Output GeoJSON file path (default: examples/dev_output/mow_progress.geojson)

Examples
--------
    # Use defaults (Yuka fixture, now_index=23, all packets)
    uv run python examples/generate_mow_progress_geojson.py

    # Custom fixture and index
    uv run python examples/generate_mow_progress_geojson.py my_fixture.json 50

    # Filter by a specific ub_path_hash
    uv run python examples/generate_mow_progress_geojson.py my_fixture.json 23 2205094020499805439

    # Write to a custom output path
    uv run python examples/generate_mow_progress_geojson.py my_fixture.json 23 0 /tmp/progress.geojson

"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from shapely.geometry import Point

from pymammotion.data.model.generate_geojson import GeojsonGenerator
from pymammotion.data.model.hash_list import AreaHashNameList, CommDataCouple, HashList, MowPath, MowPathPacket
from pymammotion.data.model.location import LocationPoint
from pymammotion.utility.map import CoordinateConverter

# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------

args = sys.argv[1:]
fixture_path = Path(args[0]) if len(args) > 0 else Path("tests/fixtures/yuka_fixture.json")
_cli_now_index = int(args[1]) if len(args) > 1 else None
_cli_ub_path_hash = int(args[2]) if len(args) > 2 else None
output_path = Path(args[3]) if len(args) > 3 else Path("examples/dev_output/mow_progress.geojson")

# ---------------------------------------------------------------------------
# Load fixture
# ---------------------------------------------------------------------------

with open(fixture_path) as f:
    fixture = json.load(f)

# ---------------------------------------------------------------------------
# Build HashList from fixture — supports the full MowingDevice JSON format
# (fixture["map"]["current_mow_path"]) as well as the legacy flat list format
# (fixture["mow_path_frames"]).
# ---------------------------------------------------------------------------


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


hash_list = HashList()

if "map" in fixture:
    # Full MowingDevice JSON (new format)
    area_name_list = fixture["map"].get("area_name", [])
    hash_list.area_name = [AreaHashNameList(name=a["name"], hash=a["hash"]) for a in area_name_list]
    for tid, frames in fixture["map"].get("current_mow_path", {}).items():
        for fid, frame in frames.items():
            hash_list.update_mow_path(_make_mow_path(frame))
else:
    # Legacy flat list format
    hash_list.area_name = [AreaHashNameList(name=a["name"], hash=a["hash"]) for a in fixture.get("area_names", [])]
    for raw_frame in fixture.get("mow_path_frames", []):
        hash_list.update_mow_path(_make_mow_path(raw_frame))

# ---------------------------------------------------------------------------
# RTK location — fixture stores radians; convert to WGS-84 degrees
# Supports both new format (fixture["location"]["RTK"]) and legacy (fixture["rtk"])
# ---------------------------------------------------------------------------

rtk_raw = fixture.get("location", {}).get("RTK") or fixture.get("rtk", {})
rtk_lat_rad = rtk_raw["latitude"]
rtk_lon_rad = rtk_raw["longitude"]

import math

# Detect radians: valid lat/lon degrees are in [-180, 180].  Values outside
# that range, or abs(lat) > π/2 for degrees, indicate radians.
if abs(rtk_lat_rad) <= math.pi and abs(rtk_lon_rad) <= math.pi * 2 and abs(rtk_lat_rad) < 1.6:
    # Likely radians — use CoordinateConverter to get WGS-84 origin
    conv = CoordinateConverter(rtk_lat_rad, rtk_lon_rad)
    rtk_ll = conv.enu_to_lla(0, 0)
    rtk_deg_lat = rtk_ll.latitude
    rtk_deg_lon = rtk_ll.longitude
    print(f"RTK (radians): lat={rtk_lat_rad}, lon={rtk_lon_rad}")
else:
    rtk_deg_lat = rtk_lat_rad
    rtk_deg_lon = rtk_lon_rad

rtk_loc = LocationPoint(latitude=rtk_lat_rad, longitude=rtk_lon_rad)
rtk_point = Point(rtk_deg_lat, rtk_deg_lon)
print(f"RTK (degrees): lat={rtk_deg_lat:.6f}, lon={rtk_deg_lon:.6f}")

# ---------------------------------------------------------------------------
# Resolve now_index and ub_path_hash — CLI args override fixture values
# ---------------------------------------------------------------------------

_work = fixture.get("report_data", {}).get("work", {})
real_path_num = _work.get("real_path_num", 0)
_fixture_now_index = (real_path_num & 0x00FFFF00) >> 8
# ub_path_hash=0 means include all paths/types — the fixture's work.ub_path_hash is the
# currently-active segment only, not the full map, so default to 0 for full-map output.
_fixture_ub_path_hash = int(_work.get("ub_path_hash", 0))

now_index = _cli_now_index if _cli_now_index is not None else _fixture_now_index
ub_path_hash = _cli_ub_path_hash if _cli_ub_path_hash is not None else 0

# Decode exact device position (raw int ÷ 10000 → ENU metres), matching APK logic.
_raw_path_pos_x = _work.get("path_pos_x", 0)
_raw_path_pos_y = _work.get("path_pos_y", 0)
path_pos_x = _raw_path_pos_x / 10000.0
path_pos_y = _raw_path_pos_y / 10000.0
path_pos = (path_pos_x, path_pos_y) if (_raw_path_pos_x or _raw_path_pos_y) else None

if _cli_now_index is None:
    print(f"now_index={now_index} (decoded from real_path_num={real_path_num})")
if _cli_ub_path_hash is None:
    print(f"ub_path_hash=0 (all paths; active segment from fixture: {_fixture_ub_path_hash})")
if path_pos:
    print(f"path_pos=({path_pos_x:.4f}m, {path_pos_y:.4f}m) (from fixture report_data.work.path_pos_x/y)")

# ---------------------------------------------------------------------------
# Summarise what's in current_mow_path
# ---------------------------------------------------------------------------

total_packets = 0
total_points = 0
matching_points_by_type: dict[int, int] = {}
for tid, frames in hash_list.current_mow_path.items():
    for fidx, mow_path in frames.items():
        for pkt in mow_path.path_packets:
            total_packets += 1
            total_points += len(pkt.data_couple)
            if ub_path_hash == 0 or pkt.path_hash == ub_path_hash:
                matching_points_by_type[pkt.path_type] = (
                    matching_points_by_type.get(pkt.path_type, 0) + len(pkt.data_couple)
                )

matching_total = sum(matching_points_by_type.values())
print(f"\nPackets: {total_packets}  total points: {total_points}  "
      f"matching ub_path_hash={ub_path_hash}: {matching_total}")
for pt, cnt in sorted(matching_points_by_type.items()):
    print(f"  path_type={pt}: {cnt} pts")
print(f"now_index={now_index}  →  remaining per type: "
      + ", ".join(f"type {pt}: {max(0, cnt - max(0, now_index - 1))}" for pt, cnt in sorted(matching_points_by_type.items())))

# ---------------------------------------------------------------------------
# Generate planned and progress GeoJSON
# ---------------------------------------------------------------------------

planned = hash_list.generate_mowing_geojson(rtk_loc)
progress = GeojsonGenerator.generate_mow_progress_geojson(
    hash_list,
    now_index=now_index,
    rtk_location=rtk_point,
    ub_path_hash=ub_path_hash,
    path_pos=path_pos,
)

# ---------------------------------------------------------------------------
# Print summary
# ---------------------------------------------------------------------------

print("\n=== Planned mow path features ===")
for feat in planned["features"]:
    t = feat["properties"]["type_name"]
    coords = feat["geometry"]["coordinates"]
    print(f"  [{t}]  {len(coords)} pts  first={coords[0]}  last={coords[-1]}")

print("\n=== Mow progress features ===")
if not progress["features"]:
    print("  (empty — now_index=0 or no matching path data)")
for feat in progress["features"]:
    coords = feat["geometry"]["coordinates"]
    props = feat["properties"]
    print(f"  [path_type={props['path_type']}]  {props['point_count']} pts "
          f"(of {props['total_points']} total, now_index={props['now_index']})")
    print(f"  first={coords[0]}  last={coords[-1]}")
    print(f"  length={props['length']:.3f} m")

# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------

output_path.parent.mkdir(parents=True, exist_ok=True)
with open(output_path, "w") as f:
    json.dump(progress, f, indent=2)

print(f"\nWritten to: {output_path}")
