from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from mashumaro.mixins.orjson import DataClassORJSONMixin
from shapely import Point

from pymammotion.data.model.location import Dock, LocationPoint
from pymammotion.proto import NavGetCommDataAck, NavGetHashListAck, SvgMessageAckT
from pymammotion.utility.map import CoordinateConverter
from pymammotion.utility.mur_mur_hash import MurMurHashUtil


class PathType(IntEnum):
    """Path types for NavGetCommData / NavGetCommDataAck ``type`` field.

    These are the numeric values the device uses to identify what kind of
    map data is carried in a ``toapp_get_commondata_ack`` response.  See
    ``docs/hash_guide.md`` for a full description of each type.
    """

    AREA = 0
    """Mowing-area (zone) boundary polygon points."""

    OBSTACLE = 1
    """Keep-out / no-go obstacle boundary points."""

    PATH = 2
    """Recorded travel path segments (Luba 1 path-mode)."""

    LINE = 10
    """Stored mowing-line segments (breakpoint / sub_cmd=3 path segments)."""

    DUMP = 12
    """Dump / clippings-collection zone boundary points."""

    SVG = 13
    """Pre-rendered SVG map tile (device-side raster overview)."""

    VISUAL_SAFETY_ZONE = 25
    """Vision-camera detected safety zone (Luba 2 Vision / Pro only)."""

    VISUAL_OBSTACLE_ZONE = 26
    """Vision-camera detected obstacle zone (Luba 2 Vision / Pro only)."""

    DYNAMICS_LINE = 18
    """Live mow-progress path: the actual path the mower has driven so far
    during the current work session.  Fetched via ``CommonDataSaga`` with
    ``action=8, type=18`` and stored in ``HashList.dynamics_line``.
    Unlike the other types this has no hash key — a single request always
    returns the current session's data in sequential frames."""


@dataclass
class CommDataCouple:
    """An (x, y) coordinate pair from a common-data map frame."""

    x: float = 0.0
    y: float = 0.0


@dataclass
class AreaLabelName(DataClassORJSONMixin):
    """User-visible label name for a mowing area."""

    label: str = ""


@dataclass
class NavNameTime(DataClassORJSONMixin):
    """Name and creation/modification timestamps for a navigation map entry."""

    name: str = ""
    create_time: int = 0
    modify_time: int = 0


@dataclass
class NavGetCommData(DataClassORJSONMixin):
    """Decoded payload of a ``toapp_get_commondata_ack`` response frame."""

    pver: int = 0
    sub_cmd: int = 0
    result: int = 0
    action: int = 0
    type: int = 0
    hash: int = 0
    paternal_hash_a: int = 0
    paternal_hash_b: int = 0
    total_frame: int = 0
    current_frame: int = 0
    data_hash: int = 0
    data_len: int = 0
    data_couple: list["CommDataCouple"] = field(default_factory=list)
    reserved: str = ""
    name_time: NavNameTime = field(default_factory=NavNameTime)


@dataclass
class MowPathPacket(DataClassORJSONMixin):
    """A single packet of mow-path coordinate data within a MowPath frame."""

    path_hash: int = 0
    path_type: int = 0
    path_total: int = 0
    path_cur: int = 0
    zone_hash: int = 0
    data_couple: list["CommDataCouple"] = field(default_factory=list)


@dataclass
class MowPath(DataClassORJSONMixin):
    """Complete mow-path response assembled from one or more ``MowPathPacket`` frames."""

    pver: int = 0
    sub_cmd: int = 0
    result: int = 0
    area: int = 0
    time: int = 0
    total_frame: int = 0
    current_frame: int = 0
    total_path_num: int = 0
    valid_path_num: int = 0
    data_hash: int = 0
    transaction_id: int = 0
    reserved: list[int] = field(default_factory=list)
    data_len: int = 0
    path_packets: list[MowPathPacket] = field(default_factory=list)


@dataclass
class SvgMessageData(DataClassORJSONMixin):
    """Transform and metadata fields contained in an SVG map tile message."""

    x_move: float = 0.0
    y_move: float = 0.0
    scale: float = 0.0
    rotate: float = 0.0
    base_width_m: float = 0.0
    base_width_pix: int = 0
    base_height_m: float = 0.0
    base_height_pix: int = 0
    name_count: int = 0
    data_count: int = 0
    hide_svg: bool = False
    svg_file_name: str = ""
    svg_file_data: str = ""


