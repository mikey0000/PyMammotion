from dataclasses import dataclass

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class Camera(DataClassORJSONMixin):
    """Single camera entry within a stream subscription response."""

    cameraId: int
    token: str


@dataclass
class StreamSubscriptionResponse(DataClassORJSONMixin):
    """Agora stream subscription token and channel details returned by the cloud API."""

    appid: str
    openEncrypt: int
    cameras: list[Camera]
    channelName: str
    areaCode: str
    token: str
    uid: int
    license: str | None = None
    availableTime: int | None = None


@dataclass
class VideoResourceResponse(DataClassORJSONMixin):
    """Video resource usage and availability data returned for a device."""

    id: str
    deviceId: str
    deviceName: str
    cycleType: int
    usageYearMonth: str
    totalTime: int
    availableTime: int
