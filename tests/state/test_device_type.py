import pytest

from pymammotion.utility.device_type import DeviceType


# ---------------------------------------------------------------------------
# is_luba_pro — should return True for Luba 2 and above (excluding RTK/Spino)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("device_name", [
    "Luba-VS6ABCDE",   # LUBA_2  (Luba 2)
    "Luba-VP6ABCDE",   # LUBA_VP
    "Luba-MN6ABCDE",   # LUBA_MN
    "Luba-LD6ABCDE",   # LUBA_LD
    "Luba-VA6LZCPX",   # LUBA_VA (Luba 3 / HM442)
    "Luba-MD6ABCDE",   # LUBA_MD
    "Luba-LA6ABCDE",   # LUBA_LA
    "Luba-MB6ABCDE",   # LUBA_MB
])
def test_is_luba_pro_returns_true_for_luba2_and_above(device_name: str) -> None:
    assert DeviceType.is_luba_pro(device_name), (
        f"Expected is_luba_pro to return True for '{device_name}' "
        f"(resolved as {DeviceType.value_of_str(device_name)})"
    )


# ---------------------------------------------------------------------------
# is_luba_pro — should return False for Luba 1, RTK, and Spino
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("device_name", [
    "Luba6ABCDE",      # LUBA (Luba 1)
    "RTK6ABCDE",       # RTK
    "Spino6ABCDE",     # SPINO
])
def test_is_luba_pro_returns_false_for_non_pro_devices(device_name: str) -> None:
    assert not DeviceType.is_luba_pro(device_name), (
        f"Expected is_luba_pro to return False for '{device_name}' "
        f"(resolved as {DeviceType.value_of_str(device_name)})"
    )


# ---------------------------------------------------------------------------
# value_of_str — the generic "Yuka-" prefix (LUBA_YUKA, the original Yuka) is a
# substring of every more-specific "Yuka-XX" prefix, so LUBA_YUKA must be the
# LAST "Yuka-" rule in _VALUE_OF_STR_RULES — otherwise Yuka-MV/Yuka-ML/Yuka-VP
# etc. would all incorrectly resolve to LUBA_YUKA. Matches the APK's
# valueOfStrByDeviceName order (DeviceType.java in mammotion-2-3-8-201).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("device_name", "expected"), [
    ("Yuka-MV6ABCDE", DeviceType.YUKA_MINIV),
    ("Yuka-ML6ABCDE", DeviceType.YUKA_ML),
    ("Yuka-VP6ABCDE", DeviceType.YUKA_VP),
    ("Yuka-MN6ABCDE", DeviceType.YUKA_MINI),
    ("Yuka-YM6ABCDE", DeviceType.YUKA_MINI2),
    ("Yuka-6ABCDEF",  DeviceType.LUBA_YUKA),
])
def test_specific_yuka_prefix_not_shadowed_by_luba_yuka(
    device_name: str, expected: DeviceType
) -> None:
    """Regression: LUBA_YUKA ('Yuka-') must not shadow more specific Yuka- variants."""
    assert DeviceType.value_of_str(device_name) is expected