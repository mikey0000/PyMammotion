"""Tests for transport-level rate limiting in DeviceHandle / Transport.

Rate limiting is now owned by the Transport base class (_rate_limited_until timestamp).
`_send_marked()` raises TransportRateLimitedError immediately when the active transport
is rate-limited, without touching the network.  A real TooManyRequestsException from
transport.send() causes DeviceHandle to call transport.set_rate_limited(), starting the
12-hour ban.  The ban expires automatically — no explicit clear is needed.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.aliyun.exceptions import TooManyRequestsException
from pymammotion.device.handle import DeviceHandle
from pymammotion.device.mqtt_loop import _RATE_LIMITED_BACKOFF
from pymammotion.transport.base import Transport, TransportRateLimitedError, TransportType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mowing_device() -> MagicMock:
    device = MagicMock()
    device.online = True
    device.enabled = True
    device.report_data.dev.battery_val = 75
    device.report_data.dev.sys_status = 0
    return device


def _make_handle() -> DeviceHandle:
    return DeviceHandle(
        device_id="dev1",
        device_name="Luba-RL",
        initial_device=_make_mowing_device(),
    )


def _make_mqtt_transport(*, connected: bool = True) -> MagicMock:
    t = MagicMock()
    t.transport_type = TransportType.CLOUD_ALIYUN
    t.is_connected = connected
    t.is_rate_limited = False
    t.send = AsyncMock()
    t.set_rate_limited = MagicMock()
    t.disconnect = AsyncMock()
    t.on_message = None
    t.add_availability_listener = MagicMock()
    t.last_received_monotonic = 0.0
    t.last_send_monotonic = 0.0
    return t


# ---------------------------------------------------------------------------
# Transport base class — is_rate_limited / set_rate_limited
# ---------------------------------------------------------------------------


def _make_concrete_transport() -> Transport:
    """Return a minimal concrete Transport (abstract methods stubbed out)."""

    class _Stub(Transport):
        @property
        def transport_type(self) -> TransportType:
            return TransportType.CLOUD_ALIYUN

        @property
        def is_connected(self) -> bool:
            return True

        @property
        def availability(self):  # type: ignore[override]
            from pymammotion.transport.base import TransportAvailability
            return TransportAvailability.CONNECTED

        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def send(self, payload: bytes, iot_id: str = "") -> None:
            pass

    return _Stub()


def test_transport_not_rate_limited_initially() -> None:
    """A freshly created Transport is not rate-limited."""
    t = _make_concrete_transport()
    assert t.is_rate_limited is False


def test_transport_set_rate_limited_blocks_for_duration() -> None:
    """After set_rate_limited(), is_rate_limited is True until the ban expires."""
    t = _make_concrete_transport()
    t.set_rate_limited()
    assert t.is_rate_limited is True


def test_transport_rate_limit_expires_after_12_hours() -> None:
    """is_rate_limited returns False once _rate_limited_until is in the past."""
    t = _make_concrete_transport()
    t.set_rate_limited()
    assert t.is_rate_limited is True

    # Simulate the 12-hour ban having expired.
    t._rate_limited_until = time.monotonic() - 1  # noqa: SLF001
    assert t.is_rate_limited is False


def test_transport_rate_limit_duration_is_12_hours() -> None:
    """set_rate_limited() sets a ban of exactly _RATE_LIMIT_DURATION seconds."""
    t = _make_concrete_transport()
    before = time.monotonic()
    t.set_rate_limited()
    after = time.monotonic()

    # Ban should expire roughly 12 hours from now.
    expected = 43200.0  # 12 h
    assert before + expected <= t._rate_limited_until <= after + expected  # noqa: SLF001


def test_transport_rate_limit_constant_matches_handle_backoff() -> None:
    """Transport._RATE_LIMIT_DURATION and handle._RATE_LIMITED_BACKOFF must agree."""
    t = _make_concrete_transport()
    assert t._RATE_LIMIT_DURATION == _RATE_LIMITED_BACKOFF  # noqa: SLF001


# ---------------------------------------------------------------------------
# _send_marked raises TransportRateLimitedError when transport is rate-limited
# ---------------------------------------------------------------------------


async def test_send_marked_raises_when_transport_rate_limited() -> None:
    """_send_marked() must raise TransportRateLimitedError without calling transport.send()."""
    handle = _make_handle()
    mqtt = _make_mqtt_transport()
    mqtt.is_rate_limited = True
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    with pytest.raises(TransportRateLimitedError):
        await handle._send_marked(mqtt, b"\x01\x02\x03")  # noqa: SLF001

    mqtt.send.assert_not_awaited()


async def test_send_marked_passes_through_when_not_rate_limited() -> None:
    """_send_marked() calls transport.send() when the transport is not rate-limited."""
    handle = _make_handle()
    mqtt = _make_mqtt_transport()
    mqtt.is_rate_limited = False
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    await handle._send_marked(mqtt, b"\x01\x02\x03")  # noqa: SLF001

    mqtt.send.assert_awaited_once()


# ---------------------------------------------------------------------------
# send_raw — 429 from transport.send() triggers set_rate_limited()
# ---------------------------------------------------------------------------


async def test_send_raw_calls_set_rate_limited_on_429() -> None:
    """send_raw must call transport.set_rate_limited() when TooManyRequestsException is raised."""
    handle = _make_handle()
    mqtt = _make_mqtt_transport()
    mqtt.send = AsyncMock(side_effect=TooManyRequestsException("rate limited", "iot-id"))
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    await handle.send_raw(b"\x00")

    mqtt.set_rate_limited.assert_called_once()


async def test_send_raw_blocked_silently_when_already_rate_limited() -> None:
    """send_raw must silently drop the send (not call transport.send) when already rate-limited."""
    handle = _make_handle()
    mqtt = _make_mqtt_transport()
    mqtt.is_rate_limited = True
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    await handle.send_raw(b"\x00")

    mqtt.send.assert_not_awaited()
    # set_rate_limited must NOT be called again — the ban is already active.
    mqtt.set_rate_limited.assert_not_called()


# ---------------------------------------------------------------------------
# BLE is unaffected by rate limiting
# ---------------------------------------------------------------------------


async def test_ble_transport_not_blocked_by_rate_limited_flag() -> None:
    """BLE transport with is_rate_limited=False is never blocked by _send_marked."""
    handle = _make_handle()

    ble = MagicMock()
    ble.transport_type = TransportType.BLE
    ble.is_connected = True
    ble.is_rate_limited = False
    ble.last_send_monotonic = 0.0
    ble.send = AsyncMock()
    ble.set_rate_limited = MagicMock()
    ble.disconnect = AsyncMock()
    ble.on_message = None
    ble.add_availability_listener = MagicMock()
    ble.last_received_monotonic = 0.0
    handle._transports[TransportType.BLE] = ble  # noqa: SLF001

    await handle._send_marked(ble, b"\xAA\xBB")  # noqa: SLF001

    ble.send.assert_awaited_once()


# ---------------------------------------------------------------------------
# Rate limit does NOT reset the ban timestamp on repeated calls
# (first 429 sets it; guard-triggered TransportRateLimitedError is not a new 429)
# ---------------------------------------------------------------------------


async def test_send_raw_guard_does_not_call_set_rate_limited_again() -> None:
    """If a transport is already rate-limited, send_raw must not call set_rate_limited() again."""
    handle = _make_handle()
    mqtt = _make_mqtt_transport()
    mqtt.is_rate_limited = True
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    # Call send_raw three times while the transport is already rate-limited.
    await handle.send_raw(b"\x01")
    await handle.send_raw(b"\x02")
    await handle.send_raw(b"\x03")

    mqtt.set_rate_limited.assert_not_called()
    mqtt.send.assert_not_awaited()
