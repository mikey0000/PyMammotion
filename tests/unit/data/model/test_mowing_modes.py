"""Tests for firmware-gated obstacle-detection options (DetectionStrategy.for_device).

Mirrors the app's isLuba2YukaNewFirmwareVersion: Luba 2 and the original Yuka
switched obstacle-detection options at firmware 1.12.0. Below that they expose
the old four-option touch UI (direct/slow/less/no touch); at/above it — or when
the version is unknown — they expose the new Off/Standard/Sensitive options.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.mowing_modes import DetectionStrategy
from pymammotion.utility.device_type import DeviceType, _version_less_than

OLD = [
    DetectionStrategy.direct_touch,
    DetectionStrategy.slow_touch,
    DetectionStrategy.less_touch,
    DetectionStrategy.no_touch,
]
NEW = [DetectionStrategy.direct_touch, DetectionStrategy.no_touch, DetectionStrategy.sensitive]
LUBA1 = [DetectionStrategy.direct_touch, DetectionStrategy.slow_touch, DetectionStrategy.less_touch]


@pytest.mark.parametrize(
    ("version", "target", "expected"),
    [
        ("1.11.8", "1.12.0", True),
        ("1.12.0", "1.12.0", False),
        ("1.15.1.2304", "1.12.0", False),
        ("1.12.0.466", "1.12.0", False),
        ("5.1.2.1540 (dc75bb0b)", "1.12.0", False),  # trailing hash ignored
        ("", "1.12.0", True),  # empty parses to () < threshold
    ],
)
def test_version_less_than(version: str, target: str, expected: bool) -> None:
    assert _version_less_than(version, target) is expected


@pytest.mark.parametrize(
    ("device_name", "firmware", "expected"),
    [
        ("Luba-VS", "1.11.8", OLD),  # Luba 2, old firmware
        ("Luba-VS", "1.12.0", NEW),  # Luba 2, threshold
        ("Luba-VS", "1.15.1.2304", NEW),  # Luba 2, new firmware
        ("Luba-VS", "", NEW),  # Luba 2, unknown firmware -> new (matches app)
        ("Yuka-", "1.10.0", OLD),  # original Yuka, old firmware
        ("Yuka-", "1.13.0", NEW),  # original Yuka, new firmware
        ("Luba", "", LUBA1),  # Luba 1, firmware-independent
        ("Luba", "1.20.0", LUBA1),
        ("Yuka-MN101", "1.0.0", NEW),  # Yuka mini -> always new
        ("Yuka-VP1", "1.0.0", NEW),  # Yuka pro -> always new
    ],
)
def test_for_device_firmware_gating(device_name: str, firmware: str, expected: list[DetectionStrategy]) -> None:
    assert DetectionStrategy.for_device(device_name, firmware) == expected


def test_for_device_defaults_to_new_when_firmware_omitted() -> None:
    """Backward-compatible call without a firmware version assumes new options."""
    assert DetectionStrategy.for_device("Luba-VS") == NEW


def test_uses_new_obstacle_detection_non_gated_device() -> None:
    """Devices that aren't Luba 2 / original Yuka always use the new options."""
    assert DeviceType.uses_new_obstacle_detection("Yuka-MN101", "1.0.0") is True
    assert DeviceType.uses_new_obstacle_detection("Luba-VS", "1.11.0") is False
