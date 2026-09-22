"""Backwards-compatible re-exports for the former single ``device_constant`` module.

This module used to hold five unrelated concerns in one file: BLE opcodes,
byte-buffer index constants, the wire-value enum vocabulary, poll policy, and
display-string helpers.  They now live in siblings — ``ble_order``,
``buffer_index``, ``device_enums``, ``poll_policy`` and ``display``.

It survives as an import surface because the Home Assistant integration imports
several of these names from this exact path.  New code inside ``pymammotion``
should import from the sibling that owns the name.
"""

from __future__ import annotations

from pymammotion.utility.constant.ble_order import BleOrderCmd
from pymammotion.utility.constant.buffer_index import (
    SystemRapidStateTunnelIndex,
    SystemTardStateTunnel,
    SystemUpdateBuf,
)
from pymammotion.utility.constant.device_enums import (
    AppConnectType,
    BreakPointReason,
    PosType,
    RTKPositionMode,
    VioState,
    WorkMode,
)
from pymammotion.utility.constant.display import camera_brightness, device_connection, device_mode
from pymammotion.utility.constant.poll_policy import MOWING_ACTIVE_MODES, NO_REQUEST_MODES

__all__ = [
    "MOWING_ACTIVE_MODES",
    "NO_REQUEST_MODES",
    "AppConnectType",
    "BleOrderCmd",
    "BreakPointReason",
    "PosType",
    "RTKPositionMode",
    "SystemRapidStateTunnelIndex",
    "SystemTardStateTunnel",
    "SystemUpdateBuf",
    "VioState",
    "WorkMode",
    "camera_brightness",
    "device_connection",
    "device_mode",
]
