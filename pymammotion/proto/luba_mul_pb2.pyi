from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

ACTIVATION_FAILED: MUL_VIDEO_ERROR_CODE
ALL: MUL_CAMERA_POSITION
CREATE_CHANNEL_FAILED: MUL_VIDEO_ERROR_CODE
DESCRIPTOR: _descriptor.FileDescriptor
DUTCH: MUL_LANGUAGE
ENGLISH: MUL_LANGUAGE
FRENCH: MUL_LANGUAGE
GERMAN: MUL_LANGUAGE
HW_ERROR: MUL_WIPER_ERROR_CODE
ITALIAN: MUL_LANGUAGE
LEFT: MUL_CAMERA_POSITION
MAN: MUL_SEX
NAVIGATION_WORK_FORBID: MUL_WIPER_ERROR_CODE
NETWORK_NOT_AVAILABLE: MUL_VIDEO_ERROR_CODE
NONE_LAN: MUL_LANGUAGE
NONE_SEX: MUL_SEX
PARAM_INVAILD: MUL_VIDEO_ERROR_CODE
PORTUGUESE: MUL_LANGUAGE
REAR: MUL_CAMERA_POSITION
RIGHT: MUL_CAMERA_POSITION
SET_SUCCESS: MUL_WIPER_ERROR_CODE
SPANISH: MUL_LANGUAGE
SUCCESS: MUL_VIDEO_ERROR_CODE
SWEDISH: MUL_LANGUAGE
WOMAN: MUL_SEX
manual_power_off: lamp_manual_ctrl_sta
manual_power_on: lamp_manual_ctrl_sta
power_ctrl_on: lamp_ctrl_sta
power_off: lamp_ctrl_sta
power_on: lamp_ctrl_sta

class GetHeadlamp(_message.Message):
    __slots__ = ["get_ids"]
    GET_IDS_FIELD_NUMBER: _ClassVar[int]
    get_ids: int
    def __init__(self, get_ids: _Optional[int] = ...) -> None: ...

class Getlamprsp(_message.Message):
    __slots__ = ["get_ids", "lamp_bright", "lamp_ctrl", "lamp_manual_ctrl", "result"]
    GET_IDS_FIELD_NUMBER: _ClassVar[int]
    LAMP_BRIGHT_FIELD_NUMBER: _ClassVar[int]
    LAMP_CTRL_FIELD_NUMBER: _ClassVar[int]
    LAMP_MANUAL_CTRL_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    get_ids: int
    lamp_bright: int
    lamp_ctrl: lamp_ctrl_sta
    lamp_manual_ctrl: lamp_manual_ctrl_sta
    result: int
    def __init__(self, get_ids: _Optional[int] = ..., result: _Optional[int] = ..., lamp_ctrl: _Optional[_Union[lamp_ctrl_sta, str]] = ..., lamp_bright: _Optional[int] = ..., lamp_manual_ctrl: _Optional[_Union[lamp_manual_ctrl_sta, str]] = ...) -> None: ...

class MulAudioCfg(_message.Message):
    __slots__ = ["au_language", "au_switch", "sex"]
    AU_LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    AU_SWITCH_FIELD_NUMBER: _ClassVar[int]
    SEX_FIELD_NUMBER: _ClassVar[int]
    au_language: MUL_LANGUAGE
    au_switch: int
    sex: MUL_SEX
    def __init__(self, au_switch: _Optional[int] = ..., au_language: _Optional[_Union[MUL_LANGUAGE, str]] = ..., sex: _Optional[_Union[MUL_SEX, str]] = ...) -> None: ...

class MulSetAudio(_message.Message):
    __slots__ = ["at_switch", "au_language", "sex"]
    AT_SWITCH_FIELD_NUMBER: _ClassVar[int]
    AU_LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    SEX_FIELD_NUMBER: _ClassVar[int]
    at_switch: int
    au_language: MUL_LANGUAGE
    sex: MUL_SEX
    def __init__(self, at_switch: _Optional[int] = ..., au_language: _Optional[_Union[MUL_LANGUAGE, str]] = ..., sex: _Optional[_Union[MUL_SEX, str]] = ...) -> None: ...

class MulSetEncode(_message.Message):
    __slots__ = ["encode"]
    ENCODE_FIELD_NUMBER: _ClassVar[int]
    encode: bool
    def __init__(self, encode: bool = ...) -> None: ...

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

