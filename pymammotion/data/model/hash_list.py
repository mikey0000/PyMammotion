from dataclasses import dataclass, field
from enum import IntEnum

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.proto.mctrl_nav import AreaHashName, NavGetCommDataAck


class PathType(IntEnum):
    """Path types for common data."""

    AREA = 0
    OBSTACLE = 1
    PATH = 2


@dataclass
class FrameList(DataClassORJSONMixin):
    total_frame: int
    data: list[NavGetCommDataAck]


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

    area: dict = field(default_factory=dict)  # type 0
    path: dict = field(default_factory=dict)  # type 2
    obstacle: dict = field(default_factory=dict)  # type 1
    hashlist: list[int] = field(default_factory=list)
    area_name: list[AreaHashNameList] = field(default_factory=list)

    def set_hashlist(self, hashlist: list[int]) -> None:
        self.hashlist = hashlist
        self.area = {hash_id: frames for hash_id, frames in self.area.items() if hash_id in hashlist}
        self.path = {hash_id: frames for hash_id, frames in self.path.items() if hash_id in hashlist}
        self.obstacle = {hash_id: frames for hash_id, frames in self.obstacle.items() if hash_id in hashlist}

    def missing_frame(self, hash_data: NavGetCommDataAck) -> list[int]:
        if hash_data.type == PathType.AREA:
            return self._find_missing_frames(self.area.get(hash_data.hash))

        if hash_data.type == PathType.OBSTACLE:
            return self._find_missing_frames(self.obstacle.get(hash_data.hash))

        if hash_data.type == PathType.PATH:
            return self._find_missing_frames(self.path.get(hash_data.hash))

    def update(self, hash_data: NavGetCommDataAck) -> bool:
        """Update the map data."""
        if hash_data.type == PathType.AREA:
            existing_name = next((area for area in self.area_name if area.hash == hash_data.hash), None)
            if not existing_name:
                self.area_name.append(AreaHashName(name=f"area {len(self.area_name)+1}", hash=hash_data.hash))
            return self._add_hash_data(self.area, hash_data)

        if hash_data.type == PathType.OBSTACLE:
            return self._add_hash_data(self.obstacle, hash_data)

        if hash_data.type == PathType.PATH:
            return self._add_hash_data(self.path, hash_data)

    @staticmethod
    def _find_missing_frames(frame_list: FrameList) -> list[int]:
        if frame_list.total_frame == len(frame_list.data):
            return []
        number_list = list(range(1, frame_list.total_frame + 1))

        current_frames = {frame.current_frame for frame in frame_list.data}
        missing_numbers = [num for num in number_list if num not in current_frames]
        return missing_numbers

    @staticmethod
    def _add_hash_data(hash_dict: dict, hash_data: NavGetCommDataAck) -> bool:
        if hash_dict.get(hash_data.hash) is None:
            hash_dict[hash_data.hash] = FrameList(total_frame=hash_data.total_frame, data=[hash_data])
            return True

        if hash_data not in hash_dict[hash_data.hash].data:
            hash_dict[hash_data.hash].data.append(hash_data)
            return True
        return False
