from dataclasses import dataclass

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class RegionData(DataClassORJSONMixin):
    """Mutable container for a single region's boundary data and metadata."""

    def __init__(self) -> None:
        self.hash: int = 0
        self.action: int = 0
        self.current_frame: int = 0
        self.data_hash: int = 0
        self.data_len: int = 0
        self.p_hash_a: int = 0
        self.p_hash_b: int = 0
        self.path: list[list[float]] | None = None
        self.pver: int = 0
        self.result: int = 0
        self.sub_cmd: int = 0
        self.total_frame: int = 0
        self.type: int = 0

    def set_hash(self, hash: int) -> None:
        """Set the region hash identifier."""
        self.hash = hash

    def get_data_len(self) -> int:
        """Return the length of the region data payload."""
        return self.data_len

    def set_data_len(self, data_len: int) -> None:
        """Set the length of the region data payload."""
        self.data_len = data_len

    def get_pver(self) -> int:
        """Return the protocol version for this region."""
        return self.pver

    def set_pver(self, pver: int) -> None:
        """Set the protocol version for this region."""
        self.pver = pver

    def get_sub_cmd(self) -> int:
        """Return the sub-command code for this region operation."""
        return self.sub_cmd

    def set_sub_cmd(self, sub_cmd: int) -> None:
        """Set the sub-command code for this region operation."""
        self.sub_cmd = sub_cmd

    def get_result(self) -> int:
        """Return the result code of the last region operation."""
        return self.result

    def set_result(self, result: int) -> None:
        """Set the result code of the last region operation."""
        self.result = result

    def get_action(self) -> int:
        """Return the action type for this region command."""
        return self.action

    def set_action(self, action: int) -> None:
        """Set the action type for this region command."""
        self.action = action

    def get_type(self) -> int:
        """Return the region type identifier."""
        return self.type

    def set_type(self, type: int) -> None:
        """Set the region type identifier."""
        self.type = type

    def get_total_frame(self) -> int:
        """Return the total number of frames in the region data transfer."""
        return self.total_frame

    def set_total_frame(self, total_frame: int) -> None:
        """Set the total number of frames in the region data transfer."""
        self.total_frame = total_frame

    def get_current_frame(self) -> int:
        """Return the index of the current frame being processed."""
        return self.current_frame

    def set_current_frame(self, current_frame: int) -> None:
        """Set the index of the current frame being processed."""
        self.current_frame = current_frame

    def get_path(self) -> list[list[float]] | None:
        """Return the list of coordinate pairs making up the region path."""
        return self.path

    def set_path(self, path: list[list[float]]) -> None:
        """Set the list of coordinate pairs making up the region path."""
        self.path = path

    def get_hash(self) -> int | None:
        """Return the region hash identifier."""
        return self.hash

    def set_data_hash(self, data_hash: int) -> None:
        """Set the hash of the region data payload for integrity checking."""
        self.data_hash = data_hash

    def get_data_hash(self) -> int | None:
        """Return the hash of the region data payload."""
        return self.data_hash

    def set_p_hash_a(self, p_hash_a: int) -> None:
        """Set the first parent region hash reference."""
        self.p_hash_a = p_hash_a

    def get_p_hash_a(self) -> int | None:
        """Return the first parent region hash reference."""
        return self.p_hash_a

    def set_p_hash_b(self, p_hash_b: int) -> None:
        """Set the second parent region hash reference."""
        self.p_hash_b = p_hash_b

    def get_p_hash_b(self) -> int | None:
        """Return the second parent region hash reference."""
        return self.p_hash_b

    def __str__(self) -> str:
        return f"RegionData{{pver={self.pver}, sub_cmd={self.sub_cmd}, result={self.result}, action={self.action}, type={self.type}, Hash={self.hash}, total_frame={self.total_frame}, current_frame={self.current_frame}, data_hash={self.data_hash}, p_hash_a={self.p_hash_a}, p_hash_b={self.p_hash_b}, data_len={self.data_len}, path={self.path}}}"
