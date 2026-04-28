"""Regression test for MowPathSaga (skip_planning=True) silently returning when no route_val.

Before the fix, when ``skip_planning=True`` and the device never confirms a route
(``_route_val`` stays ``None``), the saga returned silently from ``_run`` —
``execute()`` reported success but no cover paths were ever requested, so the
caller assumed success even though no data was fetched.  The saga must instead
raise SagaFailedError.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import betterproto2
import pytest

from pymammotion.data.model.hash_list import HashList
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.mow_path_saga import MowPathSaga
from pymammotion.proto import LubaMsg, MctlNav, NavGetHashListAck
from pymammotion.transport.base import SagaFailedError


def _make_command_builder() -> MagicMock:
    """Minimal command-builder double — every method returns empty bytes."""
    cb = MagicMock()
    cb.get_all_boundary_hash_list.return_value = b""
    cb.get_hash_response.return_value = b""
    cb.generate_route_information.return_value = b""
    cb.get_line_info_list.return_value = b""
    return cb


def _hash_list_msg_sub3(hash_ids: list[int]) -> LubaMsg:
    """LubaMsg carrying a single-frame toapp_gethash_ack (sub_cmd=3)."""
    return LubaMsg(
        nav=MctlNav(
            toapp_gethash_ack=NavGetHashListAck(
                pver=1,
                sub_cmd=3,
                total_frame=1,
                current_frame=1,
                data_couple=hash_ids,
            )
        )
    )


async def test_skip_planning_with_no_route_val_raises_saga_failed() -> None:
    """When skip_planning=True and the device never delivers a route, the saga must fail."""
    broker = DeviceMessageBroker()

    async def send_command(_cmd: bytes) -> None:
        return None

    _map = HashList()

    saga = MowPathSaga(
        command_builder=_make_command_builder(),
        send_command=send_command,
        get_map=lambda: _map,
        zone_hashs=[1234567890],
        skip_planning=True,
        device_name="Luba-Test",
    )
    # Make the saga fail fast — keep step_timeout small and total_timeout reasonable.
    saga.step_timeout = 0.2
    saga.max_attempts = 1
    saga.total_timeout = 10.0

    async def _inject() -> None:
        # Step 1 only: a single sub_cmd=3 hash frame so the saga proceeds past Step 1
        # straight into Step 2.  No route confirmation is ever delivered.
        await asyncio.sleep(0.05)
        await broker.on_message(_hash_list_msg_sub3([1234567890]))

    injector = asyncio.create_task(_inject())
    try:
        with pytest.raises(SagaFailedError):
            await saga.execute(broker)
    finally:
        injector.cancel()
        try:
            await injector
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    # And critically — no cover paths should have been collected.
    assert saga.result == {}


# Sanity import to keep linter quiet about unused imports
_ = betterproto2
