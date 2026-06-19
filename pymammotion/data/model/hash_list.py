"""Hash-keyed map data model: frame lists, area/obstacle/path storage, and HashList."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any

from mashumaro.mixins.orjson import DataClassORJSONMixin
from shapely import Point

from pymammotion.proto import NavGetCommDataAck, NavGetHashListAck, SvgMessageAckT
from pymammotion.utility.map import CoordinateConverter
from pymammotion.utility.mur_mur_hash import MurMurHashUtil

if TYPE_CHECKING:
    from pymammotion.data.model.location import Dock, LocationPoint


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

    TRANSFER_ZONE = 3
    """Turning/transfer zone near the charging dock (待转区).

    Ephemeral — requested just before docking, hash is always 0, never persisted
    to the device DB.  Rendered by the APK as a separate ``areaToBeTransferredFeature``
    overlay, distinct from regular area boundaries.
    """

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

    NO_GO_ZONE_VARIANT = 22
    """Sibling of NO_GO_ZONE (23).  Both encode as ``(shape=0, type=1)`` in
    ``ManualElementMessage`` and are grouped with the user-drawn manual
    elements (21/22/23/24/25) in APK ``AreaDBHelper.deleteMapElementDB231``.
    The exact distinction from NO_GO_ZONE isn't visible in the decompiled
    APK — one variant is likely vision-detected (mirroring the 25/26
    safe/visual-obstacle split) but this isn't confirmed.  Stored separately
    in ``HashList.no_go_zone_variant`` so the two aren't conflated.
    """

    NO_GO_ZONE = 23
    """User-drawn rectangular no-go zone (APK: ``updateNoGoZone`` /
    ``rectangularRestrictedPoint``).  Observed on LUBA_VA — siblings are
    21 (virtual wall line), 25 (safe rectangle), 26 (visual obstacle zone).
    """

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
    data_couple: list[CommDataCouple] = field(default_factory=list)
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
    data_couple: list[CommDataCouple] = field(default_factory=list)


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
    svg_message: SvgMessageData = field(default_factory=SvgMessageData)


@dataclass
class FrameList(DataClassORJSONMixin):
    """Accumulates the ordered frames for a single hash-keyed map data entry."""

    total_frame: int = 0
    sub_cmd: int = 0
    data: list[NavGetCommData] = field(default_factory=list)

    @property
    def name(self) -> str:
        """Return name_time.name from the first data frame, or empty string if absent."""
        if self.data:
            return self.data[0].name_time.name
        return ""


@dataclass
class SvgFrameList(DataClassORJSONMixin):
    """Accumulates SvgMessage frames for a single SVG tile hash.

    Stored separately from FrameList so mashumaro can deserialize the
    unambiguous ``list[SvgMessage]`` type without union discrimination.
    """

    total_frame: int = 0
    sub_cmd: int = 0
    data: list[SvgMessage] = field(default_factory=list)


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

    # --- enable / rename helpers -----------------------------------------
    # ``reserved`` is an 8-byte buffer the device stores alongside the
    # plan.  Byte 2 = enable flag (0/1); the other bytes carry settings
    # encoded with a +10 offset (exact meaning not fully decoded —
    # ``docs/tasks_and_schedules.md`` § 1.3).  For enable/rename/copy
    # we round-trip the stored buffer verbatim and only mutate byte 2 so
    # callers don't have to know the layout.
    #
    # All bytes the APK writes are < 128, so latin-1 round-trips
    # losslessly between str and bytes.

    def is_enabled(self) -> bool:
        """Return True when the plan's enable flag (``reserved[2]``) is set.

        The device adds +10 to every reserved byte on echo, so byte 2 arrives
        as 10 (enabled) or 11 (disabled) in stored plans.  After a local
        ``with_enabled`` call the byte is 0 (enabled) or 1 (disabled) — the
        pre-echo value that will be sent to the device.  Both encodings are
        recognised so ``is_enabled()`` is correct on both received and
        just-modified plans.  Plans with a missing or short buffer default to
        enabled (matching APK behaviour).
        """
        raw = self.reserved.encode("latin-1") if self.reserved else b""
        if len(raw) <= 2:
            return True
        # 0 = enabled (app/send encoding); 10 = enabled (device-echo encoding)
        return raw[2] in (0, 10)

    def with_enabled(self, enabled: bool) -> Plan:
        """Return a copy of this plan with ``reserved[2]`` set for *enabled*.

        Sends byte 2 = 0 (enable) or 1 (disable) — the device adds +10 to all
        bytes on echo, so it will store/return 10 (enabled) or 11 (disabled).
        Bytes 0,1,3..7 are preserved verbatim.
        """
        raw = bytearray(self.reserved.encode("latin-1") if self.reserved else b"")
        if len(raw) < 8:
            raw.extend(b"\x00" * (8 - len(raw)))
        raw[2] = 0 if enabled else 1
        return dataclasses.replace(self, reserved=raw.decode("latin-1"))

    def with_renamed(self, new_name: str) -> Plan:
        """Return a copy of this plan with ``task_name`` set to *new_name*."""
        return dataclasses.replace(self, task_name=new_name)


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
    svg: dict[int, SvgFrameList] = field(default_factory=dict)  # type 13
    line: dict[int, FrameList] = field(
        default_factory=dict
    )  # type 10, sub cmd 3 — breakpoint line data, keyed by ub_path_hash
    visual_safety_zone: dict[int, FrameList] = field(default_factory=dict)  # type 25
    visual_obstacle_zone: dict[int, FrameList] = field(default_factory=dict)  # type 26
    corridor_line: dict[int, FrameList] = field(default_factory=dict)  # type 19
    corridor_point: dict[int, FrameList] = field(default_factory=dict)  # type 20
    transfer_zone: dict[int, FrameList] = field(default_factory=dict)  # type 3 — ephemeral dock turning zone
    virtual_wall: dict[int, FrameList] = field(default_factory=dict)  # type 21
    no_go_zone_variant: dict[int, FrameList] = field(default_factory=dict)  # type 22
    no_go_zone: dict[int, FrameList] = field(default_factory=dict)  # type 23
    plan: dict[str, Plan] = field(default_factory=dict)
    area_name: list[AreaHashNameList] = field(default_factory=list)
    current_mow_path: dict[int, dict[int, MowPath]] = field(default_factory=dict)
    generated_geojson: dict[str, Any] = field(default_factory=dict)
    geojson_yaw: float = 0.0  # RTK yaw (radians) used when generated_geojson was last built
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

    #: Fallback storage for frames whose ``type`` isn't in ``PathType`` (e.g.
    #: radar-only types like 23 observed on LUBA_VA).  Keyed [type][hash].
    #: ``find_incomplete_hashes`` consults this so an unknown-type hash isn't
    #: forever flagged as missing and stalling ``MapFetchSaga``.
    unknown_type_frames: dict[int, dict[int, FrameList]] = field(default_factory=dict)

    #: Frozen snapshot of ``area_root_hashlist`` taken when ``generated_geojson``
    #: was last built.  Used by ``geojson_needs_regeneration`` to short-circuit
    #: the expensive feature-walk when the hashlist hasn't changed.
    _geojson_hashlist_snapshot: frozenset[int] = field(default_factory=frozenset)

    def __deepcopy__(self, memo: dict[int, Any]) -> HashList:
        """Deepcopy that shares the four ``generated_*_geojson`` dicts by reference.

        These dicts can be MB-sized for large maps and are the dominant cost of
        the per-frame ``copy.deepcopy(current.map)`` in ``MowerStateReducer.apply``.
        They are ONLY ever replaced wholesale by the matching ``generate_*_geojson``
        methods — never mutated in place — so sharing references across copies
        is safe.
        """
        import copy as _copy

        cls = self.__class__
        new = cls.__new__(cls)
        memo[id(self)] = new
        shared_geojson = {
            "generated_geojson",
            "generated_mow_path_geojson",
            "generated_mow_progress_geojson",
            "generated_dynamics_line_geojson",
        }
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if f.name in shared_geojson:
                object.__setattr__(new, f.name, value)
            else:
                object.__setattr__(new, f.name, _copy.deepcopy(value, memo))
        return new

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
        self.corridor_line = {hash_id: frames for hash_id, frames in self.corridor_line.items() if hash_id in hashlist}
        self.corridor_point = {
            hash_id: frames for hash_id, frames in self.corridor_point.items() if hash_id in hashlist
        }
        self.virtual_wall = {hash_id: frames for hash_id, frames in self.virtual_wall.items() if hash_id in hashlist}
        known_types = set(self._get_path_type_mapping())
        self.unknown_type_frames = {t: bucket for t, bucket in self.unknown_type_frames.items() if t not in known_types}

        area_hashes = list(self.area.keys())
        for hash_id, plan_task in self.plan.copy().items():
            for item in plan_task.zone_hashs:
                if item not in area_hashes:
                    self.plan.pop(hash_id)
                    break

        # area_name is preserved here: orphans (whose hash is no longer in
        # self.area) are harmless because consumers key lookups by hash, and
        # dropping them racily empties the list mid-fetch.  toapp_all_hash_name
        # responses replace area_name wholesale in the saga / state reducer.

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
        """Return hash IDs from ``root_hash_lists`` entries with ``sub_cmd == 0`` (area).

        Frames are sorted by ``current_frame`` so the concatenated list is in the
        same position order the device used when building its ``bol_hash``.
        """
        if not self.root_hash_lists:
            return []
        return [
            i
            for root_list in self.root_hash_lists
            if root_list.sub_cmd == 0
            for obj in sorted(root_list.data, key=lambda d: d.current_frame)
            for i in obj.data_couple
        ]

    @property
    def computed_bol_hash(self) -> int:
        """Compute the map's bol_hash from locally stored area hash IDs.

        Mirrors the APK's ``HashDataManager.getDBCmHash()``, which MurMur-hashes
        the list of all locally stored MapElement hashes.  When our stored area
        hashes are in sync with the device, this value equals the device's
        reported ``bol_hash`` in ``report_data.locations[0].bol_hash``.

        Returns 0 when no area hashes have been fetched yet.
        """
        hashes = [h for h in self.area_root_hashlist if h != 0]
        if not hashes:
            return 0
        return int(MurMurHashUtil.hash_unsigned_list(hashes))

    @property
    def computed_areas(self) -> list[AreaHashNameList]:
        """Merge area_name and area into a fully-named list.

        For every hash in self.area:
        * If area_name already has an entry with a non-empty name → keep it.
        * If area_name has an entry but name is empty → fill from FrameList.name,
          or auto-assign the lowest unused "Area N" number.
        * If area_name has no entry at all → same as above but also add one.

        Returns a fresh list of fresh AreaHashNameList objects, so the caller
        may mutate without affecting ``self.area_name``.
        """
        # O(A) — one pass to clone entries and build a hash → entry index, plus
        # one pass to compute the initial set of used "Area N" numbers.  The
        # main loop is then O(A) with O(1) lookups, replacing the previous
        # O(A²) next()/comprehension-per-area pattern.
        area_name_list: list[AreaHashNameList] = [AreaHashNameList(name=a.name, hash=a.hash) for a in self.area_name]
        by_hash: dict[int, AreaHashNameList] = {a.hash: a for a in area_name_list}
        used_numbers: set[int] = {
            int(a.name.split()[-1])
            for a in area_name_list
            if a.name.lower().startswith("area ") and a.name.split()[-1].isdigit()
        }
        next_n = 1

        def _take_next_number() -> int:
            nonlocal next_n
            while next_n in used_numbers:
                next_n += 1
            used_numbers.add(next_n)
            return next_n

        for hash_id, area in self.area.items():
            existing_area = by_hash.get(hash_id)
            if existing_area is None:
                if area.name:
                    entry = AreaHashNameList(name=area.name, hash=hash_id)
                else:
                    entry = AreaHashNameList(name=f"Area {_take_next_number()}", hash=hash_id)
                area_name_list.append(entry)
                by_hash[hash_id] = entry
            elif not existing_area.name and area.name:
                existing_area.name = area.name
            elif not existing_area.name:
                existing_area.name = f"Area {_take_next_number()}"

        return area_name_list

    def upsert_area_name(self, hash_id: int, name: str) -> None:
        """Set (or insert) the display name for a single area hash.

        Used by the ``toapp_map_name_msg`` reducer path: when the app renames an
        area the device acks with one ``NavMapNameMsg`` (hash + new name) rather
        than re-sending the whole ``toapp_all_hash_name`` list, so we patch the
        matching ``area_name`` entry in place, appending one if the hash is not
        yet tracked.
        """
        for entry in self.area_name:
            if entry.hash == hash_id:
                entry.name = name
                return
        self.area_name.append(AreaHashNameList(name=name, hash=hash_id))

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
        if sub_cmd == 3:
            lookup: dict[int, FrameList] = self.line
            svg_for_hash: dict[int, list[SvgFrameList]] = {}
        else:
            lookup = {}
            for target in path_type_mapping.values():
                if target is self.line:
                    continue
                for hash_id, frames in target.items():
                    lookup[hash_id] = frames
            # Include unknown-type frames so hashes whose only data arrived
            # under a type pymammotion doesn't model still count as fetched.
            for bucket in self.unknown_type_frames.values():
                for hash_id, frames in bucket.items():
                    lookup.setdefault(hash_id, frames)
            # Build a reverse mapping so each data_couple hash_id can be checked
            # against every SVG tile it owns — both by direct data_hash match
            # (when the SVG tile's own hash == the area hash) and by paternal_hash_a
            # (when the SVG tile has a distinct hash but is linked to this area).
            svg_for_hash = {}
            for data_hash, svg_fl in self.svg.items():
                svg_for_hash.setdefault(data_hash, []).append(svg_fl)
                if svg_fl.data:
                    parent = svg_fl.data[0].paternal_hash_a
                    if parent and parent != data_hash:
                        svg_for_hash.setdefault(parent, []).append(svg_fl)

        incomplete: list[int] = []
        for root_list in self.root_hash_lists:
            if root_list.sub_cmd != sub_cmd:
                continue
            for obj in root_list.data:
                for hash_id in obj.data_couple:
                    if hash_id == 0:
                        continue
                    area_entry = lookup.get(hash_id)
                    svg_entries = svg_for_hash.get(hash_id, [])

                    # Nothing fetched at all for this hash yet.
                    if area_entry is None and not svg_entries:
                        incomplete.append(hash_id)
                        continue

                    # Area/boundary data exists but is still partial.
                    if area_entry is not None and self.find_missing_frames(area_entry):
                        incomplete.append(hash_id)
                        continue

                    # Any associated SVG tile (by data_hash or paternal_hash_a) is partial.
                    if any(self.find_missing_frames(fl) for fl in svg_entries):
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

    def _get_frame_list_by_type_and_hash(
        self, hash_data: NavGetCommDataAck | SvgMessageAckT
    ) -> FrameList | SvgFrameList | None:
        """Return the frame list for *hash_data*, or ``None`` if the type isn't tracked.

        SvgMessageAckT keys by ``data_hash`` into self.svg (SvgFrameList);
        NavGetCommDataAck keys by ``hash`` into the per-type FrameList dicts.
        """
        if isinstance(hash_data, SvgMessageAckT):
            return self.svg.get(hash_data.data_hash)

        path_type_mapping = self._get_path_type_mapping()
        target_dict = path_type_mapping.get(hash_data.type)
        if target_dict is None:
            return None
        return target_dict.get(hash_data.hash)

    def update_plan(self, plan: Plan) -> None:
        """Store *plan* by ``plan_id``; drop plans whose ``total_plan_num`` is zero."""
        if plan.total_plan_num != 0:
            self.plan[plan.plan_id] = plan

    def _get_path_type_mapping(self) -> dict[int, dict[int, FrameList]]:
        """Return a ``PathType → per-type dict`` mapping for NavGetCommData dispatch.

        SVG is intentionally excluded — SVG data arrives as SvgMessage (not
        NavGetCommData) and is stored in self.svg (dict[int, SvgFrameList]).
        """
        return {
            PathType.AREA: self.area,
            PathType.OBSTACLE: self.obstacle,
            PathType.PATH: self.path,
            PathType.TRANSFER_ZONE: self.transfer_zone,
            PathType.LINE: self.line,
            PathType.DUMP: self.dump,
            PathType.VISUAL_SAFETY_ZONE: self.visual_safety_zone,
            PathType.VISUAL_OBSTACLE_ZONE: self.visual_obstacle_zone,
            PathType.CORRIDOR_LINE: self.corridor_line,
            PathType.CORRIDOR_POINT: self.corridor_point,
            PathType.VIRTUAL_WALL: self.virtual_wall,
            PathType.NO_GO_ZONE_VARIANT: self.no_go_zone_variant,
            PathType.NO_GO_ZONE: self.no_go_zone,
        }

    def update(self, hash_data: NavGetCommData | SvgMessage) -> bool:
        """Route *hash_data* into the appropriate per-type dict and return whether it was new.

        AREA frames also auto-assign an ``area_name`` ("Area N") if none exists
        for the hash yet.  DYNAMICS_LINE (type 18) is keyed by frame order and
        resets on ``current_frame == 1``.

        Unknown types (e.g. radar-specific 23 we've seen on LUBA_VA) are stored
        in ``unknown_type_frames`` so the hash is still tracked as "received".
        Without this, ``find_incomplete_hashes`` would keep flagging the hash
        as missing and ``MapFetchSaga`` would stall re-requesting it.

        SvgMessage frames go to self.svg (SvgFrameList) via _add_svg_data.
        NavGetCommData with type=SVG is discarded — real SVG geometry only
        arrives as SvgMessage from toapp_svg_msg.
        """
        if isinstance(hash_data, SvgMessage):
            return self._add_svg_data(self.svg, hash_data)

        if hash_data.type == PathType.AREA:
            result = self._add_hash_data(self.area, hash_data)
            self.update_hash_lists(self.hashlist)
            return result

        # DYNAMICS_LINE is normally assembled by CommonDataSaga and stored via
        # update_dynamics_line; handle direct arrivals defensively here.
        if hash_data.type == PathType.DYNAMICS_LINE:
            if hash_data.current_frame == 1:
                self.dynamics_line = []
            self.dynamics_line.extend(hash_data.data_couple)
            return True

        # NavGetCommData with type=SVG carries no geometry — real SVG geometry only
        # arrives as SvgMessage (toapp_svg_msg).  Discard rather than storing it as a
        # geometry-less unknown-type frame (which would also mark the hash "received"
        # via find_incomplete_hashes and skip fetching its real data).
        if hash_data.type == PathType.SVG:
            return False

        path_type_mapping = self._get_path_type_mapping()
        target_dict = path_type_mapping.get(hash_data.type)

        if target_dict is not None:
            return self._add_hash_data(target_dict, hash_data)

        # Unknown type — store under unknown_type_frames keyed by (type, hash)
        # so the hash is still considered "received" by find_incomplete_hashes.
        bucket = self.unknown_type_frames.setdefault(hash_data.type, {})
        return self._add_hash_data(bucket, hash_data)

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
    def find_missing_frames(frame_list: FrameList | SvgFrameList | RootHashList | None) -> list[int]:
        """Return 1-based frame numbers absent from ``frame_list.data``."""
        if frame_list is None:
            return []

        if frame_list.total_frame == len(frame_list.data):
            return []
        number_list = list(range(1, frame_list.total_frame + 1))

        current_frames = {frame.current_frame for frame in frame_list.data}
        return [num for num in number_list if num not in current_frames]

    @staticmethod
    def _add_svg_data(svg_dict: dict[int, SvgFrameList], hash_data: SvgMessage) -> bool:
        """Insert *hash_data* into *svg_dict*; return True if anything was stored."""
        entry = svg_dict.get(hash_data.data_hash)
        if entry is None:
            svg_dict[hash_data.data_hash] = SvgFrameList(total_frame=hash_data.total_frame, data=[hash_data])
            return True
        if any(f.current_frame == hash_data.current_frame for f in entry.data):
            return True
        entry.data.append(hash_data)
        return True

    @staticmethod
    def _add_hash_data(hash_dict: dict[int, FrameList], hash_data: NavGetCommData) -> bool:
        """Insert *hash_data* into *hash_dict*; return True if anything was stored.

        Creates a new FrameList for a first sighting, otherwise appends the
        frame unless its ``current_frame`` is already present.
        """
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

    def is_map_synced(self, bol_hash: int) -> bool:
        """Return True when the local map state is fully in sync with the device.

        Three conditions must all hold:

        * **BOL hash match** — ``computed_bol_hash == bol_hash``: our root hash
          list reflects the device's current area set.
        * **No incomplete areas** — ``find_incomplete_hashes(0)`` is empty:
          every area declared in ``root_hash_lists`` has all its frame data.
        * **Area names covered** — every hash in ``area_name`` is present in
          ``area_root_hashlist``: the device's name list and our root manifest
          agree on which areas exist.

        Returns False immediately when *bol_hash* is 0 (device has not yet
        reported a valid hash) or when ``root_hash_lists`` is empty.
        """
        if not bol_hash:
            return False
        if self.computed_bol_hash != bol_hash:
            return False
        if self.find_incomplete_hashes(0):
            return False
        area_name_hashes = {a.hash for a in self.area_name}
        return not area_name_hashes or area_name_hashes.issubset(set(self.area_root_hashlist))

    def invalidate_maps(self, bol_hash: int) -> None:
        """Trigger a map re-fetch when the device reports a new ``bol_hash``.

        The ``bol_hash`` reported in every ``toapp_report_data`` is a checksum
        of the current area-root hash list.  A mismatch means the map was
        edited device-side.

        Only ``root_hash_lists`` entries with ``sub_cmd == 0`` (areas) are
        removed so that :class:`MapFetchSaga` knows to re-request the area
        manifest.  Entries for other sub_cmds (lines, dump points, …) are
        preserved.  Per-type geometry dicts (``area``, ``path``, ``obstacle`` …)
        are also preserved: once the new root hash list is fetched,
        :meth:`update_hash_lists` filters them to remove hash IDs that are no
        longer present, so entries for deleted areas are discarded then rather
        than now.  Hash IDs that remain in the new list re-use their cached
        frames and are not re-fetched.
        """
        if not bol_hash or self.computed_bol_hash == bol_hash:
            return
        self.root_hash_lists = [rl for rl in self.root_hash_lists if rl.sub_cmd != 0]
        self.update_hash_lists(self.hashlist)

    def invalidate_mow_path(self, path_hash: int) -> None:
        """Clear cached mow-path data once the job has ended.

        Only fires for ``path_hash in (0, 1)``.  Non-zero mid-job values must
        be preserved — the device advances ub_path_hash through segments during
        a mow and wiping on every change would discard live data.
        """
        if path_hash == 0:
            self.current_mow_path = {}
            self.generated_mow_path_geojson = {}
            self.generated_mow_progress_geojson = {}
            self.last_ub_path_hash = 0

    def has_mow_path_for_hash(self, path_hash: int) -> bool:
        """Return True if cover-path data for *path_hash* is already cached.

        Matches against ``path_packets[0].path_hash`` in any transaction's first
        frame — equals ``work.path_hash`` (field 2) when the cached data is current.
        """
        for frames in self.current_mow_path.values():
            for mow_path in frames.values():
                if mow_path.path_packets and mow_path.path_packets[0].path_hash == path_hash:
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

    def geojson_needs_regeneration(self, rtk: LocationPoint, yaw_threshold: float = 0.01) -> bool:
        """Return True if the stored GeoJSON is absent, has a stale RTK yaw, or has stale map hashes.

        A difference larger than *yaw_threshold* radians (~0.6°) means the
        coordinate rotation used at generation time no longer matches the
        current RTK heading, so the GeoJSON should be regenerated.

        Hash staleness is detected by comparing the current
        ``area_root_hashlist`` against the snapshot taken when the GeoJSON was
        last built.  If unchanged, the expensive per-feature hash walk is
        skipped — the dominant cost on the ~4 Hz ``system_update_buf`` hot
        path during mowing.
        """
        if not self.generated_geojson:
            return True
        if abs(rtk.yaw - self.geojson_yaw) > yaw_threshold:
            return True
        current_hashlist = frozenset(self.area_root_hashlist)
        if not current_hashlist:
            return False
        if current_hashlist == self._geojson_hashlist_snapshot:
            return False
        # Hashlist changed since last generation — verify whether any feature
        # references a hash that no longer exists on the device.
        geojson_hashes = {
            f["properties"]["hash"]
            for f in self.generated_geojson.get("features", [])
            if isinstance(f.get("properties"), dict) and f["properties"].get("hash") is not None
        }
        return bool(geojson_hashes - current_hashlist)

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
            yaw=rtk.yaw,
        )
        self.geojson_yaw = rtk.yaw
        # Record the hashlist used so the next geojson_needs_regeneration()
        # can short-circuit when state hasn't changed.
        self._geojson_hashlist_snapshot = frozenset(self.area_root_hashlist)

    def generate_mowing_geojson(self, rtk: LocationPoint) -> Any:
        """Rebuild ``generated_mow_path_geojson`` from the cached mow-path frames."""
        from pymammotion.data.model.generate_geojson import GeojsonGenerator

        coordinator_converter = CoordinateConverter(rtk.latitude, rtk.longitude)
        rtk_real_loc = coordinator_converter.enu_to_lla(0, 0)

        self.generated_mow_path_geojson = GeojsonGenerator.generate_mow_path_geojson(
            self,
            Point(rtk_real_loc.latitude, rtk_real_loc.longitude),
            yaw=rtk.yaw,
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

        # "Unset" RTK is the exact-0.0 default (radians).  Compare to 0.0, NOT round(lat, 0):
        # rounding to 0 decimals collapses everything within ~0.5 rad (~28°) of the equator to
        # 0 and would skip real fixes.
        if rtk.latitude == 0.0 or now_index < 0 or not self.current_mow_path:
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
            yaw=rtk.yaw,
        )

    def apply_dynamics_line_geojson(self, rtk: LocationPoint) -> None:
        """Convert ``dynamics_line`` to a WGS-84 LineString GeoJSON.

        No-op when RTK isn't fixed or fewer than two points have been received.
        """
        from pymammotion.data.model.generate_geojson import GeojsonGenerator

        if rtk.latitude == 0.0 or len(self.dynamics_line) < 2:
            return

        conv = CoordinateConverter(rtk.latitude, rtk.longitude)
        rtk_ll = conv.enu_to_lla(0, 0)
        self.generated_dynamics_line_geojson = GeojsonGenerator.generate_dynamics_line_geojson(
            self.dynamics_line,
            Point(rtk_ll.latitude, rtk_ll.longitude),
            yaw=rtk.yaw,
        )
