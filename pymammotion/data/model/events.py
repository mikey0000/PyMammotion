from dataclasses import dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.data.model.enums import TaskAreaStatus


@dataclass
class WorkTaskEvent(DataClassORJSONMixin):
    hash_area_map: dict[int, TaskAreaStatus] = field(default_factory=dict)
    ids: list[int] = field(default_factory=list)


@dataclass
class BladeHeightEvent(DataClassORJSONMixin):
    """In-progress blade height change event (proto DrvKnifeChangeReport).

    is_start: 1 when a height change begins, 0 when complete
    start_height / end_height: requested height range
    cur_height: current position during the change
    """

    is_start: int = 0
    start_height: int = 0
    end_height: int = 0
    cur_height: int = 0


@dataclass
class OTAProgress(DataClassORJSONMixin):
    """Firmware OTA upgrade progress (proto DrvUpgradeReport).

    progress: 0–100 percentage
    result: 0=in progress, non-zero=completion code
    devname: which sub-component is being upgraded
    version: target firmware version string
    """

    devname: str = ""
    otaid: str = ""
    version: str = ""
    progress: int = 0
    result: int = 0
    message: str = ""
    recv_cnt: int = 0


@dataclass
class Events(DataClassORJSONMixin):
    work_tasks_event: WorkTaskEvent = field(default_factory=WorkTaskEvent)
    blade_height_event: BladeHeightEvent = field(default_factory=BladeHeightEvent)
    ota_progress: OTAProgress = field(default_factory=OTAProgress)
