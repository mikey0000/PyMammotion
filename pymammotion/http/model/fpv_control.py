"""Model for ``device-server/v1/fpv/control/{token,refresh-token}``: the cloud remote-drive control token.

Mirrors ``command/fpvdrive/model/FpvControl`` in the 2.3.20.30 APK, where every field is nullable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Annotated

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias

if TYPE_CHECKING:
    from pymammotion.http.model.http import Response

_DEVICE_RESULT_OK = 0
_DEVICE_RESULT_OCCUPIED = 9


class FpvControlOutcome(Enum):
    """What a token response means for the session (``ControlTokenRepository.handleTokenResponse``)."""

    GRANTED = "granted"
    #: Another account holds the device; ``preempt_user`` names it.
    OCCUPIED = "occupied"
    UNAVAILABLE = "unavailable"


@dataclass
class FpvControl(DataClassORJSONMixin):
    """A control-token grant: the token, its lifetime, and the session limits the server sets.

    ``expire_in`` and ``timeout_exit`` are seconds; ``latency_threshold`` is milliseconds.
    """

    device_result: Annotated[int | None, Alias("deviceResult")] = None
    token: str | None = None
    issued_timestamp: Annotated[int | None, Alias("issuedTimestamp")] = None
    expire_timestamp: Annotated[int | None, Alias("expireTimestamp")] = None
    expire_in: Annotated[int | None, Alias("expireIn")] = None
    timeout_exit: Annotated[int | None, Alias("timeoutExit")] = None
    preempt_user: Annotated[str | None, Alias("preemptUser")] = None
    latency_threshold: Annotated[int | None, Alias("latencyThreshold")] = None
    fps_4g: Annotated[float | int | None, Alias("fps4G")] = None

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


def fpv_control_outcome(response: Response[FpvControl]) -> FpvControlOutcome:
    """Classify a token response the way the app does; result codes 2 and 7 are just "unavailable"."""
    if response.code != 0 or (data := response.data) is None:
        return FpvControlOutcome.UNAVAILABLE
    if data.device_result == _DEVICE_RESULT_OK and data.token and data.token.strip():
        return FpvControlOutcome.GRANTED
    if data.device_result == _DEVICE_RESULT_OCCUPIED:
        return FpvControlOutcome.OCCUPIED
    return FpvControlOutcome.UNAVAILABLE
