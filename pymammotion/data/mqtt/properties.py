from dataclasses import dataclass
from typing import Annotated, Any, Literal, Union

from mashumaro import DataClassDictMixin
from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias

from pymammotion.data.mqtt.mammotion_properties import DeviceProperties


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
class Item(DataClassDictMixin):
    time: int
    value: int | float | str | dict[str, Any] | ItemTypes  # Depending on the type of value


@dataclass
class Items(DataClassDictMixin):
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
    device_type: Annotated[Literal["LawnMower", "Tracker"], Alias("deviceType")]
    check_failed_data: Annotated[dict[str, Any], Alias("checkFailedData")]
    group_id_list: Annotated[list[str], Alias("groupIdList")]
    _tenant_id: Annotated[str, Alias("_tenantId")]
    group_id: Annotated[str, Alias("groupId")]
    category_key: Annotated[Literal["LawnMower", "Tracker"], Alias("categoryKey")]
    batch_id: Annotated[str, Alias("batchId")]
    gmt_create: Annotated[int, Alias("gmtCreate")]
    product_key: Annotated[str, Alias("productKey")]
    generate_time: Annotated[int, Alias("generateTime")]
    device_name: Annotated[str, Alias("deviceName")]
    _trace_id: Annotated[str, Alias("_traceId")]
    iot_id: Annotated[str, Alias("iotId")]
    jmsx_delivery_count: Annotated[int, Alias("JMSXDeliveryCount")]
    check_level: Annotated[int, Alias("checkLevel")]
    qos: int
    request_id: Annotated[str, Alias("requestId")]
    _category_key: Annotated[str, Alias("_categoryKey")]
    namespace: str
    tenant_id: Annotated[str, Alias("tenantId")]
    thing_type: Annotated[Literal["DEVICE"], Alias("thingType")]
    items: Annotated["Items", Alias("items")]
    tenant_instance_id: Annotated[str, Alias("tenantInstanceId")]

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class ThingPropertiesMessage(DataClassORJSONMixin):
    method: Literal["thing.properties"]
    id: str
    params: Params
    version: Literal["1.0"]


@dataclass
class MammotionPropertiesMessage(DataClassORJSONMixin):
    id: str
    version: str
    sys: dict
    params: DeviceProperties
