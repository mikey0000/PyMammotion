from dataclasses import dataclass
from typing import TypeVar

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin

DataT = TypeVar("DataT")


@dataclass
class RegionResponseData(DataClassORJSONMixin):
    """Region endpoint details including MQTT, API gateway, and push channel URLs."""

    shortRegionId: str
    oaApiGatewayEndpoint: str
    regionId: str
    mqttEndpoint: str
    pushChannelEndpoint: str
    regionEnglishName: str
    apiGatewayEndpoint: str


@dataclass
class RegionResponse(DataClassORJSONMixin):
    """Top-level response from the region-lookup API."""

    data: RegionResponseData
    code: int
    id: str | None = None
    msg: str | None = None

    class Config(BaseConfig):
        omit_default = True
