from enum import Enum


class CuttingMode(Enum):
    """job_mode"""

    single_grid = 0
    double_grid = 1
    segment_grid = 2
    no_grid = 3


class BorderPatrolMode(Enum):
    """"""
    none = 0
    one = 1
    two = 2
    three = 3
    four = 4


class ObstacleLapsMode(Enum):
    """mowingLaps"""

    none = 0
    one = 1
    two = 2
    three = 3
    four = 4


class MowOrder(Enum):
    """path_order"""

    border_first = 0
    grid_first = 1
