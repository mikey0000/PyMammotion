"""Shared mock factories for unit tests.

Plain functions, not fixtures — matching tests/unit/transport/_fakes.py and
tests/unit/messaging/_helpers.py.  One superset builder per concept, so the
half-dozen per-file variants can't drift apart (the exact failure mode
_fakes.py's docstring warns about).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from pymammotion.device.handle import DeviceHandle
from pymammotion.state.device_state import TransportAvailability
from pymammotion.transport.base import TransportType


def make_mock_transport(
    transport_type: TransportType = TransportType.CLOUD_ALIYUN,
    *,
    connected: bool = True,
    usable: bool = True,
    **overrides: Any,
) -> MagicMock:
    """A MagicMock shaped like a Transport, superset of every per-file variant.

    Every attribute a DeviceHandle/queue/poll-loop code path may touch is set
    explicitly, so a new gate reading an unset attribute fails loudly instead
    of passing on a truthy auto-created MagicMock.
    """
    t = MagicMock()
    t.transport_type = transport_type
    t.is_connected = connected
    t.availability = TransportAvailability.CONNECTED if connected else TransportAvailability.DISCONNECTED
    t.is_usable = usable
    t.is_rate_limited = False
    t.is_send_blocked = MagicMock(return_value=False)
    t.seconds_until_send_available = MagicMock(return_value=0.0)
    t.last_send_monotonic = 0.0
    t.last_received_monotonic = 0.0
    t.send = AsyncMock()
    t.send_heartbeat = AsyncMock()
    t.connect = AsyncMock()
    t.disconnect = AsyncMock()
    t.on_message = None
    t.set_rate_limited = MagicMock()
    t.add_availability_listener = MagicMock()
    for name, value in overrides.items():
        setattr(t, name, value)
    return t


def make_mock_mowing_device(**overrides: Any) -> MagicMock:
    """A MagicMock shaped like a MowingDevice.

    Explicit ``charge_state = 0`` because ``int(MagicMock())`` returns 1, which
    would push DeviceHandle._device_mode into DOCKED_CHARGING and surprise
    tests that don't otherwise care about charge state.
    """
    device = MagicMock()
    device.online = True
    device.enabled = True
    device.report_data.dev.battery_val = 75
    device.report_data.dev.charge_state = 0
    device.report_data.dev.sys_status = "idle"
    device.report_data.work.knife_height = 40
    for name, value in overrides.items():
        setattr(device, name, value)
    return device


def make_mock_handle(
    device_id: str = "dev1",
    device_name: str = "Luba-Test",
    *,
    prefer_ble: bool = False,
    device: Any | None = None,
    mqtt_transport: MagicMock | None = None,
    ble_transport: MagicMock | None = None,
) -> DeviceHandle:
    """A real DeviceHandle backed by a mock MowingDevice."""
    return DeviceHandle(
        device_id=device_id,
        device_name=device_name,
        initial_device=device if device is not None else make_mock_mowing_device(),
        prefer_ble=prefer_ble,
        mqtt_transport=mqtt_transport,
        ble_transport=ble_transport,
    )
