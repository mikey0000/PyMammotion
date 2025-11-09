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
class MowerInfo(DataClassORJSONMixin):
    blade_status: bool = False
    rain_detection: bool = False
    traversal_mode: int = 0
    turning_mode: int = 0
    blade_mode: int = 0
    blade_rpm: int = 0
    side_led: SideLight = field(default_factory=SideLight)
    collector_installation_status: bool = False
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
    left_motor_driver: str = ""
    lora_version: str = ""
    main_controller: str = ""
    model_name: str = ""
    right_motor_driver: str = ""
    rtk_rover_station: str = ""
    rtk_version: str = ""
