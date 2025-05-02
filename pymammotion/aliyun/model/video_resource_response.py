from dataclasses import dataclass
from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class VideoResourceResponse(DataClassORJSONMixin):
    id: str
    deviceId: str
    deviceName: str
    cycleType: int
    usageYearMonth: str
    totalTime: int
    availableTime: int