class SetHeadlamp(_message.Message):
    __slots__ = ["ctrl_lamp_bright", "lamp_bright", "lamp_ctrl", "lamp_manual_ctrl", "lamp_power_ctrl", "set_ids"]
    CTRL_LAMP_BRIGHT_FIELD_NUMBER: _ClassVar[int]
    LAMP_BRIGHT_FIELD_NUMBER: _ClassVar[int]
    LAMP_CTRL_FIELD_NUMBER: _ClassVar[int]
    LAMP_MANUAL_CTRL_FIELD_NUMBER: _ClassVar[int]
    LAMP_POWER_CTRL_FIELD_NUMBER: _ClassVar[int]
    SET_IDS_FIELD_NUMBER: _ClassVar[int]
    ctrl_lamp_bright: bool
    lamp_bright: int
    lamp_ctrl: lamp_ctrl_sta
    lamp_manual_ctrl: lamp_manual_ctrl_sta
    lamp_power_ctrl: int
    set_ids: int
    def __init__(self, set_ids: _Optional[int] = ..., lamp_power_ctrl: _Optional[int] = ..., lamp_ctrl: _Optional[_Union[lamp_ctrl_sta, str]] = ..., ctrl_lamp_bright: bool = ..., lamp_bright: _Optional[int] = ..., lamp_manual_ctrl: _Optional[_Union[lamp_manual_ctrl_sta, str]] = ...) -> None: ...

class Setlamprsp(_message.Message):
    __slots__ = ["result", "set_ids"]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SET_IDS_FIELD_NUMBER: _ClassVar[int]
    result: int
    set_ids: int
    def __init__(self, set_ids: _Optional[int] = ..., result: _Optional[int] = ...) -> None: ...

class SocMul(_message.Message):
    __slots__ = ["audio_cfg", "get_lamp", "get_lamp_rsp", "req_encode", "set_audio", "set_lamp", "set_lamp_rsp", "set_video", "set_video_ack", "set_wiper", "set_wiper_ack"]
    AUDIO_CFG_FIELD_NUMBER: _ClassVar[int]
    GET_LAMP_FIELD_NUMBER: _ClassVar[int]
    GET_LAMP_RSP_FIELD_NUMBER: _ClassVar[int]
    REQ_ENCODE_FIELD_NUMBER: _ClassVar[int]
    SET_AUDIO_FIELD_NUMBER: _ClassVar[int]
    SET_LAMP_FIELD_NUMBER: _ClassVar[int]
    SET_LAMP_RSP_FIELD_NUMBER: _ClassVar[int]
    SET_VIDEO_ACK_FIELD_NUMBER: _ClassVar[int]
    SET_VIDEO_FIELD_NUMBER: _ClassVar[int]
    SET_WIPER_ACK_FIELD_NUMBER: _ClassVar[int]
    SET_WIPER_FIELD_NUMBER: _ClassVar[int]
    audio_cfg: MulAudioCfg
    get_lamp: GetHeadlamp
    get_lamp_rsp: Getlamprsp
    req_encode: MulSetEncode
    set_audio: MulSetAudio
    set_lamp: SetHeadlamp
    set_lamp_rsp: Setlamprsp
    set_video: MulSetVideo
    set_video_ack: MulSetVideoAck
    set_wiper: MulSetWiper
    set_wiper_ack: MulSetWiperAck
    def __init__(self, set_audio: _Optional[_Union[MulSetAudio, _Mapping]] = ..., audio_cfg: _Optional[_Union[MulAudioCfg, _Mapping]] = ..., set_video: _Optional[_Union[MulSetVideo, _Mapping]] = ..., set_video_ack: _Optional[_Union[MulSetVideoAck, _Mapping]] = ..., set_wiper: _Optional[_Union[MulSetWiper, _Mapping]] = ..., set_wiper_ack: _Optional[_Union[MulSetWiperAck, _Mapping]] = ..., get_lamp: _Optional[_Union[GetHeadlamp, _Mapping]] = ..., set_lamp: _Optional[_Union[SetHeadlamp, _Mapping]] = ..., set_lamp_rsp: _Optional[_Union[Setlamprsp, _Mapping]] = ..., get_lamp_rsp: _Optional[_Union[Getlamprsp, _Mapping]] = ..., req_encode: _Optional[_Union[MulSetEncode, _Mapping]] = ...) -> None: ...

class MUL_LANGUAGE(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class MUL_SEX(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class MUL_CAMERA_POSITION(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class MUL_VIDEO_ERROR_CODE(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class MUL_WIPER_ERROR_CODE(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class lamp_ctrl_sta(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class lamp_manual_ctrl_sta(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
