from dataclasses import dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.http.model.http import ErrorInfo


@dataclass
class DeviceErrors(DataClassORJSONMixin):
    """Active error codes and their associated timestamps reported by the device."""

    err_code_list: list[int] = field(default_factory=list)
    err_code_list_time: list[int] = field(default_factory=list)
    error_codes: dict[str, ErrorInfo] = field(default_factory=dict)
