"""Shared device-mode enum used by ``DeviceHandle`` and the per-transport loops.

Lives in its own module so ``handle.py``, ``ble_loop.py``, and ``mqtt_loop.py``
can all import it without creating a circular dependency through ``handle.py``.
"""

from __future__ import annotations

from enum import Enum


class _DeviceMode(Enum):
    """Coarse device-state classification used to pick poll cadence per transport."""

    ACTIVE = "active"  # sys_status in MOWING_ACTIVE_MODES (mowing/returning)
    DOCKED_CHARGING = "docked_charging"  # charging on dock, battery < 100
    DOCKED_FULL = "docked_full"  # docked at 100%
    IDLE = "idle"  # paused, locked, or any non-active non-docked state
    SLEEPING = "sleeping"  # sys_status == MODE_SLEEPING (low-power sleep)
