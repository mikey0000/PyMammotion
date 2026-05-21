from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ModulesFwInfo(_message.Message):
    __slots__ = ["component_id", "component_version", "type"]
    COMPONENT_ID_FIELD_NUMBER: _ClassVar[int]
    COMPONENT_VERSION_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    component_id: str
    component_version: str
    type: int
    def __init__(self, type: _Optional[int] = ..., component_id: _Optional[str] = ..., component_version: _Optional[str] = ...) -> None: ...

class ModulesName(_message.Message):
    __slots__ = ["modules_name"]
    MODULES_NAME_FIELD_NUMBER: _ClassVar[int]
    modules_name: str
    def __init__(self, modules_name: _Optional[str] = ...) -> None: ...

class PdtDeviceFwInfo(_message.Message):
    __slots__ = ["device_version", "modules_info", "result"]
    DEVICE_VERSION_FIELD_NUMBER: _ClassVar[int]
    MODULES_INFO_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    device_version: str
    modules_info: _containers.RepeatedCompositeFieldContainer[ModulesFwInfo]
    result: int
    def __init__(self, device_version: _Optional[str] = ..., modules_info: _Optional[_Iterable[_Union[ModulesFwInfo, _Mapping]]] = ..., result: _Optional[int] = ...) -> None: ...

class PdtInfoReq(_message.Message):
    __slots__ = ["pdt_type", "sesstion_id"]
    PDT_TYPE_FIELD_NUMBER: _ClassVar[int]
    SESSTION_ID_FIELD_NUMBER: _ClassVar[int]
    pdt_type: int
    sesstion_id: str
    def __init__(self, sesstion_id: _Optional[str] = ..., pdt_type: _Optional[int] = ...) -> None: ...

class PdtInfoRsp(_message.Message):
    __slots__ = ["fw_version", "modules", "pdt_data", "sesstion_id"]
    FW_VERSION_FIELD_NUMBER: _ClassVar[int]
    MODULES_FIELD_NUMBER: _ClassVar[int]
    PDT_DATA_FIELD_NUMBER: _ClassVar[int]
    SESSTION_ID_FIELD_NUMBER: _ClassVar[int]
    fw_version: PdtDeviceFwInfo
    modules: ModulesName
    pdt_data: PdtItem
    sesstion_id: str
    def __init__(self, sesstion_id: _Optional[str] = ..., modules: _Optional[_Union[ModulesName, _Mapping]] = ..., pdt_data: _Optional[_Union[PdtItem, _Mapping]] = ..., fw_version: _Optional[_Union[PdtDeviceFwInfo, _Mapping]] = ...) -> None: ...

class PdtItem(_message.Message):
    __slots__ = ["data_msg", "data_state"]
    DATA_MSG_FIELD_NUMBER: _ClassVar[int]
    DATA_STATE_FIELD_NUMBER: _ClassVar[int]
    data_msg: str
    data_state: int
    def __init__(self, data_msg: _Optional[str] = ..., data_state: _Optional[int] = ...) -> None: ...

class PdtMessage(_message.Message):
    __slots__ = ["to_app_get_pdt_info_rsp", "to_app_result_pdt_test_rsp", "to_dev_control_pdt_test_req", "to_dev_get_pdt_info_req"]
    TO_APP_GET_PDT_INFO_RSP_FIELD_NUMBER: _ClassVar[int]
    TO_APP_RESULT_PDT_TEST_RSP_FIELD_NUMBER: _ClassVar[int]
    TO_DEV_CONTROL_PDT_TEST_REQ_FIELD_NUMBER: _ClassVar[int]
    TO_DEV_GET_PDT_INFO_REQ_FIELD_NUMBER: _ClassVar[int]
    to_app_get_pdt_info_rsp: PdtInfoRsp
    to_app_result_pdt_test_rsp: PdtTestReq
    to_dev_control_pdt_test_req: PdtTestMod
    to_dev_get_pdt_info_req: PdtInfoReq
    def __init__(self, to_dev_get_pdt_info_req: _Optional[_Union[PdtInfoReq, _Mapping]] = ..., to_app_get_pdt_info_rsp: _Optional[_Union[PdtInfoRsp, _Mapping]] = ..., to_dev_control_pdt_test_req: _Optional[_Union[PdtTestMod, _Mapping]] = ..., to_app_result_pdt_test_rsp: _Optional[_Union[PdtTestReq, _Mapping]] = ...) -> None: ...

class PdtTestMod(_message.Message):
    __slots__ = ["testmod"]
    TESTMOD_FIELD_NUMBER: _ClassVar[int]
    testmod: int
    def __init__(self, testmod: _Optional[int] = ...) -> None: ...

class PdtTestReq(_message.Message):
    __slots__ = ["control_result"]
    CONTROL_RESULT_FIELD_NUMBER: _ClassVar[int]
    control_result: int
    def __init__(self, control_result: _Optional[int] = ...) -> None: ...
