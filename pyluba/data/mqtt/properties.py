from typing import Literal, TypeVar, Generic, Union

from pydantic import BaseModel
from pydantic.generics import GenericModel

DataT = TypeVar("DataT")


class Item(GenericModel, Generic[DataT]):
    time: int
    value: DataT


class BatteryPercentageItems(BaseModel):
    batteryPercentage: Item[int]


class BMSHardwareVersionItems(BaseModel):
    bmsHardwareVersion: Item[str]


class CoordinateItems(BaseModel):
    coordinate: Item[str]  # '{"lon":0.303903,"lat":1.051868}'


class DeviceStateItems(BaseModel):
    deviceState: Item[int]


class DeviceVersionItems(BaseModel):
    deviceVersion: Item[str]


class DeviceVersionInfoItems(BaseModel):
    deviceVersionInfo: Item[str]


class ESP32VersionItems(BaseModel):
    esp32Version: Item[str]


class LeftMotorBootVersionItems(BaseModel):
    leftMotorBootVersion: Item[str]


class LeftMotorVersionItems(BaseModel):
    leftMotorVersion: Item[str]


class MCBootVersionItems(BaseModel):
    mcBootVersion: Item[str]


class NetworkInfoItems(BaseModel):
    networkInfo: Item[str]


class RightMotorBootVersionItems(BaseModel):
    rightMotorBootVersion: Item[str]


class RightMotorVersionItems(BaseModel):
    rightMotorVersion: Item[str]


class RTKVersionItems(BaseModel):
    rtkVersion: Item[str]


class StationRTKVersionItems(BaseModel):
    stationRtkVersion: Item[str]


class STM32H7VersionItems(BaseModel):
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
    STM32H7VersionItems
]


class Params(BaseModel):
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


class ThingPropertiesMessage(BaseModel):
    method: Literal["thing.properties"]
    id: str
    params: Params
    version: Literal["1.0"]
