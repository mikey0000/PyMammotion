"""``DeviceHandle.supports_wifi_movement``: the one rule for manual movement over the cloud.

Models in the release note's family tables keep the firmware thresholds; every
other mower asks the server's function list for ``002.002``, the app's own gate.
Non-mowers never qualify.  The handle is real, so name, product key and state are
read the way the library reads them.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import Device, MowerDevice, PoolCleanerDevice, RTKBaseStationDevice
from pymammotion.data.model.function_codes import FunctionCodes
from pymammotion.device.handle import DeviceHandle
from tests._helpers import UNRECOGNISED_NAME

_REMOTE_DRIVE = "002.002"
_LUBA_3 = "Luba-VAME9R5S"
_LUBA_3_PRODUCT_KEY = "uY54W5rM8YH"
_YUKA_HS = "Yuka-HS6ABCDE"
_FIRMWARE = "1.2.3.4"


def _mower(firmware: str, *, listed_for: str | None = None, product_key: str = "") -> MowerDevice:
    """Return a mower at *firmware* whose stored function list has 002.002 for *listed_for*."""
    device = MowerDevice()
    device.device_firmwares.device_version = firmware
    if listed_for is not None:
        device.function_codes = FunctionCodes(
            product_key=product_key or "pk", product_version=listed_for, codes=[_REMOTE_DRIVE]
        )
    return device


def _handle(name: str, device: Device, product_key: str = "") -> DeviceHandle:
    return DeviceHandle("dev-1", name, device, product_key=product_key)


@pytest.mark.parametrize(("firmware", "expected"), [("2.3.30.39", False), ("2.3.31.69", True)])
@pytest.mark.parametrize("listed", [True, False], ids=["listed", "unlisted"])
def test_a_table_model_follows_its_firmware_threshold_whatever_the_server_lists(
    firmware: str, expected: bool, listed: bool
) -> None:
    """The user's Luba 3 is in the newer family, so the server list neither grants nor withholds it."""
    device = _mower(firmware, listed_for=firmware if listed else None, product_key=_LUBA_3_PRODUCT_KEY)

    assert _handle(_LUBA_3, device, _LUBA_3_PRODUCT_KEY).supports_wifi_movement() is expected


@pytest.mark.parametrize("name", [_YUKA_HS, UNRECOGNISED_NAME], ids=["yuka_hs", "unknown_mower"])
def test_an_untabled_mower_supports_it_when_the_server_lists_002_002_for_its_firmware(name: str) -> None:
    assert _handle(name, _mower(_FIRMWARE, listed_for=_FIRMWARE)).supports_wifi_movement() is True


def test_an_untabled_mower_does_not_support_it_without_002_002() -> None:
    assert _handle(_YUKA_HS, _mower(_FIRMWARE)).supports_wifi_movement() is False


def test_an_untabled_mower_does_not_trust_a_list_fetched_for_other_firmware() -> None:
    """After an OTA the stored list describes the old firmware until it is fetched again."""
    handle = _handle(_YUKA_HS, _mower("1.2.3.5", listed_for=_FIRMWARE))

    assert handle.supports_wifi_movement() is False


def test_the_answer_follows_firmware_that_changes_after_construction() -> None:
    """Re-read on every call: the handle's live state, not a value captured at setup."""
    device = _mower("", listed_for=_FIRMWARE)
    handle = _handle(_YUKA_HS, device)
    assert handle.supports_wifi_movement() is False

    device.device_firmwares.device_version = _FIRMWARE

    assert handle.supports_wifi_movement() is True


def _spino() -> PoolCleanerDevice:
    device = PoolCleanerDevice()
    device.device_firmwares.device_version = _FIRMWARE
    device.function_codes = FunctionCodes(product_key="pk", product_version=_FIRMWARE, codes=[_REMOTE_DRIVE])
    return device


def _rtk() -> RTKBaseStationDevice:
    device = RTKBaseStationDevice()
    device.device_firmwares.device_version = _FIRMWARE
    device.function_codes = FunctionCodes(product_key="pk", product_version=_FIRMWARE, codes=[_REMOTE_DRIVE])
    return device


@pytest.mark.parametrize(
    ("name", "build"), [("Spino-E1C36JT4", _spino), ("RTK6ABCDE", _rtk)], ids=["spino", "rtk"]
)
def test_a_non_mower_never_supports_it_even_with_002_002(name: str, build) -> None:
    device = build()
    assert device.supports_function_code(_REMOTE_DRIVE), "precondition: the server list alone would say yes"

    assert _handle(name, device).supports_wifi_movement() is False


@pytest.mark.parametrize(("firmware", "expected"), [("1.30.0.0", False), ("1.30.31.19", True)])
def test_a_table_model_known_only_by_product_key_follows_its_threshold(firmware: str, expected: bool) -> None:
    """The Luba 2 key makes an unrecognised name a table model, so 002.002 below the threshold grants nothing."""
    luba_2_product_key = "a1iMygIwxFC"
    device = _mower(firmware, listed_for=firmware, product_key=luba_2_product_key)

    assert _handle(UNRECOGNISED_NAME, device, luba_2_product_key).supports_wifi_movement() is expected
