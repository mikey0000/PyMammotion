"""Gates for the Smart Sleep switches and three-mode Rain Protection.

The Smart Sleep gate is read from the app's RN bundle (APK 2.3.18.21):
``[y.HM432, y.HM434, y.HM442].includes(productKey) &&
compareVersion(firmwareVersion, "2.3.26.0") > 0``.  Rain Protection's entry point
is packed native code, so its gate is the X5 family the app's ``x5*`` entry
points are named for, confirmed at runtime by the device (a RAINPRO reply or
self-check 34).
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.mowing_modes import (
    RAIN_PROTECTION_DEFAULT_DELAY_HOURS,
    RAIN_PROTECTION_DELAY_HOURS,
    RainProtectionMode,
)
from pymammotion.utility.device_type import DeviceType, _version_greater_than

# HM432 / HM434 / HM442 — the three product keys the RN bundle gates on.
GATED = ["Luba-LA6ABCDE", "Luba-MB6ABCDE", "Luba-VA6ABCDE"]
UNGATED = ["Luba-VS6ABCDE", "Yuka-116ABCD", "Luba-MN6ABCDE", "RTK6ABCDEF"]


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
def test_smart_sleep_follows_the_firmware_threshold(device_name: str, firmware: str, supported: bool) -> None:
    assert DeviceType.supports_smart_sleep(device_name, firmware) is supported


@pytest.mark.parametrize("device_name", UNGATED)
def test_other_devices_never_get_smart_sleep(device_name: str) -> None:
    assert DeviceType.supports_smart_sleep(device_name, "9.9.9.9") is False


#: The user's Luba 3 (LUBA_VA, fw 2.3.30.39), which has reported self-check 34.
LUBA_3 = "Luba-VAME9R5S"
#: The app's ``isX5DeviceTyp`` family, one name per model.
X5 = [LUBA_3, "Luba-LA6ABCDE", "Luba-MB6ABCDE", "Luba-HM6ABCDE", "Yuka-MV6ABCDE", "Ezy-VT6ABCDE"]
#: Not X5: Luba 1, the user's Luba 2 (no rain settings), Luba 2 AWD X, the original Yuka, Yuka Mini, a pool robot.
NOT_X5 = ["Luba-QXABCDEF", "Luba-VS563L6H", "Luba-MNABCDEF", "Yuka-116ABCD", "Yuka-MN6ABCDE", "Spino-S1ABCDE"]


@pytest.mark.parametrize("device_name", X5)
def test_an_x5_mower_qualifies_once_the_device_proved_support(device_name: str) -> None:
    assert DeviceType.supports_rain_protection_modes(device_name, probed=True) is True


@pytest.mark.parametrize("device_name", X5)
@pytest.mark.parametrize("probed", [None, False], ids=["never-probed", "probe-failed"])
def test_an_x5_mower_waits_for_the_device(device_name: str, probed: bool | None) -> None:
    """The model list is only a precondition: which firmware has the feature is unknown."""
    assert DeviceType.supports_rain_protection_modes(device_name, probed=probed) is False


@pytest.mark.parametrize("device_name", NOT_X5)
def test_other_mowers_never_qualify_even_if_something_claimed_support(device_name: str) -> None:
    assert DeviceType.supports_rain_protection_modes(device_name, probed=True) is False


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
