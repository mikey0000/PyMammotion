"""Dynamics-line poll loop — mirrors APK ``HashDataManager`` 100003 timer.

The APK polls ``NavGetCommData(action=8, type=18)`` every 10 s while the
device is mowing/returning, for devices where
``DeviceType.isSupportDynamicsLine()`` is true (LUBA_HM included).  The
response carries the live cut-path so far, which the UI overlays as the
mower's progress.

This loop replicates that behaviour for pymammotion.  **BLE-gated** — the
loop is started from ``DeviceHandle._on_ble_connected`` and cancelled when
BLE disconnects, mirroring the ``_ble_polling_task`` lifecycle.  The 10 s
cadence would be MQTT-quota-expensive, and BLE is where the responsiveness
matters anyway (HA users watching live mow progress are typically nearby).

Per-tick gates:

* device is in ACTIVE mode (``DeviceHandle.device_mode``)
* BLE transport is still connected
* device type supports dynamics line (re-checked because LUBA_VA is
  firmware-gated and firmware may not be known at loop-start)
* no other saga is currently running on the device queue

When all gates pass, a ``CommonDataSaga`` is enqueued; on completion the
assembled point list is stored on ``device.map.dynamics_line``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import PathType
from pymammotion.device.modes import _DeviceMode
from pymammotion.messaging.common_data_saga import CommonDataSaga
from pymammotion.transport.base import TransportType
from pymammotion.utility.device_type import DeviceType

if TYPE_CHECKING:
    from pymammotion.device.handle import DeviceHandle

_logger = logging.getLogger(__name__)

#: Poll cadence — matches APK ``HashDataManager.handlerType_getDynamicsLine``
#: (10 000 ms, see ``HashDataManager.java:133, :873``).
_DYNAMICS_LINE_POLL_INTERVAL: float = 10.0


async def dynamics_line_loop(handle: DeviceHandle) -> None:
    """Periodic dynamics-line poll loop — BLE-gated.

    Started from ``DeviceHandle._on_ble_connected``; cancelled from the BLE
    availability handler when state transitions to DISCONNECTED.  Self-exits
    if it observes BLE disconnected mid-tick (defensive against any path that
    drops BLE without going through the availability handler).

    LUBA_VA is firmware-gated (must be >= 1.15.3.4422 per APK
    ``DeviceType.isSupportDynamicsLine``).  Because the main-controller
    version isn't known until the first report arrives, the loop re-checks
    ``is_support_dynamics_line(fw)`` on every tick using the current
    ``device_firmwares.main_controller``.
    """
    device_type = DeviceType.value_of_str(handle.device_name)

    while not handle._stopping:  # noqa: SLF001
        if await handle.sleep_or_rearm(_DYNAMICS_LINE_POLL_INTERVAL):
            # rearmed by a user command — re-evaluate immediately
            pass

        if handle._stopping:  # noqa: SLF001
            return

        # BLE-only gate.  If BLE went away without the availability handler
        # cancelling us (shouldn't happen, but defensive), exit cleanly so
        # the next _on_ble_connected can start a fresh loop.
        ble = handle._transports.get(TransportType.BLE)  # noqa: SLF001
        if ble is None or not ble.is_connected:
            _logger.debug("dynamics_line_loop [%s]: BLE not connected — loop exiting", handle.device_name)
            return

        if handle.device_mode() != _DeviceMode.ACTIVE:
            continue

        if handle.queue.is_saga_active:
            continue

        # Re-check on every tick — LUBA_VA depends on firmware version which
        # may not be known until reports start arriving.
        if not device_type.is_support_dynamics_line(_main_controller_version(handle)):
            continue

        await _enqueue_dynamics_line_saga(handle)


def _main_controller_version(handle: DeviceHandle) -> str | None:
    """Return the device's main-controller firmware version, or None if unknown.

    Pulls ``device_firmwares.main_controller`` off the current state snapshot;
    that's the field ``DeviceVersionUtils.isLessThanInputVersion`` consults in
    the APK.
    """
    raw = handle.snapshot.raw
    if not isinstance(raw, MowerDevice):
        return None
    fw = raw.device_firmwares.main_controller
    return fw or None


async def _enqueue_dynamics_line_saga(handle: DeviceHandle) -> None:
    """Enqueue a ``CommonDataSaga`` for the dynamics line and wire the update.

    On successful completion the assembled point list is stored on
    ``device.map.dynamics_line`` and the WGS-84 geojson is regenerated using
    the current RTK location, mirroring ``MammotionClient.get_dynamics_line``.
    """
    saga = CommonDataSaga(
        command_builder=handle.commands,
        send_command=handle.send_raw,
        action=8,
        type=PathType.DYNAMICS_LINE,
    )

    async def _on_complete() -> None:
        if not saga.result:
            return
        raw = handle.snapshot.raw
        if not isinstance(raw, MowerDevice):
            return
        raw.map.update_dynamics_line(saga.result)
        raw.map.apply_dynamics_line_geojson(raw.location.RTK)

    try:
        await handle.enqueue_saga(saga, on_complete=_on_complete)
    except Exception:  # noqa: BLE001
        _logger.debug("dynamics_line_loop [%s]: enqueue failed", handle.device_name, exc_info=True)
