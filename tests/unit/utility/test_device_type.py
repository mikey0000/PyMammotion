"""Unit tests for pymammotion.utility.device_type (DeviceType)."""
import pytest

from pymammotion.utility import device_type as dt_mod
from pymammotion.utility.device_type import (
    AliyunProductKey,
    DeviceType,
    LubaMEProductKey,
    SdPxProductKey,
    SwimmingPoolE1ProductKey,
    SwimmingPoolProductKey,
    SwimmingPoolSPProductKey,
)


# is_luba_pro — should return True for Luba 2 and above (excluding RTK/Spino)

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


# is_luba_pro — should return False for Luba 1, RTK, and Spino

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


# value_of_str — the generic "Yuka-" prefix (LUBA_YUKA, the original Yuka) is a
# substring of every more-specific "Yuka-XX" prefix, so LUBA_YUKA must be the
# LAST "Yuka-" rule in _VALUE_OF_STR_RULES — otherwise Yuka-MV/Yuka-ML/Yuka-VP
# etc. would all incorrectly resolve to LUBA_YUKA. Matches the APK's
# valueOfStrByDeviceName order (DeviceType.java in mammotion-2-3-8-201).

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


# is_yuka_mini — Yuka Mini, Yuka Mini 2, and Yuka ML are all treated as "mini"
# variants (callers in mower_api/device_config/readiness/mammotion gate behavior
# off this; ML belongs with the mini class, not the full Yuka class).

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
    "Luba-LA6ABCDE",  # LUBA_LA  — LUBA mini AWD 360 LIDAR (HM432)
    "Luba-MB6ABCDE",  # LUBA_MB  — LUBA mini Vision 800 (HM434)
    "Luba-MD6ABCDE",  # LUBA_MD  — HM433, the remaining member of the mini block
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


# from_value / value_of_str — data-driven lookup tables match the original if-chains

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
    """Transcription of the original value_of_str if-chain, as a refactor safety net.

    One branch deviates on purpose — see the SWIMMINGPOOL_S1 comment below.
    """
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
        # Deliberate deviation from the original chain: the APK returns SWIMMINGPOOL_SP
        # for an S1 *name* (``if (str.contains(SWIMMINGPOOL_S1.product_name)) return
        # SWIMMINGPOOL_SP;``), so the reference tracks the APK here rather than the bug
        # it was transcribed from.
        if DeviceType.SWIMMINGPOOL_S1.get_name() in device_name[:8]:
            return DeviceType.SWIMMINGPOOL_SP
        if DeviceType.SWIMMINGPOOL_E1.get_name() in device_name[:8] or DeviceType.contain_swimming_pool_e1_product_key(
            product_key
        ):
            return DeviceType.SWIMMINGPOOL_E1
        if any(
            prefix in device_name[:8] for prefix in DeviceType.SWIMMINGPOOL_SP.get_name().split(",")
        ) or DeviceType.contain_swimming_pool_sp_product_key(product_key):
            return DeviceType.SWIMMINGPOOL_SP
        if DeviceType.SPINO.get_name() in substring2 or DeviceType.contain_swimming_pool_product_key(product_key):
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
        if DeviceType.SD_PX.get_name() in substring2 or DeviceType.contain_sd_px_product_key(product_key):
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
        # A member may claim several prefixes (SWIMMINGPOOL_SP: "Spino-SP,Spino-S1");
        # the joined string is not a device name, so exercise each prefix on its own.
        for prefix in member.get_name().split(","):
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


@pytest.mark.parametrize(
    "product_key",
    [
        *AliyunProductKey,
        *LubaMEProductKey,
        *SwimmingPoolProductKey,
        *SwimmingPoolE1ProductKey,
        *SwimmingPoolSPProductKey,
        *SdPxProductKey,
        "unknown-key",
        "",
    ],
)
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


@pytest.mark.parametrize(
    ("product_key", "expected"),
    [
        (SwimmingPoolProductKey[0], DeviceType.SPINO),
        (SwimmingPoolE1ProductKey[0], DeviceType.SWIMMINGPOOL_E1),
        (SwimmingPoolSPProductKey[0], DeviceType.SWIMMINGPOOL_SP),
        (SwimmingPoolSPProductKey[1], DeviceType.SWIMMINGPOOL_SP),
        (SdPxProductKey[0], DeviceType.SD_PX),
        (SdPxProductKey[1], DeviceType.SD_PX),
    ],
)
def test_pool_product_key_identifies_the_device_without_a_name(product_key: str, expected: DeviceType) -> None:
    """A pool device whose name the prefix table does not cover is still classified."""
    assert DeviceType.value_of_str("", product_key) is expected
    assert DeviceType.is_swimming_pool("", product_key) is True
    assert DeviceType.is_rtk("", product_key) is False
    assert DeviceType.is_luba_pro("", product_key) is False


