from dataclasses import dataclass

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class DeviceData(DataClassORJSONMixin):
    deviceId: str


@dataclass
class Device(DataClassORJSONMixin):
    traceId: str
    code: int
    data: DeviceData
    subCode: int
    message: str
    successful: str


@dataclass
class Config(DataClassORJSONMixin):
    traceId: str
    code: int
    subCode: int
    message: str
    successful: str


@dataclass
class DataContent(DataClassORJSONMixin):
    device: Device
    config: Config


@dataclass
class InnerData(DataClassORJSONMixin):
    traceId: str
    vid: str
    code: int
    data: DataContent
    subCode: int
    message: str
    successful: str


@dataclass
class ConnectResponse(DataClassORJSONMixin):
    data: InnerData
    success: str
    api: str
