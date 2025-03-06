from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar, Union

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
class Item:
    time: int
    value: int | float | str | dict[str, Any]  # Depending on the type of value


@dataclass
class Items:
    iotState: Item
    extMod: Item
    deviceVersionInfo: Item
    leftMotorBootVersion: Item
    knifeHeight: Item
    rtMrMod: Item
    iotMsgHz: Item
    iotMsgTotal: Item
    loraRawConfig: Item
    loraGeneralConfig: Item
    leftMotorVersion: Item
    intMod: Item
    coordinate: Item
    bmsVersion: Item
    rightMotorVersion: Item
    stm32H7Version: Item
    rightMotorBootVersion: Item
    deviceVersion: Item
    rtkVersion: Item
    ltMrMod: Item
    networkInfo: Item
    bmsHardwareVersion: Item
    batteryPercentage: Item
    deviceState: Item
    deviceOtherInfo: Item
    mcBootVersion: Item


@dataclass
class Params(DataClassORJSONMixin):
    deviceType: Literal["LawnMower"]
    checkFailedData: dict
    groupIdList: list[str]
    _tenantId: str
    groupId: str
    categoryKey: Literal["LawnMower"]
    batchId: str
    gmtCreate: int
    productKey: str
    generateTime: int
    deviceName: str
    _traceId: str
    iotId: str
    JMSXDeliveryCount: int
    checkLevel: int
    qos: int
    requestId: str
    _categoryKey: str
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
