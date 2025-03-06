from dataclasses import dataclass

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class RegionData(DataClassORJSONMixin):
    def __init__(self) -> None:
        self.hash: int | None = None
        self.action: int = 0
        self.current_frame: int = 0
        self.data_hash: int | None = None
        self.data_len: int = 0
        self.p_hash_a: int | None = None
        self.p_hash_b: int | None = None
        self.path: list[list[float]] | None = None
        self.pver: int = 0
        self.result: int = 0
        self.sub_cmd: int = 0
        self.total_frame: int = 0
        self.type: int = 0

    def set_hash(self, hash: int) -> None:
        self.hash = hash

    def get_data_len(self) -> int:
        return self.data_len

    def set_data_len(self, data_len: int) -> None:
        self.data_len = data_len

    def get_pver(self) -> int:
        return self.pver

    def set_pver(self, pver: int) -> None:
        self.pver = pver

    def get_sub_cmd(self) -> int:
        return self.sub_cmd

    def set_sub_cmd(self, sub_cmd: int) -> None:
        self.sub_cmd = sub_cmd

    def get_result(self) -> int:
        return self.result

    def set_result(self, result: int) -> None:
        self.result = result

    def get_action(self) -> int:
        return self.action

    def set_action(self, action: int) -> None:
        self.action = action

    def get_type(self) -> int:
        return self.type

    def set_type(self, type: int) -> None:
        self.type = type

    def get_total_frame(self) -> int:
        return self.total_frame

    def set_total_frame(self, total_frame: int) -> None:
        self.total_frame = total_frame

    def get_current_frame(self) -> int:
        return self.current_frame

    def set_current_frame(self, current_frame: int) -> None:
        self.current_frame = current_frame

    def get_path(self) -> list[list[float]] | None:
        return self.path

    def set_path(self, path: list[list[float]]) -> None:
        self.path = path

    def get_hash(self) -> int | None:
        return self.hash

    def set_data_hash(self, data_hash: int) -> None:
        self.data_hash = data_hash

    def get_data_hash(self) -> int | None:
        return self.data_hash

    def set_p_hash_a(self, p_hash_a: int) -> None:
        self.p_hash_a = p_hash_a

    def get_p_hash_a(self) -> int | None:
        return self.p_hash_a

    def set_p_hash_b(self, p_hash_b: int) -> None:
        self.p_hash_b = p_hash_b

    def get_p_hash_b(self) -> int | None:
        return self.p_hash_b

    def __str__(self) -> str:
        return f"RegionData{{pver={self.pver}, sub_cmd={self.sub_cmd}, result={self.result}, action={self.action}, type={self.type}, Hash={self.hash}, total_frame={self.total_frame}, current_frame={self.current_frame}, data_hash={self.data_hash}, p_hash_a={self.p_hash_a}, p_hash_b={self.p_hash_b}, data_len={self.data_len}, path={self.path}}}"
