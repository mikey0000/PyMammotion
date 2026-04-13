"""Tests for MapFetchSaga and PlanFetchSaga."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.data.model.hash_list import AreaHashNameList, HashList, NavGetHashListData, Plan
from pymammotion.messaging.broker import CommandTimeoutError, DeviceMessageBroker
from pymammotion.messaging.map_saga import MapFetchSaga
from pymammotion.messaging.plan_saga import PlanFetchSaga
from pymammotion.messaging.saga import SagaFailedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hash_list_ack_response(
    total_frame: int = 1,
    current_frame: int = 1,
    sub_cmd: int = 1,
    data_couple: list[int] | None = None,
) -> MagicMock:
    """Create a minimal MagicMock that looks like a LubaMsg with toapp_gethash_ack."""
    ack = MagicMock()
    ack.pver = 1
    ack.sub_cmd = sub_cmd
    ack.total_frame = total_frame
    ack.current_frame = current_frame
    ack.data_hash = 0
    ack.hash_len = len(data_couple or [])
    ack.result = 0
    ack.data_couple = data_couple or []

    nav = MagicMock()
    nav.toapp_gethash_ack = ack

    msg = MagicMock()
    msg.nav = nav
    return msg


def _make_area_name_response(names: list[tuple[int, str]]) -> MagicMock:
    """Create a MagicMock resembling a LubaMsg with toapp_all_hash_name."""
    hashnames = []
    for h, n in names:
        item = MagicMock()
        item.hash = h
        item.name = n
        hashnames.append(item)

    area_name_msg = MagicMock()
    area_name_msg.hashnames = hashnames

    nav = MagicMock()
    nav.toapp_all_hash_name = area_name_msg

    msg = MagicMock()
    msg.nav = nav
    return msg


def _make_plan_ack_response() -> MagicMock:
    """Create a MagicMock resembling a LubaMsg with todev_planjob_set."""
    planjob = MagicMock()

    nav = MagicMock()
    nav.todev_planjob_set = planjob

    msg = MagicMock()
    msg.nav = nav
    return msg


def _make_command_builder() -> MagicMock:
    """Create a mock command builder that returns dummy bytes for every call."""
    builder = MagicMock()
    builder.get_area_name_list.return_value = b"area_name_cmd"
    builder.get_all_boundary_hash_list.return_value = b"hash_list_cmd"
    builder.get_hash_response.return_value = b"hash_response_cmd"
    builder.send_plan.return_value = b"plan_cmd"
    builder.read_plan.return_value = b"read_plan_cmd"
    return builder


def _make_subscribe_ctx() -> tuple[Any, list[Any]]:
    """Return (subscribe_side_effect, active_callbacks) for broker.subscribe_unsolicited mocking.

    subscribe_side_effect captures the callback in a context manager.
    active_callbacks holds the currently registered callback(s).
    """
    active: list[Any] = []

    class _Ctx:
        def __init__(self, cb: Any) -> None:
            self._cb = cb

        def __enter__(self) -> "_Ctx":
            active.append(self._cb)
            return self

        def __exit__(self, *args: Any) -> None:
            if active and active[-1] is self._cb:
                active.pop()

    return lambda cb: _Ctx(cb), active


def _which_one_of_for_hash(obj: Any, group: str) -> tuple[str, Any]:
    """Fake betterproto2.which_one_of that routes hash-frame messages correctly."""
    if group == "LubaSubMsg":
        return ("nav", obj.nav)
    # "SubNavMsg"
    return ("toapp_gethash_ack", obj.toapp_gethash_ack)


# ---------------------------------------------------------------------------
# MapFetchSaga tests
# ---------------------------------------------------------------------------


async def test_map_saga_fetches_area_names_for_non_luba1() -> None:
    """For non-Luba1 devices, get_area_name_list must be called."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()

    area_response = _make_area_name_response([(1, "Front lawn")])
    # sub_cmd=1 (default) → missing_hashlist(0) returns [] so step 4 is skipped
    hash_response = _make_hash_list_ack_response(total_frame=1, current_frame=1, data_couple=[])

    broker.send_and_wait.return_value = area_response

    subscribe_side_effect, active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    async def send_command(cmd: bytes) -> None:
        if active_callbacks:
            await active_callbacks[-1](hash_response)

    with patch("betterproto2.which_one_of", side_effect=_which_one_of_for_hash):
        saga = MapFetchSaga(
            device_id="dev-001",
            device_name="LUBA2",
            is_luba1=False,
            command_builder=builder,
            send_command=send_command,
            get_map=HashList,
        )
        await saga.execute(broker)

    assert saga.result is not None
    builder.get_area_name_list.assert_called_once_with("dev-001")
    # send_and_wait is only used for the area-names step now
    assert broker.send_and_wait.call_count == 1
    first_call_kwargs = broker.send_and_wait.call_args_list[0][1]
    assert first_call_kwargs["expected_field"] == "toapp_all_hash_name"


