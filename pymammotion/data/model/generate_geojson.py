import json
import logging
import math
from typing import Any

from shapely.geometry import Point

from pymammotion.data.model.hash_list import (
    AreaHashNameList,
    CommDataCouple,
    FrameList,
    HashList,
    MowPath,
    MowPathPacket,
    NavGetCommData,
)

logger = logging.getLogger(__name__)


GEOMETRY_TYPES: list[str] = ["Polygon", "Polygon", "LineString", "Point"]
MAP_OBJECT_TYPES: list[str] = ["area", "path", "obstacle", "dump"]

image_path = "/local/community/ha-mammotion-assets/dist/assets/map/"

RTK_IMAGE = {
    "iconImage": "map_icon_base_station_rtk.webp",
    "iconSize": [30, 30],
    "iconAnchor": [15, 30],
    "iconUrl": f"{image_path}map_icon_base_station_rtk.webp",
}

DOCK_IMAGE = {
    "iconImage": "icon_map_recharge.webp",
    "iconSize": [30, 30],
    "iconAnchor": [15, 15],
    "iconUrl": f"{image_path}icon_map_recharge.webp",
}

#############################
# STYLE CONFIGURATION
#############################

DOCK_STYLE = {"color": "lightgray", "fill": "lightgray", "weight": 2, "opacity": 1.0, "fillOpacity": 0.7, "radius": 10}

RTK_STYLE = {"color": "purple", "fill": "purple", "weight": 2, "opacity": 1.0, "fillOpacity": 0.7, "radius": 7}

AREA_STYLE = {
    "color": "green",
    "fill": "darkgreen",
    "weight": 3,
    "opacity": 0.8,
    "fillOpacity": 0.3,
    "dashArray": "",
    "lineCap": "round",
    "lineJoin": "round",
}

OBSTACLE_STYLE = {
    "color": "#FF4D00",
    "fill": "darkorange",
    "weight": 2,
    "opacity": 0.9,
    "fillOpacity": 0.4,
    "dashArray": "",
    "lineCap": "round",
    "lineJoin": "round",
}

PATH_STYLE = {
    "color": "#ffffff",
    "weight": 8,
    "opacity": 1.0,
    "zIndex": -1,
    "dashArray": "",
    "lineCap": "round",
    "lineJoin": "round",
    "road_center_color": "#696969",
    "road_center_dash": "8, 8",
}

POINT_STYLE = {"color": "blue", "fill": "lightblue", "weight": 2, "opacity": 1.0, "fillOpacity": 0.7, "radius": 5}

DYNAMICS_LINE_STYLE = {
    "color": "#FFD700",  # gold — visually distinct from the planned green mow path
    "weight": 3,
    "opacity": 0.9,
    "dashArray": "",
    "lineCap": "round",
    "lineJoin": "round",
}

MOW_PROGRESS_STYLE = {
    "color": "#00FF7F",  # spring green — overlaid on the planned path to show completed portion
    "weight": 3,
    "opacity": 0.9,
    "dashArray": "",
    "lineCap": "round",
    "lineJoin": "round",
}

# path_type=0: main mow stripes (弓 arch pattern)
MOW_STRIPE_STYLE = {
    "color": "green",
    "weight": 2,
    "opacity": 0.9,
    "dashArray": "",
    "lineCap": "round",
    "lineJoin": "round",
}

# path_type=2: border/perimeter passes (回 circular pattern) — APK renders these on
# a separate TRACK_ANAMORPHOSIS_SOURCE1 layer with a different visual treatment
BORDER_PASS_STYLE = {
    "color": "#00BFFF",  # deep sky blue — distinguishable from mow stripes
    "weight": 2,
    "opacity": 0.9,
    "dashArray": "6, 4",
    "lineCap": "round",
    "lineJoin": "round",
}

geojson_metadata = {"name": "Lawn Areas", "description": "Generated from Mammotion diagnostics data"}

# Map type IDs — these match PathType enum values from NavGetCommData.type
TYPE_MOWING_ZONE: int = 0
TYPE_OBSTACLE: int = 1
TYPE_PATH: int = 2

