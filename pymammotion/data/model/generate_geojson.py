import json
import math
from typing import Any

from shapely.geometry import Point

from pymammotion import logger
from pymammotion.data.model.hash_list import (
    AreaHashNameList,
    CommDataCouple,
    FrameList,
    HashList,
    MowPath,
    MowPathPacket,
    NavGetCommData,
)

# Constants
DEFAULT_X_OFFSET: int = 0
DEFAULT_Y_OFFSET: int = 0
GEOMETRY_TYPES: list[str] = ["Polygon", "Polygon", "LineString", "Point"]
MAP_OBJECT_TYPES: list[str] = ["area", "path", "obstacle", "dump"]

image_path = "/local/community/ha-mammotion-map/dist/assets/map/"

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

geojson_metadata = {"name": "Lawn Areas", "description": "Generated from Mammotion diagnostics data"}

# Map type IDs
TYPE_MOWING_ZONE: int = 0
TYPE_OBSTACLE: int = 1
TYPE_PATH: int = 2
TYPE_MOW_PATH: int = 3

# Coordinate conversion constants
METERS_PER_DEGREE_LON: int = 111320
METERS_PER_DEGREE_LAT: int = 111320

# Type aliases
Coordinate = tuple[float, float]
CoordinateList = list[list[float]]
GeoJSONFeature = dict[str, Any]
GeoJSONCollection = dict[str, Any]
LocationDict = dict[str, Coordinate]

# Path to mammotion integration diagnostics file
x_offset: int = DEFAULT_X_OFFSET
y_offset: int = DEFAULT_Y_OFFSET
geometry_types: list[str] = GEOMETRY_TYPES


def is_overlapping(p: Point, placed_points: list[Point], min_distance: float = 0.00005) -> bool:
    """Check if point p is too close to any previously placed label."""
    return any(p.distance(existing) < min_distance for existing in placed_points)


def apply_meter_offsets(lon: float, lat: float, lon_offset: float, lat_offset: float) -> list[float]:
    """Apply meter-based offsets to coordinates (in degrees)"""
    new_lon = lon + (lon_offset / (111320 * math.cos(math.radians(lat))))
    new_lat = lat + (lat_offset / 111320)
    return [new_lon, new_lat]


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
    area_names = _build_area_name_lookup(hash_list.area_name)

    geo_json: GeoJSONCollection = {"type": "FeatureCollection", "name": "Lawn Areas", "features": []}
    _add_rtk_and_dock(rtk_location, dock_location, dock_rotation, geo_json)
    total_frames = _process_map_objects(hash_list, rtk_location, area_names, geo_json)

    # _save_geojson(geo_json)
    logger.debug("GeoJson complete. Total Frames processed:", total_frames)
    return geo_json


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


def _build_area_name_lookup(area_names: list[AreaHashNameList]) -> dict[int, str]:
    """Build a hash lookup table for area names.

    Args:
        area_names: List of AreaHashNameList objects

    Returns:
        Dictionary mapping hash to area name

    """
    return {item.hash: item.name for item in area_names}


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
            logger.debug(hash_key, type_name)

            if not _validate_frame_list(frame_list, hash_key, area_names):
                continue

            local_coords = _collect_frame_coordinates(frame_list)
            total_frames += len(frame_list.data)

            lonlat_coords = _convert_to_lonlat_coords(local_coords, rtk_location)
            length, area = map_object_stats(local_coords)

            feature = _create_feature(hash_key, frame_list, type_name, lonlat_coords, length, area)
            if feature:
                geo_json["features"].append(feature)

    for key, path_packet_list in hash_list.current_mow_path.items():
        local_coords = _collect_mow_frame_coordinates(path_packet_list)
        total_frames += len(path_packet_list.path_packets)

        lonlat_coords = _convert_to_lonlat_coords(local_coords, rtk_location)
        length, area = map_object_stats(local_coords)

        feature = _create_mow_path_feature(key, path_packet_list, lonlat_coords, length, area)
        if feature:
            geo_json["features"].append(feature)

    return total_frames


