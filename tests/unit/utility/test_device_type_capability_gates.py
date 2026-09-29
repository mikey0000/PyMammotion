"""``DeviceType`` capability gates: each mirrors the app's own row or feature condition."""

import pytest

from pymammotion.utility.device_type import DeviceType
from tests._helpers import LUBA1_PRODUCT_KEY, UNRECOGNISED_NAME


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
        # Luba 1, Luba 2 (incl. the Luba 2 Pro/X) and the original Yuka never offer it (user-confirmed).
        ("Luba-VS6ABCDE", "2.3.28.1", False),
        ("Luba-VS6ABCDE", "9.9.9.9", False),
        ("Luba-VP6ABCDE", "2.3.28.1", False),
        ("Yuka-6ABCDEF", "2.3.28.1", False),
        ("Luba-1ABCDEF", "2.3.28.1", False),
        ("Yuka-VP6ABCDE", "2.3.28.1", True),  # Yuka Plus (MN241), not the original Yuka
        ("Yuka-MN6ABCDE", "2.3.28.1", True),
        ("Yuka-YM6ABCDE", "2.3.28.1", True),  # YUKA_MINI2
        ("Yuka-HS6ABCDE", "2.3.28.1", True),
        ("Luba-MN6ABCDE", "2.3.28.1", True),
        ("Luba-LS6ABCDE", "2.3.28.1", True),
        ("Luba-MS6ABCDE", "2.3.28.1", True),
        ("Ezy-VT6ABCDE", "2.3.28.1", True),
        ("Luba-HM6ABCDE", "2.3.28.1", True),
        ("Luba-ME6ABCDE", "2.3.28.1", True),
        ("Luba-SP6ABCDE", "2.3.28.1", True),
        ("Luba-TR6ABCDE", "2.3.28.1", True),
        ("Kumar-MK6ABCDE", "2.3.28.1", True),  # CM900
        ("Maston-R6ABCDE", "2.3.28.1", True),  # CM901
        ("Spino-E1ABCD", "2.3.28.1", False),  # pool robots do not mow
        ("Spino-H1ABCD", "2.3.28.1", False),
        ("RTK6ABCDE", "2.3.28.1", False),  # base stations do not mow
        ("RBSA16ABCDE", "2.3.28.1", False),
        ("garbage", "2.3.28.1", False),  # an unrecognised device is not known to be a mower
    ],
)
def test_supports_auto_change_direction_mirrors_the_app_gate(device_name: str, firmware: str, expected: bool) -> None:
    """Auto-reverse mowing direction: a mower on firmware 2.3.28.1 or newer, except Luba 1/Luba 2/original Yuka.

    The app has no native model list; the server capability code (never fetched here) filters those three out.
    """
    assert DeviceType.supports_auto_change_direction(device_name, firmware) is expected


def test_supports_auto_change_direction_excludes_a_luba_1_known_only_by_product_key() -> None:
    """The gate resolves through the product key too, so a Luba 1 without a known name is still excluded."""
    assert DeviceType.value_of_str(UNRECOGNISED_NAME, LUBA1_PRODUCT_KEY) is DeviceType.LUBA
    assert DeviceType.supports_auto_change_direction(UNRECOGNISED_NAME, "2.3.28.1", LUBA1_PRODUCT_KEY) is False


_POOLS = {
    DeviceType.SPINO,
    DeviceType.SWIMMINGPOOL_S1,
    DeviceType.SWIMMINGPOOL_E1,
    DeviceType.SWIMMINGPOOL_SP,
    DeviceType.SD_PX,
    DeviceType.SPINO_H1,
}
_BASE_STATIONS = {DeviceType.RTK, DeviceType.RTK3A0, DeviceType.RTK3A1, DeviceType.RTK3A2, DeviceType.RTKNB}


def _a_name_for(member: DeviceType) -> str:
    """A device name that resolves to ``member``, or "" when the member resolves by product key alone."""
    for prefix in member.get_name().split(","):
        if DeviceType.value_of_str(prefix + "6ABCDE") is member:
            return prefix + "6ABCDE"
    return ""


