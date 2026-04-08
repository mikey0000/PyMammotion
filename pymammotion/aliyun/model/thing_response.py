from dataclasses import dataclass

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.data.mqtt.properties import Items


@dataclass
class ThingPropertiesResponse(DataClassORJSONMixin):
    """Response from the thing-properties query API."""

    code: int
    data: Items | None
    id: str | None = None
