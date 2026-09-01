"""Shared mock factories for unit tests.

Plain functions, not fixtures — matching tests/unit/transport/_fakes.py and
tests/unit/messaging/_helpers.py.  One superset builder per concept, so the
half-dozen per-file variants can't drift apart (the exact failure mode
_fakes.py's docstring warns about).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import partial
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from pymammotion.device.handle import DeviceHandle
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import JWTTokenInfo
from pymammotion.state.device_state import TransportAvailability
from pymammotion.transport.base import TransportType
from pymammotion.transport.ble import BLETransport
from pymammotion.transport.cloud import CloudTransport


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
    # isinstance() honours a Mock's __class__, and the send paths now narrow on it:
    # the quota and terminal-auth API live on CloudTransport, not on Transport.
    t.__class__ = BLETransport if transport_type is TransportType.BLE else CloudTransport
    t.transport_type = transport_type
    t.is_connected = connected
    t.availability = TransportAvailability.CONNECTED if connected else TransportAvailability.DISCONNECTED
    t.is_usable = usable
    t.is_rate_limited = False
    t.is_send_blocked = MagicMock(return_value=False)
    t.seconds_until_send_available = MagicMock(return_value=0.0)
    if transport_type is not TransportType.BLE:
        t.is_cloud_banned = False
        t.is_quota_exhausted = False
        # Bind the *real* refusal so a double cannot quietly neuter the gate: it is a
        # method now, and a plain MagicMock attribute would return a Mock and let every
        # blocked send through.  Bound to the mock, so it reads the mock's
        # is_send_blocked / is_cloud_banned / seconds_until_send_available.
        t.raise_if_send_blocked = partial(CloudTransport.raise_if_send_blocked, t)
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



def make_http_posting(
    status: int,
    body: dict,
    content_type: str = "application/json",
) -> tuple[MammotionHTTP, MagicMock]:
    """A MammotionHTTP whose ``_client_session`` POSTs return a canned response.

    Returns the session too, so callers can assert on url/json/headers.  The
    far-future ``expires_in`` keeps ``refresh_token_decorator`` from rotating.
    """
    http = MammotionHTTP()
    http.login_info = MagicMock(access_token="tok")  # type: ignore[assignment]
    http.expires_in = time.time() + 3600
    http.jwt_info = JWTTokenInfo(iot="https://iot.example", robot="https://robot.example")
    resp = MagicMock(status=status, headers={"Content-Type": content_type})
    resp.json = AsyncMock(return_value=body)
    session = MagicMock()
    session.post = AsyncMock(return_value=resp)

    @asynccontextmanager
    async def _fake_session() -> object:  # type: ignore[misc]
        yield session

    http._client_session = _fake_session  # type: ignore[method-assign]
    return http, session
