from dataclasses import dataclass
from typing import List, Optional

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin

@dataclass
class Camera(DataClassORJSONMixin):
    cameraId: int
    token: str

@dataclass
class Data(DataClassORJSONMixin):
    appid: str
    cameras: List[Camera]
    channelName: str
    token: str
    uid: int

@dataclass
class StreamSubscriptionResponse(DataClassORJSONMixin):
    code: int
    msg: str
    data: Optional[Data] = None

    class Config(BaseConfig):
        omit_default = True