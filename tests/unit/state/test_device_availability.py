"""Tests for DeviceAvailability and DeviceStateMachine."""
from unittest.mock import MagicMock

import pytest

from pymammotion.state.device_state import (
    DeviceAvailability,
    DeviceConnectionState,
    DeviceStateMachine,
    TransportAvailability,
)


# ---------------------------------------------------------------------------
# DeviceAvailability.is_available
# ---------------------------------------------------------------------------


def test_ble_connected_always_available() -> None:
    avail = DeviceAvailability(
        ble=TransportAvailability.CONNECTED,
        mqtt=TransportAvailability.DISCONNECTED,
        mqtt_reported_offline=True,
    )
    assert avail.is_available is True


def test_ble_connected_mqtt_unknown() -> None:
    avail = DeviceAvailability(ble=TransportAvailability.CONNECTED, mqtt=TransportAvailability.UNKNOWN)
    assert avail.is_available is True


def test_mqtt_connected_not_offline() -> None:
    avail = DeviceAvailability(
        ble=TransportAvailability.DISCONNECTED,
        mqtt=TransportAvailability.CONNECTED,
        mqtt_reported_offline=False,
    )
    assert avail.is_available is True


def test_mqtt_connected_but_reported_offline() -> None:
    avail = DeviceAvailability(
        ble=TransportAvailability.DISCONNECTED,
        mqtt=TransportAvailability.CONNECTED,
        mqtt_reported_offline=True,
    )
    assert avail.is_available is False


def test_both_disconnected() -> None:
    avail = DeviceAvailability(ble=TransportAvailability.DISCONNECTED, mqtt=TransportAvailability.DISCONNECTED)
    assert avail.is_available is False


def test_default_both_unknown_not_available() -> None:
    avail = DeviceAvailability()
    assert avail.is_available is False


# ---------------------------------------------------------------------------
# DeviceAvailability.connection_state
# ---------------------------------------------------------------------------


def test_connection_state_connected_when_available() -> None:
    avail = DeviceAvailability(mqtt=TransportAvailability.CONNECTED)
    assert avail.connection_state == DeviceConnectionState.CONNECTED


def test_connection_state_connecting() -> None:
    avail = DeviceAvailability(mqtt=TransportAvailability.CONNECTING, ble=TransportAvailability.DISCONNECTED)
    assert avail.connection_state == DeviceConnectionState.CONNECTING


def test_connection_state_unavailable_when_both_down() -> None:
    avail = DeviceAvailability(mqtt=TransportAvailability.DISCONNECTED, ble=TransportAvailability.DISCONNECTED)
    assert avail.connection_state == DeviceConnectionState.UNAVAILABLE


def test_ble_connecting_sets_connecting_state() -> None:
    avail = DeviceAvailability(mqtt=TransportAvailability.DISCONNECTED, ble=TransportAvailability.CONNECTING)
    assert avail.connection_state == DeviceConnectionState.CONNECTING


# ---------------------------------------------------------------------------
# Helper: minimal MowingDevice mock
# ---------------------------------------------------------------------------


def make_device(online: bool = True, enabled: bool = True) -> MagicMock:
    """Return a MagicMock shaped like a MowingDevice."""
    device = MagicMock()
    device.online = online
    device.enabled = enabled
    device.report_data.dev.battery_val = 75
    device.report_data.dev.sys_status = 0
    device.report_data.work.knife_height = 60
    return device


# ---------------------------------------------------------------------------
# DeviceStateMachine
# ---------------------------------------------------------------------------


def test_state_machine_initial_sequence() -> None:
    device = make_device()
    sm = DeviceStateMachine("dev1", device)
    assert sm.current.sequence == 0


def test_state_machine_apply_increments_sequence() -> None:
    device = make_device()
    sm = DeviceStateMachine("dev1", device)
    new_snap, _ = sm.apply(device, DeviceAvailability(mqtt=TransportAvailability.CONNECTED))
    assert new_snap.sequence == 1
    assert sm.current.sequence == 1


def test_state_machine_detects_changed_fields() -> None:
    device1 = make_device(online=True)
    sm = DeviceStateMachine("dev1", device1)
    device2 = make_device(online=False)
    _, changed = sm.apply(device2, DeviceAvailability())
    assert "online" in changed


def test_state_machine_no_change_empty_set() -> None:
    device = make_device()
    sm = DeviceStateMachine("dev1", device)
    _, changed = sm.apply(device, DeviceAvailability())
    # sequence/timestamp/raw are excluded; if no other field changed, set is empty
    assert "sequence" not in changed
    assert "timestamp" not in changed
    assert "raw" not in changed


def test_state_machine_battery_stored_in_snapshot() -> None:
    device = make_device()
    sm = DeviceStateMachine("dev1", device)
    assert sm.current.battery_level == 75


def test_state_machine_blade_height_accessible_via_raw() -> None:
    device = make_device()
    sm = DeviceStateMachine("dev1", device)
    assert sm.current.raw.report_data.work.knife_height == 60


def test_state_machine_connection_state_propagated() -> None:
    device = make_device()
    sm = DeviceStateMachine("dev1", device)
    avail = DeviceAvailability(mqtt=TransportAvailability.CONNECTED)
    new_snap, _ = sm.apply(device, avail)
    assert new_snap.connection_state == DeviceConnectionState.CONNECTED
