"""Shared helpers for saga + broker + queue tests.

Plain functions (not pytest fixtures) so call sites stay terse —
``_make_command_builder()`` rather than threading a fixture parameter through
every test.  Pytest fixtures live in ``conftest.py``; these helpers live here
so tests can call them directly without registering them as parameters.
"""
from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import MagicMock

import betterproto2

from pymammotion.data.model.hash_list import (
    CommDataCouple,
    HashList,
    MowPath,
    NavGetCommData,
    NavGetHashListData,
    NavNameTime,
)
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.map_saga import MapFetchSaga
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


def hash_list_msg(
    hash_ids: list[int], *, sub_cmd: int = 0, current_frame: int = 1, total_frame: int = 1
) -> LubaMsg:
    """Build a LubaMsg carrying one toapp_gethash_ack frame with the given hash IDs."""
    return LubaMsg(
        nav=MctlNav(
            toapp_gethash_ack=NavGetHashListAck(
                pver=1,
                sub_cmd=sub_cmd,
                total_frame=total_frame,
                current_frame=current_frame,
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


def apply_msg_to_map(msg: LubaMsg, m: HashList) -> None:
    """Minimal StateReducer simulation: update m with each incoming nav message."""
    if not msg.nav:
        return
    try:
        leaf_name, leaf_val = betterproto2.which_one_of(msg.nav, "SubNavMsg")
        if leaf_name == "toapp_gethash_ack":
            m.update_root_hash_list(NavGetHashListData.from_dict(leaf_val.to_dict(casing=betterproto2.Casing.SNAKE)))
        elif leaf_name == "toapp_get_commondata_ack":
            m.update(NavGetCommData.from_dict(leaf_val.to_dict(casing=betterproto2.Casing.SNAKE)))
        elif leaf_name == "cover_path_upload":
            m.update_mow_path(MowPath.from_dict(leaf_val.to_dict(casing=betterproto2.Casing.SNAKE)))
    except Exception:  # noqa: BLE001
        pass


async def run_saga_with_messages(
    broker: DeviceMessageBroker,
    saga: MapFetchSaga,
    messages: list[LubaMsg],
    delay: float = 0.02,
    map_update: HashList | None = None,
) -> None:
    """Drive saga + sequential message injection concurrently.

    If *map_update* is provided, each message is also applied to that HashList
    to simulate the StateReducer updating device.map before the saga reads it.
    """

    async def _inject() -> None:
        for msg in messages:
            await asyncio.sleep(delay)
            if map_update is not None:
                apply_msg_to_map(msg, map_update)
            await broker.on_message(msg)

    injector = asyncio.create_task(_inject())
    try:
        await saga.execute(broker)
    finally:
        injector.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await injector
