from dataclasses import dataclass

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class DeviceData(DataClassORJSONMixin):
    """Device identifier data returned from a connect response."""

    deviceId: str


@dataclass
class Device(DataClassORJSONMixin):
    """Device-level connect result including trace and status info."""

    traceId: str
    code: int
    data: DeviceData
    subCode: int
    message: str
    successful: str


@dataclass
class Config(DataClassORJSONMixin):
    """Configuration-level connect result including trace and status info."""

    traceId: str
    code: int
    subCode: int
    message: str
    successful: str


@dataclass
class DataContent(DataClassORJSONMixin):
    """Container holding device and config sub-responses from a connect call."""

    device: Device
    config: Config


@dataclass
class InnerData(DataClassORJSONMixin):
    """Inner data envelope for a connect response."""

    traceId: str
    vid: str
    code: int
    data: DataContent
    subCode: int
    message: str
    successful: str


@dataclass
class ConnectResponse(DataClassORJSONMixin):
    """Top-level response from the cloud device connect API."""

    data: InnerData
    success: str
    api: str
