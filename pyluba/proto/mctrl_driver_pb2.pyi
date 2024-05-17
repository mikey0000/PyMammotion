from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DrvKnifeHeight(_message.Message):
    __slots__ = ["knifeHeight"]
    KNIFEHEIGHT_FIELD_NUMBER: _ClassVar[int]
    knifeHeight: int
    def __init__(self, knifeHeight: _Optional[int] = ...) -> None: ...

class DrvKnifeStatus(_message.Message):
    __slots__ = ["knife_status"]
    KNIFE_STATUS_FIELD_NUMBER: _ClassVar[int]
    knife_status: int
    def __init__(self, knife_status: _Optional[int] = ...) -> None: ...

class DrvMotionCtrl(_message.Message):
    __slots__ = ["setAngularSpeed", "setLinearSpeed"]
    SETANGULARSPEED_FIELD_NUMBER: _ClassVar[int]
    SETLINEARSPEED_FIELD_NUMBER: _ClassVar[int]
    setAngularSpeed: int
    setLinearSpeed: int
    def __init__(self, setAngularSpeed: _Optional[int] = ..., setLinearSpeed: _Optional[int] = ...) -> None: ...

class DrvSrSpeed(_message.Message):
    __slots__ = ["rw", "speed"]
    RW_FIELD_NUMBER: _ClassVar[int]
    SPEED_FIELD_NUMBER: _ClassVar[int]
    rw: int
    speed: float
    def __init__(self, rw: _Optional[int] = ..., speed: _Optional[float] = ...) -> None: ...

class MctrlDriver(_message.Message):
    __slots__ = ["bidire_knife_height_report", "bidire_speed_read_set", "toapp_knife_status", "todev_devmotion_ctrl", "todev_knife_height_set"]
    BIDIRE_KNIFE_HEIGHT_REPORT_FIELD_NUMBER: _ClassVar[int]
    BIDIRE_SPEED_READ_SET_FIELD_NUMBER: _ClassVar[int]
    TOAPP_KNIFE_STATUS_FIELD_NUMBER: _ClassVar[int]
    TODEV_DEVMOTION_CTRL_FIELD_NUMBER: _ClassVar[int]
    TODEV_KNIFE_HEIGHT_SET_FIELD_NUMBER: _ClassVar[int]
    bidire_knife_height_report: DrvKnifeHeight
    bidire_speed_read_set: DrvSrSpeed
    toapp_knife_status: DrvKnifeStatus
    todev_devmotion_ctrl: DrvMotionCtrl
    todev_knife_height_set: DrvKnifeHeight
    def __init__(self, todev_devmotion_ctrl: _Optional[_Union[DrvMotionCtrl, _Mapping]] = ..., todev_knife_height_set: _Optional[_Union[DrvKnifeHeight, _Mapping]] = ..., bidire_speed_read_set: _Optional[_Union[DrvSrSpeed, _Mapping]] = ..., bidire_knife_height_report: _Optional[_Union[DrvKnifeHeight, _Mapping]] = ..., toapp_knife_status: _Optional[_Union[DrvKnifeStatus, _Mapping]] = ...) -> None: ...
