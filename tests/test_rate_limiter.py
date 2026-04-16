"""Tests for :mod:`pymammotion.aliyun.rate_limiter`."""

from __future__ import annotations

import asyncio

import pytest

from pymammotion.aliyun.rate_limiter import AdaptiveRateLimiter, RequestCoalescer


@pytest.mark.asyncio
async def test_rate_limiter_passes_through_when_clear() -> None:
    """When no 429s have been observed, wait_until_clear returns immediately."""
    limiter = AdaptiveRateLimiter()
    # Must complete in well under the base_delay.
    await asyncio.wait_for(limiter.wait_until_clear(), timeout=0.2)
    assert not limiter.is_blocked
    assert limiter.consecutive_hits == 0


@pytest.mark.asyncio
async def test_rate_limiter_backs_off_exponentially(monkeypatch: pytest.MonkeyPatch) -> None:
    """Consecutive 429s should grow the cool-down and mark the limiter as blocked."""
    # Deterministic jitter so assertions don't flake.
    monkeypatch.setattr("pymammotion.aliyun.rate_limiter.random.uniform", lambda a, b: 0.0)

    limiter = AdaptiveRateLimiter(base_delay=2.0, max_delay=60.0)

    first = limiter.note_rate_limited()
    second = limiter.note_rate_limited()
    third = limiter.note_rate_limited()

    assert first == pytest.approx(2.0)
    assert second == pytest.approx(4.0)
    assert third == pytest.approx(8.0)
    assert limiter.is_blocked
    assert limiter.consecutive_hits == 3


@pytest.mark.asyncio
async def test_rate_limiter_caps_at_max_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated 429s cap at ``max_delay`` even past the exponent ceiling."""
    monkeypatch.setattr("pymammotion.aliyun.rate_limiter.random.uniform", lambda a, b: 0.0)
    limiter = AdaptiveRateLimiter(base_delay=2.0, max_delay=10.0, max_exponent=6)

    cooldowns = [limiter.note_rate_limited() for _ in range(8)]

    assert cooldowns[-1] == pytest.approx(10.0)
    assert max(cooldowns) <= 10.0


@pytest.mark.asyncio
async def test_rate_limiter_success_clears_state() -> None:
    """A single note_success resets the hit counter and clears the gate."""
    limiter = AdaptiveRateLimiter()
    limiter.note_rate_limited()
    limiter.note_rate_limited()
    assert limiter.consecutive_hits == 2

    limiter.note_success()
    assert limiter.consecutive_hits == 0
    assert not limiter.is_blocked
    # Should pass through immediately.
    await asyncio.wait_for(limiter.wait_until_clear(), timeout=0.1)


@pytest.mark.asyncio
async def test_rate_limiter_wait_actually_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """wait_until_clear should actually sleep for the remaining cool-down window."""
    # Small deterministic cool-down so the test is fast but provably non-zero.
    monkeypatch.setattr("pymammotion.aliyun.rate_limiter.random.uniform", lambda a, b: 0.0)
    limiter = AdaptiveRateLimiter(base_delay=0.2, max_delay=1.0)
    limiter.note_rate_limited()

    loop = asyncio.get_running_loop()
    start = loop.time()
    await limiter.wait_until_clear()
    elapsed = loop.time() - start

    assert elapsed >= 0.15  # allow a tiny fudge for loop scheduling


@pytest.mark.asyncio
async def test_coalescer_deduplicates_in_flight_calls() -> None:
    """Two concurrent callers with the same key share a single factory invocation."""
    coalescer: RequestCoalescer = RequestCoalescer()
    call_count = 0

    async def factory() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return "result"

    results = await asyncio.gather(
        coalescer.run("key-1", factory),
        coalescer.run("key-1", factory),
        coalescer.run("key-1", factory),
    )

    assert results == ["result", "result", "result"]
    assert call_count == 1


@pytest.mark.asyncio
async def test_coalescer_does_not_dedupe_different_keys() -> None:
    """Distinct keys should each invoke their own factory."""
    coalescer: RequestCoalescer = RequestCoalescer()
    call_count = 0

    async def factory() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        return f"result-{call_count}"

    await asyncio.gather(
        coalescer.run("key-a", factory),
        coalescer.run("key-b", factory),
    )

    assert call_count == 2


@pytest.mark.asyncio
async def test_coalescer_propagates_exceptions_to_all_waiters() -> None:
    """If the first caller fails, every pending waiter should see the same exception."""
    coalescer: RequestCoalescer = RequestCoalescer()

    class _FakeError(RuntimeError):
        pass

    async def factory() -> str:
        await asyncio.sleep(0.01)
        raise _FakeError("boom")

    with pytest.raises(_FakeError):
        await asyncio.gather(
            coalescer.run("key", factory),
            coalescer.run("key", factory),
        )


@pytest.mark.asyncio
async def test_coalescer_clears_slot_after_completion() -> None:
    """After the first call completes, the slot frees and a new call re-runs the factory."""
    coalescer: RequestCoalescer = RequestCoalescer()
    call_count = 0

    async def factory() -> int:
        nonlocal call_count
        call_count += 1
        return call_count

    first = await coalescer.run("key", factory)
    second = await coalescer.run("key", factory)

    assert first == 1
    assert second == 2