async def test_map_saga_skips_area_names_for_luba1() -> None:
    """For Luba1 devices, get_area_name_list must NOT be called."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()

    hash_response = _make_hash_list_ack_response(total_frame=1, current_frame=1, data_couple=[])

    subscribe_side_effect, active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    async def send_command(cmd: bytes) -> None:
        if active_callbacks:
            await active_callbacks[-1](hash_response)

    with patch("betterproto2.which_one_of", side_effect=_which_one_of_for_hash):
        saga = MapFetchSaga(
            device_id="dev-002",
            device_name="LUBA1",
            is_luba1=True,
            command_builder=builder,
            send_command=send_command,
            get_map=HashList,
        )
        await saga.execute(broker)

    assert saga.result is not None
    builder.get_area_name_list.assert_not_called()
    # send_and_wait is never called for Luba1 (no area names, hash frames via queue)
    assert broker.send_and_wait.call_count == 0


async def test_map_saga_refetches_area_names_on_restart() -> None:
    """Area names are re-requested on each attempt (no caching across retries)."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()

    area_response = _make_area_name_response([(10, "Back yard")])
    hash_response = _make_hash_list_ack_response(total_frame=1, current_frame=1, data_couple=[])

    broker.send_and_wait.return_value = area_response

    subscribe_side_effect, active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    call_count = 0

    async def send_command(cmd: bytes) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            pass  # First attempt: no delivery → timeout forces restart
        elif active_callbacks:
            await active_callbacks[-1](hash_response)

    _map = HashList()
    with patch("betterproto2.which_one_of", side_effect=_which_one_of_for_hash):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            saga = MapFetchSaga(
                device_id="dev-003",
                device_name="LUBA2",
                is_luba1=False,
                command_builder=builder,
                send_command=send_command,
                get_map=lambda: _map,
            )
            saga.step_timeout = 0.01  # short timeout so the test doesn't hang
            await saga.execute(broker)

    assert saga.result is not None
    area_calls = [
        call for call in broker.send_and_wait.call_args_list if call[1].get("expected_field") == "toapp_all_hash_name"
    ]
    # Area names are re-requested on each attempt (attempt 1 failed → attempt 2 succeeded = 2 calls)
    assert len(area_calls) == 2
    assert saga.result.area_name[0].name == "Back yard"


async def test_map_saga_clears_partial_state_on_restart() -> None:
    """result must be None at the start of each _run() call."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()

    hash_response = _make_hash_list_ack_response(total_frame=1, current_frame=1, data_couple=[])

    subscribe_side_effect, active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    call_count = 0

    async def send_command(cmd: bytes) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            pass  # First attempt: timeout → restart
        elif active_callbacks:
            await active_callbacks[-1](hash_response)

    with patch("betterproto2.which_one_of", side_effect=_which_one_of_for_hash):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            saga = MapFetchSaga(
                device_id="dev-004",
                device_name="LUBA1",
                is_luba1=True,
                command_builder=builder,
                send_command=send_command,
                get_map=HashList,
            )
            saga.step_timeout = 0.01

            assert saga.result is None
            await saga.execute(broker)
            assert saga.result is not None


async def test_map_saga_raises_saga_failed_after_max_attempts() -> None:
    """When all attempts time out, SagaFailedError must be raised."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()
    send_command = AsyncMock()

    broker.send_and_wait.side_effect = CommandTimeoutError("toapp_gethash_ack", 3)

    saga = MapFetchSaga(
        device_id="dev-005",
        device_name="LUBA1",
        is_luba1=True,
        command_builder=builder,
        send_command=send_command,
        get_map=HashList,
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):  # skip 1s delays
        with pytest.raises(SagaFailedError) as exc_info:
            await saga.execute(broker)

    assert exc_info.value.name == "map_fetch"
    assert exc_info.value.attempts == saga.max_attempts


# ---------------------------------------------------------------------------
# PlanFetchSaga tests
# ---------------------------------------------------------------------------


async def test_plan_saga_sends_plan_and_waits_for_ack() -> None:
    """read_plan must be called and saga completes after receiving todev_planjob_set."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()

    subscribe_side_effect, active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    plan_response = MagicMock()
    plan_response.nav = MagicMock()

    leaf_val = MagicMock()
    leaf_val.to_dict.return_value = {"total_plan_num": 0}

    async def send_command(cmd: bytes) -> None:
        if active_callbacks:
            await active_callbacks[-1](plan_response)

    def _which_plan(obj: Any, group: str) -> tuple[str, Any]:
        if group == "LubaSubMsg":
            return ("nav", obj.nav)
        return ("todev_planjob_set", leaf_val)

    with patch("betterproto2.which_one_of", side_effect=_which_plan):
        saga = PlanFetchSaga(command_builder=builder, send_command=send_command)
        await saga.execute(broker)

    assert saga.result == {}
    builder.read_plan.assert_called_once_with(sub_cmd=2, plan_index=0)


async def test_plan_saga_retries_on_timeout() -> None:
    """When first attempt times out, saga must restart and succeed on second attempt."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()

    subscribe_side_effect, active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    plan_response = MagicMock()
    plan_response.nav = MagicMock()

    leaf_val = MagicMock()
    leaf_val.to_dict.return_value = {"total_plan_num": 0}

    call_count = 0

    async def send_command(cmd: bytes) -> None:
        nonlocal call_count
        call_count += 1
        if call_count >= 2 and active_callbacks:  # First call times out, second succeeds
            await active_callbacks[-1](plan_response)

    def _which_plan(obj: Any, group: str) -> tuple[str, Any]:
        if group == "LubaSubMsg":
            return ("nav", obj.nav)
        return ("todev_planjob_set", leaf_val)

    with patch("betterproto2.which_one_of", side_effect=_which_plan):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            saga = PlanFetchSaga(command_builder=builder, send_command=send_command)
            saga.step_timeout = 0.01
            await saga.execute(broker)

    assert saga.result == {}
    assert builder.read_plan.call_count == 2  # called once per attempt
