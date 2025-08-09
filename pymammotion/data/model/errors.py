from dataclasses import field, dataclass

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.http.model.http import ErrorInfo


@dataclass(DataClassORJSONMixin)
class DeviceErrors:
    err_code_list: list = field(default_factory=list)
    err_code_list_time: list | None = field(default_factory=list)
    error_codes: dict[str, ErrorInfo] = field(default_factory=dict)