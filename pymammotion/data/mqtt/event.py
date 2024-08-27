from base64 import b64decode
from dataclasses import dataclass
from typing import Any, Literal, Optional, Union

from google.protobuf import json_format
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import SerializableType

from pymammotion.proto import luba_msg_pb2


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

    # Campi opzionali
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

    @classmethod
    def from_dicts(cls, payload: dict) -> "ThingEventMessage":
        """Deserializza il payload JSON in un'istanza di ThingEventMessage."""
        method = payload.get("method")
        event_id = payload.get("id")
        params_dict = payload.get("params", {})
        version = payload.get("version")

        # Determina quale classe usare per i parametri
        identifier = params_dict.get("identifier")
        if identifier == "device_protobuf_msg_event":
            params_obj = DeviceProtobufMsgEventParams(**params_dict)
        elif identifier == "device_warning_event":
            params_obj = DeviceWarningEventParams(**params_dict)
        else:
            raise ValueError(f"Unknown identifier: {identifier}")

        # Crea e restituisce l'istanza di ThingEventMessage
        return cls(method=method, id=event_id, params=params_obj, version=version)
