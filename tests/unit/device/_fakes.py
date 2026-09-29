"""Hand-written fakes for the device-package unit tests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pymammotion.http.model.fpv_control import FpvControl
from pymammotion.http.model.http import Response
from pymammotion.proto import DrvSessionCtrlReq, DrvSessionExitAppNfty, LubaMsg
from tests._helpers import block_forever

#: An arbitrary epoch-millisecond start, so frames carry realistic app timestamps.
FAKE_CLOCK_START_MS = 1_700_000_000_000


@dataclass(eq=False)
class _FakeTimer:
    due_ms: int
    order: int
    callback: Callable[[], Awaitable[None]]
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeDriveClock:
    """A ``DriveClock`` whose time moves only when a test calls :meth:`advance`.

    Due callbacks are awaited in (due time, scheduling order), so work a callback schedules
    for "now" runs within the same ``advance`` call — no event-loop timing is involved.
    """

    def __init__(self, start_ms: int = FAKE_CLOCK_START_MS) -> None:
        self._now_ms = start_ms
        self._timers: list[_FakeTimer] = []
        self._order = 0

    def now_ms(self) -> int:
        return self._now_ms

    def call_later(self, delay: float, callback: Callable[[], Awaitable[None]]) -> _FakeTimer:
        self._order += 1
        timer = _FakeTimer(self._now_ms + round(delay * 1000), self._order, callback)
        self._timers.append(timer)
        return timer

    @property
    def armed(self) -> int:
        """Timers still waiting to fire."""
        return sum(1 for timer in self._timers if not timer.cancelled)

    async def advance(self, seconds: float = 0.0) -> None:
        target = self._now_ms + round(seconds * 1000)
        while due := sorted(
            (t for t in self._timers if not t.cancelled and t.due_ms <= target), key=lambda t: (t.due_ms, t.order)
        ):
            timer = due[0]
            self._timers.remove(timer)
            self._now_ms = max(self._now_ms, timer.due_ms)
            await timer.callback()
        self._now_ms = target


@dataclass
class FrameSink:
    """The cloud send a session is given: records every payload and can fail on demand.

    *failures* is consumed one per send: an exception instance is raised, ``"hang"`` blocks
    until the send's *timeout* cuts it, as the client's send does, ``None`` succeeds.  Once it
    is exhausted every send succeeds.
    """

    failures: list[BaseException | str | None] = field(default_factory=list)
    sent: list[LubaMsg] = field(default_factory=list)
    timeouts: list[float] = field(default_factory=list)

    async def __call__(self, payload: bytes, *, timeout: float) -> None:
        self.sent.append(LubaMsg().parse(payload))
        self.timeouts.append(timeout)
        if not self.failures:
            return
        if (failure := self.failures.pop(0)) == "hang":
            async with asyncio.timeout(timeout):
                await block_forever()
        elif isinstance(failure, BaseException):
            raise failure

    @property
    def ctrl(self) -> list[DrvSessionCtrlReq]:
        return [m.driver.todev_session_ctrl_req for m in self.sent if m.driver.todev_session_ctrl_req is not None]

    @property
    def exits(self) -> list[DrvSessionExitAppNfty]:
        return [m.driver.todev_session_exit_nfty for m in self.sent if m.driver.todev_session_exit_nfty is not None]

    @property
    def kinds(self) -> list[str]:
        """``"frame"`` / ``"exit"`` per payload, in send order."""
        return ["frame" if m.driver.todev_session_ctrl_req is not None else "exit" for m in self.sent]


@dataclass
class ScriptedTokens:
    """An ``FpvTokenSource`` answering from scripts; an exception in a script is raised.

    Each token request takes the next of *request_gates*, if any is left, and answers only
    once that gate is set; the answer is the next script entry at that moment.
    """

    requests: list[Response[FpvControl] | BaseException] = field(default_factory=list)
    refreshes: list[Response[FpvControl] | BaseException] = field(default_factory=list)
    refreshed_with: list[str] = field(default_factory=list)
    request_count: int = 0
    request_gates: list[asyncio.Event] = field(default_factory=list)

    async def request(self) -> Response[FpvControl]:
        self.request_count += 1
        if self.request_gates:
            await self.request_gates.pop(0).wait()
        return self._answer(self.requests, "request")

    async def refresh(self, token: str) -> Response[FpvControl]:
        self.refreshed_with.append(token)
        return self._answer(self.refreshes, "refresh")

    @staticmethod
    def _answer(script: list[Response[FpvControl] | BaseException], call: str) -> Response[FpvControl]:
        if not script:
            msg = f"unscripted token {call}"
            raise AssertionError(msg)
        if isinstance(item := script.pop(0), BaseException):
            raise item
        return item