@dataclass
class SvgMessage(DataClassORJSONMixin):
    """Envelope for a device-rendered SVG map tile response frame."""

    pver: int = 0
    sub_cmd: int = 0
    total_frame: int = 0
    current_frame: int = 0
    data_hash: int = 0
    paternal_hash_a: int = 0
    type: int = 0
    result: int = 0
    svg_message: "SvgMessageData" = field(default_factory=SvgMessageData)


@dataclass
class FrameList(DataClassORJSONMixin):
    """Accumulates the ordered frames for a single hash-keyed map data entry."""

    total_frame: int = 0
    sub_cmd: int = 0
    data: list[NavGetCommData | SvgMessage] = field(default_factory=list)


@dataclass
class EdgePoints(DataClassORJSONMixin):
    """Edge/boundary points received during edgewise mapping (toapp_edge_points).

    Keyed by hash in HashList.edge_points.  Frames are appended as they arrive;
    complete when len(frames) == total_frame.
    """

    hash: int = 0
    action: int = 0
    type: int = 0
    total_frame: int = 0
    frames: dict[int, list[CommDataCouple]] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """True when all frames have been received."""
        return self.total_frame > 0 and len(self.frames) >= self.total_frame

    def missing_frames(self) -> list[int]:
        """Return 1-based frame numbers not yet received."""
        return [f for f in range(1, self.total_frame + 1) if f not in self.frames]

    @property
    def all_points(self) -> list[CommDataCouple]:
        """Return all points in frame order."""
        result: list[CommDataCouple] = []
        for frame_num in sorted(self.frames):
            result.extend(self.frames[frame_num])
        return result


@dataclass
class Plan(DataClassORJSONMixin):
    """A scheduled mowing plan (job) retrieved from the device."""

    pver: int = 0
    sub_cmd: int = 2
    area: int = 0
    work_time: int = 0
    version: str = ""
    id: str = ""
    user_id: str = ""
    device_id: str = ""
    plan_id: str = ""
    task_id: str = ""
    job_id: str = ""
    start_time: str = ""
    end_time: str = ""
    week: int = 0
    knife_height: int = 0
    model: int = 0
    edge_mode: int = 0
    required_time: int = 0
    route_angle: int = 0
    route_model: int = 0
    route_spacing: int = 0
    ultrasonic_barrier: int = 0
    total_plan_num: int = 0
    plan_index: int = 0
    result: int = 0
    speed: float = 0.0
    task_name: str = ""
    job_name: str = ""
    zone_hashs: list[int] = field(default_factory=list)
    reserved: str = ""
    start_date: str = ""
    end_date: str = ""
    trigger_type: int = 0
    day: int = 0
    weeks: list[int] = field(default_factory=list)
    remained_seconds: int = 0
    toward_mode: int = 0
    toward_included_angle: int = 0


@dataclass(eq=False, repr=False)
class NavGetHashListData(DataClassORJSONMixin):
    """Dataclass for NavGetHashListData."""

    pver: int = 0
    sub_cmd: int = 0
    total_frame: int = 0
    current_frame: int = 0
    data_hash: int = 0
    hash_len: int = 0
    reserved: str = ""
    result: int = 0
    data_couple: list[int] = field(default_factory=list)


@dataclass
class RootHashList(DataClassORJSONMixin):
    """Top-level hash list grouping all hash IDs for a given sub-command type."""

    total_frame: int = 0
    sub_cmd: int = 0
    data: list[NavGetHashListData] = field(default_factory=list)


@dataclass
class AreaHashNameList(DataClassORJSONMixin):
    """Wrapper so we can serialize to and from dict."""

    name: str
    hash: int


