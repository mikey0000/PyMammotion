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


class SpinoSysStatus(IntEnum):
    """Top-level system state shown on the Spino home screen.

    Mirrors the ``SpinoSysStatus`` proto enum and the four UI labels
    surfaced by ``DeviceStateSwimmingPoolSPFragment.tvDeviceStatus``:
    STANDBY, WORKING, RETURNING, and the SP-only CHARGEBACKING.
    """

    READY = 0           # UI label: "STANDBY"
    WORKING = 1         # UI label: "WORKING"
    WORKBACKING = 2     # UI label: "RETURNING"
    CHARGEBACKING = 3   # UI label: SP-only "RETURNING TO CHARGE"


class SpinoWorkMode(IntEnum):
    """Cleaning mode picker on the Spino home screen.

    Mirrors the ``SwimmingWorkModule`` Java enum used by the Mammotion app's
    mode buttons. The numeric values match ``dev_statue_t.work_mode``.
    """

    RECHARGE = 0  # SP-only "RECHARGE" button
    AUTO = 1      # "ALL"
    FLOOR = 2     # "FLOOR"
    WALL = 3      # "WALL"
    ECO = 4       # "ECO"
    LINE = 5      # "LINE"


class WallMaterial(IntEnum):
    """Pool wall material — user-selectable in the calibration screen.

    Mirrors the ``WallMaterialE`` proto enum.
    """

    GLASS = 0
    CERAMICS = 1
    SAND_STONE = 2


class PoolBottomType(IntEnum):
    """Pool bottom shape — user-selectable in the calibration screen.

    Mirrors the ``PoolBottomTypeE`` proto enum.
    """

    RIGHT_ANGLE_SIMPLE = 0
    RIGHT_ANGLE_COMPLEX = 1
    CURVE_SIMPLE = 2
    CURVE_COMPLEX = 3


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
    sys_status: SpinoSysStatus = SpinoSysStatus.READY
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
