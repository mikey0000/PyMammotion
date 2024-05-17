from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class BaseInfo(_message.Message):
    __slots__ = ["battVal", "devStatus", "devVersion", "initStatus", "isTilt"]
    BATTVAL_FIELD_NUMBER: _ClassVar[int]
    DEVSTATUS_FIELD_NUMBER: _ClassVar[int]
    DEVVERSION_FIELD_NUMBER: _ClassVar[int]
    INITSTATUS_FIELD_NUMBER: _ClassVar[int]
    ISTILT_FIELD_NUMBER: _ClassVar[int]
    battVal: int
    devStatus: int
    devVersion: str
    initStatus: int
    isTilt: int
    def __init__(self, devVersion: _Optional[str] = ..., devStatus: _Optional[int] = ..., battVal: _Optional[int] = ..., initStatus: _Optional[int] = ..., isTilt: _Optional[int] = ...) -> None: ...

class MctrlOta(_message.Message):
    __slots__ = ["to_app_get_info_rsp", "to_dev_get_info_req"]
    TO_APP_GET_INFO_RSP_FIELD_NUMBER: _ClassVar[int]
    TO_DEV_GET_INFO_REQ_FIELD_NUMBER: _ClassVar[int]
    to_app_get_info_rsp: ToAppGetInfoRsp
    to_dev_get_info_req: ToDevGetInfoReq
    def __init__(self, to_dev_get_info_req: _Optional[_Union[ToDevGetInfoReq, _Mapping]] = ..., to_app_get_info_rsp: _Optional[_Union[ToAppGetInfoRsp, _Mapping]] = ...) -> None: ...

class OtaInfo(_message.Message):
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

class ToAppGetInfoRsp(_message.Message):
    __slots__ = ["base", "ota", "result", "type"]
    class InfoCase(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = []
    BASE: ToAppGetInfoRsp.InfoCase
    BASE_FIELD_NUMBER: _ClassVar[int]
    INFO_NOT_SET: ToAppGetInfoRsp.InfoCase
    OTA: ToAppGetInfoRsp.InfoCase
    OTA_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    base: BaseInfo
    ota: OtaInfo
    result: int
    type: ToAppGetInfoRsp.InfoCase
    def __init__(self, result: _Optional[int] = ..., type: _Optional[_Union[ToAppGetInfoRsp.InfoCase, str]] = ..., base: _Optional[_Union[BaseInfo, _Mapping]] = ..., ota: _Optional[_Union[OtaInfo, _Mapping]] = ...) -> None: ...

class ToDevGetInfoReq(_message.Message):
    __slots__ = ["type"]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    type: int
    def __init__(self, type: _Optional[int] = ...) -> None: ...
