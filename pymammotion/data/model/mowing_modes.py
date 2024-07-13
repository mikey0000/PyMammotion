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
