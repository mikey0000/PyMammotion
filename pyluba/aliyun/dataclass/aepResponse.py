from dataclasses import dataclass
from typing import Generic, Literal, TypeVar, Optional

from mashumaro import DataClassDictMixin
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
    id: Optional[str] = None  # id optional