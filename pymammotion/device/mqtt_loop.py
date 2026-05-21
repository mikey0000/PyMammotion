"""MQTT-side cadence driver for ``DeviceHandle``.

Pulled out of ``handle.py`` so the loop body — and the per-mode poll-interval
table that drives it — can be read and tuned in isolation from the rest of the
facade.

The loop is a free coroutine that takes the owning ``DeviceHandle`` rather than
a method on it.  All state (transports, rearm event, last-send timestamps,
``_stopping``, …) is read directly off the handle; the loop owns nothing.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING

from pymammotion.device.ble_loop import _BLE_MODE_RECHECK_INTERVAL
from pymammotion.device.modes import _DeviceMode
from pymammotion.transport.base import Transport, TransportType

if TYPE_CHECKING:
    from pymammotion.device.handle import DeviceHandle

_logger = logging.getLogger(__name__)

#: Activity-loop backoff when MQTT is rate-limited and no BLE is available.
_RATE_LIMITED_BACKOFF: float = 43200.0  # 12 hours

#: MQTT one-shot (count=1) poll cadence per device mode.  Tuned for cloud quotas.
#: Each entry can be overridden at process startup via an environment variable:
#:   MAMMOTION_POLL_ACTIVE_SECS, MAMMOTION_POLL_DOCKED_CHARGING_SECS,
#:   MAMMOTION_POLL_DOCKED_FULL_SECS, MAMMOTION_POLL_IDLE_SECS
_MQTT_POLL_INTERVAL: dict[_DeviceMode, float] = {
    _DeviceMode.ACTIVE: float(os.environ.get("MAMMOTION_POLL_ACTIVE_SECS", 15 * 60)),
    _DeviceMode.DOCKED_CHARGING: float(os.environ.get("MAMMOTION_POLL_DOCKED_CHARGING_SECS", 30 * 60)),
    _DeviceMode.DOCKED_FULL: float(os.environ.get("MAMMOTION_POLL_DOCKED_FULL_SECS", 60 * 60)),
    _DeviceMode.IDLE: float(os.environ.get("MAMMOTION_POLL_IDLE_SECS", 15 * 60)),
}


def poll_interval(handle: DeviceHandle) -> float:
    """Return the MQTT one-shot poll interval based on current device mode.

    See ``_MQTT_POLL_INTERVAL`` for the per-mode cadence table.
    """
    return _MQTT_POLL_INTERVAL[handle._device_mode()]  # noqa: SLF001


async def mqtt_activity_loop(handle: DeviceHandle) -> None:
    """Periodic one-shot report-poll loop (MQTT-side cadence driver).

    Sends ``request_iot_sys(count=1)`` via the best available transport
    (BLE if connected, MQTT otherwise) once the device has been silent for
    longer than the per-mode interval defined in ``_MQTT_POLL_INTERVAL``:

    * **ACTIVE**         — 20 min (mowing/returning).
    * **DOCKED_CHARGING** — 30 min (docked, battery < 100%).
    * **DOCKED_FULL**    — 60 min (docked, battery 100%).
    * **IDLE**           — 15 min (paused/locked/lost).

    While ``handle._ble_stream_active`` is True the BLE polling loop is feeding
    a continuous count=0 stream and this loop defers entirely; the BLE
    availability handler clears the flag and rearms us on disconnect.

    The timer resets on either incoming device data or a sent poll, so a
    device that doesn't respond is polled at most once per interval.

    The loop is interruptible: ``record_user_command`` sets ``_rearm_event``
    to wake an in-progress sleep early for immediate re-evaluation.
    """
    last_poll_sent_at: float = 0.0

    while not handle._stopping:  # noqa: SLF001
        interval = poll_interval(handle)

        # While the BLE polling loop owns a continuous stream, this loop
        # has nothing useful to do — fresh state is arriving over BLE.
        if handle._ble_stream_active:  # noqa: SLF001
            await handle._sleep_or_rearm(_BLE_MODE_RECHECK_INTERVAL)  # noqa: SLF001
            continue

        # No usable transport (cloud reported device offline + no BLE,
        # BLE in cooldown + no MQTT, or nothing registered).  Skip the
        # poll attempt — ``_rearm_event`` fires on BLE state changes and
        # ``mqtt_reported_offline`` clears on the next inbound MQTT frame,
        # so both natural recovery signals already wake us.
        if not handle.has_usable_transport:
            _logger.debug(
                "poll_loop [%s]: no usable transport (mqtt_offline=%s) — backing off %.0fs",
                handle.device_name,
                handle._availability.mqtt_reported_offline,  # noqa: SLF001
                interval,
            )
            await handle._sleep_or_rearm(interval)  # noqa: SLF001
            continue

        # Timer: the later of "last data received" and "last poll sent".
        # Including last_poll_sent_at prevents spam when the device doesn't respond.
        last_recv = max(
            (t.last_received_monotonic for t in handle._transports.values()),  # noqa: SLF001
            default=0.0,
        )
        last_activity = max(last_recv, last_poll_sent_at)
        wait = interval - (time.monotonic() - last_activity)

        if wait > 0:
            if await handle._sleep_or_rearm(wait):  # noqa: SLF001
                continue  # rearmed by user command — re-evaluate immediately
            last_recv = max(
                (t.last_received_monotonic for t in handle._transports.values()),  # noqa: SLF001
                default=0.0,
            )
            last_activity = max(last_recv, last_poll_sent_at)
            if time.monotonic() - last_activity < interval:
                continue

        if not handle._transports:  # noqa: SLF001
            await handle._sleep_or_rearm(interval)  # noqa: SLF001
            continue

        # Back off if MQTT is rate-limited and no BLE transport is connected.
        mqtt: Transport | None = None
        for tt in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
            t = handle._transports.get(tt)  # noqa: SLF001
            if t is not None:
                mqtt = t
                break
        if mqtt is not None and mqtt.is_rate_limited:
            ble = handle._transports.get(TransportType.BLE)  # noqa: SLF001
            if ble is None or not ble.is_connected:
                _logger.debug(
                    "poll_loop [%s]: MQTT rate-limited, no BLE — backing off %.0fh",
                    handle.device_name,
                    _RATE_LIMITED_BACKOFF / 3600,
                )
                await handle._sleep_or_rearm(_RATE_LIMITED_BACKOFF)  # noqa: SLF001
                continue

        if handle.queue.is_saga_active or handle._in_no_request_mode():  # noqa: SLF001
            _logger.debug("poll_loop [%s]: saga active or no-request mode — deferring", handle.device_name)
            await handle._sleep_or_rearm(interval)  # noqa: SLF001
            continue

        _logger.debug(
            "poll_loop [%s]: %.0fs since last activity — sending one-shot poll (interval=%.0fs)",
            handle.device_name,
            time.monotonic() - last_activity,
            interval,
        )
        last_poll_sent_at = time.monotonic()
        await handle._send_one_shot_report()  # noqa: SLF001
