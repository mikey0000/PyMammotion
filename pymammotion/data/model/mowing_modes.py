from __future__ import annotations

from enum import IntEnum

from pymammotion.utility.device_type import DeviceType


class CuttingMode(IntEnum):
    """job_mode"""

    single_grid = 0
    double_grid = 1
    segment_grid = 2
    no_grid = 3


class CuttingSpeedMode(IntEnum):
    """speed"""

    normal = 0
    slow = 1
    fast = 2


class BorderPatrolMode(IntEnum):
    """"""

    none = 0
    one = 1
    two = 2
    three = 3
    four = 4


class ObstacleLapsMode(IntEnum):
    """mowingLaps"""

    none = 0
    one = 1
    two = 2
    three = 3
    four = 4


class MowOrder(IntEnum):
    """path_order"""

    border_first = 0
    grid_first = 1


class TraversalMode(IntEnum):
    """Traversal mode when returning."""

    direct = 0
    follow_perimeter = 1


class TurningMode(IntEnum):
    """Turning mode on corners."""

    zero_turn = 0
    multipoint = 1


class DetectionStrategy(IntEnum):
    """Obstacle detection mode (ultra_wave / detect_mode protocol field).

    Luba 1 uses an old-style UI with three options:
      0  direct_touch  "Direct touch"
      1  slow_touch    "Slow touch"
      2  less_touch    "Less touch"

    Original Yuka (LUBA_YUKA) uses the old-style UI with four options:
      0  direct_touch  "Direct touch"
      1  slow_touch    "Slow touch"
      2  less_touch    "Less touch"
      10 no_touch      "No touch"

    All other devices (Luba 2+, all Yuka mini/pro/MV variants) use a new-style UI:
      0   direct_touch  "Off"       — firmware also accepts 1; APK sends 1 but device treats both identically
      10  no_touch      "Standard"  — proactive obstacle avoidance
      11  sensitive     "Sensitive" — avoids obstacles and non-grassy areas
    """

    direct_touch = 0
    slow_touch = 1
    less_touch = 2
    no_touch = 10
    sensitive = 11

    @classmethod
    def for_device(cls, device_name: str) -> list[DetectionStrategy]:
        """Return the detection strategies supported by the given device."""
        dt = DeviceType.value_of_str(device_name)
        if dt == DeviceType.LUBA:
            return [cls.direct_touch, cls.slow_touch, cls.less_touch]
        if dt == DeviceType.LUBA_YUKA:
            return [cls.direct_touch, cls.slow_touch, cls.less_touch, cls.no_touch]
        return [cls.direct_touch, cls.no_touch, cls.sensitive]


class PathAngleSetting(IntEnum):
    """Path Angle type."""

    relative_angle = 0
    absolute_angle = 1
    random_angle = 2  # Luba Pro / Luba 2 Yuka only