def _validate_frame_list(frame_list: FrameList, hash_key: int, area_names: dict[int, str]) -> bool:
    """Validate that frame list has complete frame data.

    Args:
        frame_list: FrameList object to validate
        hash_key: Hash key for the area
        area_names: Dictionary mapping hash to area name

    Returns:
        True if valid, False otherwise

    """
    if len(frame_list.data) != frame_list.total_frame:
        area_name = area_names.get(hash_key, "Unknown")
        logger.debug(f"Error: full coord data not available for area: '{area_name}' - '{hash_key}'")
        return False
    return True


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


def _collect_mow_frame_coordinates(frame_list: MowPath) -> list[CommDataCouple]:
    """Collect coordinates from all frames in a FrameList."""
    local_coords: list[CommDataCouple] = []
    for frame in frame_list.path_packets:
        local_coords.extend(frame.data_couple)
    return local_coords


def _convert_to_lonlat_coords(local_coords: list[CommDataCouple], rtk_location: Point) -> CoordinateList:
    """Convert local x,y coordinates to lon,lat coordinates.

    Args:
        local_coords: List of coordinate dictionaries with 'x' and 'y' keys
        rtk_location: Tuple of (longitude, latitude) for rtk position

    Returns:
        List of [longitude, latitude] coordinate pairs

    """
    lonlat_coords: CoordinateList = [
        list(lon_lat_delta(rtk_location, xy.x + x_offset, xy.y + y_offset)) for xy in local_coords
    ]
    lonlat_coords.reverse()  # GeoJSON polygons go clockwise
    return lonlat_coords


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

    properties = _create_feature_properties(hash_key, type_id, type_name, first_frame, length, area, object_name)
    geometry = _create_feature_geometry(type_id, lonlat_coords, properties)

    if geometry is None:
        return None

    return {"type": "Feature", "properties": properties, "geometry": geometry}


def _create_mow_path_feature(
    key: int, path_packet_list: MowPath, lonlat_coords: CoordinateList, length: float, area: float
) -> GeoJSONFeature | None:
    first_frame = path_packet_list.path_packets[0]

    properties = _create_feature_mow_path_properties(key, first_frame, length, path_packet_list.area)
    geometry = _create_feature_geometry(3, lonlat_coords, properties)

    if geometry is None:
        return None

    return {"type": "Feature", "properties": properties, "geometry": geometry}


def _create_feature_mow_path_properties(
    hash_key: int, first_frame: MowPathPacket, length: float, area: float
) -> dict[str, Any]:
    """Create properties dictionary for GeoJSON feature."""
    return {
        "hash": hash_key,
        "type_name": "mow_path",
        "zone_hash": first_frame.zone_hash,
        "length": length,
        "area": area,
    }


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
    elif type_id == TYPE_OBSTACLE:
        properties.update(OBSTACLE_STYLE)
        return {"type": "Polygon", "coordinates": [lonlat_coords]}
    elif type_id == TYPE_PATH and len(lonlat_coords) > 1:
        properties.update(PATH_STYLE)
        return {"type": "LineString", "coordinates": lonlat_coords}
    elif type_id == TYPE_MOW_PATH and len(lonlat_coords) > 1:
        properties["color"] = "green"
        return {"type": "LineString", "coordinates": lonlat_coords}
    else:
        return None  # Point (ignore)


def _save_geojson(geoJSON: GeoJSONCollection) -> None:
    """Save GeoJSON data to file.

    Args:
        geoJSON: GeoJSON collection to save

    """
    with open("areas.json", "w") as json_file:
        json.dump(geoJSON, json_file, indent=2)


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
    new_lon = rtk.y + (x / (METERS_PER_DEGREE_LON * math.cos(math.radians(rtk.x))))
    new_lat = rtk.x + (y / METERS_PER_DEGREE_LAT)
    return new_lon, new_lat


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
    area = 0.5 * abs(sum(coords[i].x * coords[i + 1].y - coords[i + 1].x * coords[i].y for i in range(len(coords) - 1)))

    return length, area


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
