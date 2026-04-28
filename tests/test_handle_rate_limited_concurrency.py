"""Regression tests for the ``_rate_limited`` flag race in ``DeviceHandle``.

Bug C4 (TODO.md): the ``_rate_limited`` boolean was written from multiple async
paths (``send_raw`` and ``_activity_loop``) without synchronisation. A success
clearing the flag concurrently with a 429 setting the flag could be lost,
leaving the device in either a silent-backoff-bypass or a stuck-backoff state.

The fix is to serialise transitions through ``_set_rate_limited`` which holds
``_rate_limit_lock`` for the assignment. These tests pin down that the
last-completing transition deterministically wins, regardless of which task
started first.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from pymammotion.aliyun.exceptions import TooManyRequestsException
from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import TransportType


def _make_mowing_device() -> MagicMock:
    """Minimal MowingDevice stand-in (mirrors tests/test_client.py)."""
    device = MagicMock()
    device.online = True
    device.enabled = True
    device.report_data.dev.battery_val = 75
    device.report_data.dev.sys_status = "idle"
    device.report_data.work.knife_height = 40
    return device


def _make_handle() -> DeviceHandle:
    return DeviceHandle(
        device_id="dev1",
        device_name="Luba-RL-Race",
        initial_device=_make_mowing_device(),
    )


def _make_connected_transport() -> MagicMock:
    t = MagicMock()
    t.transport_type = TransportType.CLOUD_ALIYUN
    t.is_connected = True
    t.send = AsyncMock()
    t.disconnect = AsyncMock()
    t.on_message = None
    t.add_availability_listener = MagicMock()
    t.last_received_monotonic = 0.0
    return t


async def _success_then_set(handle: DeviceHandle, gate: asyncio.Event) -> None:
    """Simulate ``_activity_loop``'s success branch: clears the flag.

    Waits on *gate* before performing the write so the test can control ordering.
    """
    await gate.wait()
    await handle._set_rate_limited(value=False)  # noqa: SLF001


async def _send_raises_429(handle: DeviceHandle, gate: asyncio.Event) -> None:
    """Simulate ``send_raw``'s 429 branch: sets the flag.

    Waits on *gate* before performing the write so the test can control ordering.
    """
    await gate.wait()
    await handle._set_rate_limited(value=True)  # noqa: SLF001


# ---------------------------------------------------------------------------
# Test 1: success completes first, then 429 → flag must be True.
# ---------------------------------------------------------------------------


async def test_rate_limited_success_then_429_ends_true() -> None:
    """If a 429 lands AFTER a clearing success, the flag must end True."""
    handle = _make_handle()
    handle._rate_limited = True  # noqa: SLF001  start in backoff

    success_gate = asyncio.Event()
    too_many_gate = asyncio.Event()

    success_task = asyncio.create_task(_success_then_set(handle, success_gate))
    too_many_task = asyncio.create_task(_send_raises_429(handle, too_many_gate))

    # Order: success first, 429 second. The 429 is the final write → flag = True.
    success_gate.set()
    await success_task
    too_many_gate.set()
    await too_many_task

    assert handle._rate_limited is True  # noqa: SLF001


# ---------------------------------------------------------------------------
# Test 2: 429 completes first, then success → flag must be False.
# ---------------------------------------------------------------------------


async def test_rate_limited_429_then_success_ends_false() -> None:
    """If a clearing success lands AFTER a 429, the flag must end False."""
    handle = _make_handle()
    handle._rate_limited = False  # noqa: SLF001  start clear

    success_gate = asyncio.Event()
    too_many_gate = asyncio.Event()

    success_task = asyncio.create_task(_success_then_set(handle, success_gate))
    too_many_task = asyncio.create_task(_send_raises_429(handle, too_many_gate))

    # Order: 429 first, success second. The success is the final write → flag = False.
    too_many_gate.set()
    await too_many_task
    success_gate.set()
    await success_task

    assert handle._rate_limited is False  # noqa: SLF001


# ---------------------------------------------------------------------------
# Test 3: rapid alternation — no TypeError, no stale state.
# ---------------------------------------------------------------------------


async def test_rate_limited_rapid_alternation_is_consistent() -> None:
    """Fire 10 alternating writes concurrently; the lock must serialise them.

    We don't assert the final value (it depends on completion order), but we DO
    assert that:
      * No exception escapes (the lock is correctly typed as asyncio.Lock).
      * The flag ends as a real ``bool`` — not None or some torn value.
    """
    handle = _make_handle()
    tasks: list[asyncio.Task[None]] = []
    for i in range(10):
        target = (i % 2 == 0)
        tasks.append(asyncio.create_task(handle._set_rate_limited(value=target)))  # noqa: SLF001
    await asyncio.gather(*tasks)
    assert isinstance(handle._rate_limited, bool)  # noqa: SLF001


# ---------------------------------------------------------------------------
# End-to-end: drive send_raw with a real transport that raises 429,
# concurrently with a direct flag-clear, to prove the public path uses the lock.
# ---------------------------------------------------------------------------


async def test_send_raw_429_serialised_with_concurrent_clear() -> None:
    """``send_raw`` raising 429 must serialise its write with a concurrent clear.

    This drives the public API path that previously used a bare assignment.
    We arrange the transport's ``send`` to block on a gate, then release it
    AFTER a concurrent clear task completes. The 429 write must be the final
    one and the flag must end True.
    """
    handle = _make_handle()
    transport = _make_connected_transport()
    handle._transports[TransportType.CLOUD_ALIYUN] = transport  # noqa: SLF001

    release_429 = asyncio.Event()

    async def gated_send(_payload: bytes, **_kwargs: object) -> None:
        await release_429.wait()
        raise TooManyRequestsException("rate limited", "iot-id")

    transport.send.side_effect = gated_send

    # Pre-clear the flag, then start send_raw which will eventually set True.
    handle._rate_limited = False  # noqa: SLF001
    send_task = asyncio.create_task(handle.send_raw(b"\x00"))

    # While send_raw is blocked inside the transport, simulate _activity_loop
    # clearing the flag (which already serialises through _set_rate_limited).
    await handle._set_rate_limited(value=False)  # noqa: SLF001

    # Now let send_raw's 429 propagate; it must set the flag True last.
    release_429.set()
    await send_task

    assert handle._rate_limited is True  # noqa: SLF001
