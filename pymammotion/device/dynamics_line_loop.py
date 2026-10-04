"""Dynamics-line poll loop — the APK ``HashDataManager`` 100003 timer.

The APK polls ``NavGetCommData(action=8, type=18)`` every 10 s for the whole job on
devices where ``DeviceType.isSupportDynamicsLine()`` holds (the lidar models).  Over
BLE, which has no send quota, so does this loop: it starts on BLE connect and is
cancelled on disconnect.  Over the cloud a fetch costs a request plus one ack per
frame from the 600-send quota, so it polls only inside the viewing window that
``DeviceHandle.watch_dynamics_line`` opens each time the map asks for mow progress.

Per-tick gates: a job is running, the model supports the line (LUBA_VA is firmware
gated, so re-checked each tick), no saga is running, a transport is usable, and over
the cloud ``mow_path_fetch_enabled`` is on.  The state reducer stores what arrives.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import PathType
from pymammotion.device.modes import _DeviceMode
from pymammotion.messaging.common_data_saga import CommonDataSaga
from pymammotion.transport.base import TransportType
from pymammotion.utility.device_type import DeviceType

if TYPE_CHECKING:
    from pymammotion.device.loop_host import LoopHost

_logger = logging.getLogger(__name__)

#: How long one map poll keeps the dynamics line polled.
DYNAMICS_LINE_WATCH_SECONDS: float = 300.0

#: Poll cadence while watched.  BLE matches the APK's 10 s timer
#: (``HashDataManager.java:133, :873``); the cloud is slower to spare the send quota.
_BLE_POLL_INTERVAL: float = 10.0
_CLOUD_POLL_INTERVAL: float = 60.0


async def dynamics_line_loop(handle: LoopHost) -> None:
    """Poll while BLE is connected or a viewing window is open, fetching once on entry."""
    device_type = DeviceType.value_of_str(handle.device_name)
    while not handle.is_stopping and (_ble_connected(handle) or handle.dynamics_line_watched):
        ble_connected = _ble_connected(handle)
        if _should_poll(handle, device_type, ble_connected=ble_connected):
            await _enqueue_dynamics_line_saga(handle)
        # Plain sleep, not sleep_or_rearm: on_saga_end sets the shared rearm event after
        # this loop's own saga, which would collapse the interval into back-to-back polls.
        await asyncio.sleep(_BLE_POLL_INTERVAL if ble_connected else _CLOUD_POLL_INTERVAL)


def _ble_connected(handle: LoopHost) -> bool:
    ble = handle.get_transport(TransportType.BLE)
    return ble is not None and ble.is_connected


def _should_poll(handle: LoopHost, device_type: DeviceType, *, ble_connected: bool) -> bool:
    if handle.cadence_mode() != _DeviceMode.ACTIVE or handle.queue.is_saga_active:
        return False
    if not handle.has_usable_transport or not (ble_connected or handle.mow_path_fetch_enabled):
        return False
    return device_type.is_support_dynamics_line(_device_version(handle))


def _device_version(handle: LoopHost) -> str | None:
    """Return the device's firmware version, or None if unknown.

    ``DeviceVersionUtils.isLessThanInputVersion`` in the APK compares the stored
    ``device_current_version_<name>`` — the whole-device version from the base
    info, the version screen and the cloud check — not a module's version, so
    this is ``device_firmwares.device_version`` rather than ``main_controller``.
    """
    raw = handle.snapshot.raw
    if not isinstance(raw, MowerDevice):
        return None
    return raw.device_firmwares.device_version or None


async def _enqueue_dynamics_line_saga(handle: LoopHost) -> None:
    """Enqueue a ``CommonDataSaga`` for the dynamics line; the state reducer stores what it receives."""
    saga = CommonDataSaga(
        command_builder=handle.commands,
        send_command=handle.send_raw,
        action=8,
        type=PathType.DYNAMICS_LINE,
    )
    try:
        await handle.enqueue_saga(saga)
    except Exception:
        _logger.debug("dynamics_line_loop [%s]: enqueue failed", handle.device_name, exc_info=True)
