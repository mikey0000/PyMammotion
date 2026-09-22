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
    variants) use a new-style UI whose off position is value **1**, not 0
    (``WorkingSettingManage.aytomatiTypecRange = {"1", "10", "11"}``):
      1   slow_touch    "Basic"       — labelled ``state_close``; the firmware accepts 0 here too
      10  no_touch      "Standard"  — proactive obstacle avoidance
      11  sensitive     "Sensitive" — avoids obstacles and non-grassy areas

    Labels are a function of the value *and* of which list the device has, so
    use :meth:`option_key` rather than the member name to present a strategy.
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
        return [cls.slow_touch, cls.no_touch, cls.sensitive]

    def option_key(self, options: list[DetectionStrategy]) -> str:
        """Return the app's label key for this strategy within *options*.

        ``SettingOptionsView.initBypassingStrategy`` labels by value *and* by
        which list the device has: 0 is always the off position, and 1 is
        "Slow touch" only on the older lists that also carry 0 — on the new
        Off/Standard/Sensitive list, 1 *is* the off position.

        (The app additionally falls back to "Off" for 1 on any list shorter
        than four, which would label two of Luba 1's three tabs identically;
        keying off the presence of 0 keeps every option distinct.)
        """
        if self is DetectionStrategy.slow_touch and DetectionStrategy.direct_touch not in options:
            return "off"
        return _OPTION_KEYS[self]

    @classmethod
    def from_option_key(cls, key: str, options: list[DetectionStrategy]) -> DetectionStrategy:
        """Resolve a label key back to the strategy *options* uses for it.

        Raises:
            ValueError: if *key* is not one of the keys *options* presents.

        """
        for strategy in options:
            if strategy.option_key(options) == key:
                return strategy
        msg = f"{key!r} is not an obstacle-detection option of {[s.name for s in options]}"
        raise ValueError(msg)


#: Label key per strategy, named after the APK string each tab renders
#: (``state_close`` / ``title_slow_touch`` / ``title_less_touch`` /
#: ``title_standard`` / ``title_proguard``).  ``slow_touch`` is the one that
#: depends on the device's list — see :meth:`DetectionStrategy.option_key`.
_OPTION_KEYS: dict[DetectionStrategy, str] = {
    DetectionStrategy.direct_touch: "off",
    DetectionStrategy.slow_touch: "slow_touch",
    DetectionStrategy.less_touch: "less_touch",
    DetectionStrategy.no_touch: "standard",
    DetectionStrategy.sensitive: "sensitive",
}


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


class RainProtectionMode(IntEnum):
    """Rain-protection strategy, new in app 2.3.18 ("Rain Protection" screen).

    Replaces the plain on/off rain switch on capable devices — see
    ``DeviceType.supports_rain_protection_modes``, whose firmware gate is still
    unconfirmed.  Values are read verbatim from the app's RN bundle
    (``RainProtectionMode`` in ``assets/index.android.bundle``, APK 2.3.18.21):

      0  off    — mows in rain anyway
      1  smart  — rain sensor plus OpenWeather data, computes its own resume time;
                  falls back to sensor behaviour with no internet
      2  sensor — rain sensor only, resumes after ``delay_duration`` hours

    The app defaults to ``sensor``.  The wire encoding is not modelled here: the
    setter is a native module (``RainProtectionModule.setRainProtectionMode``) in
    the packed part of the APK, so writing one would be guesswork.
    """

    off = 0
    smart = 1
    sensor = 2


#: Resume delays (hours) the app offers for ``RainProtectionMode.sensor``; it
#: forces 0 for every other mode.  Verbatim from the same RN bundle.
RAIN_PROTECTION_DELAY_HOURS: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 24, 48)

#: Delay the app pre-selects when a device reports a value outside the list above.
RAIN_PROTECTION_DEFAULT_DELAY_HOURS = 24


class PathAngleSetting(IntEnum):
    """Path Angle type."""

    relative_angle = 0
    absolute_angle = 1
    random_angle = 2  # Luba Pro / Luba 2 Yuka only
