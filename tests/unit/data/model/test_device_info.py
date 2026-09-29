"""``device_info`` settings models: the unread sentinels and loading state saved before a field existed."""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.device_info import ChargeSettings, MowerInfo, RainProtectionSettings
from pymammotion.data.model.mowing_modes import RAIN_PROTECTION_DEFAULT_DELAY_HOURS, RainProtectionMode


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (ChargeSettings(), False),
        (ChargeSettings(smart_charge=True, charge_limit=100), True),
        (ChargeSettings(charge_limit=80, valley_charge_start_time=1320, valley_charge_end_time=360), True),
    ],
    ids=["defaults", "smart", "custom"],
)
def test_charge_settings_are_reported_once_the_device_sent_a_limit(settings: ChargeSettings, expected: bool) -> None:
    """The device always reports a limit of 80-100, so 0 can only mean "never read"."""
    assert settings.reported is expected


def test_reported_is_derived_and_not_persisted() -> None:
    assert "reported" not in ChargeSettings(charge_limit=90).to_dict()


def test_saved_mower_state_without_the_charge_levels_still_loads() -> None:
    """State persisted before ids 14/15 were modelled restores with both levels unread."""
    saved = MowerInfo(charge_settings=ChargeSettings(charge_limit=90)).to_dict()
    del saved["recharge_level"], saved["resume_level"]

    restored = MowerInfo.from_dict(saved)

    assert (restored.recharge_level, restored.resume_level) == (0, 0)
    assert restored.charge_settings.charge_limit == 90


def test_saved_state_without_rain_protection_loads_as_never_probed() -> None:
    """State persisted before rain protection was modelled must restore, not fail the whole device."""
    saved = MowingDevice(name="Luba-VAME9R5S").to_dict()
    del saved["mower_state"]["rain_protection"]
    saved["mower_state"]["rain_detection"] = True

    restored = MowingDevice.from_dict(saved)

    assert restored.mower_state.rain_protection == RainProtectionSettings()
    assert restored.mower_state.rain_protection.supported is None
    assert restored.mower_state.rain_detection is True


def test_rain_protection_is_unreported_until_a_mode_arrives() -> None:
    """The default delay is the app's, not the device's: it must not read as a reported value."""
    assert RainProtectionSettings().reported is False
    assert RainProtectionSettings(supported=True).reported is False
    assert RainProtectionSettings(supported=True, mode=RainProtectionMode.off).reported is True


def test_rain_protection_round_trips_and_does_not_persist_reported() -> None:
    settings = RainProtectionSettings(supported=True, mode=RainProtectionMode.sensor, delay_hours=6)

    assert "reported" not in settings.to_dict()
    assert RainProtectionSettings.from_dict(settings.to_dict()) == settings


def test_a_sensor_mode_value_replaces_the_remembered_delay() -> None:
    updated = RainProtectionSettings(mode=RainProtectionMode.off).with_mode(RainProtectionMode.sensor, 6)

    assert updated == RainProtectionSettings(supported=True, mode=RainProtectionMode.sensor, delay_hours=6)


@pytest.mark.parametrize("mode", [RainProtectionMode.off, RainProtectionMode.smart])
def test_another_mode_keeps_the_remembered_sensor_delay(mode: RainProtectionMode) -> None:
    """The device sends 0 outside Sensor mode; switching back to Sensor must resend the user's delay."""
    updated = RainProtectionSettings(mode=RainProtectionMode.sensor, delay_hours=6).with_mode(mode, 0)

    assert (updated.mode, updated.delay_hours, updated.supported) == (mode, 6, True)


def test_a_delay_the_app_does_not_offer_is_not_remembered() -> None:
    updated = RainProtectionSettings(delay_hours=12).with_mode(RainProtectionMode.sensor, 13)

    assert (updated.mode, updated.delay_hours) == (RainProtectionMode.sensor, 12)


def test_an_unknown_mode_is_kept_verbatim() -> None:
    """Firmware may add a mode; storing the int keeps it from being shown as a known one."""
    updated = RainProtectionSettings().with_mode(7, 5)

    assert (updated.mode, updated.delay_hours, updated.supported) == (7, RAIN_PROTECTION_DEFAULT_DELAY_HOURS, True)
