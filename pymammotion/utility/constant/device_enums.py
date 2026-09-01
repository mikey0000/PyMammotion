"""Enums for values reported verbatim by the device.

Each member value is a wire value, so these subclass ``UnknownTolerantIntEnum``:
a frame carrying a value newer firmware invented must degrade, not crash the
message pipeline.
"""

from __future__ import annotations

from pymammotion.utility.enum_base import UnknownTolerantIntEnum


class VioState(UnknownTolerantIntEnum):
    """Visual-inertial odometry signal quality.

    Surfaces on ``vio_to_app_info_msg.vio_state``.  Sourced from the APK's
    ``SignalHelper.VioSignalType`` interface
    (``newui/mvp/view/activity/status/newstatus/SignalHelper.java:265``).

    The APK only recognises values 0-3; anything outside that range
    (e.g. ``172`` observed when the camera pipeline is initialising) is
    treated as unknown in both the app UI and this enum.  ``VioState(x)``
    for any unrecognised ``x`` returns :data:`SIGNAL_UNKNOWN` instead of
    raising :exc:`ValueError` (via ``UnknownTolerantIntEnum._missing_``).
    """

    SIGNAL_UNKNOWN = -1
    UNKNOWN = -1  # alias of SIGNAL_UNKNOWN (canonical) so the base _missing_ can return it
    SIGNAL_NONE = 0
    SIGNAL_INIT = 1
    SIGNAL_GOOD = 2
    SIGNAL_BAD = 3


class RTKPositionMode(UnknownTolerantIntEnum):
    """Positioning / RTK source mode reported on ``rpt_basestation_info.rtk_status``.

    Labelled "Positioning status" in the app UI.  Sourced from the APK's
    ``SignalHelper.RTKPositionModeType`` interface
    (``newui/mvp/view/activity/status/newstatus/SignalHelper.java:217``).
    """

    UNKNOWN = -1
    #: Antenna Over DataLink — RTK corrections via the LoRa pairing to a base station.
    RTK_OVER_DATALINK = 0
    #: RTK Over Internet — network-RTK via the device's 4G/Wi-Fi uplink.
    RTK_OVER_INTERNET = 1
    #: iNavi network RTK (cloud-sourced).
    INAVI_NET_RTK = 2
    #: iNavi RTK Box (dedicated external box).
    INAVI_RTK_BOX = 3


class AppConnectType(UnknownTolerantIntEnum):
    """How the app/client is linked to the device, reported on the RTK base station and mowers.

    Older mowers do not support connect_type 3.

    Surfaces on ``rpt_basestation_info.app_connect_type`` and on
    ``rpt_connect_status.connect_type`` in mower report frames.  Sourced from
    the APK's ``MACarDataManager.java``:

    - ``currentConn 1=ble`` debug string (``:5689, :9444, :9739, :10172``)
    - ``if (appConnectType != 2 && wifiRssi == 0)`` gate at ``:7774`` —
      establishes that ``2`` implies Wi-Fi

    ``3`` is inferred from observed traces: the value matches a bitmask of ``CON_BLE | CON_WIFI`` — both
    transports engaged simultaneously.
    ``0`` is treated as the unset/unknown sentinel.
    """

    UNKNOWN = 0
    CON_BLE = 1
    CON_WIFI = 2
    CON_BLE_WIFI = 3


class WorkMode(UnknownTolerantIntEnum):
    """Numeric work-mode identifiers reported by the device status field.

    Mirrors the APK's ``DeviceWorkState`` enum
    (``device/source/device/enums/DeviceWorkState.java:5-38``, 2.3.8.201).
    ``MODE_EDIT_BOUNDARY`` is that enum's ``MODE_SECOND_EDIT``; ``MODE_POWER_OFF``
    has no counterpart there but is still reported by older firmware.

    Wire-coerced, so unmodelled values resolve to ``UNKNOWN`` rather than raising
    (see :class:`~pymammotion.utility.enum_base.UnknownTolerantIntEnum`).
    """

    UNKNOWN = -1
    MODE_NOT_ACTIVE = 0
    MODE_ONLINE = 1
    MODE_OFFLINE = 2
    MODE_POWER_OFF = 3
    MODE_DISABLE = 8
    MODE_INITIALIZATION = 10
    MODE_READY = 11
    MODE_UNCONNECTED = 12
    MODE_WORKING = 13
    MODE_RETURNING = 14
    MODE_CHARGING = 15
    MODE_UPDATING = 16
    MODE_LOCK = 17
    MODE_SYSTEM_ERROR = 18
    MODE_PAUSE = 19
    MODE_MANUAL_MOWING = 20
    MODE_UPDATE_SUCCESS = 22
    MODE_OTA_UPGRADE_FAIL = 23
    MODE_JOB_DRAW = 31
    MODE_OBSTACLE_DRAW = 32
    MODE_CHANNEL_DRAW = 34
    MODE_ERASER_DRAW = 35
    MODE_EDIT_BOUNDARY = 36
    MODE_LOCATION_ERROR = 37
    MODE_BOUNDARY_JUMP = 38
    MODE_CHARGING_PAUSE = 39
    MODE_AUTO_ERASER_DRAW = 43
    MODE_CORRIDOR_DRAW = 44
    #: Automatic exploration mapping (MN231 "auto mapping"), not a mow job.
    MODE_CORRIDOR_WORKING = 45
    MODE_CORRIDOR_PAUSE = 46
    MODE_CORRIDOR_RETURNING = 47
    #: Low-power sleep.  The device answers neither MQTT nor BLE until it is woken
    #: (the app wakes it with ``POST /device-server/v1/device/wakeup``).
    MODE_SLEEPING = 48
    MODE_RESET_CHARGE = 50
    MODE_BACKING_UP = 51
    MODE_RECOVERY = 52


