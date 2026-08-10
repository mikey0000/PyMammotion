"""Unit tests for the ``Saga`` base class itself.

The base was previously only covered indirectly, through concrete sagas in
``tests/integration/test_sagas.py``.  That left its own contract — frame
extraction, the collector's envelope handling, step timeouts, the total-timeout
wall — untested, which is awkward when the base is being refactored.

Two groups here:

* **Contract** — behaviour every saga depends on, which must not drift.
* **Envelope** — the collector must work for ``ctrl`` (Spino) as well as ``nav``.
  ``LubaSubMsg`` is a oneof so envelope selection is uniform, but the leaves are
  not: ``MctlNav`` nests them in a ``SubNavMsg`` oneof while ``SpinoCtrl`` has a
  single plain field.  Both shapes have to work.
"""

from __future__ import annotations

import asyncio

import pytest

from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.saga import Saga
from pymammotion.proto import (
    LubaMsg,
    MctlNav,
    MctlSys,
    NavGetCommDataAck,
    NavGetHashListAck,
    PlanJobSet,
    SpinoCtrl,
)
from pymammotion.transport.base import CommandTimeoutError, SagaFailedError


class _NoopSaga(Saga):
    """Minimal concrete saga — the base's own helpers are what's under test."""

    name = "test_saga"

    def __init__(self) -> None:
        self.runs = 0

    async def _run(self, broker: DeviceMessageBroker) -> None:
        self.runs += 1


def _nav_msg(**leaf: object) -> LubaMsg:
    return LubaMsg(nav=MctlNav(**leaf))  # type: ignore[arg-type]


def _ctrl_msg(jobid: int = 1, totalplannum: int = 1) -> LubaMsg:
    return LubaMsg(ctrl=SpinoCtrl(plan_job_set=PlanJobSet(jobid=jobid, totalplannum=totalplannum)))


# ---------------------------------------------------------------------------
# extract_nav_frame — the unwrap every saga needs
# ---------------------------------------------------------------------------


def test_extract_nav_frame_returns_name_and_value() -> None:
    msg = _nav_msg(toapp_gethash_ack=NavGetHashListAck(pver=1, total_frame=2, current_frame=1))
    frame = Saga.extract_nav_frame(msg, "toapp_gethash_ack")
    assert frame is not None
    name, value = frame
    assert name == "toapp_gethash_ack"
    assert value.current_frame == 1


def test_extract_nav_frame_rejects_a_different_leaf() -> None:
    msg = _nav_msg(toapp_get_commondata_ack=NavGetCommDataAck(pver=1))
    assert Saga.extract_nav_frame(msg, "toapp_gethash_ack") is None


def test_extract_nav_frame_rejects_a_non_nav_envelope() -> None:
    """A sys frame must never satisfy a nav collector."""
    assert Saga.extract_nav_frame(LubaMsg(sys=MctlSys()), "toapp_gethash_ack") is None


def test_extract_nav_frame_accepts_tuple_and_frozenset() -> None:
    msg = _nav_msg(toapp_gethash_ack=NavGetHashListAck(pver=1))
    assert Saga.extract_nav_frame(msg, ("a", "toapp_gethash_ack")) is not None
    assert Saga.extract_nav_frame(msg, frozenset({"a", "toapp_gethash_ack"})) is not None


def test_extract_nav_frame_swallows_malformed_messages() -> None:
    """Malformed frames are noise, not failures — callers must not need try/except."""
    assert Saga.extract_nav_frame(object(), "toapp_gethash_ack") is None
    assert Saga.extract_nav_frame(None, "toapp_gethash_ack") is None


# ---------------------------------------------------------------------------
# _collect_frames — nav envelope (the existing default)
# ---------------------------------------------------------------------------


async def test_collect_frames_queues_only_matching_leaves() -> None:
    broker = DeviceMessageBroker()
    saga = _NoopSaga()
    with saga._collect_frames(broker, "toapp_gethash_ack") as queue:  # noqa: SLF001
        await broker.on_message(_nav_msg(toapp_gethash_ack=NavGetHashListAck(pver=1)))
        await broker.on_message(_nav_msg(toapp_get_commondata_ack=NavGetCommDataAck(pver=1)))
        await broker.on_message(LubaMsg(sys=MctlSys()))
        assert queue.qsize() == 1


async def test_collect_frames_honours_the_predicate() -> None:
    broker = DeviceMessageBroker()
    saga = _NoopSaga()
    with saga._collect_frames(broker, "toapp_gethash_ack", lambda v: v.sub_cmd == 0) as queue:  # noqa: SLF001
        await broker.on_message(_nav_msg(toapp_gethash_ack=NavGetHashListAck(pver=1, sub_cmd=3)))
        assert queue.qsize() == 0
        await broker.on_message(_nav_msg(toapp_gethash_ack=NavGetHashListAck(pver=1, sub_cmd=0)))
        assert queue.qsize() == 1


