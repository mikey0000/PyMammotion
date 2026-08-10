"""Tests for the reusable transfer protocols in ``pymammotion.messaging.transfers``.

These are the two frame-exchange shapes the device actually speaks, extracted so
sagas stop hand-rolling them:

* ``ack_stream``    — device streams frames, each must be acked before the next.
* ``indexed_fetch`` — app asks for item *i*, device answers with exactly one frame.

Everything else about a saga (branching, resume, batching) stays plain Python in
the saga; only the mechanics live here.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pymammotion.messaging.transfers import ack_stream, indexed_fetch
from pymammotion.proto import (
    LubaMsg,
    MctlNav,
    NavGetCommDataAck,
    PlanJobSet,
    SpinoCtrl,
)
from pymammotion.transport.base import CommandTimeoutError


def _frame(current: int, total: int, *, type_code: int = 3) -> LubaMsg:
    return LubaMsg(
        nav=MctlNav(
            toapp_get_commondata_ack=NavGetCommDataAck(
                pver=1, action=8, type=type_code, hash=1, total_frame=total, current_frame=current
            )
        )
    )


def _plan_frame(jobid: int, total: int) -> LubaMsg:
    return LubaMsg(ctrl=SpinoCtrl(plan_job_set=PlanJobSet(jobid=jobid, totalplannum=total)))


# ---------------------------------------------------------------------------
# ack_stream
# ---------------------------------------------------------------------------


async def test_ack_stream_acks_every_frame_including_the_last() -> None:
    """The device waits for the echo before sending the next frame — and the APK
    acks the final frame too (HashDataManager.setRegionalData)."""
    queue: asyncio.Queue = asyncio.Queue()
    for i in (1, 2, 3):
        queue.put_nowait(_frame(i, 3))
    acked: list[int] = []

    async def ack(frame: Any) -> None:
        acked.append(frame.current_frame)

    frames = await ack_stream(queue, field="toapp_get_commondata_ack", ack=ack, timeout=0.1)

    assert acked == [1, 2, 3]
    assert sorted(frames) == [1, 2, 3]


async def test_ack_stream_returns_frames_keyed_by_frame_number() -> None:
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(_frame(1, 1))

    async def ack(_frame: Any) -> None:
        return None

    frames = await ack_stream(queue, field="toapp_get_commondata_ack", ack=ack, timeout=0.1)
    assert list(frames) == [1]
    assert frames[1].total_frame == 1


async def test_ack_stream_completes_on_frame_count_not_frame_number() -> None:
    """A retransmitted frame must not be able to end the stream early.

    The device re-sends unacked frames every ~1 s, so ``current_frame == total``
    can arrive while an earlier frame is still missing.  Counting distinct frames
    is the only safe completion rule.
    """
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(_frame(2, 2))  # last frame arrives first
    queue.put_nowait(_frame(2, 2))  # ...and again (retransmit)
    queue.put_nowait(_frame(1, 2))  # the genuinely missing one

    async def ack(_frame: Any) -> None:
        return None

    frames = await ack_stream(queue, field="toapp_get_commondata_ack", ack=ack, timeout=0.1)
    assert sorted(frames) == [1, 2], "must wait for frame 1 despite seeing 2/2 twice"


async def test_ack_stream_acks_duplicates_too() -> None:
    """A retransmit means the device didn't hear our ack — so ack it again."""
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(_frame(1, 2))
    queue.put_nowait(_frame(1, 2))
    queue.put_nowait(_frame(2, 2))
    acked: list[int] = []

    async def ack(frame: Any) -> None:
        acked.append(frame.current_frame)

    await ack_stream(queue, field="toapp_get_commondata_ack", ack=ack, timeout=0.1)
    assert acked == [1, 1, 2]


async def test_ack_stream_times_out_when_the_device_goes_quiet() -> None:
    queue: asyncio.Queue = asyncio.Queue()

    async def ack(_frame: Any) -> None:
        return None

    with pytest.raises(CommandTimeoutError):
        await ack_stream(queue, field="toapp_get_commondata_ack", ack=ack, timeout=0.01)


