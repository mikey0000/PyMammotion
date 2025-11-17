from base64 import b64decode
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from google.protobuf import json_format
from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias, SerializableType

from pymammotion.proto import luba_msg_pb2


class Base64EncodedProtobuf(SerializableType):
    def __init__(self, proto: str) -> None:
        self.proto = proto

    def _serialize(self):
        return self.proto

    @classmethod
    def _deserialize(cls, value):
        return cls(*value)

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v: str):
        if not isinstance(v, str):
            raise TypeError("string required")
        binary = b64decode(v, validate=True)
        data = luba_msg_pb2.LubaMsg()
        data.ParseFromString(binary)
        return json_format.MessageToDict(data)


@dataclass
class DeviceProtobufMsgEventValue(DataClassORJSONMixin):
    content: str


@dataclass
class DeviceWarningEventValue(DataClassORJSONMixin):
    # TODO: enum for error codes
    # (see resources/res/values-en-rUS/strings.xml in APK)
    code: int


@dataclass
class DeviceConfigurationRequestValue(DataClassORJSONMixin):
    code: int
    bizId: str
    params: str


@dataclass
class DeviceNotificationEventCode(DataClassORJSONMixin):
    localTime: int
    code: str


@dataclass
class DeviceNotificationEventValue(DataClassORJSONMixin):
    data: str  # parsed to DeviceNotificationEventCode


@dataclass
class DeviceBizReqEventValue(DataClassORJSONMixin):
    bizType: str
    bizId: str
    params: str


@dataclass
class GeneralParams(DataClassORJSONMixin):
    group_id_list: Annotated[list[str], Alias("groupIdList")]
    group_id: Annotated[str, Alias("groupId")]
    category_key: Annotated[Literal["LawnMower", "Tracker"], Alias("categoryKey")]
    batch_id: Annotated[str, Alias("batchId")]
    gmt_create: Annotated[int, Alias("gmtCreate")]
    product_key: Annotated[str, Alias("productKey")]
    type: str
    device_name: Annotated[str, Alias("deviceName")]
    iot_id: Annotated[str, Alias("iotId")]
    check_level: Annotated[int, Alias("checkLevel")]
    namespace: str
    tenant_id: Annotated[str, Alias("tenantId")]
    name: str
    thing_type: Annotated[Literal["DEVICE"], Alias("thingType")]
    time: int
    tenant_instance_id: Annotated[str, Alias("tenantInstanceId")]
    value: Any

    # Optional fields
    identifier: str | None = None
    check_failed_data: Annotated[dict | None, Alias("checkFailedData")] = None
    _tenant_id: Annotated[str | None, Alias("_tenantId")] = None
    generate_time: Annotated[int | None, Alias("generateTime")] = None
    jmsx_delivery_count: Annotated[int | None, Alias("JMSXDeliveryCount")] = None
    qos: int | None = None
    request_id: Annotated[str | None, Alias("requestId")] = None
    _category_key: Annotated[str | None, Alias("_categoryKey")] = None
    device_type: Annotated[str | None, Alias("deviceType")] = None
    _trace_id: Annotated[str | None, Alias("_traceId")] = None

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class DeviceProtobufMsgEventParams(GeneralParams):
    identifier: Literal["device_protobuf_msg_event"]
    type: Literal["info"]
    value: DeviceProtobufMsgEventValue


@dataclass
class DeviceNotificationEventParams(GeneralParams):
    """Device notification event.

    {'data': '{"localTime":1725159492000,"code":"1002"}'},
    """

    identifier: Literal["device_notification_event", "device_information_event", "device_warning_code_event"]
    type: Literal["info"]
    value: DeviceNotificationEventValue


@dataclass
class DeviceBizReqEventParams(GeneralParams):
    identifier: Literal["device_biz_req_event"]
    type: Literal["info"]
    value: DeviceBizReqEventValue


@dataclass
class DeviceWarningEventParams(GeneralParams):
    identifier: Literal["device_warning_event"]
    type: Literal["alert"]
    value: DeviceWarningEventValue


@dataclass
class DeviceConfigurationRequestEvent(GeneralParams):
    type: Literal["info"]
    value: DeviceConfigurationRequestValue


@dataclass
class DeviceLogProgressEventParams(GeneralParams):
    identifier: Literal["device_log_progress_event"]
    type: Literal["info"]
    value: DeviceNotificationEventValue


@dataclass
class ThingEventMessage(DataClassORJSONMixin):
    method: Literal["thing.events", "thing.properties"]
    id: str
    params: (
        DeviceProtobufMsgEventParams
        | DeviceWarningEventParams
        | DeviceNotificationEventParams
        | DeviceLogProgressEventParams
        | DeviceBizReqEventParams
        | DeviceConfigurationRequestEvent
        | dict
    )
    version: Literal["1.0"]

    @classmethod
    def from_dicts(cls, payload: dict) -> "ThingEventMessage":
        """Deserialize payload JSON ThingEventMessage."""
        method = payload.get("method")
        event_id = payload.get("id")
        params_dict = payload.get("params", {})
        version = payload.get("version")

        identifier = params_dict.get("identifier")
        if identifier is None:
            """Request configuration event."""
            params_obj = DeviceConfigurationRequestEvent.from_dict(params_dict)
        elif identifier == "device_protobuf_msg_event":
            params_obj = DeviceProtobufMsgEventParams.from_dict(params_dict)
        elif identifier == "device_warning_event":
            params_obj = DeviceWarningEventParams.from_dict(params_dict)
        elif identifier == "device_biz_req_event":
            params_obj = DeviceBizReqEventParams.from_dict(params_dict)
        elif identifier == "device_log_progress_event":
            params_obj = DeviceLogProgressEventParams.from_dict(params_dict)
        elif identifier == "device_config_req_event":
            params_obj = payload.get("params", {})
        elif (
            identifier == "device_notification_event"
            or identifier == "device_warning_code_event"
            or identifier == "device_information_event"
        ):
            params_obj = DeviceNotificationEventParams.from_dict(params_dict)
        else:
            raise ValueError(f"Unknown identifier: {identifier} {params_dict}")

        return cls(method=method, id=event_id, params=params_obj, version=version)


@dataclass
class MammotionProtoMsgParams(DataClassORJSONMixin, SerializableType):
    value: DeviceProtobufMsgEventValue
    iot_id: str = ""
    product_key: str = ""
    device_name: str = ""

    @classmethod
    def _deserialize(cls, d: dict[str, Any]) -> "MammotionProtoMsgParams":
        """Override from_dict to allow dict manipulation before conversion."""
        proto: str = d["content"]

        return cls(value=DeviceProtobufMsgEventValue(content=proto))


@dataclass
class MammotionEventMessage(DataClassORJSONMixin):
    id: str
    version: str
    sys: dict
    params: MammotionProtoMsgParams
    method: str
