from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PlanJobSet(_message.Message):
    __slots__ = ["cmd", "day", "deviceid", "enable", "enddate", "jobid", "jobname", "operating_power", "planindex", "remained_seconds", "result", "speed", "startdate", "starttime", "sub_mode", "totalplannum", "triggertype", "userid", "weeks", "work_mode"]
    CMD_FIELD_NUMBER: _ClassVar[int]
    DAY_FIELD_NUMBER: _ClassVar[int]
    DEVICEID_FIELD_NUMBER: _ClassVar[int]
    ENABLE_FIELD_NUMBER: _ClassVar[int]
    ENDDATE_FIELD_NUMBER: _ClassVar[int]
    JOBID_FIELD_NUMBER: _ClassVar[int]
    JOBNAME_FIELD_NUMBER: _ClassVar[int]
    OPERATING_POWER_FIELD_NUMBER: _ClassVar[int]
    PLANINDEX_FIELD_NUMBER: _ClassVar[int]
    REMAINED_SECONDS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    SPEED_FIELD_NUMBER: _ClassVar[int]
    STARTDATE_FIELD_NUMBER: _ClassVar[int]
    STARTTIME_FIELD_NUMBER: _ClassVar[int]
    SUB_MODE_FIELD_NUMBER: _ClassVar[int]
    TOTALPLANNUM_FIELD_NUMBER: _ClassVar[int]
    TRIGGERTYPE_FIELD_NUMBER: _ClassVar[int]
    USERID_FIELD_NUMBER: _ClassVar[int]
    WEEKS_FIELD_NUMBER: _ClassVar[int]
    WORK_MODE_FIELD_NUMBER: _ClassVar[int]
    cmd: int
    day: int
    deviceid: str
    enable: int
    enddate: str
    jobid: str
    jobname: str
    operating_power: int
    planindex: int
    remained_seconds: int
    result: int
    speed: int
    startdate: str
    starttime: int
    sub_mode: int
    totalplannum: int
    triggertype: int
    userid: str
    weeks: _containers.RepeatedScalarFieldContainer[int]
    work_mode: int
    def __init__(self, cmd: _Optional[int] = ..., work_mode: _Optional[int] = ..., sub_mode: _Optional[int] = ..., userid: _Optional[str] = ..., deviceid: _Optional[str] = ..., starttime: _Optional[int] = ..., totalplannum: _Optional[int] = ..., planindex: _Optional[int] = ..., result: _Optional[int] = ..., speed: _Optional[int] = ..., operating_power: _Optional[int] = ..., jobname: _Optional[str] = ..., jobid: _Optional[str] = ..., startdate: _Optional[str] = ..., enddate: _Optional[str] = ..., triggertype: _Optional[int] = ..., day: _Optional[int] = ..., weeks: _Optional[_Iterable[int]] = ..., remained_seconds: _Optional[int] = ..., enable: _Optional[int] = ...) -> None: ...

class SpinoCtrl(_message.Message):
    __slots__ = ["plan_job_set"]
    PLAN_JOB_SET_FIELD_NUMBER: _ClassVar[int]
    plan_job_set: PlanJobSet
    def __init__(self, plan_job_set: _Optional[_Union[PlanJobSet, _Mapping]] = ...) -> None: ...