@dataclass
class HashList(DataClassORJSONMixin):
    """stores our map data.
    [hashID, FrameList].
    hashlist for all our hashIDs for verification
    """

    root_hash_lists: list[RootHashList] = field(default_factory=list)
    area: dict[int, FrameList] = field(default_factory=dict)  # type 0
    path: dict[int, FrameList] = field(default_factory=dict)  # type 2
    obstacle: dict[int, FrameList] = field(default_factory=dict)  # type 1
    dump: dict[int, FrameList] = field(default_factory=dict)  # type 12? / sub cmd 4
    svg: dict[int, FrameList] = field(default_factory=dict)  # type 13
    line: dict[int, FrameList] = field(
        default_factory=dict
    )  # type 10, sub cmd 3 — breakpoint line data, keyed by ub_path_hash
    visual_safety_zone: dict[int, FrameList] = field(default_factory=dict)  # type 25
    visual_obstacle_zone: dict[int, FrameList] = field(default_factory=dict)  # type 26
    plan: dict[str, Plan] = field(default_factory=dict)
    area_name: list[AreaHashNameList] = field(default_factory=list)
    current_mow_path: dict[int, dict[int, MowPath]] = field(default_factory=dict)
    generated_geojson: dict[str, Any] = field(default_factory=dict)
    generated_mow_path_geojson: dict[str, Any] = field(default_factory=dict)
    last_ub_path_hash: int = 0
    plans_stale: bool = False
    edge_points: dict[int, EdgePoints] = field(default_factory=dict)  # hash → EdgePoints
    dynamics_line: list[CommDataCouple] = field(default_factory=list)
    """Assembled live mow-progress path from the most recent CommonDataSaga
    (action=8, type=18) response.  Each entry is an (x, y) coordinate pair
    in the device's local coordinate system.  Cleared and replaced on each
    successful fetch.  Empty list when no mowing session is active or the
    first fetch has not completed yet."""
    generated_dynamics_line_geojson: dict[str, Any] = field(default_factory=dict)
    """GeoJSON FeatureCollection generated from ``dynamics_line`` after each
    successful fetch.  Contains a single LineString feature representing the
    path the mower has actually driven in the current session.  Updated in
    place by ``_apply_dynamics_line_geojson`` in ``client.py``."""
    generated_mow_progress_geojson: dict[str, Any] = field(default_factory=dict)
    """GeoJSON FeatureCollection showing the completed portion of the planned
    mow path, sliced to ``mowing_state.now_index``.  Updated by
    ``_apply_mow_progress_geojson`` in ``client.py`` on each state change
    while the device is actively mowing."""

    def update_hash_lists(self, hashlist: list[int], bol_hash: int | None = None) -> None:
        """Prune all map dictionaries to only retain entries whose hash is present in hashlist."""
        if not hashlist:
            return
        if bol_hash and bol_hash != 0:
            self.invalidate_maps(bol_hash)
        self.area = {hash_id: frames for hash_id, frames in self.area.items() if hash_id in hashlist}
        self.path = {hash_id: frames for hash_id, frames in self.path.items() if hash_id in hashlist}
        self.obstacle = {hash_id: frames for hash_id, frames in self.obstacle.items() if hash_id in hashlist}
        self.dump = {hash_id: frames for hash_id, frames in self.dump.items() if hash_id in hashlist}
        self.svg = {hash_id: frames for hash_id, frames in self.svg.items() if hash_id in hashlist}
        self.visual_safety_zone = {
            hash_id: frames for hash_id, frames in self.visual_safety_zone.items() if hash_id in hashlist
        }
        self.visual_obstacle_zone = {
            hash_id: frames for hash_id, frames in self.visual_obstacle_zone.items() if hash_id in hashlist
        }

        area_hashes = list(self.area.keys())
        for hash_id, plan_task in self.plan.copy().items():
            for item in plan_task.zone_hashs:
                if item not in area_hashes:
                    self.plan.pop(hash_id)
                    break

        self.area_name = [
            area_item
            for area_item in self.area_name
            if area_item.hash in self.area.keys() or area_item.hash in hashlist
        ]

    @property
    def area_names_stale(self) -> bool:
        """True when area data is present but no area names have been fetched.

        Used by MapStalenessWatcher to trigger a lightweight area-name-only
        re-fetch without requiring a full map sync.
        """
        return bool(self.area) and not self.area_name

    @property
    def hashlist(self) -> list[int]:
        """Return all hash IDs from every RootHashList as a flat list."""
        if not self.root_hash_lists:
            return []
        # Combine data_couple from all RootHashLists
        return [i for root_list in self.root_hash_lists for obj in root_list.data for i in obj.data_couple]

    @property
    def area_root_hashlist(self) -> list[int]:
        """Return hash IDs from RootHashLists whose sub_cmd indicates area data (sub_cmd == 0)."""
        if not self.root_hash_lists:
            return []
        # Combine data_couple from all RootHashLists
        return [
            i
            for root_list in self.root_hash_lists
            for obj in root_list.data
            for i in obj.data_couple
            if root_list.sub_cmd == 0
        ]

    def missing_hashlist(self, sub_cmd: int = 0) -> list[int]:
        """Return missing hashlist."""
        all_hash_ids = set(self.area.keys()).union(
            self.path.keys(),
            self.obstacle.keys(),
            self.dump.keys(),
            self.svg.keys(),
            self.visual_safety_zone.keys(),
            self.visual_obstacle_zone.keys(),
        )
        if sub_cmd == 3:
            all_hash_ids = set(self.line.keys())
        return [
            i
            for root_list in self.root_hash_lists
            for obj in root_list.data
            if root_list.sub_cmd == sub_cmd
            for i in obj.data_couple
            if i not in all_hash_ids
        ]

    def missing_root_hash_frame(self, hash_list: NavGetHashListAck) -> list[int]:
        """Return missing root hash frame."""
        target_root_list = next(
            (
                rhl
                for rhl in self.root_hash_lists
                if rhl.total_frame == hash_list.total_frame and rhl.sub_cmd == hash_list.sub_cmd
            ),
            None,
        )
        if target_root_list is None:
            return []

        return self.find_missing_frames(target_root_list)

    def update_root_hash_list(self, hash_list: NavGetHashListData) -> None:
        """Insert or replace a NavGetHashListData frame in the matching RootHashList, creating one if needed."""
        target_root_list = next(
            (
                rhl
                for rhl in self.root_hash_lists
                if rhl.total_frame == hash_list.total_frame and rhl.sub_cmd == hash_list.sub_cmd
            ),
            None,
        )

        if target_root_list is None:
            # Create new RootHashList if none exists for this total_frame
            new_root_list = RootHashList(total_frame=hash_list.total_frame, sub_cmd=hash_list.sub_cmd, data=[hash_list])
            self.root_hash_lists.append(new_root_list)
            return

        for index, obj in enumerate(target_root_list.data):
            if obj.current_frame == hash_list.current_frame:
                # Replace the item if current_frame matches
                target_root_list.data[index] = hash_list
                return

        # If no match was found, append the new item
        target_root_list.data.append(hash_list)

    def missing_hash_frame(self, hash_ack: NavGetHashListAck) -> list[int]:
        """Returns a combined list of all missing frames across all RootHashLists."""
        missing_frames = []
        filtered_lists = [rl for rl in self.root_hash_lists if rl.sub_cmd == hash_ack.sub_cmd]
        for root_list in filtered_lists:
            missing = self.find_missing_frames(root_list)
            if missing:
                missing_frames.extend(missing)
        return missing_frames

    def missing_frame(self, hash_data: NavGetCommDataAck | SvgMessageAckT) -> list[int]:
        """Return frame numbers not yet received for the FrameList identified by hash_data."""
        frame_list = self._get_frame_list_by_type_and_hash(hash_data)
        return self.find_missing_frames(frame_list)

    def _get_frame_list_by_type_and_hash(self, hash_data: NavGetCommDataAck | SvgMessageAckT) -> FrameList | None:
        """Get the appropriate FrameList based on hash_data type and hash."""
        path_type_mapping = self._get_path_type_mapping()
        target_dict = path_type_mapping.get(hash_data.type)

        if target_dict is None:
            return None

        # Handle SvgMessage with data_hash attribute
        if isinstance(hash_data, SvgMessageAckT):
            return target_dict.get(hash_data.data_hash)

        # Handle NavGetCommDataAck with hash attribute
        return target_dict.get(hash_data.hash)

    def update_plan(self, plan: Plan) -> None:
        """Store a Plan by its plan_id, ignoring plans with a zero total_plan_num."""
        if plan.total_plan_num != 0:
            self.plan[plan.plan_id] = plan

    def _get_path_type_mapping(self) -> dict[int, dict[int, FrameList]]:
        """Return mapping of PathType to corresponding hash dictionary."""
        return {
            PathType.AREA: self.area,
            PathType.OBSTACLE: self.obstacle,
            PathType.PATH: self.path,
            PathType.LINE: self.line,
            PathType.DUMP: self.dump,
            PathType.SVG: self.svg,
            PathType.VISUAL_SAFETY_ZONE: self.visual_safety_zone,
            PathType.VISUAL_OBSTACLE_ZONE: self.visual_obstacle_zone,
        }

    def update(self, hash_data: NavGetCommData | SvgMessage) -> bool:
        """Update the map data."""

        if hash_data.type == PathType.AREA and isinstance(hash_data, NavGetCommData):
            existing_name = next((area for area in self.area_name if area.hash == hash_data.hash), None)
            if not existing_name:
                used_numbers = {
                    int(a.name.split()[-1])
                    for a in self.area_name
                    if a.name.startswith("area ") and a.name.split()[-1].isdigit()
                }
                n = 1
                while n in used_numbers:
                    n += 1
                self.area_name.append(AreaHashNameList(name=f"area {n}", hash=hash_data.hash))
            result = self._add_hash_data(self.area, hash_data)
            self.update_hash_lists(self.hashlist)
            return result

        # DYNAMICS_LINE (type 18) is frameless with respect to hash keys — frames
        # are assembled by CommonDataSaga and the final flat list is stored via
        # update_dynamics_line().  If a raw NavGetCommDataAck somehow arrives here
        # we still handle it gracefully by accumulating the data_couple points.
        if hash_data.type == PathType.DYNAMICS_LINE and isinstance(hash_data, NavGetCommData):
            if hash_data.current_frame == 1:
                self.dynamics_line = []
            self.dynamics_line.extend(hash_data.data_couple)
            return True

        path_type_mapping = self._get_path_type_mapping()
        target_dict = path_type_mapping.get(hash_data.type)

        if target_dict is not None:
            return self._add_hash_data(target_dict, hash_data)

        return False

    def update_dynamics_line(self, points: list[CommDataCouple]) -> None:
        """Replace the live mow-progress path with a freshly assembled point list.

        Called by ``CommonDataSaga`` (via the client's ``on_complete`` callback)
        once all frames for a type-18 response have been collected and assembled
        in order.  Replaces the previous path entirely — the device always returns
        the full current-session path, not a delta.
        """
        self.dynamics_line = points

    def find_missing_mow_path_frames(self) -> dict[int, list[int]]:
        """Find missing frames in current_mow_path grouped by transaction_id.

        Returns a mapping of transaction_id -> list of missing frame numbers.
        Only transaction_ids with at least one missing frame are included.
        """
        missing_frames: dict[int, list[int]] = {}

        if not self.current_mow_path:
            return missing_frames

        for transaction_id, frames_by_index in self.current_mow_path.items():
            if not frames_by_index:
                continue

            # Get total_frame from any MowPath object for this transaction_id
            any_mow_path = next(iter(frames_by_index.values()))
            total_frame = any_mow_path.total_frame

            if total_frame == 0:
                continue

            expected_frames = set(range(1, total_frame + 1))
            current_frames = set(frames_by_index.keys())
            missing_for_transaction = sorted(expected_frames - current_frames)

            if missing_for_transaction:
                missing_frames[transaction_id] = missing_for_transaction

        return missing_frames

    def update_mow_path(self, path: MowPath) -> None:
        """Update the current_mow_path with the latest MowPath data."""
        # TODO check if we need to clear the current_mow_path first
        transaction_id = path.transaction_id
        if transaction_id not in self.current_mow_path:
            self.current_mow_path[transaction_id] = {}
        self.current_mow_path[transaction_id][path.current_frame] = path

    @staticmethod
    def find_missing_frames(frame_list: FrameList | RootHashList | None) -> list[int]:
        """Return 1-based frame numbers absent from frame_list.data relative to total_frame."""
        if frame_list is None:
            return []

        if frame_list.total_frame == len(frame_list.data):
            return []
        number_list = list(range(1, frame_list.total_frame + 1))

        current_frames = {frame.current_frame for frame in frame_list.data}
        return [num for num in number_list if num not in current_frames]

    @staticmethod
    def _add_hash_data(hash_dict: dict[int, FrameList], hash_data: NavGetCommData | SvgMessage) -> bool:
        """Insert hash_data into hash_dict, creating a new FrameList or appending a new frame as needed."""
        if isinstance(hash_data, SvgMessage):
            if hash_dict.get(hash_data.data_hash, None) is None:
                hash_dict[hash_data.data_hash] = FrameList(total_frame=hash_data.total_frame, data=[hash_data])
                return True

            if hash_data not in hash_dict[hash_data.data_hash].data:
                exists = next(
                    (
                        rhl
                        for rhl in hash_dict[hash_data.data_hash].data
                        if rhl.current_frame == hash_data.current_frame
                    ),
                    None,
                )
                if exists:
                    return True
                hash_dict[hash_data.data_hash].data.append(hash_data)
                return True
            return False

        if hash_dict.get(hash_data.hash, None) is None:
            hash_dict[hash_data.hash] = FrameList(total_frame=hash_data.total_frame, data=[hash_data])
            return True

        if hash_data not in hash_dict[hash_data.hash].data:
            exists = next(
                (rhl for rhl in hash_dict[hash_data.hash].data if rhl.current_frame == hash_data.current_frame),
                None,
            )
            if exists:
                return True
            hash_dict[hash_data.hash].data.append(hash_data)
            return True
        return False

    def invalidate_maps(self, bol_hash: int) -> None:
        """Clear root_hash_lists if the locally computed area hash no longer matches the device-reported bol_hash."""
        if MurMurHashUtil.hash_unsigned_list(self.area_root_hashlist) != bol_hash:
            self.root_hash_lists = []

    def invalidate_mow_path(self, ub_path_hash: int) -> None:
        """Clear current_mow_path when ub_path_hash transitions to 0 (job ended).

        Only clears on transition to zero — ub_path_hash changes during a mow
        as the device advances through segments, so non-zero transitions must
        not discard already-fetched cover path data.
        """
        if ub_path_hash == 0:
            self.current_mow_path = {}
            self.generated_mow_path_geojson = {}
            self.generated_mow_progress_geojson = {}
            self.last_ub_path_hash = 0

    def has_mow_path_for_hash(self, ub_path_hash: int) -> bool:
        """Return True if ub_path_hash appears as path_hash in any transaction's first packet.

        Checks current_mow_path[transaction_id][frame].path_packets[0].path_hash
        across all transactions, so the caller can determine whether cover path
        data for the device's current segment is already held locally.
        """
        for frames in self.current_mow_path.values():
            for mow_path in frames.values():
                if mow_path.path_packets and mow_path.path_packets[0].path_hash == ub_path_hash:
                    return True
        return False

    def invalidate_breakpoint_line(self, ub_path_hash: int) -> bool:
        """Synchronise self.line to the device's current ub_path_hash.

        self.line holds type-10 breakpoint line data (sub cmd 3), keyed by
        ub_path_hash.  The device reports the hash of the line segment it has
        breakpointed on via work.ub_path_hash.

        - Zero means the mower is not on a breakpoint line; clear everything.
        - Non-zero: retain only the entry matching ub_path_hash (the currently
          active line) and discard any others that are now stale.

        Returns True if the caller should re-fetch line data from the device
        (i.e. the active hash is not yet cached), False if no re-fetch is needed.
        """
        if ub_path_hash == 0:
            self.line = {}
            return False
        self.line = {h: frames for h, frames in self.line.items() if h == ub_path_hash}
        return ub_path_hash not in self.line

    def generate_geojson(self, rtk: LocationPoint, dock: Dock) -> Any:
        """Generate geojson from frames."""
        from pymammotion.data.model.generate_geojson import GeojsonGenerator

        coordinator_converter = CoordinateConverter(rtk.latitude, rtk.longitude)
        RTK_real_loc = coordinator_converter.enu_to_lla(0, 0)

        dock_location = coordinator_converter.enu_to_lla(dock.latitude, dock.longitude)
        dock_rotation = coordinator_converter.get_transform_yaw_with_yaw(dock.rotation) + 180

        self.generated_geojson = GeojsonGenerator.generate_geojson(
            self,
            Point(RTK_real_loc.latitude, RTK_real_loc.longitude),
            Point(dock_location.latitude, dock_location.longitude),
            int(dock_rotation),
        )

    def generate_mowing_geojson(self, rtk: LocationPoint) -> Any:
        """Generate geojson from frames."""
        from pymammotion.data.model.generate_geojson import GeojsonGenerator

        coordinator_converter = CoordinateConverter(rtk.latitude, rtk.longitude)
        rtk_real_loc = coordinator_converter.enu_to_lla(0, 0)

        self.generated_mow_path_geojson = GeojsonGenerator.generate_mow_path_geojson(
            self,
            Point(rtk_real_loc.latitude, rtk_real_loc.longitude),
        )

        return self.generated_mow_path_geojson
