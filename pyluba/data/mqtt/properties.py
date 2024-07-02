from dataclasses import dataclass
from typing import Generic, Literal, TypeVar, Union

from mashumaro import DataClassDictMixin
from mashumaro.mixins.orjson import DataClassORJSONMixin

DataT = TypeVar("DataT")


@dataclass
class Item(DataClassDictMixin, Generic[DataT]):
    time: int
    value: DataT


@dataclass
class BatteryPercentageItems(DataClassORJSONMixin):
    batteryPercentage: Item[int]


@dataclass
class BMSHardwareVersionItems(DataClassORJSONMixin):
    bmsHardwareVersion: Item[str]


@dataclass
class CoordinateItems(DataClassORJSONMixin):
    coordinate: Item[str]  # '{"lon":0.303903,"lat":1.051868}'


@dataclass
class DeviceStateItems(DataClassORJSONMixin):
    deviceState: Item[int]


@dataclass
class DeviceVersionItems(DataClassORJSONMixin):
    deviceVersion: Item[str]


@dataclass
class DeviceVersionInfoItems(DataClassORJSONMixin):
    deviceVersionInfo: Item[str]


@dataclass
class ESP32VersionItems(DataClassORJSONMixin):
    esp32Version: Item[str]


@dataclass
class LeftMotorBootVersionItems(DataClassORJSONMixin):
    leftMotorBootVersion: Item[str]


@dataclass
class LeftMotorVersionItems(DataClassORJSONMixin):
    leftMotorVersion: Item[str]


@dataclass
class MCBootVersionItems(DataClassORJSONMixin):
    mcBootVersion: Item[str]


@dataclass
class NetworkInfoItems(DataClassORJSONMixin):
    networkInfo: Item[str]


@dataclass
class RightMotorBootVersionItems(DataClassORJSONMixin):
    rightMotorBootVersion: Item[str]


@dataclass
class RightMotorVersionItems(DataClassORJSONMixin):
    rightMotorVersion: Item[str]


@dataclass
class RTKVersionItems(DataClassORJSONMixin):
    rtkVersion: Item[str]


@dataclass
class StationRTKVersionItems(DataClassORJSONMixin):
    stationRtkVersion: Item[str]


@dataclass
class STM32H7VersionItems(DataClassORJSONMixin):
    stm32H7Version: Item[str]


Items = Union[
    BatteryPercentageItems,
    BMSHardwareVersionItems,
    CoordinateItems,
    DeviceStateItems,
    DeviceVersionItems,
    DeviceVersionInfoItems,
    ESP32VersionItems,
    LeftMotorBootVersionItems,
    LeftMotorVersionItems,
    MCBootVersionItems,
    NetworkInfoItems,
    RightMotorBootVersionItems,
    RightMotorVersionItems,
    RTKVersionItems,
    StationRTKVersionItems,
    STM32H7VersionItems,
]


@dataclass
class Params(DataClassORJSONMixin):
    checkFailedData: dict
    groupIdList: list[str]
    groupId: str
    categoryKey: Literal["LawnMower"]
    batchId: str
    gmtCreate: int
    productKey: str
    deviceName: str
    iotId: str
    checkLevel: int
    namespace: str
    tenantId: str
    thingType: Literal["DEVICE"]
    items: Items
    tenantInstanceId: str


@dataclass
class ThingPropertiesMessage(DataClassORJSONMixin):
    method: Literal["thing.properties"]
    id: str
    params: Params
    version: Literal["1.0"]