@pytest.mark.parametrize(
    "member",
    [member for member in DeviceType if member is not DeviceType.UNKNOWN and _a_name_for(member)],
    ids=lambda member: member.name,
)
def test_supports_continue_last_job_is_offered_on_every_mower_and_nothing_else(member: DeviceType) -> None:
    """The app's resume entry points exist only on mower screens and compare no model list or firmware."""
    expected = member not in _POOLS and member not in _BASE_STATIONS
    assert DeviceType.supports_continue_last_job(_a_name_for(member)) is expected


def test_supports_continue_last_job_refuses_an_unrecognised_device() -> None:
    assert DeviceType.supports_continue_last_job("garbage") is False


@pytest.mark.parametrize("firmware", ["", "unknown", "1.0.0", "9.9.9.9"])
def test_supports_continue_last_job_does_not_gate_on_firmware(firmware: str) -> None:
    """Neither the RN report screen nor the native start path compares a firmware version."""
    assert DeviceType.supports_continue_last_job("Luba-VA6ABCDE", firmware) is True


@pytest.mark.parametrize(
    ("device_name", "expected"),
    [
        ("Luba-VA6ABCDE", True),
        ("Luba-HM6ABCDE", True),
        ("Luba-MH6ABCDE", True),  # LUBA_HM's second prefix
        ("Luba-ME6ABCDE", True),
        ("Luba-TR6ABCDE", True),
        ("Luba-MB6ABCDE", True),
        ("Luba-LA6ABCDE", True),
        ("Luba-SP6ABCDE", True),
        ("Yuka-MV6ABCDE", True),
        ("Yuka-ML6ABCDE", True),
        ("Kumar-MK6ABCDE", True),  # CM900
        ("Maston-R6ABCDE", True),  # CM901
        ("Luba-LS6ABCDE", False),  # the SE variants of LA and MB are not on the list
        ("Luba-MS6ABCDE", False),
        ("Luba-VS6ABCDE", False),  # Luba 2
        ("Luba-1ABCDEF", False),
        ("Yuka-VP6ABCDE", False),
        ("Spino-E1ABCD", False),
    ],
)
def test_supports_ride_boundary_distance_mirrors_the_app_gate(device_name: str, expected: bool) -> None:
    """The app's edge-coverage row (2.3.20.30 SettingOptionsView.refreshData) lists these models, no firmware."""
    assert DeviceType.supports_ride_boundary_distance(device_name) is expected


@pytest.mark.parametrize(
    ("device_name", "edge_mode", "distance", "expected"),
    [
        ("Luba-VA6ABCDE", 1, 0.5, 0.5),
        ("Luba-VA6ABCDE", 2, 0.2, 0.2),  # any distance passes through unchanged
        ("Luba-VA6ABCDE", 0, 0.5, 0.0),  # no border laps: no edge to ride on
        ("Luba-VS6ABCDE", 1, 0.5, 0.0),  # model the app never offers the row on
    ],
)
def test_ride_boundary_distance_to_send_applies_the_model_and_border_lap_gate(
    device_name: str, edge_mode: int, distance: float, expected: float
) -> None:
    """The one rule both routes and schedules send through."""
    assert DeviceType.ride_boundary_distance_to_send(device_name, edge_mode, distance) == expected


_OLDER = "older"  # needs 1.30.31.19
_NEWER = "newer"  # needs 2.3.31.69

