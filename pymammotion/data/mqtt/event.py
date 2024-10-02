from base64 import b64decode
from dataclasses import dataclass
from typing import Any, Literal, Optional, Union

from google.protobuf import json_format
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import SerializableType

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
    groupIdList: list[str]
    groupId: str
    categoryKey: Literal["LawnMower"]
    batchId: str
    gmtCreate: int
    productKey: str
    type: str
    deviceName: str
    iotId: str
    checkLevel: int
    namespace: str
    tenantId: str
    name: str
    thingType: Literal["DEVICE"]
    time: int
    tenantInstanceId: str
    value: Any

    identifier: Optional[str] = None
    checkFailedData: Optional[dict] = None
    _tenantId: Optional[str] = None
    generateTime: Optional[int] = None
    JMSXDeliveryCount: Optional[int] = None
    qos: Optional[int] = None
    requestId: Optional[str] = None
    _categoryKey: Optional[str] = None
    deviceType: Optional[str] = None
    _traceId: Optional[str] = None


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

    identifier: Literal["device_notification_event", "device_warning_code_event"]
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
class ThingEventMessage(DataClassORJSONMixin):
    method: Literal["thing.events", "thing.properties"]
    id: str
    params: Union[DeviceProtobufMsgEventParams, DeviceWarningEventParams, dict]
    version: Literal["1.0"]

    @classmethod
    def from_dicts(cls, payload: dict) -> "ThingEventMessage":
        """Deserialize payload JSON ThingEventMessage."""
        method = payload.get("method")
        event_id = payload.get("id")
        params_dict = payload.get("params", {})
        version = payload.get("version")

        # Determina quale classe usare per i parametri
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
        elif identifier == "device_config_req_event":
            params_obj = payload.get("params", {})
        elif identifier == "device_notification_event" or identifier == "device_warning_code_event":
            params_obj = DeviceNotificationEventParams.from_dict(params_dict)
        else:
            raise ValueError(f"Unknown identifier: {identifier} {params_dict}")

        return cls(method=method, id=event_id, params=params_obj, version=version)
