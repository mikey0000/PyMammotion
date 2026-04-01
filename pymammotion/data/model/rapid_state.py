from dataclasses import dataclass
from enum import Enum

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.data.model.enums import FuseLocalizationStatus
from pymammotion.utility.conversions import parse_double


class RTKStatus(Enum):
    NONE = 0
    BAD = 1
    FINE = 4


@dataclass
class RapidState(DataClassORJSONMixin):
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
    # Visible satellite counts from tard_state_data[15]
    view_l1: int = 0  # visible L1-band satellite count
    view_l2: int = 0  # visible L2-band satellite count
    # IMU/vision fusion state from tard_state_data[16]
    fuse_status: int = 0  # FuseLocalizationStatus value
    vision_state_raw: int = 0  # raw vision system state
    # Mow path progress from tard_state_data[14]
    now_index: int = 0  # current position index into the planned mow path point array
    start_index: int = 0  # start index of the current mow segment

    @property
    def fuse_localization_status(self) -> FuseLocalizationStatus:
        """Return the IMU/vision fusion localisation state as a typed enum."""
        try:
            return FuseLocalizationStatus(self.fuse_status)
        except ValueError:
            return FuseLocalizationStatus.NO_POSE

    @classmethod
    def from_raw(cls, raw: list[int]) -> "RapidState":
        """Construct a RapidState from the raw integer list received in a rapid-state device message."""
        state = RapidState(
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
        if len(raw) > 14:
            raw14 = int(raw[14])
            state.now_index = (raw14 & 0x00FFFF00) >> 8
            state.start_index = (raw14 & 0xFFFF000000) >> 24
        if len(raw) > 15:
            raw15 = int(raw[15])
            state.view_l1 = raw15 & 0xFF
            state.view_l2 = (raw15 >> 8) & 0xFF
        if len(raw) > 16:
            raw16 = int(raw[16])
            state.fuse_status = (raw16 & 0xFF00) >> 8
            state.vision_state_raw = (raw16 & 0xFF000000) >> 24
        return state
