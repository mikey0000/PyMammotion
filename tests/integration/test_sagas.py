"""Tests for MapFetchSaga, MowPathSaga, and PlanFetchSaga."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.data.model.hash_list import (
    AreaHashNameList,
    HashList,
    MowPath,
    NavGetHashListData,
    Plan,
    RootHashList,
)
from pymammotion.messaging.broker import CommandTimeoutError, DeviceMessageBroker
from pymammotion.messaging.map_saga import MapFetchSaga
from pymammotion.messaging.mow_path_saga import MowPathSaga
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
    # "SubNavMsg" — detect area-name responses by hashnames being a real list.
    if isinstance(getattr(getattr(obj, "toapp_all_hash_name", None), "hashnames", None), list):
        return ("toapp_all_hash_name", obj.toapp_all_hash_name)
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
    # Area names are re-requested on each attempt (attempt 1 failed)
    assert len(area_calls) == 1
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


async def test_plan_saga_iterates_all_indices_when_total_plan_num_is_3() -> None:
    """When totalPlanNum=3, PlanFetchSaga must request indices 0, 1, and 2.

    This is a regression test for the bug where only plan_index=0 was ever
    requested: the device returns totalPlanNum in the first response, and the
    saga must loop through the remaining indices rather than returning early.
    """
    broker = AsyncMock(spec=DeviceMessageBroker)
    builder = _make_command_builder()

    subscribe_side_effect, active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    # Three plans, each with a distinct plan_id.  All carry totalPlanNum=3 so the
    # saga knows the total from the first response and loops for indices 1 and 2.
    plan_dicts = [
        {"total_plan_num": 3, "plan_id": "plan-aaa", "plan_index": 0, "task_name": "Plan A"},
        {"total_plan_num": 3, "plan_id": "plan-bbb", "plan_index": 1, "task_name": "Plan B"},
        {"total_plan_num": 3, "plan_id": "plan-ccc", "plan_index": 2, "task_name": "Plan C"},
    ]
    call_count = 0

    async def send_command(cmd: bytes) -> None:
        nonlocal call_count
        if active_callbacks:
            leaf_val = MagicMock()
            leaf_val.to_dict.return_value = plan_dicts[call_count]
            response = MagicMock()
            # _which_plan is called with response.nav as `obj` when unpacking
            # SubNavMsg, so the leaf_val must be reachable via response.nav._leaf_val.
            response.nav._leaf_val = leaf_val
            call_count += 1
            await active_callbacks[-1](response)

    def _which_plan(obj: Any, group: str) -> tuple[str, Any]:
        if group == "LubaSubMsg":
            return ("nav", obj.nav)
        return ("todev_planjob_set", obj._leaf_val)

    with patch("betterproto2.which_one_of", side_effect=_which_plan):
        saga = PlanFetchSaga(command_builder=builder, send_command=send_command)
        await saga.execute(broker)

    # Saga must have sent one read_plan per index.
    assert builder.read_plan.call_count == 3
    builder.read_plan.assert_any_call(sub_cmd=2, plan_index=0)
    builder.read_plan.assert_any_call(sub_cmd=2, plan_index=1)
    builder.read_plan.assert_any_call(sub_cmd=2, plan_index=2)

    # All three plans must be in the result.
    assert set(saga.result.keys()) == {"plan-aaa", "plan-bbb", "plan-ccc"}


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


# ---------------------------------------------------------------------------
# MapFetchSaga: get_hash_response is an ack-only command (regression)
# ---------------------------------------------------------------------------


async def test_map_saga_only_acks_get_hash_response_in_response_to_frames() -> None:
    """get_hash_response must only be sent in response to an incoming frame.

    It is not a "request next frame" command — the device streams frames
    after ``get_all_boundary_hash_list`` and each frame is acked via
    ``get_hash_response(total_frame, current_frame)``.  Acking is what the
    device interprets as "send me the next one".  Mirrors
    HashDataManager.setHashList in the APK (line 1173).
    """
    from pymammotion.data.model.hash_list import NavGetHashListData, RootHashList

    broker = AsyncMock(spec=DeviceMessageBroker)
    subscribe_side_effect, active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    builder = _make_command_builder()

    hash_list = HashList()
    total_frames = 3
    delivered = 0
    send_log: list[str] = []

    async def _deliver_frame(frame: int) -> None:
        """Append the next frame to device.map and push it to the broker callback."""
        # Simulate the state reducer: append the frame to root_hash_lists before
        # the saga wakes on the queue.
        if not hash_list.root_hash_lists:
            hash_list.root_hash_lists = [RootHashList(total_frame=total_frames, sub_cmd=0, data=[])]
        hash_list.root_hash_lists[0].data.append(
            NavGetHashListData(
                pver=1,
                sub_cmd=0,
                total_frame=total_frames,
                current_frame=frame,
                data_hash=0,
                hash_len=0,
                data_couple=[],
            )
        )
        if active_callbacks:
            await active_callbacks[-1](
                _make_hash_list_ack_response(total_frame=total_frames, current_frame=frame, sub_cmd=0)
            )

    async def send_command(cmd: bytes) -> None:
        nonlocal delivered
        if cmd == b"hash_list_cmd":
            send_log.append("get_all_boundary_hash_list")
            delivered = 1
            await _deliver_frame(delivered)
        elif cmd == b"hash_response_cmd":
            send_log.append("get_hash_response")
            # Device only sends more frames if acked and there are more to deliver.
            if delivered < total_frames:
                delivered += 1
                await _deliver_frame(delivered)

    with patch("betterproto2.which_one_of", side_effect=_which_one_of_for_hash):
        saga = MapFetchSaga(
            device_id="dev-ack",
            device_name="LUBA1",
            is_luba1=True,  # skip area-name fetch
            command_builder=builder,
            send_command=send_command,
            get_map=lambda: hash_list,
        )
        saga.step_timeout = 0.1
        await saga.execute(broker)

    # Exactly one kick-off request.
    assert send_log.count("get_all_boundary_hash_list") == 1
    # One ack per frame received — no proactive "request next" sends.
    assert send_log.count("get_hash_response") == total_frames
    # Order: the kick-off comes first, then ack follows each frame.
    assert send_log == [
        "get_all_boundary_hash_list",
        "get_hash_response",
        "get_hash_response",
        "get_hash_response",
    ]
    # Each ack carries the current_frame of the frame it acknowledges —
    # NOT ``next_frame - 1`` (the old proactive-request pattern).
    acked_frames = [call.kwargs.get("current_frame") for call in builder.get_hash_response.call_args_list]
    assert acked_frames == [1, 2, 3]


# ---------------------------------------------------------------------------
# MapFetchSaga resume after interruption (bug regression)
# ---------------------------------------------------------------------------


def _seed_partial_map(
    area_hashes: list[int],
    *,
    complete_hashes: set[int],
    partial_hash: int | None = None,
    partial_total: int = 10,
    partial_received: int = 5,
) -> HashList:
    """Build a HashList simulating state after an interrupted map fetch.

    - ``root_hash_lists`` is populated with *area_hashes* (sub_cmd=0), marking it complete.
    - Entries in *complete_hashes* get a full ``FrameList`` (total=1, one frame).
    - *partial_hash* (if given) gets a partial ``FrameList`` with only
      *partial_received* of *partial_total* frames.
    """
    from pymammotion.data.model.hash_list import (
        FrameList,
        NavGetCommData,
        NavGetHashListData,
        RootHashList,
    )

    hash_list = HashList()
    # Fully populated root hash list for sub_cmd=0.
    hash_list.root_hash_lists = [
        RootHashList(
            total_frame=1,
            sub_cmd=0,
            data=[
                NavGetHashListData(
                    pver=1,
                    sub_cmd=0,
                    total_frame=1,
                    current_frame=1,
                    data_hash=0,
                    hash_len=len(area_hashes),
                    data_couple=list(area_hashes),
                )
            ],
        )
    ]
    for h in complete_hashes:
        hash_list.area[h] = FrameList(
            total_frame=1,
            sub_cmd=0,
            data=[NavGetCommData(pver=1, sub_cmd=0, type=0, hash=h, total_frame=1, current_frame=1)],
        )
    if partial_hash is not None:
        hash_list.area[partial_hash] = FrameList(
            total_frame=partial_total,
            sub_cmd=0,
            data=[
                NavGetCommData(
                    pver=1,
                    sub_cmd=0,
                    type=0,
                    hash=partial_hash,
                    total_frame=partial_total,
                    current_frame=i,
                )
                for i in range(1, partial_received + 1)
            ],
        )
    return hash_list


async def test_find_incomplete_hashes_flags_partial_area() -> None:
    """An area with a key-present but frame-incomplete FrameList must be flagged incomplete."""
    hash_list = _seed_partial_map(
        area_hashes=[111, 222, 333],
        complete_hashes={111, 222},
        partial_hash=333,
        partial_total=10,
        partial_received=5,
    )

    # Old behaviour: key-present-only check — hash 333 is "not missing".
    assert hash_list.missing_hashlist(0) == []

    # New behaviour: frame-aware check — hash 333 IS incomplete.
    assert hash_list.find_incomplete_hashes(0) == [333]


async def test_map_saga_resumes_partial_area_via_synchronize_hash_data() -> None:
    """After interruption mid-area, saga must re-send synchronize_hash_data for the partial hash.

    Regression test: ``missing_hashlist`` used to only check key-presence, so a
    partially-fetched area was treated as done and the saga exited leaving
    area 3 incomplete.  ``find_incomplete_hashes`` fixes this.
    """
    from pymammotion.data.model.hash_list import NavGetCommData

    hash_list = _seed_partial_map(
        area_hashes=[111, 222, 333],
        complete_hashes={111, 222},
        partial_hash=333,
        partial_total=2,
        partial_received=1,
    )

    broker = AsyncMock(spec=DeviceMessageBroker)
    subscribe_side_effect, active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    builder = _make_command_builder()
    builder.synchronize_hash_data.return_value = b"sync_cmd"
    builder.get_regional_data.return_value = b"regional_cmd"

    sent_commands: list[bytes] = []

    async def send_command(cmd: bytes) -> None:
        sent_commands.append(cmd)
        if cmd == b"hash_list_cmd" and active_callbacks:
            # Deliver the single-frame root hash list (same hashes as seeded).
            await active_callbacks[-1](
                _make_hash_list_ack_response(
                    total_frame=1, current_frame=1, sub_cmd=0, data_couple=[111, 222, 333]
                )
            )
        # After saga sends synchronize_hash_data for the partial hash,
        # simulate the device delivering the missing frame.
        elif cmd == b"sync_cmd" and active_callbacks:
            # Append the missing second frame of the partial area.
            hash_list.area[333].data.append(
                NavGetCommData(
                    pver=1,
                    sub_cmd=0,
                    type=0,
                    hash=333,
                    total_frame=2,
                    current_frame=2,
                )
            )
            msg = MagicMock()
            msg.nav.toapp_get_commondata_ack = MagicMock(hash=333, type=0, current_frame=2, total_frame=2)
            await active_callbacks[-1](msg)

    def _which_one_of(obj: Any, group: str) -> tuple[str, Any]:
        if group == "LubaSubMsg":
            return ("nav", obj.nav)
        # For SubNavMsg, obj is msg.nav.  Detect the frame type by whether
        # toapp_gethash_ack.total_frame is a real int (set explicitly by
        # _make_hash_list_ack_response) vs a MagicMock (auto-created attribute).
        if isinstance(getattr(obj.toapp_gethash_ack, "total_frame", None), int):
            return ("toapp_gethash_ack", obj.toapp_gethash_ack)
        return ("toapp_get_commondata_ack", obj.toapp_get_commondata_ack)

    with patch("betterproto2.which_one_of", side_effect=_which_one_of):
        saga = MapFetchSaga(
            device_id="dev-resume",
            device_name="Luba-Resume",
            is_luba1=True,  # skip area-name fetch
            command_builder=builder,
            send_command=send_command,
            get_map=lambda: hash_list,
        )
        saga.step_timeout = 0.05

        await saga.execute(broker)

    # Saga must have asked the device to resume hash 333 via synchronize_hash_data.
    builder.synchronize_hash_data.assert_called_with(hash_num=333)
    # And NOT for already-complete hashes.
    assert {c.kwargs.get("hash_num") for c in builder.synchronize_hash_data.call_args_list} == {333}


async def test_invalidate_maps_clears_only_root_hash_list_on_mismatch() -> None:
    """A bol_hash mismatch clears root_hash_lists but preserves per-type dicts.

    Per-type dicts are filtered lazily by update_hash_lists once the new root
    hash list is received.  Hash IDs still present in the new list reuse their
    cached frames; only IDs that have been removed are eventually pruned.
    """
    from pymammotion.data.model.hash_list import FrameList, NavGetCommData

    hash_list = _seed_partial_map(
        area_hashes=[111, 222],
        complete_hashes={111, 222},
    )
    hash_list.path[999] = FrameList(
        total_frame=1,
        sub_cmd=0,
        data=[NavGetCommData(pver=1, sub_cmd=0, type=2, hash=999, total_frame=1, current_frame=1)],
    )

    # Any non-matching bol_hash triggers invalidation.
    hash_list.invalidate_maps(bol_hash=0xDEADBEEF)

    # Root hash list is cleared so MapFetchSaga re-fetches it.
    assert hash_list.root_hash_lists == []
    # Per-type dicts are preserved; update_hash_lists will prune them once the
    # new root hash list is available.
    assert 111 in hash_list.area
    assert 222 in hash_list.area
    assert 999 in hash_list.path


# ---------------------------------------------------------------------------
# MowPathSaga
# ---------------------------------------------------------------------------


async def test_mow_path_saga_preserves_current_mow_path_across_runs() -> None:
    """current_mow_path must NOT be wiped at the start of each _run() call.

    Wiping on retry defeats the per-hash skip logic that lets the saga avoid
    re-fetching cover-path data already cached from prior frames.  Stale entries
    are cleared by ``HashList.invalidate_mow_path()`` only when the device
    reports ``path_hash`` 0 or 1 (job ended), mirroring the APK's HashDataManager.
    """
    hash_list = HashList()
    stale_tx = {99999: {1: MowPath(total_frame=3, current_frame=1, transaction_id=99999)}}
    hash_list.current_mow_path = dict(stale_tx)

    broker = AsyncMock(spec=DeviceMessageBroker)
    subscribe_side_effect, _active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    builder = _make_command_builder()
    send_command = AsyncMock()

    with patch("betterproto2.which_one_of", side_effect=_which_one_of_for_hash):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            saga = MowPathSaga(
                command_builder=builder,
                send_command=send_command,
                get_map=lambda: hash_list,
                zone_hashs=[100],
            )
            saga.step_timeout = 0.01
            await saga.execute(broker)

    # The saga itself must leave stale entries alone — per-hash skip relies on this.
    assert hash_list.current_mow_path == stale_tx

    # Only invalidate_mow_path(0) clears it (job ended → cache flush).
    hash_list.invalidate_mow_path(0)
    assert hash_list.current_mow_path == {}


async def test_mow_path_saga_syncs_before_route_and_line_info() -> None:
    """A BLE sync must be sent immediately before generate_route_information and before the
    first get_line_info_list — the intervening frame loops stale the run's initial sync.
    """

    class _StopAfterLineInfo(Exception):
        """Sentinel to halt the saga right after the cover-path request is issued."""

    # Pre-seed a sub_cmd=3 root list with one line hash so the saga reaches step 2 (route)
    # and step 3-4 (cover paths) instead of early-returning.  current_mow_path stays empty
    # so the hash counts as "missing" and get_line_info_list is issued.
    hash_list = HashList()
    hash_list.root_hash_lists = [
        RootHashList(
            total_frame=1,
            sub_cmd=3,
            data=[NavGetHashListData(sub_cmd=3, total_frame=1, current_frame=1, data_couple=[100])],
        )
    ]

    broker = AsyncMock(spec=DeviceMessageBroker)
    subscribe_side_effect, active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    # Route response returned by the (mocked) send_and_wait for step 2.
    route_val = MagicMock(sub_cmd=0, path_hash=0)
    route_response = MagicMock()
    route_response.nav.bidire_reqconver_path = route_val
    broker.send_and_wait.return_value = route_response

    # Step-1 hash frame (sub_cmd=3, single frame) fed when the line-hash-list request is sent.
    hash_frame = MagicMock()
    hash_frame.nav.toapp_gethash_ack = MagicMock(sub_cmd=3, current_frame=1, total_frame=1)

    cb = MagicMock()
    cb.send_todev_ble_sync.return_value = b"ble_sync"
    cb.get_all_boundary_hash_list.return_value = b"hash_list_cmd"
    cb.get_hash_response.return_value = b"hash_response_cmd"
    cb.generate_route_information.return_value = b"route_cmd"
    cb.get_line_info_list.side_effect = _StopAfterLineInfo  # halt once the cover-path request fires

    async def send_command(cmd: bytes) -> None:
        if cmd == b"hash_list_cmd" and active_callbacks:
            await active_callbacks[-1](hash_frame)

    def _which(obj: Any, group: str) -> tuple[str, Any]:
        if group == "LubaSubMsg":
            return ("nav", obj.nav)
        # SubNavMsg: the route response carries an int sub_cmd on bidire_reqconver_path.
        bidire = getattr(obj, "bidire_reqconver_path", None)
        if isinstance(getattr(bidire, "sub_cmd", None), int):
            return ("bidire_reqconver_path", bidire)
        return ("toapp_gethash_ack", obj.toapp_gethash_ack)

    with patch("betterproto2.which_one_of", side_effect=_which), patch("asyncio.sleep", new_callable=AsyncMock):
        saga = MowPathSaga(
            command_builder=cb,
            send_command=send_command,
            get_map=lambda: hash_list,
            zone_hashs=[100],
            sync_type=2,  # BLE
        )
        saga.step_timeout = 0.01
        with pytest.raises(_StopAfterLineInfo):
            await saga.execute(broker)

    names = [
        c[0]
        for c in cb.mock_calls
        if c[0]
        in {
            "send_todev_ble_sync",
            "get_all_boundary_hash_list",
            "get_hash_response",
            "generate_route_information",
            "get_line_info_list",
        }
    ]

    route_idx = names.index("generate_route_information")
    assert names[route_idx - 1] == "send_todev_ble_sync", f"no sync before route: {names[: route_idx + 1]}"

    line_idx = names.index("get_line_info_list")
    assert names[line_idx - 1] == "send_todev_ble_sync", f"no sync before cover-path: {names[: line_idx + 1]}"

    cb.send_todev_ble_sync.assert_called_with(sync_type=2)


# ---------------------------------------------------------------------------
# SpinoPlanFetchSaga tests — Spino path mirrors the mower's PlanFetchSaga but
# the leaf field name is ``plan_job_set`` (not ``todev_planjob_set``), the
# payload lives in ``LubaMsg.ctrl.plan_job_set``, and plans are keyed by the
# numeric ``jobid`` (fixed64) instead of a string ``plan_id``.
# ---------------------------------------------------------------------------


async def test_spino_plan_saga_collects_all_plans_by_jobid() -> None:
    """SpinoPlanFetchSaga must loop plan_index 0..total-1 and key by jobid."""
    from pymammotion.messaging.spino_plan_saga import SpinoPlanFetchSaga

    broker = AsyncMock(spec=DeviceMessageBroker)

    builder = MagicMock()
    builder.read_spino_plan.return_value = b"read_spino_plan_cmd"

    subscribe_side_effect, active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    # Three plans on the device.  Each "response" is a MagicMock standing
    # in for the LubaMsg; ``_extract_plan_job_set`` only reaches it via
    # ``betterproto2.which_one_of(..., "LubaSubMsg")`` which we patch
    # below to return the appropriate PlanJobSet stub per call.
    fake_plans = [
        MagicMock(totalplannum=3, jobid=0xAA01, jobname="A"),
        MagicMock(totalplannum=3, jobid=0xAA02, jobname="B"),
        MagicMock(totalplannum=3, jobid=0xAA03, jobname="C"),
    ]
    responses = [MagicMock(ctrl=MagicMock(plan_job_set=p)) for p in fake_plans]
    call_idx = 0

    async def send_command(_cmd: bytes) -> None:
        nonlocal call_idx
        if active_callbacks:
            await active_callbacks[-1](responses[call_idx])
            call_idx += 1

    def _which(obj: Any, group: str) -> tuple[str, Any]:
        # Saga subscribes on ``plan_job_set``; ``_collect_frames`` only
        # cares that the leaf name matches.  ``_extract_plan_job_set``
        # uses the ``LubaSubMsg`` group to dig back down.
        if group == "LubaSubMsg":
            return ("ctrl", obj.ctrl)
        return ("plan_job_set", obj.ctrl.plan_job_set)

    with patch("betterproto2.which_one_of", side_effect=_which):
        saga = SpinoPlanFetchSaga(command_builder=builder, send_command=send_command)
        await saga.execute(broker)

    # All three jobids landed, keyed numerically
    assert set(saga.result.keys()) == {0xAA01, 0xAA02, 0xAA03}
    # First call at index 0 + two more for indices 1, 2
    assert builder.read_spino_plan.call_count == 3
    builder.read_spino_plan.assert_any_call(plan_index=0)
    builder.read_spino_plan.assert_any_call(plan_index=1)
    builder.read_spino_plan.assert_any_call(plan_index=2)


async def test_spino_plan_saga_empty_device_short_circuits() -> None:
    """``totalplannum == 0`` means no plans — saga must return immediately."""
    from pymammotion.messaging.spino_plan_saga import SpinoPlanFetchSaga

    broker = AsyncMock(spec=DeviceMessageBroker)

    builder = MagicMock()
    builder.read_spino_plan.return_value = b"read_spino_plan_cmd"

    subscribe_side_effect, active_callbacks = _make_subscribe_ctx()
    broker.subscribe_unsolicited.side_effect = subscribe_side_effect

    empty_response = MagicMock(
        ctrl=MagicMock(plan_job_set=MagicMock(totalplannum=0, jobid=0))
    )

    async def send_command(_cmd: bytes) -> None:
        if active_callbacks:
            await active_callbacks[-1](empty_response)

    def _which(obj: Any, group: str) -> tuple[str, Any]:
        if group == "LubaSubMsg":
            return ("ctrl", obj.ctrl)
        return ("plan_job_set", obj.ctrl.plan_job_set)

    with patch("betterproto2.which_one_of", side_effect=_which):
        saga = SpinoPlanFetchSaga(command_builder=builder, send_command=send_command)
        await saga.execute(broker)

    assert saga.result == {}
    # Only the first read — saga short-circuits on totalplannum=0.
    assert builder.read_spino_plan.call_count == 1