#: Every member's Wi-Fi-movement family, from the release note's model lists mapped through the
#: app's product names (``DeviceMultimodelHelper.getExtMod``).  None: not listed, or ambiguous.
_WIFI_MOVEMENT_FAMILY: dict[DeviceType, str | None] = {
    DeviceType.UNKNOWN: None,
    DeviceType.RTK: None,
    DeviceType.LUBA: None,  # Luba 1 is not in either list
    DeviceType.LUBA_2: _OLDER,  # "LUBA 2 AWD"
    DeviceType.LUBA_YUKA: _OLDER,  # "YUKA"
    DeviceType.YUKA_MINI: _OLDER,  # "YUKA mini"
    DeviceType.YUKA_MINI2: _OLDER,  # MN230 like YUKA_MINI; the app's isYuKaMini() names it "YUKA mini"
    DeviceType.LUBA_VP: _OLDER,  # "LUBA 2 AWD 3000X" (LUBA 2X)
    DeviceType.LUBA_MN: _OLDER,  # "LUBA mini AWD"
    DeviceType.YUKA_VP: _OLDER,  # "YUKA 1000/2000/3000", app label "YUKA(2025)"
    DeviceType.SPINO: None,
    DeviceType.RTK3A1: None,
    DeviceType.LUBA_LD: _OLDER,  # "LUBA mini AWD LiDAR"
    DeviceType.RTK3A0: None,
    DeviceType.RTK3A2: None,
    DeviceType.YUKA_MINIV: _NEWER,  # "YUKA mini 2 Vision"; the app's is231SimilarParameterSettings()
    DeviceType.LUBA_VA: _NEWER,  # "LUBA 3 AWD"
    DeviceType.YUKA_ML: _NEWER,  # "YUKA mini 2 LiDAR"
    DeviceType.LUBA_MD: None,  # HM433, no product name
    DeviceType.LUBA_LA: _NEWER,  # "LUBA mini 2 AWD 1500"
    DeviceType.SWIMMINGPOOL_S1: None,
    DeviceType.SWIMMINGPOOL_E1: None,
    DeviceType.YUKA_MN100: None,  # Ezymow
    DeviceType.RTKNB: None,
    DeviceType.LUBA_MB: _NEWER,  # "LUBA mini 2 AWD 1000"
    DeviceType.CM900: None,
    DeviceType.YUKA_MN101: None,  # Ezymow
    DeviceType.SWIMMINGPOOL_SP: None,
    DeviceType.SD_PX: None,
    DeviceType.LUBA_HM: None,  # "LUBA 4 AWD"
    DeviceType.LUBA_ME: None,  # "LUBA 4 Pro AWD"
    DeviceType.LUBA_SP: None,  # "Luba mini 3 AWD"
    DeviceType.LUBA_TR: None,  # "Taru"
    DeviceType.LUBA_LS: _NEWER,  # "LUBA mini 2 AWD 1500" (SE)
    DeviceType.LUBA_MS: _NEWER,  # "LUBA mini 2 Vision 1000" (SE)
    DeviceType.CM901: None,
    DeviceType.YUKA_HS: None,  # ambiguous: "YUKA mini Lite 350"
    DeviceType.SPINO_H1: None,
}


def test_wifi_movement_family_table_names_every_device_type() -> None:
    """A new member must be placed in a family (or deliberately left out) before this passes."""
    assert set(_WIFI_MOVEMENT_FAMILY) == set(DeviceType)


@pytest.mark.parametrize(
    "member",
    [member for member in DeviceType if _a_name_for(member)],
    ids=lambda member: member.name,
)
def test_supports_wifi_movement_uses_each_member_s_family_threshold(member: DeviceType) -> None:
    """At 1.30.31.19 only the older family passes; at 2.3.31.69 both families do; nothing else ever does."""
    family = _WIFI_MOVEMENT_FAMILY[member]
    name = _a_name_for(member)
    assert DeviceType.supports_wifi_movement(name, "1.30.31.19") is (family == _OLDER)
    assert DeviceType.supports_wifi_movement(name, "2.3.31.69") is (family is not None)


@pytest.mark.parametrize(
    ("firmware", "expected"),
    [
        ("1.30.31.18", False),
        ("1.30.31.19", True),
        ("1.30.32.0", True),
        ("1.31.0.0", True),
        ("1.30.9.0", False),  # numeric, not string, compare
        ("1.15.20.2303", False),
        ("", False),  # unknown version: never guess
        ("unknown", False),
    ],
)
def test_supports_wifi_movement_older_family_needs_1_30_31_19(firmware: str, expected: bool) -> None:
    assert DeviceType.supports_wifi_movement("Luba-VS6ABCDE", firmware) is expected
    assert DeviceType.supports_wifi_movement("Yuka-6ABCDEF", firmware) is expected


