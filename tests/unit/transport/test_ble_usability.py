"""is_usable and what gates it: BLEDevice presence, advertisement RSSI, and cooldown.

Split out of ``test_ble.py``.  ``DeviceHandle.active_transport()`` reads ``is_usable``
to decide whether BLE is even a candidate, so everything that can drive it False —
no device, a weak advertisement, a tripped failure threshold — is one concern.
"""

from __future__ import annotations

import time
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

from bleak import BLEDevice
import pytest

from pymammotion.transport.ble import BLETransport, BLETransportConfig
from tests.unit.transport._fakes import make_ble_device
from tests.unit.transport._fakes import make_fake_ble_client
from tests.unit.transport._fakes import make_fake_ble_message


@pytest.fixture
def config() -> BLETransportConfig:
    return BLETransportConfig(device_id="test-device-001", ble_address="AA:BB:CC:DD:EE:FF")


@pytest.fixture
def transport(config: BLETransportConfig) -> BLETransport:
    return BLETransport(config)


# is_usable / change-detection / cooldown / clear_ble_device


def test_is_usable_false_when_no_device(transport: BLETransport) -> None:
    """A transport with no cached BLEDevice is not usable."""
    assert transport.is_usable is False
    assert transport.ble_address is None


def test_is_usable_true_after_set_ble_device(transport: BLETransport) -> None:
    """Setting a BLEDevice makes the transport usable and exposes its address."""
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))
    assert transport.is_usable is True
    assert transport.ble_address == "AA:BB:CC:DD:EE:FF"


def test_set_ble_device_returns_true_on_first_set(transport: BLETransport) -> None:
    """First-ever set is reported as a change."""
    assert transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF")) is True


def test_set_ble_device_returns_true_on_address_change(transport: BLETransport) -> None:
    """Setting a different-address device is reported as a change."""
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))
    assert transport.set_ble_device(make_ble_device("11:22:33:44:55:66")) is True


def test_set_ble_device_returns_false_on_same_address(transport: BLETransport) -> None:
    """Re-setting with the same address (different BLEDevice instance) reports no change."""
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))
    # Different instance, same address — caller can short-circuit downstream work.
    assert transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF")) is False


def test_is_usable_true_when_rssi_above_threshold(transport: BLETransport) -> None:
    """A strong advertisement RSSI keeps the transport usable."""
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"), rssi=-55)
    assert transport.is_usable is True


def test_is_usable_false_when_rssi_below_threshold(transport: BLETransport) -> None:
    """An RSSI weaker than config.min_rssi marks the transport unusable."""
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"), rssi=-95)
    assert transport.is_usable is False


def test_is_usable_true_when_rssi_unknown(transport: BLETransport) -> None:
    """An unknown RSSI (never pushed) does not gate is_usable."""
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))
    assert transport._last_rssi is None  # noqa: SLF001
    assert transport.is_usable is True


def test_set_ble_device_without_rssi_keeps_last_known(transport: BLETransport) -> None:
    """A refresh that omits RSSI leaves the previously reported value intact."""
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"), rssi=-95)
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))
    assert transport._last_rssi == -95  # noqa: SLF001
    assert transport.is_usable is False


def test_clear_ble_device_resets_rssi(transport: BLETransport) -> None:
    """clear_ble_device() forgets the last RSSI along with the device."""
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"), rssi=-90)
    transport.clear_ble_device()
    assert transport._last_rssi is None  # noqa: SLF001


def test_clear_ble_device_resets_state(transport: BLETransport) -> None:
    """clear_ble_device() drops the device, resets failures, and clears any cooldown."""
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))
    transport._consecutive_failures = 2  # noqa: SLF001
    transport._connect_cooldown_until = 1e12  # noqa: SLF001 — far future cooldown
    transport.clear_ble_device()
    assert transport._ble_device is None  # noqa: SLF001
    assert transport._consecutive_failures == 0  # noqa: SLF001
    assert transport._connect_cooldown_until == 0.0  # noqa: SLF001
    assert transport.is_usable is False


