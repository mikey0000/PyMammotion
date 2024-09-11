from enum import Enum


class PositionMode(Enum):
    FIX = 0
    SINGLE = 1
    FLOAT = 2
    NONE = 3
    UNKNOWN = 4

    @staticmethod
    def from_value(value: int):
        if value == 0:
            return PositionMode.FIX
        elif value == 1:
            return PositionMode.SINGLE
        elif value == 2:
            return PositionMode.FLOAT
        elif value == 3:
            return PositionMode.NONE
        else:
            return PositionMode.UNKNOWN

    def __str__(self) -> str:
        if self == PositionMode.FIX:
            return "Fix"
        elif self == PositionMode.SINGLE:
            return "Single"
        elif self == PositionMode.FLOAT:
            return "Float"
        elif self == PositionMode.NONE:
            return "None"
        else:
            return "-"


class RTKStatus(Enum):
    NONE = 0
    SINGLE = 1
    FIX = 4
    FLOAT = 5
    UNKNOWN = 6

    @staticmethod
    def from_value(value: int):
        if value == 0:
            return RTKStatus.NONE
        elif value == 1 or value == 2:
            return RTKStatus.SINGLE
        elif value == 4:
            return RTKStatus.FIX
        elif value == 5:
            return RTKStatus.FLOAT
        else:
            return RTKStatus.UNKNOWN

    def __str__(self) -> str:
        if self == RTKStatus.NONE:
            return "None"
        elif self == RTKStatus.SINGLE:
            return "Single"
        elif self == RTKStatus.FIX:
            return "Fix"
        elif self == RTKStatus.FLOAT:
            return "Float"
        else:
            return "Unknown"
