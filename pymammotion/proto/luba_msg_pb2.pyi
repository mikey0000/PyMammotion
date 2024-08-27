from pymammotion.proto import basestation_pb2 as _basestation_pb2
from pymammotion.proto import mctrl_driver_pb2 as _mctrl_driver_pb2
from pymammotion.proto import mctrl_nav_pb2 as _mctrl_nav_pb2
from pymammotion.proto import mctrl_sys_pb2 as _mctrl_sys_pb2
from pymammotion.proto import dev_net_pb2 as _dev_net_pb2
from pymammotion.proto import mctrl_ota_pb2 as _mctrl_ota_pb2
from pymammotion.proto import luba_mul_pb2 as _luba_mul_pb2
from pymammotion.proto import mctrl_pept_pb2 as _mctrl_pept_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor
DEV_BASESTATION: MsgDevice
DEV_BMS: MsgDevice
DEV_COMM_ESP: MsgDevice
DEV_IOTCTRL: MsgDevice
DEV_IOTSERVER: MsgDevice
DEV_LEFTMOTOR: MsgDevice
DEV_LOCALIZATION: MsgDevice
DEV_MAINCTL: MsgDevice
DEV_MOBILEAPP: MsgDevice
DEV_NAVIGATION: MsgDevice
DEV_PERCEPTION: MsgDevice
DEV_RIGHTMOTOR: MsgDevice
DEV_RTKCLI: MsgDevice
DEV_USBHOST: MsgDevice
MSG_ATTR_NONE: MsgAttr
MSG_ATTR_REPORT: MsgAttr
MSG_ATTR_REQ: MsgAttr
MSG_ATTR_RESP: MsgAttr
MSG_CMD_TYPE_APPLICATION: MsgCmdType
MSG_CMD_TYPE_EMBED_DRIVER: MsgCmdType
MSG_CMD_TYPE_EMBED_MIDWARE: MsgCmdType
MSG_CMD_TYPE_EMBED_OTA: MsgCmdType
MSG_CMD_TYPE_EMBED_SYS: MsgCmdType
MSG_CMD_TYPE_ESP: MsgCmdType
MSG_CMD_TYPE_LOCALIZATION: MsgCmdType
MSG_CMD_TYPE_MUL: MsgCmdType
MSG_CMD_TYPE_NAV: MsgCmdType
MSG_CMD_TYPE_PEPT: MsgCmdType
MSG_CMD_TYPE_PLANNING: MsgCmdType
MSG_CMD_TYPE_START: MsgCmdType
SOC_MODULE_MULTIMEDIA: MsgDevice

class LubaMsg(_message.Message):
    __slots__ = ["base", "driver", "msgattr", "msgtype", "mul", "nav", "net", "null", "ota", "pept", "rcver", "sender", "seqs", "subtype", "sys", "timestamp", "version"]
    BASE_FIELD_NUMBER: _ClassVar[int]
    DRIVER_FIELD_NUMBER: _ClassVar[int]
    MSGATTR_FIELD_NUMBER: _ClassVar[int]
    MSGTYPE_FIELD_NUMBER: _ClassVar[int]
    MUL_FIELD_NUMBER: _ClassVar[int]
    NAV_FIELD_NUMBER: _ClassVar[int]
    NET_FIELD_NUMBER: _ClassVar[int]
    NULL_FIELD_NUMBER: _ClassVar[int]
    OTA_FIELD_NUMBER: _ClassVar[int]
    PEPT_FIELD_NUMBER: _ClassVar[int]
    RCVER_FIELD_NUMBER: _ClassVar[int]
    SENDER_FIELD_NUMBER: _ClassVar[int]
    SEQS_FIELD_NUMBER: _ClassVar[int]
    SUBTYPE_FIELD_NUMBER: _ClassVar[int]
    SYS_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    base: _basestation_pb2.BaseStation
    driver: _mctrl_driver_pb2.MctlDriver
    msgattr: MsgAttr
    msgtype: MsgCmdType
    mul: _luba_mul_pb2.SocMul
    nav: _mctrl_nav_pb2.MctlNav
    net: _dev_net_pb2.DevNet
    null: MsgNull
    ota: _mctrl_ota_pb2.MctlOta
    pept: _mctrl_pept_pb2.MctlPept
    rcver: MsgDevice
    sender: MsgDevice
    seqs: int
    subtype: int
    sys: _mctrl_sys_pb2.MctlSys
    timestamp: int
    version: int
    def __init__(self, msgtype: _Optional[_Union[MsgCmdType, str]] = ..., sender: _Optional[_Union[MsgDevice, str]] = ..., rcver: _Optional[_Union[MsgDevice, str]] = ..., msgattr: _Optional[_Union[MsgAttr, str]] = ..., seqs: _Optional[int] = ..., version: _Optional[int] = ..., subtype: _Optional[int] = ..., net: _Optional[_Union[_dev_net_pb2.DevNet, _Mapping]] = ..., sys: _Optional[_Union[_mctrl_sys_pb2.MctlSys, _Mapping]] = ..., nav: _Optional[_Union[_mctrl_nav_pb2.MctlNav, _Mapping]] = ..., driver: _Optional[_Union[_mctrl_driver_pb2.MctlDriver, _Mapping]] = ..., ota: _Optional[_Union[_mctrl_ota_pb2.MctlOta, _Mapping]] = ..., mul: _Optional[_Union[_luba_mul_pb2.SocMul, _Mapping]] = ..., null: _Optional[_Union[MsgNull, _Mapping]] = ..., pept: _Optional[_Union[_mctrl_pept_pb2.MctlPept, _Mapping]] = ..., base: _Optional[_Union[_basestation_pb2.BaseStation, _Mapping]] = ..., timestamp: _Optional[int] = ...) -> None: ...

class MsgNull(_message.Message):
    __slots__ = []
    def __init__(self) -> None: ...

class MsgCmdType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class MsgAttr(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class MsgDevice(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
