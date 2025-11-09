from dataclasses import dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class WorkTaskEvent(DataClassORJSONMixin):
    hash_area_map: dict[int, int] = field(default_factory=dict)
    ids: list[int] = field(default_factory=list)


@dataclass
class Events(DataClassORJSONMixin):
    work_tasks_event: WorkTaskEvent = field(default_factory=WorkTaskEvent)
