"""The MQTT poll loop's handling of a device in low-power sleep (``MODE_SLEEPING``).

Sleep drops the device's broker connection, so nothing we send reaches it and the
only route back is ``MammotionHTTP.wake_up_device``.  The invariants: a sleeping
device is never polled, and the loop defers on the long sleep interval rather than
the cadence of whatever else it would have been classified as.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.device.ble_loop import _BLE_POLL_INTERVAL
from pymammotion.device.handle import DeviceHandle
from pymammotion.device.modes import _DeviceMode
from pymammotion.device.mqtt_loop import (
    _MQTT_NEW_POLL_INTERVAL,
    _MQTT_POLL_INTERVAL,
    _SLEEPING_RECHECK_INTERVAL,
    mqtt_activity_loop,
    poll_interval,
)
from pymammotion.transport.base import TransportType
from pymammotion.utility.constant import NO_REQUEST_MODES, WorkMode
from tests.unit._helpers import make_mock_handle, make_mock_transport


def _handle_with_status(sys_status: int, *, charge_state: int = 0, battery: int = 100) -> DeviceHandle:
    """A real handle reporting the given device state."""
    handle = make_mock_handle("dev1", "Luba-VATEST")
    dev = handle.snapshot.raw.report_data.dev
    dev.sys_status = sys_status
    dev.charge_state = charge_state
    dev.battery_val = battery
    return handle


def test_sleeping_status_is_its_own_mode() -> None:
    handle = _handle_with_status(WorkMode.MODE_SLEEPING)
    assert handle.cadence_mode() is _DeviceMode.SLEEPING
    # Public surface, so HA never has to touch the private _DeviceMode enum.
    assert handle.is_sleeping is True


def test_sleeping_on_the_dock_is_not_mistaken_for_charging() -> None:
    """Sleep is checked before charge state, which would otherwise claim it."""
    handle = _handle_with_status(WorkMode.MODE_SLEEPING, charge_state=1, battery=80)
    assert handle.cadence_mode() is _DeviceMode.SLEEPING


@pytest.mark.parametrize("status", [WorkMode.MODE_READY, WorkMode.MODE_WORKING, WorkMode.MODE_CHARGING])
def test_awake_statuses_are_not_sleeping(status: WorkMode) -> None:
    assert _handle_with_status(status).is_sleeping is False


@pytest.mark.parametrize("table", [_MQTT_POLL_INTERVAL, _MQTT_NEW_POLL_INTERVAL, _BLE_POLL_INTERVAL])
def test_cadence_tables_are_total(table: dict) -> None:
    """poll_interval indexes these by mode, so a missing entry is a KeyError at runtime."""
    assert set(table) == set(_DeviceMode)


@pytest.mark.parametrize("firmware", ["1.11.0.0", "9.9.9.9"])
def test_sleeping_recheck_is_long_on_both_firmware_paths(firmware: str) -> None:
    """Rate-limited and quota-free firmware share the sleep interval — neither polls."""
    handle = _handle_with_status(WorkMode.MODE_SLEEPING)
    with patch.object(type(handle), "firmware_version", property(lambda _self: firmware)):
        assert poll_interval(handle) == _SLEEPING_RECHECK_INTERVAL


def test_sleeping_recheck_is_longer_than_every_awake_interval() -> None:
    awake = [v for mode, v in _MQTT_NEW_POLL_INTERVAL.items() if mode is not _DeviceMode.SLEEPING]
    assert _SLEEPING_RECHECK_INTERVAL >= max(awake)


def test_sleeping_is_a_no_request_mode() -> None:
    """Belt to the transport gate's braces: no poll while we know it is asleep."""
    assert WorkMode.MODE_SLEEPING in NO_REQUEST_MODES


def _loop_handle(*, usable: bool) -> MagicMock:
    """A DeviceHandle double reporting SLEEPING, driven for exactly one tick.

    A cloud transport is registered with its last-received stamp pushed well past
    any interval, so the loop's debounce cannot be what stops the poll — the mode
    gates have to.  Staleness is expressed relative to ``time.monotonic()`` rather
    than by freezing the clock, matching the BLE loop tests.
    """
    handle = MagicMock()
    handle.is_stopping = False
    handle.device_name = "Luba-VATEST"
    handle.ble_stream_active = False
    handle.cadence_mode = MagicMock(return_value=_DeviceMode.SLEEPING)
    handle.in_no_request_mode = MagicMock(return_value=True)
    handle.has_usable_transport = usable
    handle.firmware_version = "9.9.9.9"

    mqtt = make_mock_transport(TransportType.CLOUD_MAMMOTION)
    handle.has_any_transport = True
    handle.cloud_transport = MagicMock(return_value=TransportType.CLOUD_MAMMOTION)
    handle.get_transport = MagicMock(return_value=mqtt)
    # Pushed well past any interval so the loop's debounce cannot be what stops
    # the poll — the mode gates have to be.
    handle.last_transport_activity = time.monotonic() - (_SLEEPING_RECHECK_INTERVAL + 60)

    handle.queue = MagicMock(is_saga_active=False)
    handle.availability = MagicMock(mqtt_reported_offline=not usable)
    handle.send_one_shot_report = AsyncMock()

    slept: list[float] = []

    async def _sleep_or_rearm(seconds: float) -> bool:
        slept.append(seconds)
        handle.is_stopping = True
        return False

    handle.sleep_or_rearm = AsyncMock(side_effect=_sleep_or_rearm)
    handle.slept = slept
    return handle


@pytest.mark.parametrize("usable", [False, True])
async def test_sleeping_device_is_never_polled_and_backs_off_long(usable: bool) -> None:
    """Whether or not the cloud has reported it offline yet, no poll goes out.

    ``usable=False`` is the normal case (the cloud saw it drop), stopped by the
    transport pre-flight; ``usable=True`` is the transient window before that report
    lands, where NO_REQUEST_MODES is what holds the send back.  Both back off on the
    sleep interval, which is why the bucket has to exist for the pre-flight path too.
    """
    handle = _loop_handle(usable=usable)
    await asyncio.wait_for(mqtt_activity_loop(handle), timeout=1)
    handle.send_one_shot_report.assert_not_called()
    assert handle.slept == [_SLEEPING_RECHECK_INTERVAL]
    # usable=True must have got as far as the mode gate; usable=False stops before it.
    assert handle.in_no_request_mode.called is usable
