"""``DeviceType`` capability helpers, one row per model, against the app's own answers.

Source: the decompiled app 2.3.20.30 ``device/source/device/enums/DeviceType.java``.  Each
expectation below is that file's answer; a helper that disagrees has drifted from the app.
"""

import pytest

from pymammotion.utility.device_type import DeviceType

_NAMES = {
    DeviceType.LUBA_SP: "Luba-SP6ABCDE",
    DeviceType.LUBA_TR: "Luba-TR6ABCDE",
    DeviceType.LUBA_LS: "Luba-LS6ABCDE",
    DeviceType.LUBA_MS: "Luba-MS6ABCDE",
    DeviceType.CM900: "Kumar-MK6ABCDE",
    DeviceType.CM901: "Maston-R6ABCDE",
    DeviceType.YUKA_HS: "Yuka-HS6ABCDE",
    DeviceType.SPINO_H1: "Spino-H1ABCDE",
}

#: One column per helper; each value is the 2.3.20.30 ``DeviceType.java`` answer (line numbers
#: there): isLubaType 679, isSupportDynamicsLine 826, isYuKaType 946, isSupportFillLight 830,
#: isSupportBladeSpeed 803, isX5DeviceTyp 914, isSupportBatteryLoopCount 799, isSwimmingPool 894,
#: isRTK 751, isLubaPro 667, has4G 591, isLuba1 619.  Edge coverage is
#: SettingOptionsView.refreshData, Smart Sleep the RN battery page, Wildlife Safety the
#: ``is231SimilarParameterSettings`` exclusion.
_HELPERS = {
    "is_luba_type": lambda dt, name: dt.is_luba_type(),
    "is_support_dynamics_line": lambda dt, name: dt.is_support_dynamics_line(),
    "is_yu_ka_type": lambda dt, name: dt.is_yu_ka_type(),
    "is_yuka": lambda dt, name: DeviceType.is_yuka(name),
    "is_support_fill_light": lambda dt, name: DeviceType.is_support_fill_light(name),
    "is_support_blade_speed": lambda dt, name: DeviceType.is_support_blade_speed(name),
    "is_x5_series": lambda dt, name: DeviceType.is_x5_series(name),
    "supports_battery_cycle_count": lambda dt, name: dt.supports_battery_cycle_count(),
    "is_swimming_pool": lambda dt, name: DeviceType.is_swimming_pool(name),
    "is_rtk": lambda dt, name: DeviceType.is_rtk(name),
    "is_luba_pro": lambda dt, name: DeviceType.is_luba_pro(name),
    "has_4g": lambda dt, name: DeviceType.has_4g(name),
    "is_luba1": lambda dt, name: DeviceType.is_luba1(name),
    "ride_boundary_distance": lambda dt, name: DeviceType.supports_ride_boundary_distance(name),
    "smart_sleep": lambda dt, name: DeviceType.supports_smart_sleep(name, "9.9.9.9"),
    "wildlife_safety": lambda dt, name: DeviceType.supports_wildlife_safety(name, "9.9.9.9"),
}

_T, _F = True, False
# YUKA_HS is the lidar variant here: the app's ``isYukaHSVision()`` is a runtime flag a name
# cannot carry, and a vision HS would also join the 231 set (no Wildlife Safety).
_EXPECTED = {
    #                     luba  dyn  yuka is_yuka fill blade x5 cycles pool rtk  pro  4g  luba1 ride sleep wild
    DeviceType.LUBA_SP: (_T, _T, _F, _F, _T, _T, _T, _T, _F, _F, _T, _T, _F, _T, _F, _T),
    DeviceType.LUBA_TR: (_T, _T, _F, _F, _T, _T, _T, _T, _F, _F, _T, _T, _F, _T, _F, _T),
    DeviceType.LUBA_LS: (_T, _T, _F, _F, _T, _T, _T, _F, _F, _F, _T, _T, _F, _F, _T, _T),
    DeviceType.LUBA_MS: (_T, _T, _F, _F, _T, _T, _T, _F, _F, _F, _T, _T, _F, _F, _T, _F),
    DeviceType.CM900: (_T, _T, _F, _F, _T, _T, _T, _T, _F, _F, _T, _T, _F, _T, _F, _T),
    DeviceType.CM901: (_T, _T, _F, _F, _T, _T, _T, _T, _F, _F, _T, _T, _F, _T, _F, _T),
    DeviceType.YUKA_HS: (_F, _T, _T, _T, _T, _T, _T, _F, _F, _F, _T, _T, _F, _F, _F, _T),
    DeviceType.SPINO_H1: (_F, _F, _F, _F, _F, _F, _F, _T, _T, _F, _F, _T, _F, _F, _F, _F),
}


@pytest.mark.parametrize(
    ("member", "helper", "expected"),
    [
        pytest.param(member, helper, row[index], id=f"{member.name}-{helper}")
        for member, row in _EXPECTED.items()
        for index, helper in enumerate(_HELPERS)
    ],
)
def test_every_helper_answers_as_the_app_does(member: DeviceType, helper: str, expected: bool) -> None:
    name = _NAMES[member]
    assert DeviceType.value_of_str(name) is member, "the name must resolve before a helper can be checked"
    assert _HELPERS[helper](member, name) is expected


@pytest.mark.parametrize("device_name", ["Ezy-VT6ABCDE", "Yuka-CV6ABCDE", "Ezy-LD6ABCDE"])
def test_the_ezy_mowers_joined_the_x5_platform(device_name: str) -> None:
    """2.3.20.30 ``isX5DeviceTyp`` added YUKA_MN100 and YUKA_MN101; 2.3.8.201 had neither."""
    assert DeviceType.is_x5_series(device_name) is True


@pytest.mark.parametrize("device_name", ["Luba-LS6ABCDE", "Luba-MS6ABCDE"])
def test_the_se_variants_get_smart_sleep_from_its_threshold(device_name: str) -> None:
    """The 2.3.20.30 battery page lists HM432SE/HM434SE beside HM432/HM434/HM442, same ``> 2.3.26.0``."""
    assert DeviceType.supports_smart_sleep(device_name, "2.3.26.1") is True
    assert DeviceType.supports_smart_sleep(device_name, "2.3.26.0") is False