async def test_collect_frames_unsubscribes_on_exit() -> None:
    """RAII: frames arriving after the block must not reach a dead queue."""
    broker = DeviceMessageBroker()
    saga = _NoopSaga()
    with saga._collect_frames(broker, "toapp_gethash_ack") as queue:  # noqa: SLF001
        pass
    await broker.on_message(_nav_msg(toapp_gethash_ack=NavGetHashListAck(pver=1)))
    assert queue.qsize() == 0


# ---------------------------------------------------------------------------
# _collect_frames — ctrl envelope (Spino).  New in step 1.
#
# SpinoPlanFetchSaga previously carried a ~35-line copy of _collect_frames for
# no reason other than the base hard-wiring the nav envelope.
# ---------------------------------------------------------------------------


async def test_collect_frames_supports_the_ctrl_envelope() -> None:
    broker = DeviceMessageBroker()
    saga = _NoopSaga()
    with saga._collect_frames(broker, "plan_job_set", envelope="ctrl") as queue:  # noqa: SLF001
        await broker.on_message(_ctrl_msg(jobid=42))
        assert queue.qsize() == 1


async def test_ctrl_collector_ignores_nav_frames() -> None:
    broker = DeviceMessageBroker()
    saga = _NoopSaga()
    with saga._collect_frames(broker, "plan_job_set", envelope="ctrl") as queue:  # noqa: SLF001
        await broker.on_message(_nav_msg(toapp_gethash_ack=NavGetHashListAck(pver=1)))
        assert queue.qsize() == 0


async def test_nav_collector_ignores_ctrl_frames() -> None:
    """The default envelope stays nav — a Spino frame must not satisfy a mower saga."""
    broker = DeviceMessageBroker()
    saga = _NoopSaga()
    with saga._collect_frames(broker, "plan_job_set") as queue:  # noqa: SLF001
        await broker.on_message(_ctrl_msg())
        assert queue.qsize() == 0


async def test_ctrl_collector_honours_the_predicate() -> None:
    broker = DeviceMessageBroker()
    saga = _NoopSaga()
    with saga._collect_frames(broker, "plan_job_set", envelope="ctrl", predicate=lambda v: v.jobid == 9) as queue:  # noqa: SLF001
        await broker.on_message(_ctrl_msg(jobid=1))
        assert queue.qsize() == 0
        await broker.on_message(_ctrl_msg(jobid=9))
        assert queue.qsize() == 1


def test_extract_frame_handles_both_leaf_shapes() -> None:
    """nav leaves live in a oneof; SpinoCtrl.plan_job_set is a plain field."""
    nav = _nav_msg(toapp_gethash_ack=NavGetHashListAck(pver=1))
    assert Saga.extract_frame(nav, "toapp_gethash_ack", envelope="nav") is not None

    ctrl = _ctrl_msg(jobid=3)
    frame = Saga.extract_frame(ctrl, "plan_job_set", envelope="ctrl")
    assert frame is not None
    assert frame[0] == "plan_job_set"
    assert frame[1].jobid == 3


def test_spino_saga_no_longer_overrides_the_collector() -> None:
    """The whole point of the envelope parameter — the duplicate copy is gone."""
    from pymammotion.messaging.spino_plan_saga import SpinoPlanFetchSaga

    assert "_collect_frames" not in vars(SpinoPlanFetchSaga)


# ---------------------------------------------------------------------------
# _next_frame / _region_data / execute
# ---------------------------------------------------------------------------


async def test_next_frame_returns_a_queued_item() -> None:
    saga = _NoopSaga()
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()
    queue.put_nowait(sentinel)
    assert await saga._next_frame(queue, "field") is sentinel  # noqa: SLF001


async def test_next_frame_raises_command_timeout() -> None:
    saga = _NoopSaga()
    saga.step_timeout = 0.01
    with pytest.raises(CommandTimeoutError):
        await saga._next_frame(asyncio.Queue(), "toapp_gethash_ack", 7)  # noqa: SLF001


def test_region_data_echoes_every_field_the_device_expects() -> None:
    """The device only sends the next frame when the echo matches."""
    frame = NavGetCommDataAck(
        pver=1, action=8, type=3, hash=99, total_frame=5, current_frame=2, sub_cmd=1
    )
    rd = Saga._region_data(frame)  # noqa: SLF001
    assert (rd.total_frame, rd.current_frame, rd.sub_cmd) == (5, 2, 1)
    assert (rd.type, rd.hash, rd.action) == (3, 99, 8)


async def test_execute_enforces_the_total_timeout_wall() -> None:
    class _Hanging(_NoopSaga):
        total_timeout = 0.02

        async def _run(self, broker: DeviceMessageBroker) -> None:
            await asyncio.sleep(10)

    with pytest.raises(SagaFailedError):
        await _Hanging().execute(DeviceMessageBroker())


async def test_execute_returns_on_success() -> None:
    saga = _NoopSaga()
    await saga.execute(DeviceMessageBroker())
    assert saga.runs == 1


