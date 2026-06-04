"""Unit tests for pymammotion.utility.device_type (DeviceType)."""
import pytest

from pymammotion.utility import device_type as dt_mod
from pymammotion.utility.device_type import (
    AliyunProductKey,
    DeviceType,
    LubaMEProductKey,
)


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


# ---------------------------------------------------------------------------
# is_yuka_mini — Yuka Mini, Yuka Mini 2, and Yuka ML are all treated as "mini"
# variants (callers in mower_api/device_config/readiness/mammotion gate behavior
# off this; ML belongs with the mini class, not the full Yuka class).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("device_name", [
    "Yuka-MN6ABCDE",  # YUKA_MINI
    "Yuka-YM6ABCDE",  # YUKA_MINI2
    "Yuka-ML6ABCDE",  # YUKA_ML
])
def test_is_yuka_mini_returns_true_for_mini_class(device_name: str) -> None:
    assert DeviceType.is_yuka_mini(device_name), (
        f"Expected is_yuka_mini True for '{device_name}' "
        f"(resolved as {DeviceType.value_of_str(device_name)})"
    )


@pytest.mark.parametrize("device_name", [
    "Yuka-6ABCDEF",   # LUBA_YUKA (original Yuka)
    "Yuka-VP6ABCDE",  # YUKA_VP
    "Yuka-MV6ABCDE",  # YUKA_MINIV
    "Luba-VS6ABCDE",  # LUBA_2
    "RTK6ABCDE",      # RTK
])
def test_is_yuka_mini_returns_false_for_non_mini(device_name: str) -> None:
    assert not DeviceType.is_yuka_mini(device_name), (
        f"Expected is_yuka_mini False for '{device_name}' "
        f"(resolved as {DeviceType.value_of_str(device_name)})"
    )


@pytest.mark.parametrize("device_name", [
    "Yuka-MN6ABCDE",  # YUKA_MINI
    "Yuka-YM6ABCDE",  # YUKA_MINI2
    "Yuka-ML6ABCDE",  # YUKA_ML
    "Yuka-MV6ABCDE",  # YUKA_MINIV
    "Yuka-VP6ABCDE",  # YUKA_VP
    "Luba-MN6ABCDE",  # LUBA_MN
    "Luba-VP6ABCDE",  # LUBA_VP
    "Luba-LD6ABCDE",  # LUBA_LD
])
def test_is_mini_or_x_series_returns_true(device_name: str) -> None:
    assert DeviceType.is_mini_or_x_series(device_name), (
        f"Expected is_mini_or_x_series True for '{device_name}' "
        f"(resolved as {DeviceType.value_of_str(device_name)})"
    )


@pytest.mark.parametrize("device_name", [
    "Yuka-6ABCDEF",   # LUBA_YUKA (original Yuka)
    "Luba-VS6ABCDE",  # LUBA_2
    "Luba6ABCDE",     # LUBA
    "RTK6ABCDE",      # RTK
    "Spino6ABCDE",    # SPINO
])
def test_is_mini_or_x_series_returns_false(device_name: str) -> None:
    assert not DeviceType.is_mini_or_x_series(device_name), (
        f"Expected is_mini_or_x_series False for '{device_name}' "
        f"(resolved as {DeviceType.value_of_str(device_name)})"
    )


# ===========================================================================
# from_value / value_of_str — data-driven lookup tables match the original if-chains
# ===========================================================================

# --- reference reimplementations of the ORIGINAL if-chains ------------------

_FROM_VALUE_REFERENCE = {
    0: DeviceType.RTK,
    1: DeviceType.LUBA,
    2: DeviceType.LUBA_2,
    3: DeviceType.LUBA_YUKA,
    4: DeviceType.YUKA_MINI,
    5: DeviceType.YUKA_MINI2,
    6: DeviceType.LUBA_VP,
    7: DeviceType.LUBA_MN,
    8: DeviceType.YUKA_VP,
    9: DeviceType.SPINO,
    10: DeviceType.RTK3A1,
    11: DeviceType.LUBA_LD,
    12: DeviceType.RTK3A0,
    13: DeviceType.RTK3A2,
    14: DeviceType.YUKA_MINIV,
    15: DeviceType.LUBA_VA,
    16: DeviceType.YUKA_ML,
    17: DeviceType.LUBA_MD,
    18: DeviceType.LUBA_LA,
    19: DeviceType.SWIMMINGPOOL_S1,
    20: DeviceType.SWIMMINGPOOL_E1,
    21: DeviceType.YUKA_MN100,
    22: DeviceType.RTKNB,
    23: DeviceType.LUBA_MB,
    24: DeviceType.CM900,
    25: DeviceType.YUKA_MN101,
    26: DeviceType.SWIMMINGPOOL_SP,
    27: DeviceType.SD_PX,
    28: DeviceType.LUBA_HM,
    29: DeviceType.LUBA_ME,
}


