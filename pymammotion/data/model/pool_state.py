"""Spino swimming-pool cleaner state model.

Contains only fields that are confirmed to either:
  (a) be displayed somewhere in the Mammotion Android app's pool-cleaner
      UI (DeviceStateSwimmingPoolFragment / SP variant, settings screens,
      SwimmingMapActivity), or
  (b) be a user-configurable setting sent via ``app_downlink_cmd_t``.

Internal-only proto fields (e.g. ``wheel_status``, ``pump_status``, the
RSSI fields) are deliberately omitted until we see them surface in the UI
or have a clear use for them. They can always be added in a follow-up
once captured Spino traffic confirms what's actually populated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.utility.enum_base import UnknownTolerantIntEnum


class SpinoSysStatus(UnknownTolerantIntEnum):
    """Top-level system state reported in ``dev_statue_t.sys_status`` (int32).

    Values mirror the app-side ``SpinoSysStatus`` constants
    (``DeviceStateSwimmingPoolSPFragment.SpinoSysStatus``, 0-8). The Mammotion
    app collapses these nine states into three home-screen labels via
    ``updateDeviceState()``:

    * STANDBY  ← IDLE (0), PREPARE (1), CHARGING (6)
    * WORKING  ← WAIT_WATER (2), WORKING (3), LEAVE_DOCK (7)
    * RETURNING ← PAUSE_GO_CHARGE (4), END_GO_CHARGE (5), RECALLING (8)
    """

    UNKNOWN = -1
    IDLE = 0  # SYS_STA_IDLE → "STANDBY"
    PREPARE = 1  # SYS_STA_PREPARE → "STANDBY"
    WAIT_WATER = 2  # SYS_STA_WAIT_WATER → "WORKING"
    WORKING = 3  # SYS_STA_WORKING → "WORKING"
    PAUSE_GO_CHARGE = 4  # SYS_STA_PAUSE_GO_CHARGE → "RETURNING"
    END_GO_CHARGE = 5  # SYS_STA_END_GO_CHARGE → "RETURNING"
    CHARGING = 6  # SYS_STA_CHARGING → "STANDBY"
    LEAVE_DOCK = 7  # SYS_STA_LEVE_DOCK (app typo) → "WORKING"
    RECALLING = 8  # SYS_STA_RECALLING → "RETURNING"


class SpinoWorkMode(UnknownTolerantIntEnum):
    """Cleaning mode reported in ``dev_statue_t.work_mode`` and sent to start a job.

    Values mirror the ``SwimmingSPWorkModule`` / ``SwimmingWorkModule`` Java
    enums (1-6; -1 = unknown). ``RECHARGE`` (0) is the proto ``APP_WORK.IDLE``
    value: starting a job with module ``0`` (``startPC210SwimmingConmand(.., 0,
    ..)``) is how the app's RECHARGE button sends the cleaner back to charge.
    ``CUSTOM`` (6) is SP-variant only.
    """

    UNKNOWN = -1
    RECHARGE = 0  # APP_WORK.IDLE — start with module 0 triggers return-to-charge
    AUTO = 1  # "ALL"
    FLOOR = 2  # "FLOOR"
    WALL = 3  # "WALL"
    ECO = 4  # "ECO" (SP variant labels this "Water surface")
    LINE = 5  # "LINE" / waterline
    CUSTOM = 6  # SP-only "CUSTOM"


class WallMaterial(UnknownTolerantIntEnum):
    """Pool wall material — user-selectable in the calibration screen.

    Mirrors the ``WallMaterialE`` proto enum.
    """

    UNKNOWN = -1
    GLASS = 0
    CERAMICS = 1
    SAND_STONE = 2


class PoolBottomType(UnknownTolerantIntEnum):
    """Pool bottom shape — user-selectable in the calibration screen.

    Mirrors the ``PoolBottomTypeE`` proto enum.
    """

    UNKNOWN = -1
    RIGHT_ANGLE_SIMPLE = 0
    RIGHT_ANGLE_COMPLEX = 1
    CURVE_SIMPLE = 2
    CURVE_COMPLEX = 3


class SpinoToggle(IntEnum):
    """On/off toggles the Spino exposes via the generic ``SysCommCmd`` (``allpowerfullRW``).

    The value is the command ``id`` used in ``read_write_device(rw_id, context, rw)``:
    ``context`` carries 0/1, ``rw`` is 1 to write and 0 to read.  **Member names match
    the corresponding ``PoolState`` boolean field names** so the reducer can map an
    incoming ``SysCommCmd`` straight onto state via ``SpinoToggle(id).name``.

    ``buzzer`` is on the main pool-settings screen; the other three live in the app's
    "Beta Features" screen (``SwimmingPoolTestToolsActivity``).
    """

    buzzer = 20  # title_buzzer
    turbo_clean = 21  # title_power_clean (force module)
    platform_cleaning = 22  # title_step_clean (stairs module)
    waterline_parking = 23  # title_waterline_dock (waterline module)


@dataclass
class PoolPoint(DataClassORJSONMixin):
    """A single point in pool-local 2D coordinates.

    Pool coordinates are device-relative — there is no GNSS / RTK origin
    and no scale documented in the proto. They mirror ``MapPoints`` from
    ``mctrl_sys.proto`` (float x, float y) and are only used by the map
    view to render boundary outlines and cleaning paths.
    """

    x: float = 0.0
    y: float = 0.0


@dataclass
class PoolMap(DataClassORJSONMixin):
    """Pool geometry as drawn by ``SwimmingMapActivity``.

    Two independent point lists, both transmitted via the ``MapInfo``
    sub-message of ``AppDownlinkCmdT``:

    - ``boundary``: pool outline (``MapInfo`` with ``tag == 0``)
    - ``cleaning_path``: planned/actual cleaning route (``tag == 1``)

    The Android UI does not currently render the device's live position in
    the pool, nor a dock symbol, so neither is modelled here. Multi-packet
    transfers (``pack_index`` / ``pack_num``) are reassembled by the
    reducer before the points land on this dataclass.
    """

    boundary: list[PoolPoint] = field(default_factory=list)
    cleaning_path: list[PoolPoint] = field(default_factory=list)


@dataclass
class PoolState(DataClassORJSONMixin):
    """Runtime state surfaced by the Spino home screen + settings screens.

    All fields here correspond to something the user can see or change in
    the app. The Spino sends these via ``MctlSys.report_info`` (for the
    runtime fields) and ``MctlSys.app_downlink_cmd`` (for the configurable
    settings, both as commands from the app and as ack responses from the
    device).
    """

    # --- Runtime status (DevStatueT) ---------------------------------------
    sys_status: SpinoSysStatus = SpinoSysStatus.IDLE
    work_mode: SpinoWorkMode = SpinoWorkMode.AUTO
    battery: int = 0
    """Battery percentage (0-100). Mirrors ``dev_statue_t.bat_val``."""

    # --- Cleaning session timing -------------------------------------------
    # Used by the home-screen "work time" string. The app computes the
    # display string locally; we just retain the raw timestamps.
    start_work_time: int = 0
    end_work_time: int = 0

    # --- Configurable settings (AppDownlinkCmdT) ---------------------------
    wall_material: WallMaterial = WallMaterial.GLASS
    bottom_type: PoolBottomType = PoolBottomType.RIGHT_ANGLE_SIMPLE
    floor_speed: float = 0.0

    # --- Toggle settings (SysCommCmd / allpowerfullRW, see SpinoToggle) -----
    # Field names match SpinoToggle member names so the reducer can map by id.
    buzzer: bool = False
    turbo_clean: bool = False
    platform_cleaning: bool = False
    waterline_parking: bool = False
