"""BLE-side cadence drivers for ``DeviceHandle``.

Two coroutines extracted from ``handle.py``:

* :func:`ble_activity_loop` — the 20 s ``todev_ble_sync(2)`` heartbeat that
  keeps the GATT link alive on a fixed cadence regardless of other traffic.
* :func:`ble_polling_loop` — drives either the continuous (count=0) report
  stream or count=1 polls, depending on device mode.

Both are free coroutines that take the owning ``DeviceHandle`` rather than
methods on it; per-instance state lives on the handle.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from pymammotion.device.modes import _DeviceMode
from pymammotion.proto import RptAct
from pymammotion.transport.base import TransportError, TransportType

if TYPE_CHECKING:
    from pymammotion.device.handle import DeviceHandle

_logger = logging.getLogger(__name__)

#: Keep-alive interval for BLE heartbeats.
_KEEP_ALIVE_BLE_INTERVAL: float = 20.0
#: Max consecutive BLE heartbeat failures before the loop gives up on BLE and falls back to MQTT.
_BLE_HEARTBEAT_FAIL_LIMIT: int = 30
#: Renewal cadence for the BLE continuous report-stream — must stay below the device 10 s timeout.
_BLE_STREAM_RENEW_INTERVAL: float = 8.0
#: Maximum sleep between BLE polling-loop ticks; caps mode-flip reaction time.
_BLE_MODE_RECHECK_INTERVAL: float = 30.0
#: ``sync_type`` for BLE heartbeats (matches APK ``sendBlueToothDeviceSync(2, ...)``).
_KEEP_ALIVE_SYNC_TYPE_BLE: int = 2

#: BLE poll cadence per device mode.  ``None`` means continuous count=0 stream
#: renewed every ``_BLE_STREAM_RENEW_INTERVAL`` seconds.  Numeric values are
#: count=1 polls at that cadence.
_BLE_POLL_INTERVAL: dict[_DeviceMode, float | None] = {
    _DeviceMode.ACTIVE: None,  # continuous stream
    _DeviceMode.DOCKED_CHARGING: 1 * 60.0,
    _DeviceMode.DOCKED_FULL: 5 * 60.0,
    _DeviceMode.IDLE: 5 * 60.0,
}


async def ble_activity_loop(handle: DeviceHandle) -> None:
    """BLE-specific heartbeat loop — runs independently of the MQTT loop.

    Sends ``todev_ble_sync(2)`` every ``_KEEP_ALIVE_BLE_INTERVAL`` seconds
    on a fixed cadence, **regardless of user-sent commands or active sagas**:

    * The first heartbeat fires immediately on loop start (right after
      ``_on_ble_connected``), then the cadence is timed off each send.  This
      matches the APK's behaviour (``MACarDataManager.java`` msg 1002 lambda
      schedules the first BLE sync at ~1 s post-connect) and avoids a 20 s
      silent window where the firmware-side GATT keep-alive timer could trip
      if the queue's initial ``get_report_cfg`` is dropped by a saga gate.
    * Recent user commands or inbound traffic do not delay a heartbeat —
      predictable cadence is more important than saving one packet.
    * The send bypasses the device queue and goes directly to the transport.
      A long saga holds the queue's exclusive lock for minutes; routing
      heartbeats through the queue meant they were either dropped
      (``skip_if_saga_active=True``) or stuck behind the saga, letting the
      GATT link time out mid-mow.  ``BLETransport._operation_lock``
      serializes the heartbeat against any concurrent saga write so direct
      dispatch is still safe.

    Exits (without cancelling the MQTT loop) when:
      * The BLE transport is removed from the handle.
      * Consecutive failures reach ``_BLE_HEARTBEAT_FAIL_LIMIT``.
      * BLE is no longer connected (``_on_ble_connected`` restarts on reconnect).
      * The handle is stopping.
    """
    while not handle._stopping:  # noqa: SLF001
        ble = handle.get_transport(TransportType.BLE)
        if ble is None:
            break  # transport removed — exit cleanly
        if not ble.is_connected:
            # BLE disconnected — exit and let _on_ble_connected restart this loop.
            break
        if handle._ble_heartbeat_failures >= _BLE_HEARTBEAT_FAIL_LIMIT:  # noqa: SLF001
            _logger.warning(
                "ble_loop [%s]: %d consecutive failures — exiting BLE loop",
                handle.device_name,
                handle._ble_heartbeat_failures,  # noqa: SLF001
            )
            break

        cmd_bytes = handle.commands.send_todev_ble_sync(sync_type=_KEEP_ALIVE_SYNC_TYPE_BLE)
        try:
            await ble.send_heartbeat(cmd_bytes, iot_id=handle.iot_id)
            handle._ble_heartbeat_failures = 0  # noqa: SLF001
        except TransportError:
            handle._ble_heartbeat_failures += 1  # noqa: SLF001
            _logger.debug(
                "ble_loop [%s]: send failed (attempt %d/%d) — marking disconnected",
                handle.device_name,
                handle._ble_heartbeat_failures,  # noqa: SLF001
                _BLE_HEARTBEAT_FAIL_LIMIT,
            )
        except Exception:  # noqa: BLE001
            handle._ble_heartbeat_failures += 1  # noqa: SLF001
            _logger.debug("ble_loop [%s]: unexpected error in heartbeat", handle.device_name, exc_info=True)

        try:
            await asyncio.sleep(_KEEP_ALIVE_BLE_INTERVAL)
        except asyncio.CancelledError:
            break


async def ble_polling_loop(handle: DeviceHandle) -> None:
    """BLE-side polling and continuous-stream loop, tied to BLE connection lifetime.

    Each tick reads :meth:`DeviceHandle._device_mode` and dispatches:

    * **Continuous mode** (``_BLE_POLL_INTERVAL[mode] is None`` — ACTIVE
      or IDLE): re-send ``request_iot_sys(RPT_START, count=0)`` every
      ``_BLE_STREAM_RENEW_INTERVAL`` to renew the device-side subscription
      before its 10 s timeout expires.  Sets ``_ble_stream_active`` so the
      MQTT loop knows to skip its redundant poll.

    * **Polling mode** (DOCKED_CHARGING, DOCKED_FULL): if the loop was
      previously streaming, send a single ``RPT_STOP`` and clear the flag.
      Then issue a ``request_iot_sys(count=1)`` poll at the table cadence.

    Sleeps are capped at ``_BLE_MODE_RECHECK_INTERVAL`` so a mode flip
    (e.g. dock → mow) is reacted to within ~30 s.

    The loop exits silently when BLE is no longer connected (or the
    availability handler cancels the task on disconnect).  The device
    clears any active subscription on its own after the 10 s timeout if
    the link is lost mid-stream.
    """
    last_one_shot_at: float = 0.0
    was_continuous: bool = False
    try:
        while not handle._stopping:  # noqa: SLF001
            ble = handle._transports.get(TransportType.BLE)  # noqa: SLF001
            if ble is None or not ble.is_connected:
                break

            mode = handle._device_mode()  # noqa: SLF001
            ble_interval = _BLE_POLL_INTERVAL[mode]

            if was_continuous and ble_interval is not None:
                # Transitioned out of continuous mode — issue a single STOP.
                try:
                    await handle._enqueue_ble_stream_command(RptAct.RPT_STOP, count=1)  # noqa: SLF001
                except Exception:
                    _logger.debug("ble_polling [%s]: STOP enqueue failed", handle.device_name, exc_info=True)
                handle._ble_stream_active = False  # noqa: SLF001
                handle._rearm_event.set()  # noqa: SLF001 — wake MQTT loop now that it owns the cadence again
                last_one_shot_at = 0.0  # force a fresh count=1 poll on this tick

            if ble_interval is None:
                try:
                    if handle._ble_stream_active:  # noqa: SLF001
                        # Stream already running — send RPT_KEEP to renew the
                        # device-side subscription before the 10 s timeout.
                        await handle._send_report_stream_keep()  # noqa: SLF001
                    else:
                        # Stream not yet active — establish it with RPT_START.
                        await handle._enqueue_ble_stream_command(RptAct.RPT_START, count=0)  # noqa: SLF001
                        handle._ble_stream_active = True  # noqa: SLF001
                except Exception:
                    _logger.debug(
                        "ble_polling [%s]: stream renew/start failed",
                        handle.device_name,
                        exc_info=True,
                    )
                wait = _BLE_STREAM_RENEW_INTERVAL
            else:
                now = time.monotonic()
                if now - last_one_shot_at >= ble_interval and not handle._in_no_request_mode():  # noqa: SLF001
                    try:
                        await handle._send_one_shot_report()  # noqa: SLF001
                        last_one_shot_at = now
                    except Exception:
                        _logger.debug(
                            "ble_polling [%s]: one-shot enqueue failed",
                            handle.device_name,
                            exc_info=True,
                        )
                time_until_next_poll = ble_interval - (time.monotonic() - last_one_shot_at)
                wait = max(1.0, min(time_until_next_poll, _BLE_MODE_RECHECK_INTERVAL))

            was_continuous = ble_interval is None

            try:
                await asyncio.sleep(wait)
            except asyncio.CancelledError:
                break
    finally:
        if handle._ble_stream_active:  # noqa: SLF001
            handle._ble_stream_active = False  # noqa: SLF001
            handle._rearm_event.set()  # noqa: SLF001
