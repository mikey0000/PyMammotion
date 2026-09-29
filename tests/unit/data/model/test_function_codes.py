"""The stored function set, and the (product key, firmware) pair it answers for.

The app caches the list per ``(productKey, productVersion)`` and treats a lookup
at any other firmware as a miss, so an answer fetched before an OTA must not
keep gating features after it.
"""

from __future__ import annotations

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.function_codes import FunctionCodes

PRODUCT_KEY = "a1BmXWlsdbA"
FIRMWARE = "1.12.3.10"


def _mower(firmware: str = FIRMWARE, codes: FunctionCodes | None = None) -> MowerDevice:
    device = MowerDevice(name="Luba-VSLKJX")
    device.device_firmwares.device_version = firmware
    if codes is not None:
        device.function_codes = codes
    return device


def test_a_fetched_set_is_current_only_for_its_own_key_and_firmware() -> None:
    codes = FunctionCodes(product_key=PRODUCT_KEY, product_version=FIRMWARE, codes=["002.002"])

    assert codes.is_current_for(PRODUCT_KEY, FIRMWARE)
    assert not codes.is_current_for(PRODUCT_KEY, "1.12.4.0")
    assert not codes.is_current_for("other", FIRMWARE)


def test_an_empty_set_fetched_for_a_firmware_is_still_current() -> None:
    """A firmware that publishes no functions has been answered; refetching it would just repeat the answer."""
    assert FunctionCodes(product_key=PRODUCT_KEY, product_version=FIRMWARE).is_current_for(PRODUCT_KEY, FIRMWARE)


def test_nothing_fetched_is_never_current() -> None:
    assert not FunctionCodes().is_current_for(PRODUCT_KEY, FIRMWARE)
    assert not FunctionCodes().is_current_for("", "")


def test_the_device_supports_a_code_listed_for_its_firmware() -> None:
    device = _mower(codes=FunctionCodes(product_key=PRODUCT_KEY, product_version=FIRMWARE, codes=["002.002"]))

    assert device.supports_function_code("002.002")
    assert not device.supports_function_code("001.006.001")


def test_a_set_fetched_for_older_firmware_supports_nothing() -> None:
    """``FunctionsConfigFacade.hasFunctionCode`` answers false on a cache miss for the current version."""
    stale = FunctionCodes(product_key=PRODUCT_KEY, product_version="1.11.0.0", codes=["002.002"])

    assert not _mower(codes=stale).supports_function_code("002.002")


def test_a_device_with_unknown_firmware_supports_nothing() -> None:
    device = _mower(firmware="", codes=FunctionCodes(product_key=PRODUCT_KEY, product_version="", codes=["002.002"]))

    assert not device.supports_function_code("002.002")


def test_a_device_saved_before_function_codes_existed_still_restores() -> None:
    """HA restores ``MowerDevice.from_dict(stored)``; a store predating the field must load, not drop the device."""
    stored = _mower().to_dict()
    del stored["function_codes"]

    restored = MowerDevice.from_dict(stored)

    assert restored.function_codes == FunctionCodes()
    assert restored.device_firmwares.device_version == FIRMWARE


def test_the_function_set_round_trips_through_to_dict() -> None:
    device = _mower(codes=FunctionCodes(product_key=PRODUCT_KEY, product_version=FIRMWARE, codes=["003.001"]))

    assert MowerDevice.from_dict(device.to_dict()).supports_function_code("003.001")
