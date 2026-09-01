"""Display-string helpers for reported device values.

These derive human-readable strings from wire values; nothing in ``pymammotion``
calls them, but the Home Assistant integration does (its sensor layer).  They are
grouped here so there is one place to look for "how do I render this field".

``device_connection`` takes a structural :class:`ConnectionInfo` rather than
importing ``data.model.report_info.ConnectData``: the concrete dataclass satisfies
it, and typing it structurally keeps ``utility/`` free of an upward import into
``data/model/`` — the previous type-only import was the sole reason this package
depended on the layer above it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pymammotion.utility.constant.device_enums import WorkMode


@runtime_checkable
class ConnectionInfo(Protocol):
    """The connectivity fields ``device_connection`` reads off a report."""

    wifi_rssi: int
    ble_rssi: int
    connect_type: int
    used_net: str


def device_connection(connect: ConnectionInfo) -> str:
    """Return string representation of device connection."""

    if connect.wifi_rssi != 0 and connect.ble_rssi != 0:
        return "WIFI/BLE"

    if connect.connect_type == 2 or connect.used_net == "NET_USED_TYPE_WIFI" or connect.wifi_rssi != 0:
        return "WIFI"

    if connect.connect_type == 1 or connect.used_net == "NET_USED_TYPE_MNET":
        return "3G/4G"

    if connect.ble_rssi != 0:
        return "BLE"

    return "None"


#: sys_status value -> ``WorkMode`` member name.  Built from the enum so a new mode
#: is added in one place, and used instead of ``WorkMode(value).name`` so an
#: unmodelled value doesn't trip the enum's unknown-value log.  ``UNKNOWN`` is our
#: own sentinel and never arrives on the wire.
_WORK_MODE_NAMES: dict[int, str] = {mode.value: mode.name for mode in WorkMode if mode is not WorkMode.UNKNOWN}


def device_mode(value: int) -> str:
    """Return the ``WorkMode`` name for *value*, or ``"Invalid mode"`` if unmodelled."""
    return _WORK_MODE_NAMES.get(value, "Invalid mode")


def camera_brightness(value: int) -> str:
    """Return the brightness corresponding to the given value."""

    if value not in (0, 1):
        if value > 45:
            return "Light"
        return "Dark"

    modes = {
        0: "Dark",
        1: "Light",
    }
    return modes.get(value, "Invalid mode")
