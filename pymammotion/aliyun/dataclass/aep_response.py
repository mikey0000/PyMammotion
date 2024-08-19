from dataclasses import dataclass
from typing import Optional

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class DeviceData(DataClassORJSONMixin):
    deviceSecret: str
    productKey: str
    deviceName: str


@dataclass
class AepResponse(DataClassORJSONMixin):
    code: int
    data: DeviceData
    id: Optional[str] = None

    class Config(BaseConfig):
        omit_default = True
