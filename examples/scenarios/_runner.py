"""Runner that wraps a scenario coroutine in try/except + step timing.

A scenario implementation is a plain async function that calls
``runner.step(name, ...)`` to record progress.  When it returns the report
is finalised; if it raises, the runner captures the exception type, the
last step it was on, and a *depth snapshot* so the report shows how far
the saga got.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

from examples.scenarios._common import get_handle, snapshot_map, snapshot_mow_path, transport_label
from examples.scenarios._report import ScenarioReport, ScenarioStep, utc_now_iso
from pymammotion.messaging.saga import SagaFailedError
from pymammotion.transport.base import CommandTimeoutError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.client import MammotionClient
    from pymammotion.device.handle import DeviceHandle

_logger = logging.getLogger(__name__)


class ScenarioRunner:
    """Mutable accumulator passed to scenario implementations.

    Implementations call ``await runner.step(name, coro)`` for each
    observable step.  The runner records duration + details and re-raises
    any exception so :func:`run_scenario` can finalise the report.
    """

    def __init__(self, report: ScenarioReport, handle: DeviceHandle, which: str = "map") -> None:
        self.report = report
        self.handle = handle
        self._which = which  # "map" or "mow_path" — controls which snapshot is taken
        self._current_step: str | None = None

    @property
    def which(self) -> str:
        return self._which

    @which.setter
    def which(self, value: str) -> None:
        self._which = value

    def snapshot(self) -> dict[str, Any]:
        """Take the snapshot matching the runner's mode."""
        if self._which == "mow_path":
            return snapshot_mow_path(self.handle)
        return snapshot_map(self.handle)

    async def step(
        self,
        name: str,
        coro: Awaitable[Any] | Callable[[], Awaitable[Any]] | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> Any:
        """Run *coro* as a named step and record its outcome.

        *coro* may be an already-constructed awaitable, a zero-arg callable
        returning one, or ``None`` for a marker-only step (used to record
        a checkpoint without an associated async call).
        """
        self._current_step = name
        started = time.monotonic()
        step_details = dict(details or {})
        try:
            if coro is None:
                result = None
            elif callable(coro):
                result = await coro()
            else:
                result = await coro
        except Exception as exc:  # let outer handler finalise the report
            duration = time.monotonic() - started
            self.report.steps.append(ScenarioStep(name=name, ok=False, duration_s=duration, details=step_details))
            _logger.debug("scenario step %r failed: %s: %s", name, type(exc).__name__, exc)
            raise
        duration = time.monotonic() - started
        self.report.steps.append(ScenarioStep(name=name, ok=True, duration_s=duration, details=step_details))
        return result


async def run_scenario(
    name: str,
    client: MammotionClient,
    device_name: str,
    impl: Callable[[ScenarioRunner], Awaitable[None]],
    *,
    which: str = "map",
    print_summary: bool = True,
) -> ScenarioReport:
    """Run *impl* as a named scenario, returning a :class:`ScenarioReport`.

    Catches expected saga failures (``SagaFailedError``, ``CommandTimeoutError``,
    ``asyncio.TimeoutError``, ``asyncio.CancelledError``) plus generic
    exceptions; populates ``report.failure`` with a depth snapshot in each case.
    """
    started_at = utc_now_iso()
    t0 = time.monotonic()
    handle = get_handle(client, device_name)
    report = ScenarioReport(
        name=name,
        transport=transport_label(handle),
        device_name=device_name,
        ok=False,
        started_at=started_at,
        duration_s=0.0,
    )
    runner = ScenarioRunner(report, handle, which=which)

    try:
        await impl(runner)
        report.ok = True
    except (TimeoutError, SagaFailedError, CommandTimeoutError, asyncio.CancelledError) as exc:
        report.failure = {
            "type": type(exc).__name__,
            "message": str(exc) or repr(exc),
            "last_step": runner._current_step,  # noqa: SLF001 - same module trust
            "snapshot": runner.snapshot(),
        }
    except Exception as exc:
        report.failure = {
            "type": type(exc).__name__,
            "message": str(exc) or repr(exc),
            "last_step": runner._current_step,  # noqa: SLF001
            "snapshot": runner.snapshot(),
        }
        _logger.exception("scenario %r raised an unhandled exception", name)
    finally:
        report.duration_s = time.monotonic() - t0
        with contextlib.suppress(Exception):
            report.result_counts = runner.snapshot()
        if print_summary:
            print(report.pretty())  # noqa: T201

    return report
