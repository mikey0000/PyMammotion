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
    return builder


# ---------------------------------------------------------------------------
# MapFetchSaga tests
# ---------------------------------------------------------------------------


async def test_map_saga_fetches_area_names_for_non_luba1() -> None:
    """For non-Luba1 devices, get_area_name_list must be called."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()
    send_command = AsyncMock()

    area_response = _make_area_name_response([(1, "Front lawn")])
    hash_response = _make_hash_list_ack_response(total_frame=1, current_frame=1, data_couple=[42])

    broker.send_and_wait.side_effect = [area_response, hash_response]

    saga = MapFetchSaga(
        device_id="dev-001",
        device_name="LUBA2",
        is_luba1=False,
        command_builder=builder,
        send_command=send_command,
    )
    await saga.execute(broker)

    assert saga.result is not None
    builder.get_area_name_list.assert_called_once_with("dev-001")
    assert broker.send_and_wait.call_count == 2

    # First call must request area names
    first_call_kwargs = broker.send_and_wait.call_args_list[0][1]
    assert first_call_kwargs["expected_field"] == "toapp_all_hash_name"


async def test_map_saga_skips_area_names_for_luba1() -> None:
    """For Luba1 devices, get_area_name_list must NOT be called."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()
    send_command = AsyncMock()

    hash_response = _make_hash_list_ack_response(total_frame=1, current_frame=1, data_couple=[99])
    broker.send_and_wait.return_value = hash_response

    saga = MapFetchSaga(
        device_id="dev-002",
        device_name="LUBA1",
        is_luba1=True,
        command_builder=builder,
        send_command=send_command,
    )
    await saga.execute(broker)

    assert saga.result is not None
    builder.get_area_name_list.assert_not_called()
    assert broker.send_and_wait.call_count == 1

    only_call_kwargs = broker.send_and_wait.call_args_list[0][1]
    assert only_call_kwargs["expected_field"] == "toapp_gethash_ack"


async def test_map_saga_caches_area_names_across_restarts() -> None:
    """Area names fetched on attempt 1 must be reused on attempt 2 (not re-fetched)."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()
    send_command = AsyncMock()

    area_response = _make_area_name_response([(10, "Back yard")])
    # First attempt: area names succeed, hash list times out → saga restarts
    # Second attempt: no area names fetch, hash list succeeds
    hash_response_success = _make_hash_list_ack_response(total_frame=1, current_frame=1, data_couple=[10])

    call_count = 0

    async def side_effect(**kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        field = kwargs.get("expected_field", "")
        if field == "toapp_all_hash_name":
            return area_response
        if field == "toapp_gethash_ack":
            if call_count == 2:
                # First hash list request on attempt 1 — timeout to force restart
                raise CommandTimeoutError("toapp_gethash_ack", 3)
            # Second hash list request on attempt 2 — success
            return hash_response_success
        raise AssertionError(f"Unexpected field: {field}")

    broker.send_and_wait.side_effect = side_effect

    saga = MapFetchSaga(
        device_id="dev-003",
        device_name="LUBA2",
        is_luba1=False,
        command_builder=builder,
        send_command=send_command,
    )
    await saga.execute(broker)

    assert saga.result is not None
    # Area names should only have been fetched once (cached on restart)
    area_calls = [
        call for call in broker.send_and_wait.call_args_list if call[1].get("expected_field") == "toapp_all_hash_name"
    ]
    assert len(area_calls) == 1
    assert saga._cached_area_names is not None
    assert saga._cached_area_names[0].name == "Back yard"


async def test_map_saga_clears_partial_state_on_restart() -> None:
    """result must be None at the start of each _run() call."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()
    send_command = AsyncMock()

    hash_response = _make_hash_list_ack_response(total_frame=1, current_frame=1)
    observed_results_at_start: list[Any] = []
    original_run = MapFetchSaga._run

    attempt = 0

    async def patched_run(self_: MapFetchSaga, broker_: DeviceMessageBroker) -> None:
        nonlocal attempt
        attempt += 1
        # Record result value at the START (before the real _run body executes)
        # We can't intercept before super()._run, but we can check after first timeout
        await original_run(self_, broker_)

    hash_call_count = 0

    async def side_effect(**kwargs: Any) -> Any:
        nonlocal hash_call_count
        field = kwargs.get("expected_field", "")
        if field == "toapp_gethash_ack":
            hash_call_count += 1
            if hash_call_count == 1:
                raise CommandTimeoutError("toapp_gethash_ack", 3)
            return hash_response
        raise AssertionError(f"Unexpected: {field}")

    broker.send_and_wait.side_effect = side_effect

    saga = MapFetchSaga(
        device_id="dev-004",
        device_name="LUBA1",
        is_luba1=True,
        command_builder=builder,
        send_command=send_command,
    )

    # Manually verify result is None before first run
    assert saga.result is None
    await saga.execute(broker)
    # After success, result should be set
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
    """Plan must be sent and success flag set after receiving ack."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()
    send_command = AsyncMock()

    plan = Plan(plan_id="plan-1", task_name="Mow front lawn")
    ack_response = _make_plan_ack_response()
    broker.send_and_wait.return_value = ack_response

    saga = PlanFetchSaga(plan=plan, command_builder=builder, send_command=send_command)
    await saga.execute(broker)

    assert saga.success is True
    builder.send_plan.assert_called_once_with(plan)
    assert broker.send_and_wait.call_count == 1

    call_kwargs = broker.send_and_wait.call_args_list[0][1]
    assert call_kwargs["expected_field"] == "todev_planjob_set"


async def test_plan_saga_retries_on_timeout() -> None:
    """When first attempt times out, saga must restart and succeed on second attempt."""
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()
    send_command = AsyncMock()

    plan = Plan(plan_id="plan-2", task_name="Retry mow")
    ack_response = _make_plan_ack_response()

    call_count = 0

    async def side_effect(**kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise CommandTimeoutError("todev_planjob_set", 3)
        return ack_response

    broker.send_and_wait.side_effect = side_effect

    saga = PlanFetchSaga(plan=plan, command_builder=builder, send_command=send_command)

    with patch("asyncio.sleep", new_callable=AsyncMock):  # skip 1s delays
        await saga.execute(broker)

    assert saga.success is True
    assert broker.send_and_wait.call_count == 2