# Coordinate conversion constants
METERS_PER_DEGREE: int = 111320

# Type aliases
Coordinate = tuple[float, float]
CoordinateList = list[list[float]]
GeoJSONFeature = dict[str, Any]
GeoJSONCollection = dict[str, Any]
LocationDict = dict[str, Coordinate]

# Path to mammotion integration diagnostics file
geometry_types: list[str] = GEOMETRY_TYPES


class GeojsonGenerator:
    """Class for logging GeoJSON data."""

    @staticmethod
    def is_overlapping(p: Point, placed_points: list[Point], min_distance: float = 0.00005) -> bool:
        """Check if point p is too close to any previously placed label."""
        return any(p.distance(existing) < min_distance for existing in placed_points)

    @staticmethod
    def apply_meter_offsets(lon: float, lat: float, lon_offset: float, lat_offset: float) -> list[float]:
        """Apply meter-based offsets to coordinates (in degrees)"""
        new_lon = lon + (lon_offset / (METERS_PER_DEGREE * math.cos(math.radians(lat))))
        new_lat = lat + (lat_offset / METERS_PER_DEGREE)
        return [new_lon, new_lat]

    @staticmethod
    def generate_geojson(
        hash_list: HashList, rtk_location: Point, dock_location: Point, dock_rotation: int
    ) -> GeoJSONCollection:
        """Generate GeoJSON from hash list data.

        Args:
            hash_list: HashList object containing map data
            rtk_location: Tuple of (longitude, latitude) for rtk position
            :param hash_list:
            :param rtk_location:
            :param dock_rotation:
            :param dock_location:

        """
        area_names = GeojsonGenerator._build_area_name_lookup(hash_list.area_name)

        geo_json: GeoJSONCollection = {"type": "FeatureCollection", "name": "Lawn Areas", "features": []}
        GeojsonGenerator._add_rtk_and_dock(rtk_location, dock_location, dock_rotation, geo_json)
        total_frames = GeojsonGenerator._process_map_objects(hash_list, rtk_location, area_names, geo_json)

        # _save_geojson(geo_json)
        return geo_json

    @staticmethod
    def generate_mow_path_geojson(hash_list: HashList, rtk_location: Point) -> GeoJSONCollection:
        """Generate GeoJSON from hash list data."""
        geo_json: GeoJSONCollection = {"type": "FeatureCollection", "name": "Mowing Lawn Areas", "features": []}

        total_frames = GeojsonGenerator._process_mow_map_objects(hash_list, rtk_location, geo_json)
        return geo_json

    @staticmethod
    def generate_dynamics_line_geojson(dynamics_line: list[CommDataCouple], rtk_location: Point) -> GeoJSONCollection:
        """Generate a GeoJSON FeatureCollection from the live mow-progress path.

        Converts the raw ``list[CommDataCouple]`` (device-local x/y metres) to
        a single GeoJSON ``LineString`` feature in WGS-84 lon/lat, using the
        same RTK-origin coordinate transform used for all other map objects.

        The resulting feature has ``type_name = "dynamics_line"`` and is styled
        in gold so it is visually distinct from the planned mow-path (green).

        Args:
            dynamics_line: Assembled path points from ``HashList.dynamics_line``.
            rtk_location:  Shapely ``Point(latitude, longitude)`` for the RTK
                           base station — the origin of the device coordinate
                           system.

        Returns:
            GeoJSON FeatureCollection with zero or one LineString features.
            Zero features when *dynamics_line* has fewer than two points.

        """
        geo_json: GeoJSONCollection = {
            "type": "FeatureCollection",
            "name": "Mow Progress Path",
            "features": [],
        }

        if len(dynamics_line) < 2:
            return geo_json

        # Convert local x/y → lon/lat.  Unlike polygon boundaries the dynamics
        # line must NOT be reversed — point order encodes time (start → current).
        lonlat_coords: CoordinateList = [
            list(GeojsonGenerator.lon_lat_delta(rtk_location, pt.x, pt.y)) for pt in dynamics_line
        ]
        length, _ = GeojsonGenerator.map_object_stats(dynamics_line)

        properties: dict[str, Any] = {
            "type_name": "dynamics_line",
            "point_count": len(dynamics_line),
            "length": length,
            **DYNAMICS_LINE_STYLE,
        }

        geo_json["features"].append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {"type": "LineString", "coordinates": lonlat_coords},
            }
        )
        return geo_json

    @staticmethod
    def generate_mow_progress_geojson(
        hash_list: HashList,
        now_index: int,
        rtk_location: Point,
        ub_path_hash: int = 0,
        path_pos: tuple[float, float] | None = None,
    ) -> GeoJSONCollection:
        """Generate a GeoJSON FeatureCollection showing the remaining mow path portion.

        Produces one feature per unique ``path_hash`` found in
        ``hash_list.current_mow_path``.  ``now_index`` is specific to the
        currently-active path segment identified by ``ub_path_hash``; other
        segments (downloaded as part of the same task but not yet started —
        ``current_mow_path`` is cleared on hash change) are shown in full.

        When ``path_pos`` is provided (ENU metres decoded from
        ``report_data.work.path_pos_x/y``) it is prepended as the precise
        starting coordinate for the active segment — matching APK behaviour
        where the current device position begins the remaining-path line.

        Args:
            hash_list:    HashList containing ``current_mow_path`` data.
            now_index:    Current point index within the active path segment
                          (``report_data.work.now_index``).  Applied only to
                          the segment whose ``path_hash == ub_path_hash``.
            rtk_location: Shapely ``Point(latitude, longitude)`` for the RTK
                          base station.
            ub_path_hash: Active path hash from ``report_data.work.ub_path_hash``.
                          Selects which segment gets ``now_index`` applied.
                          Pass 0 to treat all segments as active (fallback).
            path_pos:     Optional ``(x_metres, y_metres)`` ENU position of the
                          device (``report_data.work.path_pos_x / 10000``, same
                          for y).  Prepended to the active segment's remaining
                          points when non-zero.

        Returns:
            GeoJSON FeatureCollection with one LineString feature per path hash.

        """
        geo_json: GeoJSONCollection = {
            "type": "FeatureCollection",
            "name": "Mow Progress",
            "features": [],
        }

        if now_index < 0 or not hash_list.current_mow_path:
            return geo_json

        # Build ordered path-hash list from root_hash_lists sub_cmd=3.
        # This list reflects the mowing order the device will follow.
        ordered_hashes: list[int] = []
        for rhl in hash_list.root_hash_lists:
            if rhl.sub_cmd == 3:
                for entry in rhl.data:
                    ordered_hashes.extend(entry.data_couple)
                break

        # Determine which hashes are still remaining (active or not yet started).
        # Hashes that appear before ub_path_hash in the ordered list are already
        # completed and should not be shown.
        if ub_path_hash and ordered_hashes:
            try:
                active_idx = ordered_hashes.index(ub_path_hash)
            except ValueError:
                active_idx = 0
            visible_hashes: set[int] = set(ordered_hashes[active_idx:])
        else:
            visible_hashes = set()  # empty = no filtering when no order info

        # Collect packets per path_hash, grouped by path_cur for correct ordering.
        # path_cur is the packet's sequence number within its path_hash stream.
        packets_by_hash: dict[int, dict[int, MowPathPacket]] = {}  # hash → {path_cur: packet}
        type_by_hash: dict[int, int] = {}
        for transaction_id in sorted(hash_list.current_mow_path.keys()):
            frames = hash_list.current_mow_path[transaction_id]
            for frame_idx in sorted(frames.keys()):
                mow_path = frames[frame_idx]
                for packet in mow_path.path_packets:
                    if visible_hashes and packet.path_hash not in visible_hashes:
                        continue
                    packets_by_hash.setdefault(packet.path_hash, {})[packet.path_cur] = packet
                    type_by_hash.setdefault(packet.path_hash, packet.path_type)

        # Assemble points per hash in path_cur order.
        points_by_hash: dict[int, list[CommDataCouple]] = {}
        for path_hash, cur_map in packets_by_hash.items():
            pts: list[CommDataCouple] = []
            for cur in sorted(cur_map.keys()):
                pts.extend(cur_map[cur].data_couple)
            points_by_hash[path_hash] = pts

        def _hash_order(h: int) -> int:
            try:
                return ordered_hashes.index(h)
            except ValueError:
                return len(ordered_hashes)

        # One feature per path_hash, emitted in mowing order.
        for path_hash in sorted(points_by_hash.keys(), key=_hash_order):
            all_points = points_by_hash[path_hash]
            total = len(all_points)
            is_active = ub_path_hash == 0 or path_hash == ub_path_hash

            if is_active:
                if path_pos is not None and (path_pos[0] != 0.0 or path_pos[1] != 0.0):
                    remaining: list[CommDataCouple] = [CommDataCouple(x=path_pos[0], y=path_pos[1])] + all_points[
                        now_index:
                    ]
                else:
                    remaining = all_points[max(0, now_index - 1) :]
                applied_index = now_index
            else:
                remaining = all_points
                applied_index = 0

            if len(remaining) < 2:
                continue

            lonlat_coords: CoordinateList = GeojsonGenerator._convert_to_lonlat_coords(remaining, rtk_location)
            length, _ = GeojsonGenerator.map_object_stats(remaining)

            geo_json["features"].append(
                {
                    "type": "Feature",
                    "properties": {
                        "type_name": "mow_progress",
                        "path_hash": path_hash,
                        "path_type": type_by_hash[path_hash],
                        "is_active": is_active,
                        "point_count": len(remaining),
                        "now_index": applied_index,
                        "total_points": total,
                        "length": length,
                        **MOW_PROGRESS_STYLE,
                    },
                    "geometry": {"type": "LineString", "coordinates": lonlat_coords},
                }
            )
        return geo_json

    @staticmethod
    def _add_rtk_and_dock(
        rtk_location: Point, dock_location: Point, dock_rotation: int, geo_json: GeoJSONCollection
    ) -> None:
        geo_json["features"].append(
            {
                "type": "Feature",
                "properties": {
                    "title": "RTK Base",
                    "Name": "RTK Base",
                    "description": "RTK Base Station location",
                    "type_name": "station",
                    **RTK_STYLE,
                    **RTK_IMAGE,
                },
                "geometry": {"type": "Point", "coordinates": [rtk_location.y, rtk_location.x]},
            }
        )

        geo_json["features"].append(
            {
                "type": "Feature",
                "properties": {
                    "title": "Dock",
                    "Name": "Dock",
                    "description": "Charging dock location",
                    "type_name": "station",
                    "rotation": dock_rotation,
                    **DOCK_STYLE,
                    **DOCK_IMAGE,
                },
                "geometry": {"type": "Point", "coordinates": [dock_location.y, dock_location.x]},
            }
        )

    @staticmethod
    def _build_area_name_lookup(area_names: list[AreaHashNameList]) -> dict[int, str]:
        """Build a hash lookup table for area names.

        Args:
            area_names: List of AreaHashNameList objects

        Returns:
            Dictionary mapping hash to area name

        """
        return {item.hash: item.name for item in area_names}

    @staticmethod
    def _process_map_objects(
        hash_list: HashList, rtk_location: Point, area_names: dict[int, str], geo_json: GeoJSONCollection
    ) -> int:
        """Process all map objects and add them to GeoJSON.

        Args:
            hash_list: HashList object containing map data
            rtk_location: Tuple of (longitude, latitude) for rtk position
            area_names: Dictionary mapping hash to area name
            geo_json: GeoJSON collection to add features to

        Returns:
            Total number of frames processed

        """
        total_frames = 0

        # Map type names to their corresponding dictionaries in HashList
        type_mapping: dict[str, dict[int, FrameList]] = {
            "area": hash_list.area,
            "path": hash_list.path,
            "obstacle": hash_list.obstacle,
            "dump": hash_list.dump,
        }

        for type_name, map_objects in type_mapping.items():
            for hash_key, frame_list in map_objects.items():
                if not GeojsonGenerator._validate_frame_list(frame_list, hash_key, area_names):
                    continue

                local_coords = GeojsonGenerator._collect_frame_coordinates(frame_list)
                total_frames += len(frame_list.data)

                lonlat_coords = GeojsonGenerator._convert_to_lonlat_coords(local_coords, rtk_location)
                length, area = GeojsonGenerator.map_object_stats(local_coords)

                feature = GeojsonGenerator._create_feature(hash_key, frame_list, type_name, lonlat_coords, length, area)
                if feature:
                    geo_json["features"].append(feature)

        return total_frames

    @staticmethod
    def _process_mow_map_objects(hash_list: HashList, rtk_location: Point, geo_json: GeoJSONCollection) -> int:
        """Process all mow path objects and add them to GeoJSON.

        Each transaction_id in current_mow_path represents a separate mowing path
        consisting of multiple frames. A feature is generated only when all
        frames for that transaction_id have been received.

        Key findings:
        - path_type=2 = border/edge paths, path_type=0 = main mow stripes
        - Order is zone 1 first (border then mow paths), then zone 2 (border then mow paths) — matching the zone order we passed in one_hashs
        - total_paths=125 but only valid_path_num=2 per frame — the device sends a subset of paths per frame, across 5 frames total
        """
        total_frames = 0

        for transaction_id, frames_by_index in hash_list.current_mow_path.items():
            if not frames_by_index:
                continue

            # Use any frame to determine total_frame and other metadata
            any_mow_path = next(iter(frames_by_index.values()))
            total_frame = any_mow_path.total_frame

            if total_frame == 0:
                continue

            # Only generate features when we have all frames for this transaction
            if len(frames_by_index) != total_frame:
                continue

            ordered_mow_paths = [frames_by_index[i] for i in sorted(frames_by_index.keys())]
            total_frames += 1

            # Group coordinates by path_type so each type becomes a separate feature.
            # path_type=0: main mow stripes (弓 arch), path_type=2: border passes (回 circular).
            coords_by_path_type: dict[int, list[CommDataCouple]] = {}
            for mow_frame in ordered_mow_paths:
                for packet in mow_frame.path_packets:
                    coords_by_path_type.setdefault(packet.path_type, []).extend(packet.data_couple)

            for path_type, local_coords in coords_by_path_type.items():
                lonlat_coords = GeojsonGenerator._convert_to_lonlat_coords(local_coords, rtk_location)
                length, area = GeojsonGenerator.map_object_stats(local_coords)

                feature = GeojsonGenerator._create_mow_path_feature(
                    any_mow_path, path_type, lonlat_coords, length, area
                )
                if feature:
                    geo_json["features"].append(feature)

        return total_frames

    @staticmethod
    def _process_svg_map_objects(hash_list: HashList, rtk_location: Point, geo_json: GeoJSONCollection) -> None:
        """Process all SVG map objects and add them to GeoJSON."""
        for hash_key, frame_list in hash_list.svg.items():
            logger.debug(hash_key, frame_list)

    @staticmethod
    def _validate_frame_list(frame_list: FrameList, hash_key: int, area_names: dict[int, str] | None = None) -> bool:
        """Validate that frame list has complete frame data.

        Args:
            frame_list: FrameList object to validate
            hash_key: Hash key for the area
            area_names: Dictionary mapping hash to area name

        Returns:
            True if valid, False otherwise

        """
        if len(frame_list.data) != frame_list.total_frame:
            area_name = area_names.get(hash_key, "Unknown") if area_names else "Unknown"
            logger.debug(f"Error: full coord data not available for area: '{area_name}' - '{hash_key}'")
            return False
        return True

    @staticmethod
    def _collect_frame_coordinates(frame_list: FrameList) -> list[CommDataCouple]:
        """Collect coordinates from all frames in a FrameList.

        Args:
            frame_list: FrameList containing frame data

        Returns:
            List of coordinate dictionaries with 'x' and 'y' keys

        """
        local_coords: list[CommDataCouple] = []
        for frame in frame_list.data:
            if isinstance(frame, NavGetCommData):
                local_coords.extend(frame.data_couple)
            # TODO svg message needs different transform
            # elif isinstance(frame, SvgMessage):
            #     local_coords.extend(frame.)
        return local_coords

    @staticmethod
    def _convert_to_lonlat_coords(
        local_coords: list[CommDataCouple], rtk_location: Point, x_offset: int = 0, y_offset: int = 0
    ) -> CoordinateList:
        """Convert local x,y coordinates to lon,lat coordinates.

        Args:
            local_coords: List of coordinate dictionaries with 'x' and 'y' keys
            rtk_location: Tuple of (longitude, latitude) for rtk position

        Returns:
            List of [longitude, latitude] coordinate pairs

        """
        lonlat_coords: CoordinateList = [
            list(GeojsonGenerator.lon_lat_delta(rtk_location, xy.x + x_offset, xy.y + y_offset)) for xy in local_coords
        ]
        lonlat_coords.reverse()  # GeoJSON polygons go clockwise
        return lonlat_coords

    @staticmethod
    def _create_feature(
        hash_key: int, frame_list: FrameList, type_name: str, lonlat_coords: CoordinateList, length: float, area: float
    ) -> GeoJSONFeature | None:
        """Create a GeoJSON feature from frame list data.

        Args:
            hash_key: Hash identifier for the feature
            frame_list: FrameList containing frame data
            type_name: Type name of the map object
            lonlat_coords: List of [longitude, latitude] coordinate pairs
            length: Calculated length of the feature
            area: Calculated area of the feature

        Returns:
            GeoJSON feature dictionary or None if invalid

        """
        first_frame = frame_list.data[0]
        type_id = first_frame.type
        object_name = ""
        if isinstance(first_frame, NavGetCommData):
            object_name = first_frame.name_time.name

        properties = GeojsonGenerator._create_feature_properties(
            hash_key, type_id, type_name, first_frame, length, area, object_name
        )
        geometry = GeojsonGenerator._create_feature_geometry(type_id, lonlat_coords, properties)

        if geometry is None:
            return None

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    @staticmethod
    def _create_mow_path_feature(
        path_packet_list: MowPath, path_type: int, lonlat_coords: CoordinateList, length: float, area: float
    ) -> GeoJSONFeature | None:
        """Create a GeoJSON feature for a mow path, styled by path_type.

        path_type=0 produces main mow stripes (弓 arch pattern).
        path_type=2 produces border/perimeter passes (回 circular pattern).
        """
        if len(lonlat_coords) < 2:
            return None

        style = BORDER_PASS_STYLE if path_type == 2 else MOW_STRIPE_STYLE
        type_label = "border_pass" if path_type == 2 else "mow_path"

        properties: dict[str, Any] = {
            "transaction_id": path_packet_list.transaction_id,
            "type_name": type_label,
            "path_type": path_type,
            "total_path_num": path_packet_list.total_path_num,
            "length": length,
            "area": path_packet_list.area,
            "time": path_packet_list.time,
            **style,
        }
        return {
            "type": "Feature",
            "properties": properties,
            "geometry": {"type": "LineString", "coordinates": lonlat_coords},
        }

    @staticmethod
    def _create_feature_properties(
        hash_key: int, type_id: int, type_name: str, first_frame: Any, length: float, area: float, object_name: str = ""
    ) -> dict[str, Any]:
        """Create properties dictionary for GeoJSON feature.

        Args:
            hash_key: Hash identifier
            object_name: Name of the object
            type_id: Type ID of the feature
            type_name: Type name of the feature
            first_frame: First frame from the FrameList
            length: Calculated length
            area: Calculated area

        Returns:
            Properties dictionary

        """
        return {
            "hash": hash_key,
            "title": object_name,
            "Name": object_name,
            "description": "description <b>test</b>",
            "type_id": type_id,
            "type_name": type_name,
            "parent_hash_a": first_frame.paternal_hash_a,
            "parent_hash_b": first_frame.paternal_hash_b,
            "length": length,
            "area": area,
        }

    @staticmethod
    def _create_feature_geometry(
        type_id: int, lonlat_coords: CoordinateList, properties: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Create geometry dictionary for GeoJSON feature based on type.

        Args:
            type_id: Type ID determining geometry type
            lonlat_coords: List of [longitude, latitude] coordinate pairs
            properties: Properties dictionary to modify with style information

        Returns:
            Geometry dictionary or None if invalid type

        """
        if type_id == TYPE_MOWING_ZONE:
            properties.update(AREA_STYLE)
            return {"type": "Polygon", "coordinates": [lonlat_coords]}
        if type_id == TYPE_OBSTACLE:
            properties.update(OBSTACLE_STYLE)
            return {"type": "Polygon", "coordinates": [lonlat_coords]}
        if type_id == TYPE_PATH and len(lonlat_coords) > 1:
            properties.update(PATH_STYLE)
            return {"type": "LineString", "coordinates": lonlat_coords}
        return None  # Point (ignore)

    @staticmethod
    def _save_geojson(geoJSON: GeoJSONCollection) -> None:
        """Save GeoJSON data to file.

        Args:
            geoJSON: GeoJSON collection to save

        """
        with open("areas.json", "w") as json_file:
            json.dump(geoJSON, json_file, indent=2)

    @staticmethod
    def lon_lat_delta(rtk: Point, x: float, y: float) -> Coordinate:
        """Add delta (in meters) to lon/lat, return new lon/lat.

        Args:
            lon: Longitude in degrees
            lat: Latitude in degrees
            x: X offset in meters
            y: Y offset in meters

        Returns:
            Tuple of (new_longitude, new_latitude)

        """
        new_lon = rtk.y + (x / (METERS_PER_DEGREE * math.cos(math.radians(rtk.x))))
        new_lat = rtk.x + (y / METERS_PER_DEGREE)
        return new_lon, new_lat

    @staticmethod
    def map_object_stats(coords: list[CommDataCouple]) -> Coordinate:
        """Calculate length and area statistics for map object coordinates.

        Args:
            coords: List of coordinate dictionaries with 'x' and 'y' keys

        Returns:
            Tuple of (length, area) in meters and square meters

        """
        # Point Object
        if len(coords) < 2:
            return 0.0, 0.0

        def distance(p1: CommDataCouple, p2: CommDataCouple) -> float:
            """Calculate Euclidean distance between two points."""
            return math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2)

        length = sum(distance(coords[i], coords[i + 1]) for i in range(len(coords) - 1))

        # Open line
        if coords[0] != coords[-1]:
            return length, 0.0

        # Closed Polygon - Calculate area using shoelace formula
        area = 0.5 * abs(
            sum(coords[i].x * coords[i + 1].y - coords[i + 1].x * coords[i].y for i in range(len(coords) - 1))
        )

        return length, area

    @staticmethod
    def is_point_in_polygon(x: float, y: float, poly: list[list[float]]) -> bool:
        """Test if a point is inside a polygon using ray casting algorithm.

        Args:
            x: X coordinate of the point
            y: Y coordinate of the point
            poly: Polygon as list of [x, y] coordinate pairs

        Returns:
            True if point is inside polygon, False otherwise

        """
        return (
            sum(
                (y > poly[i][1]) != (y > poly[(i + 1) % len(poly)][1])
                and (
                    x
                    < (poly[(i + 1) % len(poly)][0] - poly[i][0])
                    * (y - poly[i][1])
                    / (poly[(i + 1) % len(poly)][1] - poly[i][1])
                    + poly[i][0]
                )
                for i in range(len(poly))
            )
            % 2
            == 1
        )
