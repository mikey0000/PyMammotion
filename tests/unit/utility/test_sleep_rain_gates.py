"""Firmware gates for the Smart Sleep switches and three-mode Rain Protection.

The Smart Sleep gate is read from the app's RN bundle (APK 2.3.18.21):
``[y.HM432, y.HM434, y.HM442].includes(productKey) &&
compareVersion(firmwareVersion, "2.3.26.0") > 0``.  The Rain Protection gate is
provisional — its entry point is in the packed native code — and these tests pin
the shape of the gate rather than the threshold itself.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.mowing_modes import (
    RAIN_PROTECTION_DEFAULT_DELAY_HOURS,
    RAIN_PROTECTION_DELAY_HOURS,
    RainProtectionMode,
)
from pymammotion.utility import device_type as dt_mod
from pymammotion.utility.device_type import DeviceType, _version_greater_than

# HM432 / HM434 / HM442 — the three product keys the RN bundle gates on.
GATED = ["Luba-LA6ABCDE", "Luba-MB6ABCDE", "Luba-VA6ABCDE"]
UNGATED = ["Luba-VS6ABCDE", "Yuka-116ABCD", "Luba-MN6ABCDE", "RTK6ABCDEF"]

GATES = [DeviceType.supports_smart_sleep, DeviceType.supports_rain_protection_modes]


@pytest.mark.parametrize("gate", GATES)
@pytest.mark.parametrize("device_name", GATED)
@pytest.mark.parametrize(
    ("firmware", "supported"),
    [
        ("2.3.27.0", True),
        # The app compares ``> 0``, so the threshold build itself does not qualify.
        ("2.3.26.0", False),
        ("2.3.25.9", False),
        # These settings write to device storage; an unknown version must not qualify.
        ("", False),
    ],
)
def test_gate_follows_the_firmware_threshold(gate, device_name: str, firmware: str, supported: bool) -> None:
    assert gate(device_name, firmware) is supported


@pytest.mark.parametrize("gate", GATES)
@pytest.mark.parametrize("device_name", UNGATED)
def test_other_devices_never_qualify(gate, device_name: str) -> None:
    assert gate(device_name, "9.9.9.9") is False


def test_the_two_gates_are_independently_tunable(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rain threshold is a guess borrowed from the sleep gate, not the same fact.

    Sharing one constant would mean confirming or correcting one capability
    silently moved the other, so correcting the rain threshold must leave the
    confirmed sleep gate alone.
    """
    device, firmware = GATED[0], "2.3.27.0"
    assert DeviceType.supports_rain_protection_modes(device, firmware) is True

    monkeypatch.setattr(dt_mod, "_RAIN_PROTECTION_MODES_FIRMWARE", "9.9.9.9")

    assert DeviceType.supports_rain_protection_modes(device, firmware) is False
    assert DeviceType.supports_smart_sleep(device, firmware) is True


@pytest.mark.parametrize(
    ("version", "target", "expected"),
    [
        ("2.3.27.0", "2.3.26.0", True),
        ("2.3.26.1", "2.3.26.0", True),
        ("2.3.26.0", "2.3.26.0", False),
        ("2.3.26", "2.3.26.0", False),
        ("2.3.26.0 (dc75bb0b)", "2.3.26.0", False),
        ("", "2.3.26.0", False),
    ],
)
def test_version_greater_than(version: str, target: str, expected: bool) -> None:
    assert _version_greater_than(version, target) is expected


def test_rain_protection_mode_values() -> None:
    """Verbatim from the RN bundle's RainProtectionMode."""
    assert (RainProtectionMode.off, RainProtectionMode.smart, RainProtectionMode.sensor) == (0, 1, 2)


def test_rain_protection_delay_options() -> None:
    assert RAIN_PROTECTION_DELAY_HOURS == (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 24, 48)
    assert RAIN_PROTECTION_DEFAULT_DELAY_HOURS in RAIN_PROTECTION_DELAY_HOURS
