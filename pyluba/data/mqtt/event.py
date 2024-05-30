from base64 import b64decode
from dataclasses import dataclass
from typing import Any, Literal, Union

from google.protobuf import json_format
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import SerializableType

from pyluba.proto import luba_msg_pb2


class Base64EncodedProtobuf(SerializableType):
    def __init__(self, proto: str):
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
    content: Base64EncodedProtobuf

@dataclass
class DeviceWarningEventValue(DataClassORJSONMixin):
    # TODO: enum for error codes
    # (see resources/res/values-en-rUS/strings.xml in APK)
    code: int

@dataclass
class GeneralParams(DataClassORJSONMixin):
    identifier: str
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

@dataclass
class DeviceProtobufMsgEventParams(GeneralParams):
    identifier: Literal["device_protobuf_msg_event"]
    type: Literal["info"]
    value: DeviceProtobufMsgEventValue

@dataclass
class DeviceWarningEventParams(GeneralParams):
    identifier: Literal["device_warning_event"]
    type: Literal["alert"]
    value: DeviceWarningEventValue

@dataclass
class ThingEventMessage(DataClassORJSONMixin):
    method: Literal["thing.events"]
    id: str
    params: Union[DeviceProtobufMsgEventParams, DeviceWarningEventParams]
    version: Literal["1.0"]
