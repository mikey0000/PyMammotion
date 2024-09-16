from dataclasses import dataclass
from typing import List

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class Camera(DataClassORJSONMixin):
    cameraId: int
    token: str


@dataclass
class StreamSubscriptionResponse(DataClassORJSONMixin):
    appid: str
    cameras: List[Camera]
    channelName: str
    token: str
    uid: int
