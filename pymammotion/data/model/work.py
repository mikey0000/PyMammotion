"""bidire_reqconver_path as a model."""

from dataclasses import dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class CurrentTaskSettings(DataClassORJSONMixin):
    pver: int = 0
    job_id: int = 0
    job_ver: int = 0
    job_mode: int = 0
    sub_cmd: int = 0
    edge_mode: int = 0
    knife_height: int = 0
    channel_width: int = 0
    ultra_wave: int = 0
    channel_mode: int = 0
    toward: int = 0
    speed: float = 0.0
    zone_hashs: list[int] = field(default_factory=list)
    path_hash: int = 0
    reserved: str = ""
    result: int = 0
    toward_mode: int = 0
    toward_included_angle: int = 0
