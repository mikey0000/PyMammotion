from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MctlPept(_message.Message):
    __slots__ = ["perception_obstacles_visualization", "perception_universal_buff"]
    PERCEPTION_OBSTACLES_VISUALIZATION_FIELD_NUMBER: _ClassVar[int]
    PERCEPTION_UNIVERSAL_BUFF_FIELD_NUMBER: _ClassVar[int]
    perception_obstacles_visualization: perception_obstacles_visualization_t
    perception_universal_buff: perception_universal_buff_t
    def __init__(self, perception_obstacles_visualization: _Optional[_Union[perception_obstacles_visualization_t, _Mapping]] = ..., perception_universal_buff: _Optional[_Union[perception_universal_buff_t, _Mapping]] = ...) -> None: ...

class perception_obstacles_t(_message.Message):
    __slots__ = ["label", "num", "points_x", "points_y"]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    NUM_FIELD_NUMBER: _ClassVar[int]
    POINTS_X_FIELD_NUMBER: _ClassVar[int]
    POINTS_Y_FIELD_NUMBER: _ClassVar[int]
    label: int
    num: int
    points_x: _containers.RepeatedScalarFieldContainer[int]
    points_y: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, label: _Optional[int] = ..., num: _Optional[int] = ..., points_x: _Optional[_Iterable[int]] = ..., points_y: _Optional[_Iterable[int]] = ...) -> None: ...

class perception_obstacles_visualization_t(_message.Message):
    __slots__ = ["is_heart_beat", "num", "obstacles", "scale", "timestamp"]
    IS_HEART_BEAT_FIELD_NUMBER: _ClassVar[int]
    NUM_FIELD_NUMBER: _ClassVar[int]
    OBSTACLES_FIELD_NUMBER: _ClassVar[int]
    SCALE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    is_heart_beat: int
    num: int
    obstacles: _containers.RepeatedCompositeFieldContainer[perception_obstacles_t]
    scale: float
    timestamp: float
    def __init__(self, is_heart_beat: _Optional[int] = ..., num: _Optional[int] = ..., obstacles: _Optional[_Iterable[_Union[perception_obstacles_t, _Mapping]]] = ..., timestamp: _Optional[float] = ..., scale: _Optional[float] = ...) -> None: ...

class perception_universal_buff_t(_message.Message):
    __slots__ = ["perception_len", "perception_type", "universal_buff"]
    PERCEPTION_LEN_FIELD_NUMBER: _ClassVar[int]
    PERCEPTION_TYPE_FIELD_NUMBER: _ClassVar[int]
    UNIVERSAL_BUFF_FIELD_NUMBER: _ClassVar[int]
    perception_len: int
    perception_type: int
    universal_buff: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, perception_type: _Optional[int] = ..., perception_len: _Optional[int] = ..., universal_buff: _Optional[_Iterable[int]] = ...) -> None: ...
