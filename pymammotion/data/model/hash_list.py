from dataclasses import dataclass
from typing import TypedDict


@dataclass
class CommDataCouple:
    x: float
    y: float


@dataclass
class Hash:
    pver: int
    sub_cmd: int
    result: int
    action: int
    type: int
    hash: int
    paternal_hash_a: float
    paternal_hash_b: float
    total_frame: int
    current_frame: int
    data_hash: float
    data_len: int
    data_couple: list[CommDataCouple]


class FrameList(TypedDict):
    frame: int
    data: Hash


class HashDict(TypedDict):
    hash: int
    data: FrameList


@dataclass
class HashList:
    area: HashDict  # type 1
    path: HashDict  # type 0
    obstacle: HashDict  # type 2
