"""IntEnum definitions for mowing modes and cutting options (cutting mode, speed, border patrol, obstacle laps, mow order, detection strategy, etc.)."""

from __future__ import annotations

from enum import IntEnum

from pymammotion.utility.device_type import DeviceType


class CuttingMode(IntEnum):
    """Cutting/job mode (protobuf job_mode field)."""

    single_grid = 0
    double_grid = 1
    segment_grid = 2
    no_grid = 3


class CuttingSpeedMode(IntEnum):
    """Cutting speed mode (protobuf speed field)."""

    normal = 0
    slow = 1
    fast = 2


class BorderPatrolMode(IntEnum):
    """Number of border/perimeter patrol laps to ride before starting the mowing grid (none through four)."""

    none = 0
    one = 1
    two = 2
    three = 3
    four = 4


class ObstacleLapsMode(IntEnum):
    """Number of obstacle-avoidance mowing laps (protobuf mowingLaps field)."""

    none = 0
    one = 1
    two = 2
    three = 3
    four = 4


class MowOrder(IntEnum):
    """Mowing path order: whether to mow the border or grid first (protobuf path_order field)."""

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


class BoundaryRideDistance(IntEnum):
    """Percentage of the lawn perimeter the mower rides before starting to mow.

    Luba Pro / X3 only — sent via nav_sys_param_cmd ID 10.
    A boundary-preview pass helps verify the map before committing to a full mow.
    """

    none = 0  # no boundary ride
    quarter = 25  # ride 25 % of perimeter
    half = 50  # ride 50 % of perimeter


class DetectionStrategy(IntEnum):
    """Obstacle detection mode (ultra_wave / detect_mode protocol field).

    Luba 1 uses an old-style UI with three options:
      0  direct_touch  "Direct touch"
      1  slow_touch    "Slow touch"
      2  less_touch    "Less touch"

    Luba 2 and the original Yuka (LUBA_YUKA) below firmware 1.12.0 use the
    old-style UI with four options:
      0  direct_touch  "Direct touch"
      1  slow_touch    "Slow touch"
      2  less_touch    "Less touch"
      10 no_touch      "No touch"

    Luba 2 / Yuka at firmware 1.12.0+ and all other devices (Yuka mini/pro/MV
    variants) use a new-style UI:
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
    def for_device(cls, device_name: str, firmware_version: str = "") -> list[DetectionStrategy]:
        """Return the detection strategies supported by the given device.

        Luba 2 and the original Yuka expose the old four-option touch UI below
        firmware 1.12.0 and the new Off/Standard/Sensitive options at/above it
        (see ``DeviceType.uses_new_obstacle_detection``). Pass the device's
        firmware version so older units get the right options; when omitted the
        new options are assumed.
        """
        dt = DeviceType.value_of_str(device_name)
        if dt == DeviceType.LUBA:
            return [cls.direct_touch, cls.slow_touch, cls.less_touch]
        if dt in (DeviceType.LUBA_2, DeviceType.LUBA_YUKA) and not DeviceType.uses_new_obstacle_detection(
            device_name, firmware_version
        ):
            return [cls.direct_touch, cls.slow_touch, cls.less_touch, cls.no_touch]
        return [cls.direct_touch, cls.no_touch, cls.sensitive]


class WildlifeSafety(IntEnum):
    """Wildlife / animal protection behaviour when an animal is detected.

    Combines rw_id=13 (status: 0=off, 1=on) and rw_id=12 (mode):
      0  off             — animal protection disabled (status=0)
      1  stop_mowing     — stop the current task (title_wildguard_no_task)
      2  low_speed_mowing — reduce speed (title_wildguard_safety_speed)
    """

    off = 0
    stop_mowing = 1
    low_speed_mowing = 2


class PathAngleSetting(IntEnum):
    """Path Angle type."""

    relative_angle = 0
    absolute_angle = 1
    random_angle = 2  # Luba Pro / Luba 2 Yuka only