class BreakPointReason(UnknownTolerantIntEnum):
    """Why the device recorded a mow breakpoint, reported on ``WorkData.bp_info``.

    Decoded from the APK's breakpoint-flag switch
    (``map/fragment/BaseMapFragment.java:2400-2558``, 2.3.8.201), which maps the
    flag to the "why did mowing stop" banner shown over the map.  Several wire
    codes share a meaning — the member value is the lowest such code and
    :data:`_BREAK_POINT_SECONDARY_CODES` carries the rest, so
    ``BreakPointReason(15)`` resolves to :data:`PAUSED_MANUALLY` just like
    ``BreakPointReason(1)`` does.

    ``NONE`` means no breakpoint is outstanding; the app clears the banner and
    discards the stored breakpoint position on flag ``0``.
    """

    #: Sentinel for an unmodelled code.  Deliberately not ``-1``: the device does
    #: send ``-1``, and the app treats it as "no breakpoint" (see ``NONE``).
    UNKNOWN = -2
    #: No breakpoint outstanding.
    NONE = 0
    PAUSED_MANUALLY = 1
    BLADE_FAULT = 3
    #: Wheels stuck or lifted.
    STUCK = 4
    OUTSIDE_BOUNDARY = 5
    #: Waiting to regain RTK fix before resuming.
    NEEDS_POSITIONING = 7
    #: Waiting on the dock for enough charge to resume.
    NEEDS_CHARGE = 8
    BUMPER_DISCONNECTED = 9
    LOW_BATTERY = 10
    #: Rain detected — paused by the rain-protection setting.
    RAIN = 11
    POWERED_OFF = 12
    #: Repositioning itself automatically before resuming.
    AUTO_POSITIONING = 13
    #: The scheduled working window ended mid-job.
    SCHEDULE_WINDOW_ENDED = 18
    #: Resume was requested but the job is still paused.
    RESUME_PAUSED = 19

    @classmethod
    def _missing_(cls, value: object) -> BreakPointReason:
        """Resolve a secondary wire code to its shared reason before falling back."""
        if isinstance(value, int) and (reason := _BREAK_POINT_SECONDARY_CODES.get(value)) is not None:
            return reason
        return super()._missing_(value)


#: Extra wire codes that mean the same thing as an existing member.  ``-1`` is
#: reported by the device when it has never had a breakpoint.
_BREAK_POINT_SECONDARY_CODES: dict[int, BreakPointReason] = {
    -1: BreakPointReason.NONE,
    2: BreakPointReason.NONE,
    6: BreakPointReason.NONE,
    14: BreakPointReason.LOW_BATTERY,
    15: BreakPointReason.PAUSED_MANUALLY,
    16: BreakPointReason.AUTO_POSITIONING,
    20: BreakPointReason.BLADE_FAULT,
    21: BreakPointReason.STUCK,
}


class PosType(UnknownTolerantIntEnum):
    """Position of the robot."""

    UNKNOWN = -1
    AREA_BORDER_ON = 7
    AREA_INSIDE = 1
    AREA_OUT = 0
    CHANNEL_AREA_OVERLAP = 9
    CHANNEL_ON = 3
    CHARGE_ON = 5
    DUMPING_AREA_INSIDE = 8
    DUMPING_OUTSIDE = 10
    ABNORMAL_POSITIONING = 11
    NO_AREAS = 100
    OBS_ON = 2
    TURN_AREA_INSIDE = 4
    VIRTUAL_INSIDE = 6
