from dataclasses import dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.data.error_codes import describe, get_error_info, solution
from pymammotion.http.model.http import ErrorInfo


@dataclass
class DeviceErrors(DataClassORJSONMixin):
    """Active error codes and their associated timestamps reported by the device."""

    err_code_list: list[int] = field(default_factory=list)
    err_code_list_time: list[int] = field(default_factory=list)
    #: A table fetched from the account endpoint, when the host has one.  Optional:
    #: the library bundles the same table, and lookups fall back to it.
    error_codes: dict[str, ErrorInfo] = field(default_factory=dict)

    @property
    def active_codes(self) -> list[int]:
        """Reported codes with the padding removed, newest first.

        The device always sends ten slots and pads the unused ones with ``0``, so a
        caller that renders ``err_code_list`` directly shows "Request succeeded"
        several times over.
        """
        return [code for code in self.err_code_list if code != 0]

    def info(self, code: int | str) -> ErrorInfo | None:
        """Return the table entry for *code*, preferring a fetched table over the bundle."""
        return get_error_info(code, extra=self.error_codes)

    def describe(self, code: int | str, language: str = "en") -> str:
        """Human-readable text for *code*, never empty."""
        return describe(code, language, extra=self.error_codes)

    def solution(self, code: int | str, language: str = "en") -> str:
        """Remedy text for *code*, or an empty string when it has none."""
        return solution(code, language, extra=self.error_codes)
