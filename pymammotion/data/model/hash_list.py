from dataclasses import dataclass

from pymammotion.proto.mctrl_nav import NavGetCommDataAck


@dataclass
class FrameList:
    total_frame: int
    data: list[NavGetCommDataAck]


@dataclass
class HashList:
    """stores our map data.
    [hashID, FrameList].
    """

    area: dict  # type 0
    path: dict  # type 2
    obstacle: dict  # type 1

    def update(self, hash_data: NavGetCommDataAck) -> bool:
        """Update the map data."""
        if hash_data.type == 0:
            return self._add_hash_data(self.area, hash_data)

        if hash_data.type == 1:
            return self._add_hash_data(self.obstacle, hash_data)

        if hash_data.type == 2:
            return self._add_hash_data(self.path, hash_data)

    @staticmethod
    def _add_hash_data(hash_dict: dict, hash_data: NavGetCommDataAck) -> bool:
        if hash_dict.get(hash_data.hash) is None:
            hash_dict[hash_data.hash] = FrameList(total_frame=hash_data.total_frame, data=[hash_data])
            return True

        if hash_data not in hash_dict[hash_data.hash].data:
            hash_dict[hash_data.hash].data.append(hash_data)
            return True
        return False
