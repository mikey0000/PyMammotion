"""Tests for the de-duplicated debug log in ``DeviceHandle.active_transport``.

The 2026-05-22 HA log showed 130+ identical
``BLE preferred but not usable — falling back to TransportType.CLOUD_MAMMOTION``
debug lines, one per send.  The fix emits the line only when the
(selection-path, prefer_ble, ble_usable, mqtt_usable) tuple changes — repeat
identical selections are silent.
"""
from __future__ import annotations

import contextlib
import logging
from unittest.mock import MagicMock

import pytest

from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import NoTransportAvailableError, TransportAvailability, TransportType


@pytest.fixture
def handle() -> DeviceHandle:
    """Minimal DeviceHandle — just enough for active_transport() to run."""
    from pymammotion.data.model.device import MowerDevice

    h = DeviceHandle(
        device_id="dev-test",
        device_name="Luba-VAAAYRNG",
        initial_device=MowerDevice(),
    )
    return h


def _add_mqtt(handle: DeviceHandle, *, usable: bool = True) -> MagicMock:
    mqtt = MagicMock()
    mqtt.transport_type = TransportType.CLOUD_MAMMOTION
    mqtt.is_connected = True
    mqtt.is_usable = usable
    mqtt.availability = TransportAvailability.CONNECTED
    handle._transports[TransportType.CLOUD_MAMMOTION] = mqtt  # noqa: SLF001
    return mqtt


def _add_unusable_ble(handle: DeviceHandle) -> MagicMock:
    ble = MagicMock()
    ble.transport_type = TransportType.BLE
    ble.is_connected = False
    ble.is_usable = False
    ble.availability = TransportAvailability.DISCONNECTED
    handle._transports[TransportType.BLE] = ble  # noqa: SLF001
    return ble


def test_identical_selections_emit_one_log_line(handle: DeviceHandle, caplog: pytest.LogCaptureFixture) -> None:
    """Repeat calls with the same selection state must produce only one DEBUG line.

    Regression for the 130× log-spam observed in the HA log when BLE was
    unusable for the full session and every send hit the fallback path.
    """
    _add_mqtt(handle, usable=True)
    _add_unusable_ble(handle)

    caplog.set_level(logging.DEBUG, logger="pymammotion.device.handle")

    # Call active_transport 50 times with BLE preferred but unusable.
    for _ in range(50):
        handle.active_transport(prefer_ble=True)

    fallback_lines = [
        r for r in caplog.records if "BLE preferred but not usable — falling back" in r.getMessage()
    ]
    assert len(fallback_lines) == 1, (
        f"Expected 1 fallback log line, got {len(fallback_lines)}.  "
        f"The de-dupe in active_transport regressed."
    )


def test_state_transition_re_emits_log(handle: DeviceHandle, caplog: pytest.LogCaptureFixture) -> None:
    """When the (selection-path, prefer_ble, ble_usable, mqtt_usable) tuple
    actually changes, the new state MUST be logged."""
    mqtt = _add_mqtt(handle, usable=True)
    ble = _add_unusable_ble(handle)

    caplog.set_level(logging.DEBUG, logger="pymammotion.device.handle")

    # First call: BLE preferred but unusable → MQTT fallback
    handle.active_transport(prefer_ble=True)
    # Second call: same state → SHOULD NOT re-log
    handle.active_transport(prefer_ble=True)
    # BLE becomes usable → DIFFERENT state → MUST re-log
    ble.is_usable = True
    handle.active_transport(prefer_ble=True)

    # Snapshot rule-match logs from these three calls (no error path yet).
    rule_lines = [
        r for r in caplog.records
        if r.name == "pymammotion.device.handle"
        and (
            "BLE preferred" in r.getMessage()
            or "selected " in r.getMessage()
            or "MQTT unusable" in r.getMessage()
        )
    ]
    # Expect exactly 2 transitions logged: (1) BLE-unusable-fallback,
    # (2) BLE-usable.  The repeat in between is suppressed.
    assert len(rule_lines) == 2, (
        f"Expected 2 transition logs, got {len(rule_lines)}.  "
        f"Messages: {[r.getMessage() for r in rule_lines]}"
    )

    # Sanity: when both transports go unusable, active_transport raises
    # (we don't assert on that log here — the error path uses a different
    # logger call that's not under _log_selection's dedup).
    mqtt.is_usable = False
    ble.is_usable = False
    with contextlib.suppress(NoTransportAvailableError):
        handle.active_transport(prefer_ble=True)


def test_prefer_ble_change_is_a_transition(handle: DeviceHandle, caplog: pytest.LogCaptureFixture) -> None:
    """Switching prefer_ble between calls counts as a state change and re-logs."""
    _add_mqtt(handle, usable=True)
    _add_unusable_ble(handle)

    caplog.set_level(logging.DEBUG, logger="pymammotion.device.handle")

    handle.active_transport(prefer_ble=True)  # BLE preferred + fallback
    handle.active_transport(prefer_ble=False)  # MQTT selected directly
    handle.active_transport(prefer_ble=True)  # back to BLE preferred + fallback

    rule_lines = [
        r for r in caplog.records
        if "BLE preferred but not usable" in r.getMessage() or "selected " in r.getMessage()
    ]
    # 3 distinct (selection-path, prefer_ble) combinations → at least 3 logs
    assert len(rule_lines) >= 3
