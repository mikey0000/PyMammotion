"""Shared rate limiting + request coalescing for the Aliyun cloud gateway.

Motivation
----------
Aliyun's IoT HTTP API enforces per-account rate limits that routinely fire
``TooManyRequestsException`` (HTTP 429) during the HA integration's startup
burst — `rtk_dock_location`, `bidire_comm_cmd`, `mow_path_fetch`, and the
device-list polling are all issued back-to-back.  Prior to this module there
was no *global* awareness of being rate limited: every concurrent caller
into :py:meth:`CloudIOTGateway.send_cloud_command` would hit the 429
independently and burn another request slot, and the Aliyun SDK's own
``autoretry=True`` silently compounded that by retrying internally before
surfacing the exception.

This module provides two small, stateless-feeling primitives that
``CloudIOTGateway`` mixes into its HTTP code path:

* :class:`AdaptiveRateLimiter` — one asyncio-safe gate per gateway instance.
  When a 429 is observed, *all* subsequent calls await the cool-down before
  even attempting the network request.  Cool-downs grow exponentially with
  jitter while 429s keep arriving; a single success resets the counter.
* :class:`RequestCoalescer` — an asyncio-safe ``(key) -> Future`` map so that
  identical in-flight read requests share a single wire call instead of
  issuing N duplicates.  Writes shouldn't be coalesced, so callers opt in
  per-request.

Both primitives are deliberately transport-agnostic: no Aliyun SDK imports,
no mashumaro models, nothing that would couple them to a specific endpoint.
That keeps them usable by the MA-IoT client (``pymammotion/http/ma_iot.py``)
or future transports without duplication.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import logging
import random
import time
from typing import Any, TypeVar

_logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class AdaptiveRateLimiter:
    """Exponential-with-jitter gate over a rate-limited outbound channel.

    Usage pattern::

        limiter = AdaptiveRateLimiter()

        async def send() -> Response:
            await limiter.wait_until_clear()
            try:
                response = await _raw_send()
            except TooManyRequestsException:
                limiter.note_rate_limited()
                raise
            limiter.note_success()
            return response

    Threading / concurrency
    -----------------------
    All methods are safe to call from any coroutine on a single event loop.
    ``wait_until_clear`` is *not* a strict serialiser — if many coroutines are
    waiting on the same cool-down they will all wake simultaneously and fire
    in parallel after the window elapses.  That's intentional: on a fresh
    token bucket the limiter should allow burst traffic; the gate is
    specifically to prevent thundering-herd retries while the remote is
    actively refusing requests.
    """

    #: Base cool-down on the first 429 (seconds).
    base_delay: float = 2.0
    #: Absolute ceiling for a single cool-down (seconds).
    max_delay: float = 60.0
    #: Cap on the exponential growth exponent. ``2 ** max_exponent`` plus
    #: jitter still obeys ``max_delay``; this is just a numerical safety net.
    max_exponent: int = 6
    #: Fraction of the base cool-down to add as uniform jitter (0.2 = ±20%).
    jitter_fraction: float = 0.2

    _consecutive_hits: int = 0
    _blocked_until_monotonic: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def is_blocked(self) -> bool:
        """True when the limiter is currently holding new requests back."""
        return self._blocked_until_monotonic > time.monotonic()

    @property
    def consecutive_hits(self) -> int:
        """Number of 429s observed since the last successful request."""
        return self._consecutive_hits

    async def wait_until_clear(self) -> None:
        """Block the caller until the cool-down window elapses (no-op if clear)."""
        now = time.monotonic()
        remaining = self._blocked_until_monotonic - now
        if remaining <= 0:
            return
        _logger.info(
            "Aliyun rate limiter: pausing outbound send for %.1fs (consecutive 429s=%d)",
            remaining,
            self._consecutive_hits,
        )
        await asyncio.sleep(remaining)

    def note_rate_limited(self) -> float:
        """Record a 429 and extend the cool-down window.

        Returns the total cool-down in seconds from now.  Safe to call from
        multiple coroutines; the longest cool-down wins (i.e. concurrent 429s
        don't double up, they just refresh the deadline).
        """
        self._consecutive_hits = min(self._consecutive_hits + 1, self.max_exponent)
        exponent = self._consecutive_hits
        target = min(self.base_delay * (2 ** (exponent - 1)), self.max_delay)
        jitter = random.uniform(0, max(target * self.jitter_fraction, 0.0))
        cooldown = target + jitter
        deadline = time.monotonic() + cooldown
        if deadline > self._blocked_until_monotonic:
            self._blocked_until_monotonic = deadline
        _logger.warning(
            "Aliyun rate limiter: 429 #%d observed, cooling down %.1fs",
            self._consecutive_hits,
            cooldown,
        )
        return cooldown

    def note_success(self) -> None:
        """Record a successful request and reset the cool-down state."""
        if self._consecutive_hits == 0 and self._blocked_until_monotonic == 0.0:
            return
        self._consecutive_hits = 0
        self._blocked_until_monotonic = 0.0


class RequestCoalescer:
    """Map of ``key -> asyncio.Future`` deduplicating in-flight read requests.

    Example::

        coalescer: RequestCoalescer[bytes] = RequestCoalescer()

        async def get_device_properties(iot_id: str) -> bytes:
            async def _do() -> bytes:
                return await _raw_fetch(iot_id)

            return await coalescer.run(("props", iot_id), _do)

    If ``get_device_properties("foo")`` is already in flight when a second
    caller arrives, the second caller awaits the first's result rather than
    issuing a duplicate request.  Exceptions propagate to every awaiter.

    Intentional non-features:
    * No TTL cache — the moment the first call completes, the entry clears.
      Callers who want actual result caching should layer that above.
    * No cancellation shielding — if the first caller is cancelled, remaining
      awaiters get :class:`asyncio.CancelledError` too.  Keeping the contract
      simple; HA callers don't typically cancel individual requests.
    """

    def __init__(self) -> None:
        self._inflight: dict[Any, asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()

    async def run(self, key: Any, factory: Callable[[], Awaitable[T]]) -> T:
        """Execute ``factory()`` under ``key``; deduplicate if already in flight."""
        async with self._lock:
            existing = self._inflight.get(key)
            if existing is not None:
                _logger.debug("RequestCoalescer: sharing in-flight result for key=%r", key)
                future: asyncio.Future[T] = existing  # type: ignore[assignment]
                shared = True
            else:
                future = asyncio.get_running_loop().create_future()
                self._inflight[key] = future
                shared = False

        if shared:
            return await future

        try:
            result = await factory()
        except BaseException as exc:  # noqa: BLE001 — must forward all errors
            if not future.done():
                future.set_exception(exc)
            raise
        else:
            if not future.done():
                future.set_result(result)
            return result
        finally:
            async with self._lock:
                # Only clear if nobody replaced us (paranoia; same key cannot
                # legitimately be overwritten while this task holds the slot)
                if self._inflight.get(key) is future:
                    self._inflight.pop(key, None)
