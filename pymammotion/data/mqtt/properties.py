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
    batteryPercentage: int


@dataclass
class BMSHardwareVersionItems(DataClassORJSONMixin):
    bmsHardwareVersion: str


@dataclass
class CoordinateItems(DataClassORJSONMixin):
    coordinate: str  # '{"lon":0.303903,"lat":1.051868}'


@dataclass
class DeviceStateItems(DataClassORJSONMixin):
    deviceState: int


@dataclass
class DeviceVersionItems(DataClassORJSONMixin):
    deviceVersion: str


@dataclass
class DeviceVersionInfoItems(DataClassORJSONMixin):
    deviceVersionInfo: str


@dataclass
class ESP32VersionItems(DataClassORJSONMixin):
    esp32Version: str


@dataclass
class LeftMotorBootVersionItems(DataClassORJSONMixin):
    leftMotorBootVersion: str


@dataclass
class LeftMotorVersionItems(DataClassORJSONMixin):
    leftMotorVersion: str


@dataclass
class MCBootVersionItems(DataClassORJSONMixin):
    mcBootVersion: str


@dataclass
class NetworkInfoItems(DataClassORJSONMixin):
    networkInfo: str


@dataclass
class RightMotorBootVersionItems(DataClassORJSONMixin):
    rightMotorBootVersion: str


@dataclass
class RightMotorVersionItems(DataClassORJSONMixin):
    rightMotorVersion: str


@dataclass
class RTKVersionItems(DataClassORJSONMixin):
    rtkVersion: str


@dataclass
class StationRTKVersionItems(DataClassORJSONMixin):
    stationRtkVersion: str


@dataclass
class STM32H7VersionItems(DataClassORJSONMixin):
    stm32H7Version: str


@dataclass
class OTAProgressItems(DataClassORJSONMixin):
    result: int
    otaId: str
    progress: int
    message: str
    version: str
    properties: str


ItemTypes = Union[
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
    OTAProgressItems,
]


@dataclass
class Item:
    time: int
    value: int | float | str | dict[str, Any] | ItemTypes  # Depending on the type of value


@dataclass
class Items:
    iotState: Item | None = None
    extMod: Item | None = None
    deviceVersionInfo: Item | None = None
    leftMotorBootVersion: Item | None = None
    knifeHeight: Item | None = None
    rtMrMod: Item | None = None
    iotMsgHz: Item | None = None
    iotMsgTotal: Item | None = None
    loraRawConfig: Item | None = None
    loraGeneralConfig: Item | None = None
    leftMotorVersion: Item | None = None
    intMod: Item | None = None
    coordinate: Item | None = None
    bmsVersion: Item | None = None
    rightMotorVersion: Item | None = None
    stm32H7Version: Item | None = None
    rightMotorBootVersion: Item | None = None
    deviceVersion: Item | None = None
    rtkVersion: Item | None = None
    ltMrMod: Item | None = None
    networkInfo: Item | None = None
    bmsHardwareVersion: Item | None = None
    batteryPercentage: Item | None = None
    deviceState: Item | None = None
    deviceOtherInfo: Item | None = None
    mcBootVersion: Item | None = None
    otaProgress: Item | None = None


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
