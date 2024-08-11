from dataclasses import dataclass


@dataclass
class DeviceLimits:
    cutter_height_min: int
    cutter_height_max: int
    working_speed_min: float
    working_speed_max: float
