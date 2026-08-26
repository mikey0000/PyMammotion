"""Shared helpers for saga + broker + queue tests.

Plain functions (not pytest fixtures) so call sites stay terse —
``_make_command_builder()`` rather than threading a fixture parameter through
every test.  Pytest fixtures live in ``conftest.py``; these helpers live here
so tests can call them directly without registering them as parameters.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from pymammotion.data.model.hash_list import CommDataCouple, NavGetCommData, NavNameTime
from pymammotion.proto import (
    LubaMsg,
    MctlNav,
    NavGetCommDataAck,
    NavGetHashListAck,
    PlanJobSet,
    SpinoCtrl,
)


def make_command_builder() -> MagicMock:
    """MagicMock command-builder where every named method returns empty bytes.

    Saga tests instantiate sagas with a stub builder; the bytes value doesn't
    matter to saga logic, only that the methods exist and return something
    payload-shaped.  Explicit ``return_value = b""`` for the methods saga code
    paths actually invoke keeps the call-counting assertions
    (``cb.method.call_count``) clean.
    """
    cb = MagicMock()
    for name in (
        "get_area_name_list",
        "get_all_boundary_hash_list",
        "synchronize_hash_data",
        "get_regional_data",
        "get_hash_response",
        "generate_route_information",
        "get_line_info_list",
    ):
        getattr(cb, name).return_value = b""
    return cb


def hash_list_msg(hash_ids: list[int], *, sub_cmd: int = 0) -> LubaMsg:
    """Build a LubaMsg carrying a single-frame toapp_gethash_ack with the given hash IDs."""
    return LubaMsg(
        nav=MctlNav(
            toapp_gethash_ack=NavGetHashListAck(
                pver=1,
                sub_cmd=sub_cmd,
                total_frame=1,
                current_frame=1,
                data_couple=hash_ids,
            )
        )
    )


def comm_data_frame(
    hash_id: int,
    type_code: int,
    *,
    current_frame: int = 1,
    total_frame: int = 1,
    paternal_hash_a: int = 0,
) -> LubaMsg:
    """Build a LubaMsg carrying a single-frame toapp_get_commondata_ack."""
    return LubaMsg(
        nav=MctlNav(
            toapp_get_commondata_ack=NavGetCommDataAck(
                pver=1,
                action=8,
                type=type_code,
                hash=hash_id,
                total_frame=total_frame,
                current_frame=current_frame,
                paternal_hash_a=paternal_hash_a,
            )
        )
    )


def ctrl_plan_msg(jobid: int = 1, totalplannum: int = 1) -> LubaMsg:
    """Build a LubaMsg wrapping a SpinoCtrl ``plan_job_set`` frame (the ctrl envelope)."""
    return LubaMsg(ctrl=SpinoCtrl(plan_job_set=PlanJobSet(jobid=jobid, totalplannum=totalplannum)))


def area_frame_named(hash_val: int, name: str) -> NavGetCommData:
    """Single-frame area NavGetCommData whose name lives in ``name_time.name``."""
    return NavGetCommData(
        hash=hash_val, total_frame=1, current_frame=1,
        name_time=NavNameTime(name=name, create_time=1, modify_time=1),
        data_couple=[CommDataCouple(x=0.0, y=0.0)],
    )