def test_cooldown_expiry_restores_is_usable_without_new_advertisement(config: BLETransportConfig) -> None:
    """After the cooldown lapses, is_usable becomes True without a new advertisement.

    _record_connect_failure() no longer clears _ble_device — the device is
    merely temporarily out of range and may be reachable again once the cooldown
    expires.  is_usable is gated solely by the monotonic timer, so it recovers
    automatically when the timer lapses with no call_later or new advertisement
    required.
    """
    transport = BLETransport(config)
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))

    # Trip the cooldown — _ble_device must NOT be cleared.
    for _ in range(config.connect_failure_threshold):
        transport._record_connect_failure()  # noqa: SLF001

    # During cooldown: unusable, but device pointer preserved.
    assert transport._ble_device is not None  # noqa: SLF001
    assert transport.is_usable is False

    # Simulate expiry by rewinding the deadline.
    transport._connect_cooldown_until = time.monotonic() - 1.0  # noqa: SLF001

    # Cooldown gone, device still set — is_usable recovers on its own.
    assert transport.is_usable is True


async def test_connect_failure_threshold_triggers_cooldown(config: BLETransportConfig) -> None:
    """N consecutive BleakError failures clear the BLEDevice and start a cooldown."""
    from bleak.exc import BleakError

    from pymammotion.transport.base import BLEUnavailableError

    transport = BLETransport(config)
    transport.set_ble_device(make_ble_device(config.ble_address or "AA:BB:CC:DD:EE:FF"))

    with patch(
        "pymammotion.transport.ble.establish_connection",
        new=AsyncMock(side_effect=BleakError("connect failed")),
    ):
        for _ in range(config.connect_failure_threshold):
            with pytest.raises(BLEUnavailableError):
                await transport.connect()

    # Threshold trip → cooldown set, transport unusable; device pointer preserved.
    assert transport._ble_device is not None  # noqa: SLF001 — kept for post-cooldown re-use
    assert transport.is_usable is False
    assert transport._connect_cooldown_until > 0.0  # noqa: SLF001


async def test_out_of_slots_error_trips_cooldown_immediately(config: BLETransportConfig) -> None:
    """A single BleakOutOfConnectionSlotsError cools down at once (no threshold wait).

    The proxy/adapter is out of connection slots or the device is unreachable — an
    immediate retry can't succeed, so is_usable must go False after ONE failure and
    the handle's send paths fall through to MQTT instead of re-attempting BLE on
    every send.
    """
    from bleak_retry_connector import BleakOutOfConnectionSlotsError

    from pymammotion.transport.base import BLEUnavailableError

    # Use a threshold > 1 so a single failure proves the *immediate* path, not the
    # ordinary consecutive-failure trip (the shared fixture uses threshold=1).
    slots_config = replace(config, connect_failure_threshold=3)
    transport = BLETransport(slots_config)
    transport.set_ble_device(make_ble_device(slots_config.ble_address or "AA:BB:CC:DD:EE:FF"))

    with patch(
        "pymammotion.transport.ble.establish_connection",
        new=AsyncMock(side_effect=BleakOutOfConnectionSlotsError("out of slots")),
    ):
        with pytest.raises(BLEUnavailableError):
            await transport.connect()

    # One failure was enough: cooldown armed, transport unusable; device pointer preserved.
    assert transport._ble_device is not None  # noqa: SLF001 — kept for post-cooldown re-use
    assert transport.is_usable is False
    assert transport._connect_cooldown_until > 0.0  # noqa: SLF001


async def test_connect_during_cooldown_raises_immediately(config: BLETransportConfig) -> None:
    """While in cooldown, connect() refuses without invoking bleak."""
    from pymammotion.transport.base import BLEUnavailableError

    transport = BLETransport(config)
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))
    transport._connect_cooldown_until = time.monotonic() + 60.0  # noqa: SLF001

    establish = AsyncMock()
    with patch("pymammotion.transport.ble.establish_connection", new=establish):
        with pytest.raises(BLEUnavailableError):
            await transport.connect()

    establish.assert_not_awaited()
    assert transport.is_usable is False  # cooldown gates is_usable too


async def test_successful_connect_resets_failure_counter(config: BLETransportConfig) -> None:
    """After a successful connect, the failure counter is back to zero."""
    transport = BLETransport(config)
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))
    transport._consecutive_failures = 2  # noqa: SLF001 — simulate prior failures

    fake_client = make_fake_ble_client()
    fake_msg = make_fake_ble_message()
    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.transport.ble.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()

    assert transport._consecutive_failures == 0  # noqa: SLF001
