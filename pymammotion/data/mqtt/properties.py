from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias

from pymammotion.data.model.events import OTA_RESULT_IN_PROGRESS
from pymammotion.data.mqtt.mammotion_properties import DeviceProperties


@dataclass
class BatteryPercentageItems(DataClassORJSONMixin):
    """Property item carrying the device battery percentage."""

    batteryPercentage: int


@dataclass
class BMSHardwareVersionItems(DataClassORJSONMixin):
    """Property item carrying the BMS hardware version string."""

    bmsHardwareVersion: str


@dataclass
class CoordinateItems(DataClassORJSONMixin):
    """Property item carrying a JSON-encoded coordinate string."""

    coordinate: str  # '{"lon":0.303903,"lat":1.051868}'


@dataclass
class DeviceStateItems(DataClassORJSONMixin):
    """Property item carrying the device operational state code."""

    deviceState: int


@dataclass
class DeviceVersionItems(DataClassORJSONMixin):
    """Property item carrying the device firmware version string."""

    deviceVersion: str


@dataclass
class DeviceVersionInfoItems(DataClassORJSONMixin):
    """Property item carrying the JSON-encoded device version info blob."""

    deviceVersionInfo: str


@dataclass
class ESP32VersionItems(DataClassORJSONMixin):
    """Property item carrying the ESP32 firmware version string."""

    esp32Version: str


@dataclass
class LeftMotorBootVersionItems(DataClassORJSONMixin):
    """Property item carrying the left motor bootloader version string."""

    leftMotorBootVersion: str


@dataclass
class LeftMotorVersionItems(DataClassORJSONMixin):
    """Property item carrying the left motor firmware version string."""

    leftMotorVersion: str


@dataclass
class MCBootVersionItems(DataClassORJSONMixin):
    """Property item carrying the main controller bootloader version string."""

    mcBootVersion: str


@dataclass
class NetworkInfoItems(DataClassORJSONMixin):
    """Property item carrying the JSON-encoded network info blob."""

    networkInfo: str


@dataclass
class RightMotorBootVersionItems(DataClassORJSONMixin):
    """Property item carrying the right motor bootloader version string."""

    rightMotorBootVersion: str


@dataclass
class RightMotorVersionItems(DataClassORJSONMixin):
    """Property item carrying the right motor firmware version string."""

    rightMotorVersion: str


@dataclass
class RTKVersionItems(DataClassORJSONMixin):
    """Property item carrying the RTK module firmware version string."""

    rtkVersion: str


@dataclass
class StationRTKVersionItems(DataClassORJSONMixin):
    """Property item carrying the RTK base-station firmware version string."""

    stationRtkVersion: str


@dataclass
class STM32H7VersionItems(DataClassORJSONMixin):
    """Property item carrying the STM32-H7 main controller firmware version string."""

    stm32H7Version: str


@dataclass
class OTAProgressItems(DataClassORJSONMixin):
    """Property item reporting the progress and outcome of an OTA firmware update.

    Every field defaults: the cloud omits some of them mid-install, and mashumaro
    raises ``MissingField`` — a sibling of ``KeyError`` under ``LookupError``, so it
    escaped the caller's ``(ValueError, KeyError, TypeError)`` guard and took the whole
    properties frame with it.

    ``result`` defaults to :data:`OTA_RESULT_IN_PROGRESS` rather than 0, because 0 is
    the *success* code: defaulting it would report a missing field as a finished
    install and pin the bar to 100%.
    """

    result: int = OTA_RESULT_IN_PROGRESS
    otaId: str = ""
    progress: int = 0
    message: str = ""
    version: str = ""
    properties: str = ""


ItemTypes = (
    BatteryPercentageItems
    | BMSHardwareVersionItems
    | CoordinateItems
    | DeviceStateItems
    | DeviceVersionItems
    | DeviceVersionInfoItems
    | ESP32VersionItems
    | LeftMotorBootVersionItems
    | LeftMotorVersionItems
    | MCBootVersionItems
    | NetworkInfoItems
    | RightMotorBootVersionItems
    | RightMotorVersionItems
    | RTKVersionItems
    | StationRTKVersionItems
    | STM32H7VersionItems
    | OTAProgressItems
)


@dataclass
class Item(DataClassORJSONMixin):
    """A single timestamped property value from an Aliyun IoT thing-properties message."""

    time: int
    value: int | float | str | dict[str, Any] | ItemTypes  # Depending on the type of value


@dataclass
class Items(DataClassORJSONMixin):
    """Collection of optional property ``Item`` values from a thing-properties message."""

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
    """Envelope parameters for an Aliyun IoT ``thing.properties`` MQTT message."""

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
    """Top-level Aliyun IoT ``thing.properties`` MQTT message received from the device."""

    method: Literal["thing.properties"]
    id: str
    params: Params
    version: Literal["1.0"]


@dataclass
class MammotionPropertiesMessage(DataClassORJSONMixin):
    """Top-level properties message received over Mammotion's direct MQTT connection.

    Every envelope field is defaulted because the app's own model treats them that way:
    ``TopicProperty`` (maiot_module) declares ``sys`` and ``params`` ``@Nullable`` and
    reads ``id``/``version``/``method``/``time`` through null-tolerant getters.  Ours
    required ``id``, ``version`` and ``sys``, so a lean envelope raised ``MissingField``
    inside ``_dispatch_mammotion_properties``'s ``except Exception`` and was dropped at
    DEBUG — which is how a firmware install reported 0% for its whole run: OTA progress
    arrives as one of these posts (``.../thing/event/property/post``, carrying
    ``params.otaProgress``) and never survived parsing.
    """

    id: str = ""
    version: str = ""
    sys: dict = field(default_factory=dict)
    params: DeviceProperties = field(default_factory=DeviceProperties)
