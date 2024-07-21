from dataclasses import dataclass
from typing import TypedDict

from pymammotion.proto.mctrl_nav import NavGetCommDataAck


class FrameList(TypedDict):
    total_frame: int
    data: list[NavGetCommDataAck]


@dataclass
class HashList:
    """stores our map data.
    [hashID, FrameList]
    """

    area: dict  # type 1
    path: dict  # type 0
    obstacle: dict  # type 2

    def update(self, hash_data: NavGetCommDataAck):
        """Update the map data."""
        if hash_data.type == 0:
            if self.path.get(hash_data.hash) is None:
                self.path[hash_data.hash] = FrameList(total_frame=hash_data.total_frame, data=[hash_data])
            self.path[hash_data.hash].data.append(hash_data)

        if hash_data.type == 1:
            if self.area.get(hash_data.hash) is None:
                self.area[hash_data.hash] = FrameList(total_frame=hash_data.total_frame, data=[hash_data])
            self.area[hash_data.hash].data.append(hash_data)

        if hash_data.type == 2:
            if self.obstacle.get(hash_data.hash) is None:
                self.obstacle[hash_data.hash] = FrameList(total_frame=hash_data.total_frame, data=[hash_data])
            self.obstacle[hash_data.hash].data.append(hash_data)
