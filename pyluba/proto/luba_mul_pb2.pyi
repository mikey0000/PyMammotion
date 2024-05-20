from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

ACTIVATION_FAILED: MUL_VIDEO_ERROR_CODE
ALL: MUL_CAMERA_POSITION
CELLULAR_RESTRICTION: MUL_VIDEO_ERROR_CODE
CREATE_CHANNEL_FAILED: MUL_VIDEO_ERROR_CODE
DESCRIPTOR: _descriptor.FileDescriptor
ENGLISH: MUL_LANGUAGE
GERMAN: MUL_LANGUAGE
HW_ERROR: MUL_WIPER_ERROR_CODE
LEFT: MUL_CAMERA_POSITION
NAVIGATION_WORK_FORBID: MUL_WIPER_ERROR_CODE
NETWORK_NOT_AVAILABLE: MUL_VIDEO_ERROR_CODE
PARAM_INVAILD: MUL_VIDEO_ERROR_CODE
REAR: MUL_CAMERA_POSITION
RIGHT: MUL_CAMERA_POSITION
SET_SUCCESS: MUL_WIPER_ERROR_CODE
SUCCESS: MUL_VIDEO_ERROR_CODE

class MulAudioCfg(_message.Message):
    __slots__ = ["au_language", "au_switch"]
    AU_LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    AU_SWITCH_FIELD_NUMBER: _ClassVar[int]
    au_language: MUL_LANGUAGE
    au_switch: int
    def __init__(self, au_switch: _Optional[int] = ..., au_language: _Optional[_Union[MUL_LANGUAGE, str]] = ...) -> None: ...

class MulSetAudio(_message.Message):
    __slots__ = ["at_switch", "au_language"]
    AT_SWITCH_FIELD_NUMBER: _ClassVar[int]
    AU_LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    at_switch: int
    au_language: MUL_LANGUAGE
    def __init__(self, at_switch: _Optional[int] = ..., au_language: _Optional[_Union[MUL_LANGUAGE, str]] = ...) -> None: ...

class MulSetVideo(_message.Message):
    __slots__ = ["position", "vi_switch"]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    VI_SWITCH_FIELD_NUMBER: _ClassVar[int]
    position: MUL_CAMERA_POSITION
    vi_switch: int
    def __init__(self, position: _Optional[_Union[MUL_CAMERA_POSITION, str]] = ..., vi_switch: _Optional[int] = ...) -> None: ...

class MulSetVideoAck(_message.Message):
    __slots__ = ["error_code"]
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    error_code: MUL_VIDEO_ERROR_CODE
    def __init__(self, error_code: _Optional[_Union[MUL_VIDEO_ERROR_CODE, str]] = ...) -> None: ...

class MulSetWiper(_message.Message):
    __slots__ = ["round"]
    ROUND_FIELD_NUMBER: _ClassVar[int]
    round: int
    def __init__(self, round: _Optional[int] = ...) -> None: ...

class MulSetWiperAck(_message.Message):
    __slots__ = ["error_code"]
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    error_code: MUL_WIPER_ERROR_CODE
    def __init__(self, error_code: _Optional[_Union[MUL_WIPER_ERROR_CODE, str]] = ...) -> None: ...

class SocMul(_message.Message):
    __slots__ = ["audio_cfg", "set_audio", "set_video", "set_video_ack", "set_wiper", "set_wiper_ack"]
    AUDIO_CFG_FIELD_NUMBER: _ClassVar[int]
    SET_AUDIO_FIELD_NUMBER: _ClassVar[int]
    SET_VIDEO_ACK_FIELD_NUMBER: _ClassVar[int]
    SET_VIDEO_FIELD_NUMBER: _ClassVar[int]
    SET_WIPER_ACK_FIELD_NUMBER: _ClassVar[int]
    SET_WIPER_FIELD_NUMBER: _ClassVar[int]
    audio_cfg: MulAudioCfg
    set_audio: MulSetAudio
    set_video: MulSetVideo
    set_video_ack: MulSetVideoAck
    set_wiper: MulSetWiper
    set_wiper_ack: MulSetWiperAck
    def __init__(self, set_audio: _Optional[_Union[MulSetAudio, _Mapping]] = ..., audio_cfg: _Optional[_Union[MulAudioCfg, _Mapping]] = ..., set_video: _Optional[_Union[MulSetVideo, _Mapping]] = ..., set_video_ack: _Optional[_Union[MulSetVideoAck, _Mapping]] = ..., set_wiper: _Optional[_Union[MulSetWiper, _Mapping]] = ..., set_wiper_ack: _Optional[_Union[MulSetWiperAck, _Mapping]] = ...) -> None: ...

class MUL_LANGUAGE(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class MUL_CAMERA_POSITION(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class MUL_VIDEO_ERROR_CODE(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class MUL_WIPER_ERROR_CODE(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