# ---------------------------------------------------------------------------
# Re-entry policy: progress, not attempt-counting.  New in step 3.
#
# The old loop restarted the whole run and counted attempts, which is the wrong
# granularity for a protocol where the device retransmits unacked frames: one
# missed frame at 47/50 burned an attempt even though 46 frames were banked.
# Sagas worked around it by hand — map_saga and mow_path_saga set
# ``_reset_attempt_counter`` on genuine progress, and mow_path needed a
# ``_budget_reset_granted`` one-shot on top so the reset couldn't loop forever.
#
# ``progress()`` replaces all of that: any advance resets the budget, so
# ``max_attempts`` now caps *consecutive fruitless* attempts.
# ---------------------------------------------------------------------------


class _CountingSaga(Saga):
    """Saga that always fails, reporting progress from a caller-controlled counter."""

    name = "counting"
    max_attempts = 2

    def __init__(self, progress_values: list[object]) -> None:
        self._values = progress_values
        self.runs = 0

    async def progress(self) -> object:
        # Report the value for the run just completed; hold the last one thereafter.
        idx = min(self.runs, len(self._values) - 1)
        return self._values[idx]

    async def _run(self, broker: DeviceMessageBroker) -> None:
        self.runs += 1
        raise CommandTimeoutError("field", 1)


async def test_progress_defaults_to_none_so_untracked_sagas_still_cap_out() -> None:
    """A saga that doesn't implement progress() keeps plain attempt-capped behaviour."""

    class _Untracked(Saga):
        name = "untracked"
        max_attempts = 3

        def __init__(self) -> None:
            self.runs = 0

        async def _run(self, broker: DeviceMessageBroker) -> None:
            self.runs += 1
            raise CommandTimeoutError("field", 1)

    saga = _Untracked()
    assert await saga.progress() is None
    with pytest.raises(SagaFailedError):
        await saga.execute(DeviceMessageBroker())
    assert saga.runs == 3


async def test_stalled_saga_fails_after_max_consecutive_fruitless_attempts() -> None:
    """Progress that never advances must still terminate at max_attempts."""
    saga = _CountingSaga([0, 0, 0, 0, 0])
    with pytest.raises(SagaFailedError):
        await saga.execute(DeviceMessageBroker())
    assert saga.runs == 2  # max_attempts, no progress to earn more


async def test_progress_resets_the_attempt_budget() -> None:
    """Banked work must buy another attempt — the whole point of the change.

    Progress advances on runs 1-3 then stalls, so the saga gets its two fruitless
    attempts *after* the last advance rather than being cut off at attempt 2.
    """
    saga = _CountingSaga([1, 2, 3, 3, 3])
    with pytest.raises(SagaFailedError):
        await saga.execute(DeviceMessageBroker())
    # 2 runs that advanced (progress 1->2->3) + max_attempts(2) fruitless = 4.
    # Under plain attempt-counting this would have stopped at 2.
    assert saga.runs > 2, "progress should have bought attempts beyond max_attempts"
    assert saga.runs == 4


async def test_total_timeout_still_bounds_a_saga_that_always_progresses() -> None:
    """Endless progress must not mean an endless saga — total_timeout is the wall."""

    class _AlwaysProgressing(Saga):
        name = "always_progressing"
        max_attempts = 1
        total_timeout = 0.05

        def __init__(self) -> None:
            self.runs = 0

        async def progress(self) -> object:
            return self.runs

        async def _run(self, broker: DeviceMessageBroker) -> None:
            self.runs += 1
            raise CommandTimeoutError("field", 1)

    with pytest.raises(SagaFailedError):
        await _AlwaysProgressing().execute(DeviceMessageBroker())


async def test_successful_run_does_not_re_enter() -> None:
    saga = _NoopSaga()
    await saga.execute(DeviceMessageBroker())
    assert saga.runs == 1


async def test_gateway_timeout_is_treated_as_an_interruption() -> None:
    """It must not escape to DeviceCommandQueue, which would replay the whole saga."""
    from pymammotion.aliyun.exceptions import GatewayTimeoutException

    class _GatewayFails(Saga):
        name = "gateway"
        max_attempts = 1

        def __init__(self) -> None:
            self.runs = 0

        async def _run(self, broker: DeviceMessageBroker) -> None:
            self.runs += 1
            raise GatewayTimeoutException(20056, "iot-1")

    saga = _GatewayFails()
    with pytest.raises(SagaFailedError):
        await saga.execute(DeviceMessageBroker())


def test_manual_attempt_counter_hacks_are_gone() -> None:
    """progress() supersedes them; leaving them would give two competing signals."""
    from pymammotion.messaging.map_saga import MapFetchSaga
    from pymammotion.messaging.mow_path_saga import MowPathSaga

    import inspect

    assert not hasattr(Saga, "_reset_attempt_counter")
    # Assignment, not mention — the docstrings legitimately explain what was replaced.
    for cls in (MapFetchSaga, MowPathSaga):
        src = inspect.getsource(cls)
        assert "_reset_attempt_counter =" not in src, f"{cls.__name__} still sets the manual flag"
        assert "_budget_reset_granted =" not in src, f"{cls.__name__} still has the one-shot guard"
