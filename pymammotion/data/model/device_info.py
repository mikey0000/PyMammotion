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
class MowerInfo(DataClassORJSONMixin):
    blade_status: bool = False
    side_led: SideLight = field(default_factory=SideLight)
    collector_installation_status: bool = False
    model: str = ""
    swversion: str = ""
    product_key: str = ""
    model_id: str = ""
