"""Equivalence tests for the data-driven from_value / value_of_str refactor.

from_value and value_of_str were rewritten from long if-chains to lookup tables
(_VALUE_TO_DEVICE_TYPE / _VALUE_OF_STR_RULES). These tests pin the behavior by
comparing the live implementations against reference reimplementations of the
original chains over a broad corpus of inputs, so any precedence/ordering drift
in the tables is caught.
"""

from __future__ import annotations

import pytest

from pymammotion.utility import device_type as dt_mod
from pymammotion.utility.device_type import (
    AliyunProductKey,
    LubaMEProductKey,
    DeviceType,
)

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
