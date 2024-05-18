from base64 import b64decode
from dataclasses import dataclass
from typing import Literal, Any, Union

from pyluba.proto import luba_msg_pb2

from mashumaro.mixins.orjson import DataClassORJSONMixin

class Base64EncodedProtobuf:
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
        return data

@dataclass
class DeviceProtobufMsgEventValue(DataClassORJSONMixin):
    content: Base64EncodedProtobuf

@dataclass
class DeviceWarningEventValue(DataClassORJSONMixin):
    # TODO: enum for error codes
    # (see resources/res/values-en-rUS/strings.xml in APK)
    code: int


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


class DeviceProtobufMsgEventParams(GeneralParams):
    identifier: Literal["device_protobuf_msg_event"]
    type: Literal["info"]
    value: DeviceProtobufMsgEventValue


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
