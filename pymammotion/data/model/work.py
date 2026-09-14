"""bidire_reqconver_path as a model."""

from dataclasses import dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin


def _first_or_zero(value: int | list[int] | None) -> int:
    """Read field 21 whichever way the firmware sent it (issue #193).

    It is declared repeated so both wire forms parse; devices that send a scalar
    still arrive here as a one-element list.
    """
    if isinstance(value, list):
        return int(value[0]) if value else 0
    return int(value or 0)


@dataclass
class CurrentTaskSettings(DataClassORJSONMixin):
    """Configuration parameters for the currently active or most recent mowing task."""

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
    ride_boundary_distance: float = 0.0
    app_display_mode: int = 0
    auto_change_direction: int = field(default=0, metadata={"deserialize": _first_or_zero})