@pytest.mark.parametrize(
    ("firmware", "expected"),
    [
        ("2.3.31.68", False),
        ("2.3.31.69", True),
        ("2.3.32.0", True),
        ("2.4.0.0", True),
        ("2.3.30.39", False),
        ("2.3.9.0", False),  # numeric, not string, compare
        ("1.30.31.19", False),  # the older family's threshold is not enough here
        ("", False),
        ("unknown", False),
    ],
)
def test_supports_wifi_movement_newer_family_needs_2_3_31_69(firmware: str, expected: bool) -> None:
    assert DeviceType.supports_wifi_movement("Luba-VA6ABCDE", firmware) is expected
    assert DeviceType.supports_wifi_movement("Yuka-ML6ABCDE", firmware) is expected


@pytest.mark.parametrize(("firmware", "expected"), [("2.3.30.39", False), ("2.3.31.69", True)])
def test_supports_wifi_movement_for_the_user_s_luba_3(firmware: str, expected: bool) -> None:
    """``Luba-VAME9R5S`` reports 2.3.30.39 today, so it stays opt-in until it updates."""
    assert DeviceType.supports_wifi_movement("Luba-VAME9R5S", firmware) is expected


def test_supports_wifi_movement_older_family_passes_on_a_2_x_version() -> None:
    """Pinned, not a goal: an older model never reports 2.x, and 2.3.31.69 >= 1.30.31.19 numerically."""
    assert DeviceType.supports_wifi_movement("Luba-VS6ABCDE", "2.3.31.69") is True


def test_supports_wifi_movement_resolves_through_the_product_key() -> None:
    """A Luba 2 known only by its product key is in the older family; the key alone makes it True."""
    luba_2_product_key = "a1iMygIwxFC"

    assert DeviceType.supports_wifi_movement(UNRECOGNISED_NAME, "1.30.31.19") is False
    assert DeviceType.supports_wifi_movement(UNRECOGNISED_NAME, "1.30.31.19", luba_2_product_key) is True


def test_supports_wifi_movement_excludes_a_luba_1_known_only_by_product_key() -> None:
    assert DeviceType.supports_wifi_movement(UNRECOGNISED_NAME, "2.3.31.69", LUBA1_PRODUCT_KEY) is False


@pytest.mark.parametrize(
    "member",
    [member for member in DeviceType if _a_name_for(member)],
    ids=lambda member: member.name,
)
def test_has_wifi_movement_threshold_is_true_exactly_for_the_family_table_models(member: DeviceType) -> None:
    """The predicate and the threshold tables are one list: a listed model has a family, nothing else does."""
    assert DeviceType.has_wifi_movement_threshold(_a_name_for(member)) is (_WIFI_MOVEMENT_FAMILY[member] is not None)


def test_has_wifi_movement_threshold_resolves_through_the_product_key() -> None:
    """The Luba 2 product key places an unrecognised name in the older family."""
    assert DeviceType.has_wifi_movement_threshold(UNRECOGNISED_NAME) is False
    assert DeviceType.has_wifi_movement_threshold(UNRECOGNISED_NAME, "a1iMygIwxFC") is True


_VISION = "vision"  # the app's isSupportVision(): shows "Visual Positioning"
_LIDAR = "lidar"  # the app's isSupportRadar(): shows "LiDAR Positioning"

