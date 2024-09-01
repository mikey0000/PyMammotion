from dataclasses import dataclass
from enum import Enum

from pymammotion.utility.conversions import parse_double


class RTKStatus(Enum):
    NONE = 0
    BAD = 1
    FINE = 4


@dataclass
class RapidState:
    pos_x: float = 0
    pos_y: float = 0
    rtk_status: RTKStatus = RTKStatus.NONE
    toward: float = 0
    satellites_total: int = 0
    satellites_l2: int = 0
    rtk_age: float = 0
    lat_std: float = 0
    lon_std: float = 0
    pos_type: int = 0
    zone_hash: int = 0
    pos_level: int = 0

    @classmethod
    def from_raw(cls, raw: list[int]) -> "RapidState":
        return RapidState(
            rtk_status=RTKStatus.FINE if raw[0] == 4 else RTKStatus.BAD if raw[0] in (1, 5) else RTKStatus.NONE,
            pos_level=raw[1],
            satellites_total=raw[2],
            rtk_age=parse_double(raw[3], 4.0),
            lat_std=parse_double(raw[4], 4.0),
            lon_std=parse_double(raw[5], 4.0),
            satellites_l2=raw[6],
            pos_x=parse_double(raw[7], 4.0),
            pos_y=parse_double(raw[8], 4.0),
            toward=parse_double(raw[9], 4.0),
            pos_type=raw[10],
            zone_hash=raw[11],
        )
