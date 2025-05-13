from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor
IT_BASE: infoType
IT_OTA: infoType

class FotaInfo_t(_message.Message):
    __slots__ = ["need_ota_img_size", "need_ota_num", "ota_oid", "ota_otype", "ota_version"]
    NEED_OTA_IMG_SIZE_FIELD_NUMBER: _ClassVar[int]
    NEED_OTA_NUM_FIELD_NUMBER: _ClassVar[int]
    OTA_OID_FIELD_NUMBER: _ClassVar[int]
    OTA_OTYPE_FIELD_NUMBER: _ClassVar[int]
    OTA_VERSION_FIELD_NUMBER: _ClassVar[int]
    need_ota_img_size: int
    need_ota_num: int
    ota_oid: str
    ota_otype: int
    ota_version: str
    def __init__(self, need_ota_num: _Optional[int] = ..., need_ota_img_size: _Optional[int] = ..., ota_otype: _Optional[int] = ..., ota_oid: _Optional[str] = ..., ota_version: _Optional[str] = ...) -> None: ...

class FotaSubInfo_t(_message.Message):
    __slots__ = ["sub_img_size", "sub_img_url", "sub_mod_id", "sub_mod_ota_flag", "sub_mod_version"]
    SUB_IMG_SIZE_FIELD_NUMBER: _ClassVar[int]
    SUB_IMG_URL_FIELD_NUMBER: _ClassVar[int]
    SUB_MOD_ID_FIELD_NUMBER: _ClassVar[int]
    SUB_MOD_OTA_FLAG_FIELD_NUMBER: _ClassVar[int]
    SUB_MOD_VERSION_FIELD_NUMBER: _ClassVar[int]
    sub_img_size: int
    sub_img_url: str
    sub_mod_id: int
    sub_mod_ota_flag: int
    sub_mod_version: str
    def __init__(self, sub_mod_ota_flag: _Optional[int] = ..., sub_mod_id: _Optional[int] = ..., sub_img_size: _Optional[int] = ..., sub_mod_version: _Optional[str] = ..., sub_img_url: _Optional[str] = ...) -> None: ...

class MctlOta(_message.Message):
    __slots__ = ["fota_info", "fota_sub_info", "fw_download_ctrl", "toapp_get_info_rsp", "todev_get_info_req"]
    FOTA_INFO_FIELD_NUMBER: _ClassVar[int]
    FOTA_SUB_INFO_FIELD_NUMBER: _ClassVar[int]
    FW_DOWNLOAD_CTRL_FIELD_NUMBER: _ClassVar[int]
    TOAPP_GET_INFO_RSP_FIELD_NUMBER: _ClassVar[int]
    TODEV_GET_INFO_REQ_FIELD_NUMBER: _ClassVar[int]
    fota_info: FotaInfo_t
    fota_sub_info: FotaSubInfo_t
    fw_download_ctrl: fwDownloadCtrl
    toapp_get_info_rsp: getInfoRsp
    todev_get_info_req: getInfoReq
    def __init__(self, todev_get_info_req: _Optional[_Union[getInfoReq, _Mapping]] = ..., toapp_get_info_rsp: _Optional[_Union[getInfoRsp, _Mapping]] = ..., fw_download_ctrl: _Optional[_Union[fwDownloadCtrl, _Mapping]] = ..., fota_info: _Optional[_Union[FotaInfo_t, _Mapping]] = ..., fota_sub_info: _Optional[_Union[FotaSubInfo_t, _Mapping]] = ...) -> None: ...

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

class downlink_t(_message.Message):
    __slots__ = ["data", "fw_id", "pkg_seq"]
    DATA_FIELD_NUMBER: _ClassVar[int]
    FW_ID_FIELD_NUMBER: _ClassVar[int]
    PKG_SEQ_FIELD_NUMBER: _ClassVar[int]
    data: _containers.RepeatedScalarFieldContainer[int]
    fw_id: int
    pkg_seq: int
    def __init__(self, fw_id: _Optional[int] = ..., pkg_seq: _Optional[int] = ..., data: _Optional[_Iterable[int]] = ...) -> None: ...

class fwDownloadCtrl(_message.Message):
    __slots__ = ["cmd", "downlink", "uplink"]
    CMD_FIELD_NUMBER: _ClassVar[int]
    DOWNLINK_FIELD_NUMBER: _ClassVar[int]
    UPLINK_FIELD_NUMBER: _ClassVar[int]
    cmd: int
    downlink: downlink_t
    uplink: uplink_t
    def __init__(self, uplink: _Optional[_Union[uplink_t, _Mapping]] = ..., downlink: _Optional[_Union[downlink_t, _Mapping]] = ..., cmd: _Optional[int] = ...) -> None: ...

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
    def __init__(self, base: _Optional[_Union[baseInfo, _Mapping]] = ..., ota: _Optional[_Union[otaInfo, _Mapping]] = ..., result: _Optional[int] = ..., type: _Optional[_Union[infoType, str]] = ...) -> None: ...

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

class uplink_t(_message.Message):
    __slots__ = ["pkg_seq", "status"]
    PKG_SEQ_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    pkg_seq: int
    status: int
    def __init__(self, pkg_seq: _Optional[int] = ..., status: _Optional[int] = ...) -> None: ...

class infoType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
