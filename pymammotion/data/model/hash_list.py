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
    """``type`` field values for NavGetCommData / NavGetCommDataAck.

    See ``docs/hash_guide.md`` for the full protocol reference.
    """

    AREA = 0
    """Mowing-area (zone) boundary points."""

    OBSTACLE = 1
    """Keep-out / no-go obstacle boundary points."""

    PATH = 2
    """Recorded travel path segments (Luba 1 path-mode)."""

    LINE = 10
    """Breakpoint line segments (sub_cmd=3)."""

    DUMP = 12
    """Clippings-collection zone boundary points."""

    SVG = 13
    """Pre-rendered SVG map tile."""

    DYNAMICS_LINE = 18
    """Live mow-progress path for the current session.

    Frameless w.r.t. hash keys; stored flat in ``HashList.dynamics_line``.
    Fetched via ``CommonDataSaga`` with ``action=8, type=18``.
    """

    CORRIDOR_LINE = 19
    """Corridor line between mowing zones (MN231)."""

    CORRIDOR_POINT = 20
    """Corridor waypoint between mowing zones (MN231)."""

    VIRTUAL_WALL = 21
    """User-drawn virtual fence / keep-out line."""

    VISUAL_SAFETY_ZONE = 25
    """Vision-detected safety zone (Luba 2 Vision / Pro only)."""

    VISUAL_OBSTACLE_ZONE = 26
    """Vision-detected obstacle zone (Luba 2 Vision / Pro only)."""


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
    """Edge/boundary points from ``toapp_edge_points``, keyed by hash.

    Complete once ``len(frames) == total_frame``.
    """

    hash: int = 0
    action: int = 0
    type: int = 0
    total_frame: int = 0
    frames: dict[int, list[CommDataCouple]] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """Return True once all frames have arrived."""
        return self.total_frame > 0 and len(self.frames) >= self.total_frame

    def missing_frames(self) -> list[int]:
        """Return 1-based frame numbers not yet received."""
        return [f for f in range(1, self.total_frame + 1) if f not in self.frames]

    @property
    def all_points(self) -> list[CommDataCouple]:
        """Return all points concatenated in frame order."""
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
    """Map data store keyed by hash ID.

    ``root_hash_lists`` holds the device-reported manifest of hash IDs; the
    per-type dicts (``area``, ``path``, ``obstacle``, …) hold the actual
    frames as they arrive.
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
    corridor_line: dict[int, FrameList] = field(default_factory=dict)  # type 19
    corridor_point: dict[int, FrameList] = field(default_factory=dict)  # type 20
    virtual_wall: dict[int, FrameList] = field(default_factory=dict)  # type 21
    plan: dict[str, Plan] = field(default_factory=dict)
    area_name: list[AreaHashNameList] = field(default_factory=list)
    current_mow_path: dict[int, dict[int, MowPath]] = field(default_factory=dict)
    generated_geojson: dict[str, Any] = field(default_factory=dict)
    generated_mow_path_geojson: dict[str, Any] = field(default_factory=dict)
    last_ub_path_hash: int = 0
    plans_stale: bool = False
    edge_points: dict[int, EdgePoints] = field(default_factory=dict)  # hash → EdgePoints
    dynamics_line: list[CommDataCouple] = field(default_factory=list)
    """Assembled live mow-progress path from the latest type=18 fetch.

    (x, y) pairs in device-local coordinates.  Replaced wholesale on each
    successful fetch; empty when no session is active.
    """
    generated_dynamics_line_geojson: dict[str, Any] = field(default_factory=dict)
    """WGS-84 LineString of ``dynamics_line``, regenerated after each fetch."""
    generated_mow_progress_geojson: dict[str, Any] = field(default_factory=dict)
    """Completed portion of the planned mow path, sliced to ``now_index``."""

    def update_hash_lists(self, hashlist: list[int], bol_hash: int | None = None) -> None:
        """Drop entries from every per-type dict whose hash isn't in *hashlist*."""
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
        self.corridor_line = {
            hash_id: frames for hash_id, frames in self.corridor_line.items() if hash_id in hashlist
        }
        self.corridor_point = {
            hash_id: frames for hash_id, frames in self.corridor_point.items() if hash_id in hashlist
        }
        self.virtual_wall = {hash_id: frames for hash_id, frames in self.virtual_wall.items() if hash_id in hashlist}

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
        """Return True when areas exist but none have been named yet."""
        return bool(self.area) and not self.area_name

    @property
    def hashlist(self) -> list[int]:
        """Return every hash ID in ``root_hash_lists`` as a flat list."""
        if not self.root_hash_lists:
            return []
        return [i for root_list in self.root_hash_lists for obj in root_list.data for i in obj.data_couple]

    @property
    def area_root_hashlist(self) -> list[int]:
        """Return hash IDs from ``root_hash_lists`` entries with ``sub_cmd == 0`` (area)."""
        if not self.root_hash_lists:
            return []
        return [
            i
            for root_list in self.root_hash_lists
            for obj in root_list.data
            for i in obj.data_couple
            if root_list.sub_cmd == 0
        ]

    def missing_hashlist(self, sub_cmd: int = 0) -> list[int]:
        """Return hash IDs declared in ``root_hash_lists`` for *sub_cmd* but not yet fetched."""
        all_hash_ids = set(self.area.keys()).union(
            self.path.keys(),
            self.obstacle.keys(),
            self.dump.keys(),
            self.svg.keys(),
            self.visual_safety_zone.keys(),
            self.visual_obstacle_zone.keys(),
            self.corridor_line.keys(),
            self.corridor_point.keys(),
            self.virtual_wall.keys(),
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

    def find_incomplete_hashes(self, sub_cmd: int = 0) -> list[int]:
        """Return hashes declared in ``root_hash_lists`` that are not fully fetched.

        A hash is considered incomplete when either:

        * no entry exists for it in the per-type dict (``area`` / ``path`` /
          ``obstacle`` / …) — never fetched, or
        * an entry exists but :meth:`find_missing_frames` reports at least
          one missing frame — interrupted mid-fetch.

        This is stricter than :meth:`missing_hashlist`, which only checks
        key-presence and therefore treats a partially-fetched area as done.
        Callers that need to know "what still needs ``synchronize_hash_data``"
        should use this method so interrupted areas trigger a fresh fetch.
        """
        path_type_mapping = self._get_path_type_mapping()
        # missing_hashlist uses a union of *all* per-type keys for sub_cmd=0,
        # so replicate that lookup for sub_cmd=0 too.
        if sub_cmd == 3:
            lookup: dict[int, FrameList] = self.line
        else:
            lookup = {}
            for target in path_type_mapping.values():
                if target is self.line:
                    continue
                for hash_id, frames in target.items():
                    lookup[hash_id] = frames

        incomplete: list[int] = []
        for root_list in self.root_hash_lists:
            if root_list.sub_cmd != sub_cmd:
                continue
            for obj in root_list.data:
                for hash_id in obj.data_couple:
                    entry = lookup.get(hash_id)
                    if entry is None or self.find_missing_frames(entry):
                        incomplete.append(hash_id)
        return incomplete

    def missing_root_hash_frame(self, hash_list: NavGetHashListAck) -> list[int]:
        """Return 1-based frame numbers missing from the RootHashList matching *hash_list*."""
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
        """Insert or replace *hash_list* in its matching RootHashList, creating one if absent.

        Matching is by (total_frame, sub_cmd); within a match, by current_frame.
        """
        target_root_list = next(
            (
                rhl
                for rhl in self.root_hash_lists
                if rhl.total_frame == hash_list.total_frame and rhl.sub_cmd == hash_list.sub_cmd
            ),
            None,
        )

        if target_root_list is None:
            new_root_list = RootHashList(total_frame=hash_list.total_frame, sub_cmd=hash_list.sub_cmd, data=[hash_list])
            self.root_hash_lists.append(new_root_list)
            return

        for index, obj in enumerate(target_root_list.data):
            if obj.current_frame == hash_list.current_frame:
                target_root_list.data[index] = hash_list
                return

        target_root_list.data.append(hash_list)

    def missing_hash_frame(self, hash_ack: NavGetHashListAck) -> list[int]:
        """Return missing frame numbers across every RootHashList matching ``hash_ack.sub_cmd``."""
        missing_frames = []
        filtered_lists = [rl for rl in self.root_hash_lists if rl.sub_cmd == hash_ack.sub_cmd]
        for root_list in filtered_lists:
            missing = self.find_missing_frames(root_list)
            if missing:
                missing_frames.extend(missing)
        return missing_frames

    def missing_frame(self, hash_data: NavGetCommDataAck | SvgMessageAckT) -> list[int]:
        """Return frame numbers not yet received for the FrameList identified by *hash_data*."""
        frame_list = self._get_frame_list_by_type_and_hash(hash_data)
        return self.find_missing_frames(frame_list)

    def _get_frame_list_by_type_and_hash(self, hash_data: NavGetCommDataAck | SvgMessageAckT) -> FrameList | None:
        """Return the FrameList for *hash_data*, or ``None`` if the type isn't tracked.

        SvgMessageAckT keys by ``data_hash``; NavGetCommDataAck keys by ``hash``.
        """
        path_type_mapping = self._get_path_type_mapping()
        target_dict = path_type_mapping.get(hash_data.type)

        if target_dict is None:
            return None

        if isinstance(hash_data, SvgMessageAckT):
            return target_dict.get(hash_data.data_hash)

        return target_dict.get(hash_data.hash)

    def update_plan(self, plan: Plan) -> None:
        """Store *plan* by ``plan_id``; drop plans whose ``total_plan_num`` is zero."""
        if plan.total_plan_num != 0:
            self.plan[plan.plan_id] = plan

    def _get_path_type_mapping(self) -> dict[int, dict[int, FrameList]]:
        """Return a ``PathType → per-type dict`` mapping for dispatch."""
        return {
            PathType.AREA: self.area,
            PathType.OBSTACLE: self.obstacle,
            PathType.PATH: self.path,
            PathType.LINE: self.line,
            PathType.DUMP: self.dump,
            PathType.SVG: self.svg,
            PathType.VISUAL_SAFETY_ZONE: self.visual_safety_zone,
            PathType.VISUAL_OBSTACLE_ZONE: self.visual_obstacle_zone,
            PathType.CORRIDOR_LINE: self.corridor_line,
            PathType.CORRIDOR_POINT: self.corridor_point,
            PathType.VIRTUAL_WALL: self.virtual_wall,
        }

    def update(self, hash_data: NavGetCommData | SvgMessage) -> bool:
        """Route *hash_data* into the appropriate per-type dict and return whether it was new.

        AREA frames also auto-assign an ``area_name`` ("area N") if none exists
        for the hash yet.  DYNAMICS_LINE (type 18) is keyed by frame order and
        resets on ``current_frame == 1``.
        """
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

        # DYNAMICS_LINE is normally assembled by CommonDataSaga and stored via
        # update_dynamics_line; handle direct arrivals defensively here.
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
        """Replace ``dynamics_line`` with *points*.

        The device always returns the full current-session path, not a delta.
        """
        self.dynamics_line = points

    def find_missing_mow_path_frames(self) -> dict[int, list[int]]:
        """Return ``{transaction_id: [missing_frame, …]}`` for incomplete transactions only."""
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
        """Store *path* at ``current_mow_path[transaction_id][current_frame]``."""
        # TODO check if we need to clear the current_mow_path first
        transaction_id = path.transaction_id
        if transaction_id not in self.current_mow_path:
            self.current_mow_path[transaction_id] = {}
        self.current_mow_path[transaction_id][path.current_frame] = path

    def upsert_edge_frame(
        self,
        hash_key: int,
        action: int,
        edge_type: int,
        total_frame: int,
        current_frame: int,
        points: list[CommDataCouple],
    ) -> None:
        """Insert or update one edge-point frame for *hash_key*.

        ``total_frame`` is refreshed on each call because the device can adjust
        it mid-stream.
        """
        existing = self.edge_points.get(hash_key)
        if existing is None:
            existing = EdgePoints(
                hash=hash_key,
                action=action,
                type=edge_type,
                total_frame=total_frame,
            )
            self.edge_points[hash_key] = existing
        else:
            existing.total_frame = total_frame
        existing.frames[current_frame] = points

    def drop_incomplete_frames(self) -> None:
        """Drop ``area``/``path``/``obstacle`` entries missing any frame."""
        for target in (self.area, self.path, self.obstacle):
            for hash_id in [h for h, frame in target.items() if self.find_missing_frames(frame)]:
                del target[hash_id]

    @staticmethod
    def find_missing_frames(frame_list: FrameList | RootHashList | None) -> list[int]:
        """Return 1-based frame numbers absent from ``frame_list.data``."""
        if frame_list is None:
            return []

        if frame_list.total_frame == len(frame_list.data):
            return []
        number_list = list(range(1, frame_list.total_frame + 1))

        current_frames = {frame.current_frame for frame in frame_list.data}
        return [num for num in number_list if num not in current_frames]

    @staticmethod
    def _add_hash_data(hash_dict: dict[int, FrameList], hash_data: NavGetCommData | SvgMessage) -> bool:
        """Insert *hash_data* into *hash_dict*; return True if anything was stored.

        Creates a new FrameList for a first sighting, otherwise appends the
        frame unless its ``current_frame`` is already present.
        """
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
        """Trigger a map re-fetch when the device reports a new ``bol_hash``.

        The ``bol_hash`` reported in every ``toapp_report_data`` is a checksum
        of the current area-root hash list.  A mismatch means the map was
        edited device-side.

        Only ``root_hash_lists`` is cleared so that :class:`MapFetchSaga` knows
        to re-request it.  Per-type dicts (``area``, ``path``, ``obstacle`` …)
        are preserved: once the new root hash list is fetched,
        :meth:`update_hash_lists` filters them to remove hash IDs that are no
        longer present, so entries for deleted areas are discarded then rather
        than now.  Hash IDs that remain in the new list re-use their cached
        frames and are not re-fetched.
        """
        if MurMurHashUtil.hash_unsigned_list(self.area_root_hashlist) == bol_hash:
            return
        self.root_hash_lists = []

    def invalidate_mow_path(self, path_hash: int) -> None:
        """Clear cached mow-path data once the job has ended.

        Only fires for ``path_hash in (0, 1)``.  Non-zero mid-job values must
        be preserved — the device advances ub_path_hash through segments during
        a mow and wiping on every change would discard live data.
        """
        if path_hash == 0 or path_hash == 1:
            self.current_mow_path = {}
            self.generated_mow_path_geojson = {}
            self.generated_mow_progress_geojson = {}
            self.last_ub_path_hash = 0

    def has_mow_path_for_hash(self, ub_path_hash: int) -> bool:
        """Return True if cover-path data for *ub_path_hash* is already cached.

        Matches against ``path_packets[0].path_hash`` in any transaction's first
        frame — the device uses ub_path_hash to identify the active segment.
        """
        for frames in self.current_mow_path.values():
            for mow_path in frames.values():
                if mow_path.path_packets and mow_path.path_packets[0].path_hash == ub_path_hash:
                    return True
        return False

    def invalidate_breakpoint_line(self, ub_path_hash: int) -> bool:
        """Sync ``self.line`` to the device's active breakpoint hash; return True if a fetch is needed.

        ``self.line`` caches type-10 breakpoint segments keyed by ub_path_hash.
        Passing 0 clears the cache (mower is not on a breakpoint line).  A
        non-zero hash keeps only the matching entry and discards stale ones;
        returns True when the active hash isn't yet cached.
        """
        if ub_path_hash == 0:
            self.line = {}
            return False
        self.line = {h: frames for h, frames in self.line.items() if h == ub_path_hash}
        return ub_path_hash not in self.line

    def generate_geojson(self, rtk: LocationPoint, dock: Dock) -> Any:
        """Rebuild ``generated_geojson`` from the cached frames."""
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
        """Rebuild ``generated_mow_path_geojson`` from the cached mow-path frames."""
        from pymammotion.data.model.generate_geojson import GeojsonGenerator

        coordinator_converter = CoordinateConverter(rtk.latitude, rtk.longitude)
        rtk_real_loc = coordinator_converter.enu_to_lla(0, 0)

        self.generated_mow_path_geojson = GeojsonGenerator.generate_mow_path_geojson(
            self,
            Point(rtk_real_loc.latitude, rtk_real_loc.longitude),
        )

        return self.generated_mow_path_geojson

    def apply_mow_progress_geojson(
        self,
        rtk: LocationPoint,
        now_index: int,
        ub_path_hash: int,
        path_pos_x: int,
        path_pos_y: int,
    ) -> None:
        """Slice ``current_mow_path`` to *now_index* and store as progress GeoJSON.

        No-op when RTK isn't fixed (``latitude == 0``), ``now_index`` is
        negative, or no mow path is cached.  ``path_pos_x``/``path_pos_y`` are
        device-side integers scaled by 1e4.
        """
        from pymammotion.data.model.generate_geojson import GeojsonGenerator

        if rtk.latitude == 0 or now_index < 0 or not self.current_mow_path:
            return

        raw_x = path_pos_x / 10000.0
        raw_y = path_pos_y / 10000.0
        path_pos = (raw_x, raw_y) if (raw_x != 0.0 or raw_y != 0.0) else None

        conv = CoordinateConverter(rtk.latitude, rtk.longitude)
        rtk_ll = conv.enu_to_lla(0, 0)
        self.generated_mow_progress_geojson = GeojsonGenerator.generate_mow_progress_geojson(
            self,
            now_index,
            Point(rtk_ll.latitude, rtk_ll.longitude),
            ub_path_hash=ub_path_hash,
            path_pos=path_pos,
        )

    def apply_dynamics_line_geojson(self, rtk: LocationPoint) -> None:
        """Convert ``dynamics_line`` to a WGS-84 LineString GeoJSON.

        No-op when RTK isn't fixed or fewer than two points have been received.
        """
        from pymammotion.data.model.generate_geojson import GeojsonGenerator

        if rtk.latitude == 0 or len(self.dynamics_line) < 2:
            return

        conv = CoordinateConverter(rtk.latitude, rtk.longitude)
        rtk_ll = conv.enu_to_lla(0, 0)
        self.generated_dynamics_line_geojson = GeojsonGenerator.generate_dynamics_line_geojson(
            self.dynamics_line,
            Point(rtk_ll.latitude, rtk_ll.longitude),
        )
