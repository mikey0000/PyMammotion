"""Models for ``POST weather-server/v1/device/rain-protection/config``: the cloud's copy of rain protection.

Mirrors ``RainProtectionConfigVo`` (APK 2.3.20.30).  The app POSTs the values after the
device acknowledged them; Smart mode's resume time is presumably computed server-side
from weather data, so the server needs to know the mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias


@dataclass
class RainProtectionConfig(DataClassORJSONMixin):
    """The saved config the server echoes (``RainProtectionConfigVo``)."""

    device_name: Annotated[str, Alias("deviceName")] = ""
    rain_protection_mode: Annotated[int, Alias("rainProtectionMode")] = 0
    custom_delay_hours: Annotated[int, Alias("customDelayHours")] = 0

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True

    @classmethod
    def __pre_deserialize__(cls, d: dict[Any, Any]) -> dict[Any, Any]:
        return {k: v for k, v in d.items() if v is not None}


class WeatherServerSync(StrEnum):
    """What became of the weather-server copy after a rain-protection write the device accepted."""

    SAVED = "saved"
    #: The device changed but the server copy did not; Smart mode may then resume as Sensor would.
    FAILED = "failed"
    #: No cloud login owns the device (BLE-only), so there is no server to tell.
    SKIPPED = "skipped"
