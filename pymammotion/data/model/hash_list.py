from dataclasses import dataclass, field
from enum import IntEnum

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.proto import NavGetCommDataAck, NavGetHashListAck, SvgMessageAckT


class PathType(IntEnum):
    """Path types for common data."""

    AREA = 0
    OBSTACLE = 1
    PATH = 2
    DUMP = 12
    SVG = 13


@dataclass
class CommDataCouple:
    x: float = 0.0
    y: float = 0.0


@dataclass
class AreaLabelName(DataClassORJSONMixin):
    label: str = ""


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
    area_label: "AreaLabelName" = field(default_factory=AreaLabelName)


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
    data_count: int = 0
    hide_svg: bool = False
    name_count: int = 0
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
    dump: dict[int, FrameList] = field(default_factory=dict)  # type 12?
    svg: dict[int, FrameList] = field(default_factory=dict)  # type 13
    area_name: list[AreaHashNameList] = field(default_factory=list)

    def update_hash_lists(self, hashlist: list[int]) -> None:
        self.area = {hash_id: frames for hash_id, frames in self.area.items() if hash_id in hashlist}
        self.path = {hash_id: frames for hash_id, frames in self.path.items() if hash_id in hashlist}
        self.obstacle = {hash_id: frames for hash_id, frames in self.obstacle.items() if hash_id in hashlist}
        self.dump = {hash_id: frames for hash_id, frames in self.dump.items() if hash_id in hashlist}
        self.svg = {hash_id: frames for hash_id, frames in self.svg.items() if hash_id in hashlist}
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

    def missing_hashlist(self, sub_cmd: int = 0) -> list[int]:
        """Return missing hashlist."""
        all_hash_ids = set(self.area.keys()).union(
            self.path.keys(), self.obstacle.keys(), self.dump.keys(), self.svg.keys()
        )
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

        return self._find_missing_frames(target_root_list)

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
            missing = self._find_missing_frames(root_list)
            if missing:
                missing_frames.extend(missing)
        return missing_frames

    def missing_frame(self, hash_data: NavGetCommDataAck | SvgMessageAckT) -> list[int]:
        if hash_data.type == PathType.AREA:
            return self._find_missing_frames(self.area.get(hash_data.hash))

        if hash_data.type == PathType.OBSTACLE:
            return self._find_missing_frames(self.obstacle.get(hash_data.hash))

        if hash_data.type == PathType.PATH:
            return self._find_missing_frames(self.path.get(hash_data.hash))

        if hash_data.type == PathType.DUMP:
            return self._find_missing_frames(self.dump.get(hash_data.hash))

        if hash_data.type == PathType.SVG:
            return self._find_missing_frames(self.svg.get(hash_data.data_hash))

        return []

    def update(self, hash_data: NavGetCommData | SvgMessage) -> bool:
        """Update the map data."""

        if hash_data.type == PathType.AREA:
            existing_name = next((area for area in self.area_name if area.hash == hash_data.hash), None)
            if not existing_name:
                name = f"area {len(self.area_name)+1}" if hash_data.area_label is None else hash_data.area_label.label
                self.area_name.append(AreaHashNameList(name=name, hash=hash_data.hash))
            result = self._add_hash_data(self.area, hash_data)
            self.update_hash_lists(self.hashlist)
            return result

        if hash_data.type == PathType.OBSTACLE:
            return self._add_hash_data(self.obstacle, hash_data)

        if hash_data.type == PathType.PATH:
            return self._add_hash_data(self.path, hash_data)

        if hash_data.type == PathType.DUMP:
            return self._add_hash_data(self.dump, hash_data)

        if hash_data.type == PathType.SVG:
            return self._add_hash_data(self.svg, hash_data)

        return False

    @staticmethod
    def _find_missing_frames(frame_list: FrameList | RootHashList) -> list[int]:
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
            if hash_dict.get(hash_data.data_hash) is None:
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

        if hash_dict.get(hash_data.hash) is None:
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
