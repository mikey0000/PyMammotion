from dataclasses import dataclass, field
from typing import Any

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class ExecuteBorderParams(DataClassORJSONMixin):
    border: list[Any] = field(default_factory=list)
    currentFrame = 0
    jobIndex = ""