def _reference_value_of_str(device_name: str, product_key: str = "") -> DeviceType:
    """Verbatim transcription of the original value_of_str if-chain."""
    if not device_name and not product_key:
        return DeviceType.UNKNOWN
    try:
        substring = device_name[:3]
        substring2 = device_name[:7]
        if DeviceType.RTK.get_name() in substring or DeviceType.contain_rtk_product_key(product_key):
            return DeviceType.RTK
        if DeviceType.LUBA_2.get_name() in substring2 or DeviceType.contain_luba_2_product_key(product_key):
            return DeviceType.LUBA_2
        if DeviceType.LUBA_LD.get_name() in substring2:
            return DeviceType.LUBA_LD
        if DeviceType.LUBA_VP.get_name() in substring2:
            return DeviceType.LUBA_VP
        if DeviceType.LUBA_MN.get_name() in substring2:
            return DeviceType.LUBA_MN
        if DeviceType.YUKA_VP.get_name() in substring2:
            return DeviceType.YUKA_VP
        if DeviceType.YUKA_MINI.get_name() in substring2:
            return DeviceType.YUKA_MINI
        if DeviceType.YUKA_MINI2.get_name() in substring2:
            return DeviceType.YUKA_MINI2
        if DeviceType.RTK3A1.get_name() in substring2:
            return DeviceType.RTK3A1
        if DeviceType.RTK3A0.get_name() in substring2:
            return DeviceType.RTK3A0
        if DeviceType.RTK3A2.get_name() in substring2:
            return DeviceType.RTK3A2
        if DeviceType.YUKA_MINIV.get_name() in substring2:
            return DeviceType.YUKA_MINIV
        if DeviceType.LUBA_VA.get_name() in substring2:
            return DeviceType.LUBA_VA
        if DeviceType.YUKA_ML.get_name() in substring2:
            return DeviceType.YUKA_ML
        if DeviceType.LUBA_MD.get_name() in substring2:
            return DeviceType.LUBA_MD
        if DeviceType.LUBA_LA.get_name() in substring2:
            return DeviceType.LUBA_LA
        if DeviceType.LUBA_YUKA.get_name() in substring2:
            return DeviceType.LUBA_YUKA
        if DeviceType.SWIMMINGPOOL_S1.get_name() in device_name[:8]:
            return DeviceType.SWIMMINGPOOL_S1
        if DeviceType.SWIMMINGPOOL_E1.get_name() in device_name[:8]:
            return DeviceType.SWIMMINGPOOL_E1
        if DeviceType.SWIMMINGPOOL_SP.get_name() in device_name[:8]:
            return DeviceType.SWIMMINGPOOL_SP
        if DeviceType.SPINO.get_name() in substring2:
            return DeviceType.SPINO
        if DeviceType.YUKA_MN100.get_name() in substring2:
            return DeviceType.YUKA_MN100
        if DeviceType.YUKA_MN101.get_name() in substring2:
            return DeviceType.YUKA_MN101
        if DeviceType.RTKNB.get_name() in substring2:
            return DeviceType.RTKNB
        if DeviceType.LUBA_MB.get_name() in substring2:
            return DeviceType.LUBA_MB
        if DeviceType.CM900.get_name() in substring2:
            return DeviceType.CM900
        if DeviceType.SD_PX.get_name() in substring2:
            return DeviceType.SD_PX
        if DeviceType.LUBA_HM.get_name() in substring2:
            return DeviceType.LUBA_HM
        if DeviceType.LUBA_ME.get_name() in substring2 or DeviceType.contain_luba_me_product_key(product_key):
            return DeviceType.LUBA_ME
        if DeviceType.LUBA.get_name() in substring2 or DeviceType.contain_luba_product_key(product_key):
            return DeviceType.LUBA
    except (AttributeError, TypeError, IndexError):
        return DeviceType.UNKNOWN
    else:
        return DeviceType.UNKNOWN
    return DeviceType.UNKNOWN


# --- corpus -----------------------------------------------------------------


def _name_corpus() -> list[str]:
    names = ["", "X", "unknown-device", "Luba", "luba", "RTK", "NB"]
    for member in DeviceType:
        prefix = member.get_name()
        names.append(prefix)
        names.append(prefix + "-000000")  # realistic serial suffix
        names.append(prefix.lower())
    return names


# --- tests ------------------------------------------------------------------


@pytest.mark.parametrize("value", range(-5, 35))
def test_from_value_matches_reference(value: int) -> None:
    assert DeviceType.from_value(value) is _FROM_VALUE_REFERENCE.get(value, DeviceType.UNKNOWN)


def test_value_to_device_type_table_covers_all_ids() -> None:
    """Every real (non-UNKNOWN) device type id resolves back to itself."""
    for member in DeviceType:
        if member is DeviceType.UNKNOWN:
            continue
        assert DeviceType.from_value(member.get_value()) is member


@pytest.mark.parametrize("device_name", _name_corpus())
def test_value_of_str_name_matches_reference(device_name: str) -> None:
    assert DeviceType.value_of_str(device_name) is _reference_value_of_str(device_name)


@pytest.mark.parametrize("product_key", [*AliyunProductKey, *LubaMEProductKey, "unknown-key", ""])
def test_value_of_str_product_key_matches_reference(product_key: str) -> None:
    # empty device name forces resolution via the product key alone
    assert DeviceType.value_of_str("", product_key) is _reference_value_of_str("", product_key)


def test_value_of_str_name_and_product_key_combinations() -> None:
    """Cross product of a few names with a few product keys stays in lockstep."""
    names = ["", "Luba-VS1", "Luba", "Yuka-MN9", "RBSA1", "garbage"]
    keys = ["", AliyunProductKey[0], LubaMEProductKey[0], "unknown-key"]
    for name in names:
        for key in keys:
            assert DeviceType.value_of_str(name, key) is _reference_value_of_str(name, key)


def test_rules_table_is_well_formed() -> None:
    """Sanity: every rule's slice length is one the original used (3, 7, or 8)."""
    assert all(slice_len in (3, 7, 8) for _, slice_len, _ in dt_mod._VALUE_OF_STR_RULES)