def test_pool_product_keys_are_all_mammotion_iot() -> None:
    """None of the pool keys are on the Aliyun platform, so they must route to Mammotion MQTT."""
    for key in (*SwimmingPoolProductKey, *SwimmingPoolE1ProductKey, *SwimmingPoolSPProductKey, *SdPxProductKey):
        assert DeviceType.is_aliyun_product_key(key) is False
        assert DeviceType.is_mammotion_iot_product_key(key) is True


def test_rules_table_is_well_formed() -> None:
    """Sanity: every rule's slice length is one the original used (3, 7, or 8)."""
    assert all(slice_len in (3, 7, 8) for _, slice_len, _ in dt_mod._VALUE_OF_STR_RULES)


@pytest.mark.regression
@pytest.mark.parametrize(
    ("device_name", "model"),
    [("Luba-MB6ABCDE", "HM434"), ("Luba-MD6ABCDE", "HM433")],
)
def test_the_whole_luba_mini_block_counts_as_mini(device_name: str, model: str) -> None:
    """The Luba minis are the ``HM43x`` block, and two of them were left out.

    ``HM430`` LUBA_MN, ``HM431`` LUBA_LD, ``HM432`` LUBA_LA, ``HM433`` LUBA_MD and
    ``HM434`` LUBA_MB — the cloud product list names MB "LUBA mini Vision 800" and LA
    "LUBA mini AWD 360 LIDAR", so membership follows the block, not the APK's
    ``is2025X3DeviceType``, which is a 2025-generation grouping: it drops LUBA_LA and
    picks up YUKA_VP ("YUKA 1000", MN241), which is no kind of mini.
    """
    assert DeviceType.is_mini_or_x_series(device_name), (
        f"{model} is part of the Luba mini block but {device_name} was not counted"
    )


@pytest.mark.regression
def test_a_spino_s1_name_resolves_to_the_pc210_type() -> None:
    """The APK maps the S1 *name* to SWIMMINGPOOL_SP, not SWIMMINGPOOL_S1.

    ``DeviceType.java``: ``if (str.contains(SWIMMINGPOOL_S1.product_name)) return
    SWIMMINGPOOL_SP;`` — and its SP entry claims both prefixes, ``"Spino-SP,Spino-S1"``.
    We resolved the name to SWIMMINGPOOL_S1 (PC200), a different generation.
    """
    assert DeviceType.value_of_str("Spino-S1ABCDEF") is DeviceType.SWIMMINGPOOL_SP
    assert DeviceType.value_of_str("Spino-SPABCDE") is DeviceType.SWIMMINGPOOL_SP
    assert DeviceType.is_swimming_pool("Spino-S1ABCDEF"), "still a pool cleaner either way"


def test_a_rule_can_claim_several_name_prefixes() -> None:
    """Comma-separated prefixes, as the APK's enum writes them.

    Without splitting, the whole ``"Spino-SP,Spino-S1"`` string is compared as one
    prefix, matches nothing, and a Spino-SP falls through to the generic SPINO.
    """
    assert "," in DeviceType.SWIMMINGPOOL_SP.get_name()
    assert DeviceType.value_of_str("Spino-E1ABCDE") is DeviceType.SWIMMINGPOOL_E1
    assert DeviceType.value_of_str("SpinoABCDEF") is DeviceType.SPINO


@pytest.mark.parametrize(
    ("device_name", "expected"),
    [
        ("Luba-MB6ABCDE", True),   # LUBA mini Vision 800
        ("Luba-LA6ABCDE", True),   # LUBA mini AWD 360 LIDAR
        ("Yuka-MV6ABCDE", True),   # fill light yes; the night-light row hides for MV
        ("Yuka-VP6ABCDE", False),  # YUKA 1000 — in our mini/X grouping but has no fill light
        ("Luba-VS6ABCDE", False),  # LUBA 2
    ],
)
def test_is_support_fill_light_follows_the_apk(device_name: str, expected: bool) -> None:
    """The gate the APK's settings screen actually uses for the light rows."""
    assert DeviceType.is_support_fill_light(device_name) is expected