async def test_ack_stream_allow_empty_treats_silence_as_an_empty_result() -> None:
    """MowPathSaga's line-hash step: no response means "no breakpoint lines", not
    a failure — but only before any frame has arrived."""
    queue: asyncio.Queue = asyncio.Queue()

    async def ack(_frame: Any) -> None:
        return None

    frames = await ack_stream(
        queue, field="toapp_get_commondata_ack", ack=ack, timeout=0.01, allow_empty=True
    )
    assert frames == {}


async def test_allow_empty_still_raises_once_a_stream_has_started() -> None:
    """Silence mid-stream is a genuine interruption even when empty is tolerated."""
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(_frame(1, 3))

    async def ack(_frame: Any) -> None:
        return None

    with pytest.raises(CommandTimeoutError):
        await ack_stream(
            queue, field="toapp_get_commondata_ack", ack=ack, timeout=0.01, allow_empty=True
        )


async def test_ack_stream_drives_the_device_via_the_ack_callback() -> None:
    """Realistic shape: the device only sends frame N+1 after we ack frame N."""
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(_frame(1, 3))

    async def ack(frame: Any) -> None:
        if frame.current_frame < frame.total_frame:
            queue.put_nowait(_frame(frame.current_frame + 1, frame.total_frame))

    frames = await ack_stream(queue, field="toapp_get_commondata_ack", ack=ack, timeout=0.1)
    assert sorted(frames) == [1, 2, 3]


# ---------------------------------------------------------------------------
# indexed_fetch
# ---------------------------------------------------------------------------


async def test_indexed_fetch_requests_every_index_and_yields_each_frame() -> None:
    queue: asyncio.Queue = asyncio.Queue()
    requested: list[int] = []

    async def request(index: int) -> None:
        requested.append(index)
        queue.put_nowait(_plan_frame(jobid=100 + index, total=3))

    got = [
        frame
        async for frame in indexed_fetch(
            queue,
            field="plan_job_set",
            envelope="ctrl",
            request=request,
            total_of=lambda f: f.totalplannum,
            timeout=0.1,
        )
    ]

    assert requested == [0, 1, 2]
    assert [f.jobid for f in got] == [100, 101, 102]


async def test_indexed_fetch_stops_at_one_when_total_is_one() -> None:
    queue: asyncio.Queue = asyncio.Queue()
    requested: list[int] = []

    async def request(index: int) -> None:
        requested.append(index)
        queue.put_nowait(_plan_frame(jobid=7, total=1))

    got = [
        frame
        async for frame in indexed_fetch(
            queue,
            field="plan_job_set",
            envelope="ctrl",
            request=request,
            total_of=lambda f: f.totalplannum,
            timeout=0.1,
        )
    ]
    assert requested == [0]
    assert len(got) == 1


async def test_indexed_fetch_yields_nothing_when_the_device_has_no_items() -> None:
    """total == 0 — the device answers once to say it has nothing stored."""
    queue: asyncio.Queue = asyncio.Queue()

    async def request(_index: int) -> None:
        queue.put_nowait(_plan_frame(jobid=0, total=0))

    got = [
        frame
        async for frame in indexed_fetch(
            queue,
            field="plan_job_set",
            envelope="ctrl",
            request=request,
            total_of=lambda f: f.totalplannum,
            timeout=0.1,
        )
    ]
    assert got == []


async def test_indexed_fetch_times_out_when_the_device_never_answers() -> None:
    queue: asyncio.Queue = asyncio.Queue()

    async def request(_index: int) -> None:
        return None

    with pytest.raises(CommandTimeoutError):
        _ = [
            frame
            async for frame in indexed_fetch(
                queue,
                field="plan_job_set",
                envelope="ctrl",
                request=request,
                total_of=lambda f: f.totalplannum,
                timeout=0.01,
            )
        ]


async def test_indexed_fetch_works_on_the_nav_envelope_too() -> None:
    """Spino uses ctrl, mower plans use nav — the helper must not assume either."""
    queue: asyncio.Queue = asyncio.Queue()

    async def request(index: int) -> None:
        queue.put_nowait(_frame(current=index + 1, total=2))

    got = [
        frame
        async for frame in indexed_fetch(
            queue,
            field="toapp_get_commondata_ack",
            request=request,
            total_of=lambda f: f.total_frame,
            timeout=0.1,
        )
    ]
    assert [f.current_frame for f in got] == [1, 2]
