from dataclasses import dataclass
from typing import Optional

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class Camera(DataClassORJSONMixin):
    cameraId: int
    token: str


@dataclass
class StreamSubscriptionResponse(DataClassORJSONMixin):
    appid: str
    cameras: list[Camera]
    channelName: str
    token: str
    uid: int
    license: Optional[str] = None
    availableTime: Optional[int] = None
