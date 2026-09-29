"""Models for ``POST device-server/v1/device/work-report/page``: the account's job history per device.

Mirrors ``DeviceWorkReportPageResBean`` and its ``RecordsDTO`` (``base_module/bean/workreport``
in the 2.3.20.30 APK).  Records arrive newest first; the app offers "continue last job"
from ``records[0]``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Annotated, Any

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias


class WorkReportType(IntEnum):
    """``workType`` on a record; the RN report screen's enum (``index.android.bundle`` byte 1321677, 2.3.20.30)."""

    SINGLE = 1
    PLAN = 2
    DROPMOW = 3
    RESUME = 4


class WorkReportResult(IntEnum):
    """``workResult`` on a record; the RN report screen's enum, declared beside :class:`WorkReportType`."""

    UNKNOWN = 0
    WORKING = 1
    PAUSED = 2
    USER_ENDED = 3
    INTERRUPTED = 4
    COMPLETED = 5


def _drop_nulls(d: dict[Any, Any]) -> dict[Any, Any]:
    # Gson leaves a null at the bean's default; mashumaro would reject None for int/float.
    return {k: v for k, v in d.items() if v is not None}


@dataclass
class WorkReportRecord(DataClassORJSONMixin):
    """One job in the history (``RecordsDTO``).

    ``work_type`` / ``work_result`` stay plain ints so an unmodelled value never fails
    the parse; compare against :class:`WorkReportType` / :class:`WorkReportResult`.
    ``work_area_res`` / ``work_time_res`` (seconds) are what is left of the job, shown
    in the app's resume dialog.
    """

    id: str = ""
    device_name: Annotated[str, Alias("deviceName")] = ""
    product_id: Annotated[str, Alias("productId")] = ""
    work_id: Annotated[str, Alias("workId")] = ""
    origin_work_id: Annotated[str, Alias("originWorkId")] = "0"
    work_name: Annotated[str, Alias("workName")] = ""
    work_type: Annotated[int, Alias("workType")] = 0
    work_result: Annotated[int, Alias("workResult")] = 0
    continue_work: Annotated[bool, Alias("continueWork")] = False
    work_area: Annotated[float, Alias("workArea")] = 0.0
    work_area_res: Annotated[float, Alias("workAreaRes")] = 0.0
    work_progress: Annotated[float, Alias("workProgress")] = 0.0
    work_time_used: Annotated[int, Alias("workTimeUsed")] = 0
    work_time_res: Annotated[int, Alias("workTimeRes")] = 0
    start_work_time: Annotated[int, Alias("startWorkTime")] = 0
    end_work_time: Annotated[int, Alias("endWorkTime")] = 0

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True

    @classmethod
    def __pre_deserialize__(cls, d: dict[Any, Any]) -> dict[Any, Any]:
        return _drop_nulls(d)

    @property
    def can_resume(self) -> bool:
        """Whether the app would offer to resume this job.

        The RN report screen shows the resume button on ``continueWork && workType !== DROPMOW``.
        """
        return self.continue_work and self.work_type != WorkReportType.DROPMOW

    @property
    def resume_work_id(self) -> int:
        """The ``work_id`` for ``continue_last_job``: both app paths ``Long.parseLong`` it, sending 0 when empty."""
        return int(self.work_id) if self.work_id else 0


@dataclass
class WorkReportPage(DataClassORJSONMixin):
    """One page of work reports (``DeviceWorkReportPageResBean``)."""

    records: list[WorkReportRecord] = field(default_factory=list)
    total: int = 0
    size: int = 0
    current: int = 0
    pages: int = 0

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True

    @classmethod
    def __pre_deserialize__(cls, d: dict[Any, Any]) -> dict[Any, Any]:
        return _drop_nulls(d)
