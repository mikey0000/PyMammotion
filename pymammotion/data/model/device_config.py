from dataclasses import dataclass


@dataclass
class DeviceLimits:
    blade_height_min: int
    blade_height_max: int
    working_speed_min: float
    working_speed_max: float
