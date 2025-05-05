from dataclasses import dataclass

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
    license: str | None = None
    availableTime: int | None = None


@dataclass
class VideoResourceResponse(DataClassORJSONMixin):
    id: str
    deviceId: str
    deviceName: str
    cycleType: int
    usageYearMonth: str
    totalTime: int
    availableTime: int
