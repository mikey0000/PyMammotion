from dataclasses import dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class SideLight(DataClassORJSONMixin):
    operate: int = 0
    enable: int = 0
    start_hour: int = 0
    start_min: int = 0
    end_hour: int = 0
    end_min: int = 0
    action: int = 0


@dataclass
class DeviceNonWorkingHours(DataClassORJSONMixin):
    sub_cmd: int = 0
    start_time: str = ""
    end_time: str = ""


@dataclass
class LampInfo(DataClassORJSONMixin):
    lamp_bright: int = 0
    manual_light: bool = False
    night_light: bool = False


@dataclass
class AnimalProtection(DataClassORJSONMixin):
    mode: int = 0
    status: int = 0


@dataclass
class AudioSettings(DataClassORJSONMixin):
    language: str = ""
    volume: int = 0
    sex: int = 0


@dataclass
class MowerInfo(DataClassORJSONMixin):
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
    lamp_info: LampInfo = field(default_factory=LampInfo)


@dataclass
class DeviceFirmwares(DataClassORJSONMixin):
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
    model_name: str = ""
