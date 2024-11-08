from enum import IntEnum


class CuttingMode(IntEnum):
    """job_mode"""

    single_grid = 0
    double_grid = 1
    segment_grid = 2
    no_grid = 3


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


class BypassStrategy(IntEnum):
    """Matches up with ultra_wave."""

    direct_touch = 0
    slow_touch = 1
    less_touch = 2
    no_touch = 10  # luba 2 yuka only or possibly value of 10


class PathAngleSetting(IntEnum):
    """Path Angle type."""

    relative_angle = 0
    absolute_angle = 1
    random_angle = 2  # Luba Pro / Luba 2 Yuka only