#: Every member's positioning row in app 2.3.20.30 (``DeviceType.isSupportVision`` / ``isSupportRadar``).
#: None: the app shows neither row.
_POSITIONING: dict[DeviceType, str | None] = {
    DeviceType.UNKNOWN: None,
    DeviceType.RTK: None,
    DeviceType.LUBA: None,  # Luba 1: in neither set
    DeviceType.LUBA_2: _VISION,
    DeviceType.LUBA_YUKA: _VISION,
    DeviceType.YUKA_MINI: _VISION,
    DeviceType.YUKA_MINI2: _VISION,
    DeviceType.LUBA_VP: _VISION,
    DeviceType.LUBA_MN: _VISION,
    DeviceType.YUKA_VP: _VISION,
    DeviceType.SPINO: None,
    DeviceType.RTK3A1: None,
    DeviceType.LUBA_LD: _LIDAR,
    DeviceType.RTK3A0: None,
    DeviceType.RTK3A2: None,
    DeviceType.YUKA_MINIV: None,  # pure-visual X5: the app shows neither row
    DeviceType.LUBA_VA: _LIDAR,  # Luba 3: never a vision device in the app
    DeviceType.YUKA_ML: _LIDAR,
    DeviceType.LUBA_MD: _LIDAR,
    DeviceType.LUBA_LA: _LIDAR,
    DeviceType.SWIMMINGPOOL_S1: None,
    DeviceType.SWIMMINGPOOL_E1: None,
    DeviceType.YUKA_MN100: None,  # pure-visual X5, like YUKA_MINIV
    DeviceType.RTKNB: None,
    DeviceType.LUBA_MB: _VISION,
    DeviceType.CM900: _VISION,
    DeviceType.YUKA_MN101: _LIDAR,
    DeviceType.SWIMMINGPOOL_SP: None,
    DeviceType.SD_PX: None,
    DeviceType.LUBA_HM: _LIDAR,
    DeviceType.LUBA_ME: _LIDAR,
    DeviceType.LUBA_SP: _LIDAR,
    DeviceType.LUBA_TR: _LIDAR,
    DeviceType.LUBA_LS: _LIDAR,
    DeviceType.LUBA_MS: _VISION,
    DeviceType.CM901: _VISION,
    DeviceType.YUKA_HS: _LIDAR,  # the app decides at runtime; a name cannot, so the LiDAR variant
    DeviceType.SPINO_H1: None,
}


def test_positioning_table_names_every_device_type() -> None:
    """A new member must be given a positioning row (or deliberately none) before this passes."""
    assert set(_POSITIONING) == set(DeviceType)


@pytest.mark.parametrize(
    "member",
    [member for member in DeviceType if _a_name_for(member)],
    ids=lambda member: member.name,
)
def test_supports_vision_positioning_is_the_app_s_vision_set(member: DeviceType) -> None:
    assert DeviceType.supports_vision_positioning(_a_name_for(member)) is (_POSITIONING[member] == _VISION)


@pytest.mark.parametrize(
    "member",
    [member for member in DeviceType if _a_name_for(member)],
    ids=lambda member: member.name,
)
def test_supports_lidar_positioning_is_the_app_s_radar_set(member: DeviceType) -> None:
    assert DeviceType.supports_lidar_positioning(_a_name_for(member)) is (_POSITIONING[member] == _LIDAR)


@pytest.mark.regression
def test_the_luba_3_is_a_lidar_device_and_not_a_vision_device() -> None:
    """HA gated the visual-positioning sensor on ``is_luba_pro``, so the Luba 3 got one.

    Its vision block is uninitialised (vio_state 232), which read as "Unknown" forever; the app
    never shows that row for LUBA_VA and shows "LiDAR Positioning" instead.
    """
    assert DeviceType.supports_vision_positioning("Luba-VA6ABCDE") is False
    assert DeviceType.supports_lidar_positioning("Luba-VA6ABCDE") is True


def test_positioning_gates_resolve_through_the_product_key() -> None:
    """A Luba 2 known only by its product key is a vision device."""
    luba_2_product_key = "a1iMygIwxFC"

    assert DeviceType.supports_vision_positioning(UNRECOGNISED_NAME) is False
    assert DeviceType.supports_vision_positioning(UNRECOGNISED_NAME, luba_2_product_key) is True
    assert DeviceType.supports_lidar_positioning(UNRECOGNISED_NAME, luba_2_product_key) is False
