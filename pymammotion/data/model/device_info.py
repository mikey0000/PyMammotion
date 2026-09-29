from dataclasses import dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.data.model.mowing_modes import (
    RAIN_PROTECTION_DEFAULT_DELAY_HOURS,
    RAIN_PROTECTION_DELAY_HOURS,
    RainProtectionMode,
)


@dataclass
class SideLight(DataClassORJSONMixin):
    """Side LED light configuration including schedule and action settings."""

    operate: int = 0
    enable: int = 0
    start_hour: int = 0
    start_min: int = 0
    end_hour: int = 0
    end_min: int = 0
    action: int = 0


@dataclass
class DeviceNonWorkingHours(DataClassORJSONMixin):
    """Time window during which the mower is not permitted to operate."""

    sub_cmd: int = 0
    start_time: str = ""
    end_time: str = ""


@dataclass
class LampInfo(DataClassORJSONMixin):
    """Lamp brightness and auto/night-light mode settings."""

    lamp_bright: int = 0
    manual_light: bool = False
    night_light: bool = False


@dataclass
class AnimalProtection(DataClassORJSONMixin):
    """Animal protection mode and status configuration."""

    mode: int = 0
    status: int = 0


@dataclass
class AudioSettings(DataClassORJSONMixin):
    """Audio output settings including language, volume, and voice gender."""

    language: str = ""
    volume: int = 0
    sex: int = 0


@dataclass
class ChargeSettings(DataClassORJSONMixin):
    """Battery charging settings reported by ``MctlSys.bms_ctrl_info_msg``.

    ``smart_charge`` is the decoded form of the wire ``smart_charge_switch``, which
    the app treats inverted: 0 means smart charging is on, 1 means the user-set
    ``charge_limit`` applies.  Times are minutes since midnight.
    """

    smart_charge: bool = False
    charge_limit: int = 0
    peak_valley_charge: bool = False
    valley_charge_start_time: int = 0
    valley_charge_end_time: int = 0
    bat_cycle_times: int = 0
    bat_health_state: int = 0

    @property
    def reported(self) -> bool:
        """Whether the device has sent these settings: it always reports a limit of 80-100."""
        return self.charge_limit != 0


@dataclass
class RainProtectionSettings(DataClassORJSONMixin):
    """Rain protection (``CFG_TYPE_RAINPRO_CFG``), known only from a batch query reply or our own write.

    ``supported`` is None until the device proves the feature (a RAINPRO reply, or
    self-check 34) and ``mode`` is None until one is read or written.  ``mode`` is the
    raw ``RainProtectionMode`` value, kept as an int so a firmware value the library
    does not know survives.  ``delay_hours`` is the last Sensor-mode delay: the device
    sends 0 in the other modes, so it is remembered here the way the app keeps it in
    local storage, and switching back to Sensor sends it again.
    """

    supported: bool | None = None
    mode: int | None = None
    delay_hours: int = RAIN_PROTECTION_DEFAULT_DELAY_HOURS

    @property
    def reported(self) -> bool:
        """Whether a mode has been read or written; the defaults are the app's, not the device's."""
        return self.mode is not None

    def with_mode(self, mode: int, delay_hours: int) -> "RainProtectionSettings":
        """Return these settings holding *mode*, which the device reported or acknowledged.

        *delay_hours* replaces the remembered delay only in Sensor mode and only when it
        is one the app offers, as the app's ``applyPersistedDelay`` does.
        """
        keep_delay = mode != RainProtectionMode.sensor or delay_hours not in RAIN_PROTECTION_DELAY_HOURS
        return RainProtectionSettings(
            supported=True, mode=mode, delay_hours=self.delay_hours if keep_delay else delay_hours
        )


#: ``nav_sys_param_cmd`` context on ids 14 and 15 that leaves the level to the mower.
SMART_CHARGE_LEVEL = -1
#: The app's slider bounds, in percent, for ids 14 (return to charge at) and 15 (resume mowing at).
RECHARGE_LEVEL_RANGE = range(15, 31)
RESUME_LEVEL_RANGE = range(40, 101)


@dataclass
class MowerInfo(DataClassORJSONMixin):
    """Aggregated mower configuration including blade, navigation, and peripheral settings."""

    blade_status: bool = False
    rain_detection: bool = False
    traversal_mode: int = 0
    turning_mode: int = 0
    cutter_mode: int = 0
    cutter_rpm: int = 0
    side_led: SideLight = field(default_factory=SideLight)
    collector_installation_status: bool = False
    collect_grass_enable: int = 0
    animal_protection: AnimalProtection = field(default_factory=AnimalProtection)
    boundary_ride_distance: int = 0  # ID 10 — the mapping screen's mode picker (0/50/25); meaning unknown
    travel_speed: float = 0.0
    lora_config: str = ""
    audio: AudioSettings = field(default_factory=AudioSettings)
    model: str = ""
    swversion: str = ""
    product_key: str = ""
    model_id: str = ""
    sub_model_id: str = ""
    ble_mac: str = ""
    wifi_mac: str = ""
    wifi_ssid: str = ""
    ip_address: str = ""
    ip: int = 0
    mask: int = 0
    gateway: int = 0
    internal_model: str = ""  # thing/properties intMod — internal SKU (e.g. "HM020080YKMINI06")
    battery_hardware: str = ""  # thing/properties bmsHardwareVersion (e.g. "BW_BATTERY_25P_6S1P")
    lamp_info: LampInfo = field(default_factory=LampInfo)
    charge_settings: ChargeSettings = field(default_factory=ChargeSettings)
    recharge_level: int = 0  # ID 14 — percent, SMART_CHARGE_LEVEL for smart, 0 until read
    resume_level: int = 0  # ID 15 — percent, SMART_CHARGE_LEVEL for smart, 0 until read
    rain_protection: RainProtectionSettings = field(default_factory=RainProtectionSettings)


@dataclass
class DeviceFirmwares(DataClassORJSONMixin):
    """Firmware version strings for all sub-components of the mower."""

    device_version: str = ""
    # Core modules (Luba 1 + 2)
    main_controller: str = ""  # type 1 / 101
    left_motor_driver: str = ""  # type 3
    right_motor_driver: str = ""  # type 4
    rtk_rover_station: str = ""  # type 5 — GNSS rover
    # BT companion firmware (same MCU, OTA over BLE)
    main_controller_bt: str = ""  # type 8
    left_motor_driver_bt: str = ""  # type 9
    right_motor_driver_bt: str = ""  # type 10
    # Extended modules (Luba 2)
    bms: str = ""  # type 7  — battery management system
    bsp: str = ""  # type 11 — board support package
    middleware: str = ""  # type 12
    lora_module: str = ""  # type 14 — STM32+LLCC68 LoRa radio in mower
    lte_module: str = ""  # type 16 — 4G modem (NL668AM)
    lidar: str = ""  # type 17 — LiDAR middleware (MID-360)
    cutter_driver: str = ""  # type 203
    cutter_driver_bt: str = ""  # type 204
    # RTK base station modules
    rtk_version: str = ""  # type 102
    lora_version: str = ""  # type 103 — LoRa on RTK base station
    # Spino pool cleaner modules
    wheel_hub_motor: str = ""  # type 63 — PAWG4
    water_pump: str = ""  # type 65 — PACG4
    communication: str = ""  # type 67/72 — PESP Wi-Fi module
    model_name: str = ""
