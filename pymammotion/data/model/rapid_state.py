from dataclasses import dataclass
from enum import Enum


class RTKStatus(Enum):
    NONE = 0
    BAD = 1
    FINE = 4


@dataclass
class RapidState:
    pos_x: float
    pos_y: float
    rtk_status: RTKStatus
    toward: float
    satellites_total: int
    satellites_l2: int
    rtk_age: float
    lat_std: float
    lon_std: float
    pos_type: int
    zone_hash: int
    pos_level: int

    @classmethod
    def from_raw(cls, raw: list[int]) -> "RapidState":
        return RapidState(
            rtk_status=RTKStatus.FINE if raw[0] == 4 else RTKStatus.BAD if raw[0] in (1, 5) else RTKStatus.NONE,
            pos_level=raw[1],
            satellites_total=raw[2],
            rtk_age=raw[3] / 10000,
            lat_std=raw[4] / 10000,
            lon_std=raw[5] / 10000,
            satellites_l2=raw[6],
            pos_x=raw[7] / 10000,
            pos_y=raw[8] / 10000,
            toward=raw[9] / 10000,
            pos_type=raw[10],
            zone_hash=raw[11],
        )
