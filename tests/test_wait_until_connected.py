"""Tests for DeviceHandle.wait_until_connected readiness gating.

The method waits for a transport to be ready: BLE counts the instant it
connects, MQTT only after staying connected for ``mqtt_stable_for`` seconds, and
it returns False (continue anyway) once ``timeout`` elapses. These tests drive
the method with a minimal stand-in for ``self`` (it only uses
``is_transport_connected`` and ``device_name``) and short real timeouts.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import TransportType


def _fake_handle(connected: set[TransportType]) -> SimpleNamespace:
    """A stand-in exposing just what wait_until_connected touches."""
    return SimpleNamespace(
        device_name="Luba-TEST",
        is_transport_connected=lambda tt: tt in connected,
    )


async def _wait(fake: SimpleNamespace, **kwargs: float) -> bool:
    # Call the unbound coroutine with our stand-in as ``self``.
    return await DeviceHandle.wait_until_connected(fake, **kwargs)


@pytest.mark.asyncio
async def test_ble_connected_returns_true_immediately() -> None:
    fake = _fake_handle({TransportType.BLE})
    # Large stability window is irrelevant — BLE needs no settling.
    assert await _wait(fake, timeout=5.0, mqtt_stable_for=10.0) is True


@pytest.mark.asyncio
async def test_mqtt_ready_when_stability_window_is_zero() -> None:
    fake = _fake_handle({TransportType.CLOUD_MAMMOTION})
    assert await _wait(fake, timeout=5.0, mqtt_stable_for=0.0) is True


@pytest.mark.asyncio
async def test_mqtt_aliyun_also_counts() -> None:
    fake = _fake_handle({TransportType.CLOUD_ALIYUN})
    assert await _wait(fake, timeout=5.0, mqtt_stable_for=0.0) is True


@pytest.mark.asyncio
async def test_mqtt_not_stable_long_enough_times_out() -> None:
    # MQTT is connected but the stability window can't be met before give-up,
    # so the method returns False (caller continues anyway).
    fake = _fake_handle({TransportType.CLOUD_MAMMOTION})
    assert await _wait(fake, timeout=0.3, mqtt_stable_for=5.0) is False


@pytest.mark.asyncio
async def test_no_transport_times_out_false() -> None:
    fake = _fake_handle(set())
    assert await _wait(fake, timeout=0.3, mqtt_stable_for=10.0) is False


@pytest.mark.asyncio
async def test_ble_beats_unstable_mqtt() -> None:
    # BLE connected wins immediately even with a huge MQTT stability window.
    fake = _fake_handle({TransportType.BLE, TransportType.CLOUD_MAMMOTION})
    assert await _wait(fake, timeout=5.0, mqtt_stable_for=999.0) is True
