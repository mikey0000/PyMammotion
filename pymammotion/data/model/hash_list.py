from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.proto import NavGetCommDataAck, NavGetHashListAck, SvgMessageAckT
from pymammotion.utility.mur_mur_hash import MurMurHashUtil


class PathType(IntEnum):
    """Path types for common data."""

    AREA = 0
    OBSTACLE = 1
    PATH = 2
    LINE = 10
    DUMP = 12
    SVG = 13
    VISUAL_SAFETY_ZONE = 25


@dataclass
class CommDataCouple:
    x: float = 0.0
    y: float = 0.0


@dataclass
class AreaLabelName(DataClassORJSONMixin):
    label: str = ""


@dataclass
class NavNameTime(DataClassORJSONMixin):
    name: str = ""
    create_time: int = 0
    modify_time: int = 0


@dataclass
class NavGetCommData(DataClassORJSONMixin):
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
    path_hash: int = 0
    path_type: int = 0
    path_total: int = 0
    path_cur: int = 0
    zone_hash: int = 0
    data_couple: list["CommDataCouple"] = field(default_factory=list)


@dataclass
class MowPath(DataClassORJSONMixin):
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
    total_frame: int = 0
    sub_cmd: int = 0
    data: list[NavGetCommData | SvgMessage] = field(default_factory=list)


@dataclass
class Plan(DataClassORJSONMixin):
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
    line: dict[int, FrameList] = field(default_factory=dict)  # type 10 possibly breakpoint? / sub cmd 3
    visual_safety_zone: dict[int, FrameList] = field(default_factory=dict)  # type 25
    plan: dict[str, Plan] = field(default_factory=dict)
    area_name: list[AreaHashNameList] = field(default_factory=list)
    current_mow_path: dict[int, dict[int, MowPath]] = field(default_factory=dict)
    generated_geojson: dict[str, Any] = field(default_factory=dict)
    generated_mow_path_geojson: dict[str, Any] = field(default_factory=dict)

    def update_hash_lists(self, hashlist: list[int], bol_hash: str | None = None) -> None:
        if bol_hash:
            self.invalidate_maps(int(bol_hash))
        self.area = {hash_id: frames for hash_id, frames in self.area.items() if hash_id in hashlist}
        self.path = {hash_id: frames for hash_id, frames in self.path.items() if hash_id in hashlist}
        self.obstacle = {hash_id: frames for hash_id, frames in self.obstacle.items() if hash_id in hashlist}
        self.dump = {hash_id: frames for hash_id, frames in self.dump.items() if hash_id in hashlist}
        self.svg = {hash_id: frames for hash_id, frames in self.svg.items() if hash_id in hashlist}
        self.visual_safety_zone = {hash_id: frames for hash_id, frames in self.visual_safety_zone.items() if hash_id in hashlist}

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
    def hashlist(self) -> list[int]:
        if not self.root_hash_lists:
            return []
        # Combine data_couple from all RootHashLists
        return [i for root_list in self.root_hash_lists for obj in root_list.data for i in obj.data_couple]

    @property
    def area_root_hashlist(self) -> list[int]:
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
            self.path.keys(), self.obstacle.keys(), self.dump.keys(), self.svg.keys(), self.visual_safety_zone.keys()
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
        }

    def update(self, hash_data: NavGetCommData | SvgMessage) -> bool:
        """Update the map data."""

        if hash_data.type == PathType.AREA and isinstance(hash_data, NavGetCommData):
            existing_name = next((area for area in self.area_name if area.hash == hash_data.hash), None)
            if not existing_name:
                name = f"area {len(self.area_name)+1}"
                self.area_name.append(AreaHashNameList(name=name, hash=hash_data.hash))
            result = self._add_hash_data(self.area, hash_data)
            self.update_hash_lists(self.hashlist)
            return result

        path_type_mapping = self._get_path_type_mapping()
        target_dict = path_type_mapping.get(hash_data.type)

        if target_dict is not None:
            return self._add_hash_data(target_dict, hash_data)

        return False

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
        if frame_list is None:
            return []

        if frame_list.total_frame == len(frame_list.data):
            return []
        number_list = list(range(1, frame_list.total_frame + 1))

        current_frames = {frame.current_frame for frame in frame_list.data}
        missing_numbers = [num for num in number_list if num not in current_frames]
        return missing_numbers

    @staticmethod
    def _add_hash_data(hash_dict: dict[int, FrameList], hash_data: NavGetCommData | SvgMessage) -> bool:
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
        if MurMurHashUtil.hash_unsigned_list(self.area_root_hashlist) != bol_hash:
            self.root_hash_lists = []
