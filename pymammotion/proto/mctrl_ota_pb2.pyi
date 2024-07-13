from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor
IT_BASE: infoType
IT_OTA: infoType

class MctlOta(_message.Message):
    __slots__ = ["toapp_get_info_rsp", "todev_get_info_req"]
    TOAPP_GET_INFO_RSP_FIELD_NUMBER: _ClassVar[int]
    TODEV_GET_INFO_REQ_FIELD_NUMBER: _ClassVar[int]
    toapp_get_info_rsp: getInfoRsp
    todev_get_info_req: getInfoReq
    def __init__(self, todev_get_info_req: _Optional[_Union[getInfoReq, _Mapping]] = ..., toapp_get_info_rsp: _Optional[_Union[getInfoRsp, _Mapping]] = ...) -> None: ...

class baseInfo(_message.Message):
    __slots__ = ["batt_val", "dev_status", "dev_version", "init_status", "is_tilt"]
    BATT_VAL_FIELD_NUMBER: _ClassVar[int]
    DEV_STATUS_FIELD_NUMBER: _ClassVar[int]
    DEV_VERSION_FIELD_NUMBER: _ClassVar[int]
    INIT_STATUS_FIELD_NUMBER: _ClassVar[int]
    IS_TILT_FIELD_NUMBER: _ClassVar[int]
    batt_val: int
    dev_status: int
    dev_version: str
    init_status: int
    is_tilt: int
    def __init__(self, dev_version: _Optional[str] = ..., dev_status: _Optional[int] = ..., batt_val: _Optional[int] = ..., init_status: _Optional[int] = ..., is_tilt: _Optional[int] = ...) -> None: ...

class getInfoReq(_message.Message):
    __slots__ = ["type"]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    type: infoType
    def __init__(self, type: _Optional[_Union[infoType, str]] = ...) -> None: ...

class getInfoRsp(_message.Message):
    __slots__ = ["base", "ota", "result", "type"]
    BASE_FIELD_NUMBER: _ClassVar[int]
    OTA_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    base: baseInfo
    ota: otaInfo
    result: int
    type: infoType
    def __init__(self, result: _Optional[int] = ..., type: _Optional[_Union[infoType, str]] = ..., base: _Optional[_Union[baseInfo, _Mapping]] = ..., ota: _Optional[_Union[otaInfo, _Mapping]] = ...) -> None: ...

class otaInfo(_message.Message):
    __slots__ = ["message", "otaid", "progress", "result", "version"]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    OTAID_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    message: str
    otaid: str
    progress: int
    result: int
    version: str
    def __init__(self, otaid: _Optional[str] = ..., version: _Optional[str] = ..., progress: _Optional[int] = ..., result: _Optional[int] = ..., message: _Optional[str] = ...) -> None: ...

class infoType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