@pytest.mark.parametrize(
    ("device_name", "expected"),
    [("Luba-MB6ABCDE", True), ("Yuka-VP6ABCDE", True), ("Luba-VS6ABCDE", False), ("Luba6ABCDEF", False)],
)
def test_is_support_blade_speed_follows_the_apk(device_name: str, expected: bool) -> None:
    """The gate for the cutter-mode setting."""
    assert DeviceType.is_support_blade_speed(device_name) is expected


@pytest.mark.parametrize(
    ("device_name", "firmware", "expected"),
    [
        ("Luba-VS6ABCDE", "1.11.511.631", False),  # issue #853: Luba 2 below 1.13 hides it
        ("Luba-VS6ABCDE", "1.12.9.999", False),
        ("Luba-VS6ABCDE", "1.13.0.1", True),
        ("Luba-VS6ABCDE", "2.0.0.0", True),
        ("Luba-VS6ABCDE", "", True),  # unknown version: shown, as in the app
        ("Yuka-VP6ABCDE", "1.15.0.0", True),
        ("Luba-1ABCDEF", "1.15.0.0", False),  # Luba 1 never
        ("Yuka-MV6ABCDE", "1.15.0.0", False),  # 231-family parameter set
        ("Luba-MB6ABCDE", "1.15.0.0", False),
        ("Spino-E1ABCD", "1.15.0.0", False),
    ],
)
def test_supports_wildlife_safety_mirrors_the_app_gate(device_name: str, firmware: str, expected: bool) -> None:
    """The app hides animal protection below firmware 1.13 and for Luba 1, pools and the 231 family."""
    assert DeviceType.supports_wildlife_safety(device_name, firmware) is expected


@pytest.mark.parametrize(
    ("device_name", "firmware", "expected"),
    [
        ("Luba-VS6ABCDE", "2.1.1.5", True),  # issue #857: threshold itself passes
        ("Luba-VS6ABCDE", "2.1.1.4", False),
        ("Luba-VS6ABCDE", "2.0.9.999", False),
        ("Luba-VS6ABCDE", "2.3.26.1", True),
        ("Luba-VS6ABCDE", "3.0", True),
        ("Luba-VS6ABCDE", "", False),  # unknown version: the app hides the page
        ("Luba-VS6ABCDE", "unknown", False),
        ("Yuka-VP6ABCDE", "2.2.0.0", True),
        ("Luba-1ABCDEF", "1.15.0.0", False),  # Luba 1 firmware is below 2.1.1.5
        ("Spino-E1ABCD", "2.5.0.0", False),  # pools never
    ],
)
def test_supports_charge_limit_mirrors_the_app_gate(device_name: str, firmware: str, expected: bool) -> None:
    """The battery page needs firmware 2.1.1.5 or newer and is never shown for pool robots."""
    assert DeviceType.supports_charge_limit(device_name, firmware) is expected



@pytest.mark.parametrize(
    ("device_name", "firmware", "expected"),
    [
        ("Luba-VA6ABCDE", "2.3.28.1", True),  # issue #860: threshold itself passes
        ("Luba-VA6ABCDE", "2.3.28.0", False),
        ("Luba-VA6ABCDE", "2.3.29.0", True),
        ("Luba-VA6ABCDE", "2.4", True),
        ("Luba-VA6ABCDE", "", False),  # unknown version: never guess on a write
        ("Luba-VA6ABCDE", "unknown", False),
        ("Luba-LA6ABCDE", "2.3.28.1", True),  # HM432: interior routes only, still offered
        ("Luba-MB6ABCDE", "2.3.28.1", True),  # HM434: same
        ("Yuka-MV6ABCDE", "2.3.28.1", True),
        ("Yuka-ML6ABCDE", "2.3.28.1", True),
        ("Luba-VS6ABCDE", "2.3.28.1", False),  # Luba 2 is not on Mammotion's list
        ("Luba-1ABCDEF", "2.3.28.1", False),
        ("Spino-E1ABCD", "2.3.28.1", False),
    ],
)
def test_supports_auto_change_direction_mirrors_the_app_gate(device_name: str, firmware: str, expected: bool) -> None:
    """Auto-reverse mowing direction needs firmware 2.3.28.1 and one of the listed models."""
    assert DeviceType.supports_auto_change_direction(device_name, firmware) is expected
