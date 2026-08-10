"""Reusable frame-transfer protocols shared by the sagas.

The device speaks a small number of transfer shapes.  Sagas used to hand-roll
each one, which is where the duplication lived once frame extraction and the
retry policy had been consolidated onto :class:`~pymammotion.messaging.saga.Saga`.

These are deliberately **free functions, not base-class methods**.  A saga's
*control flow* is genuinely its own — map fetch resumes from device state,
mow-path batches by transaction, edge mapping is paced by a physical border walk
— and trying to express that as inherited template methods or declarative steps
just reinvents Python's control flow in data.  Only the *mechanics* repeat, so
only the mechanics are shared: a saga calls these where they fit and writes
ordinary loops where they don't.

Two shapes are covered:

``ack_stream``
    The device streams frames and waits for an echo of each before sending the
    next.  Used for hash lists and common-data transfers.

``indexed_fetch``
    The app asks for item *i* and the device answers with exactly one frame.
    Used for stored plans, where the first response carries the total.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.transport.base import CommandTimeoutError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

_logger = logging.getLogger(__name__)

#: ``LubaSubMsg`` envelope → the oneof group its leaves live in, or ``None`` when
#: the envelope's leaves are plain fields.  ``MctlNav`` nests everything in a
#: ``SubNavMsg`` oneof; ``SpinoCtrl`` has a single plain ``plan_job_set`` field.
#: Add an entry here to teach the collector a new envelope rather than overriding
#: ``Saga._collect_frames`` in a subclass.
LEAF_GROUPS: dict[str, str | None] = {
    "nav": "SubNavMsg",
    "ctrl": None,
}


def extract_frame(
    msg: Any,
    expected: str | tuple[str, ...] | frozenset[str],
    *,
    envelope: str = "nav",
) -> tuple[str, Any] | None:
    """Return ``(frame_name, frame_value)`` for a matching frame, else ``None``.

    *msg* must be a ``LubaMsg`` whose populated ``LubaSubMsg`` member is
    *envelope*, carrying a leaf named in *expected*.

    Returns ``None`` on any unpacking failure (malformed frame, missing oneof) so
    callers don't need a try/except — a frame we can't parse is noise, not a
    failure.
    """
    expected_set = (expected,) if isinstance(expected, str) else expected
    try:
        sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
        if sub_name != envelope or sub_val is None:
            return None
        group = LEAF_GROUPS.get(envelope, "SubNavMsg")
        if group is not None:
            frame_name, frame_val = betterproto2.which_one_of(sub_val, group)
            return (frame_name, frame_val) if frame_name in expected_set else None
        # Plain-field envelope: no oneof to interrogate, so take the first expected
        # attribute that is actually populated.
        for name in expected_set:
            value = getattr(sub_val, name, None)
            if value is not None:
                return name, value
    except Exception:  # noqa: BLE001 — protobuf malformed frames are noise, not failures
        return None
    return None


async def _await_frame(
    queue: asyncio.Queue[Any],
    *,
    field: str,
    envelope: str,
    timeout: float,
    current_frame: int,
) -> Any:
    """Await the next queued message and unwrap it, or raise ``CommandTimeoutError``."""
    try:
        msg = await asyncio.wait_for(queue.get(), timeout=timeout)
    except TimeoutError:
        raise CommandTimeoutError(field, current_frame) from None
    frame = extract_frame(msg, field, envelope=envelope)
    if frame is None:
        # The collector already filtered on this field, so this means a malformed
        # frame slipped through — treat it as an interruption rather than crashing.
        raise CommandTimeoutError(field, current_frame)
    return frame[1]


async def ack_stream(
    queue: asyncio.Queue[Any],
    *,
    field: str,
    ack: Callable[[Any], Awaitable[None]],
    timeout: float,
    envelope: str = "nav",
    allow_empty: bool = False,
) -> dict[int, Any]:
    """Receive frames, acking each one, until the whole set has arrived.

    The device sends frame N+1 only after it sees an echo of frame N, so *ack* is
    awaited for **every** frame — including the last, and including duplicates.  A
    duplicate means the device didn't hear the previous ack, so re-acking is the
    correct response, not a wasted send.  (The APK does the same:
    ``HashDataManager.setRegionalData`` acks unconditionally on receipt.)

    Completion is ``len(frames) >= total_frame``, deliberately **not**
    ``current_frame == total_frame``: the device retransmits unacked frames, so
    the final frame can arrive while an earlier one is still missing, and the
    frame-number rule would end the transfer with a hole in it.

    Args:
        queue:       Frame queue from ``Saga._collect_frames``.
        field:       Leaf name being collected — also used in timeout errors.
        ack:         Called with each received frame value; must send the echo.
        timeout:     Per-frame timeout, normally the saga's ``step_timeout``.
        envelope:    ``LubaSubMsg`` member the frames arrive on.
        allow_empty: When True, silence *before the first frame* returns ``{}``
                     instead of raising — for requests where "no response" is a
                     legitimate empty answer.  Silence mid-stream still raises.

    Returns:
        ``{current_frame: frame_value}``.

    Raises:
        CommandTimeoutError: The device went quiet before the set was complete.

    """
    frames: dict[int, Any] = {}
    while True:
        try:
            frame = await _await_frame(
                queue,
                field=field,
                envelope=envelope,
                timeout=timeout,
                current_frame=len(frames) + 1,
            )
        except CommandTimeoutError:
            if allow_empty and not frames:
                _logger.debug("ack_stream(%s): no response — treating as empty", field)
                return {}
            raise

        await ack(frame)
        frames[frame.current_frame] = frame

        total = frame.total_frame
        _logger.debug("ack_stream(%s): frame %d/%d (%d banked)", field, frame.current_frame, total, len(frames))
        if total and len(frames) >= total:
            return frames


async def indexed_fetch(
    queue: asyncio.Queue[Any],
    *,
    field: str,
    request: Callable[[int], Awaitable[None]],
    total_of: Callable[[Any], int],
    timeout: float,
    envelope: str = "nav",
) -> AsyncIterator[Any]:
    """Fetch items one index at a time, yielding each frame the device returns.

    The first response carries the total, so index 0 is requested unconditionally
    and *total_of* is consulted on its reply to decide how many more to ask for.
    A total of 0 means the device has nothing stored and nothing is yielded.

    Args:
        queue:    Frame queue from ``Saga._collect_frames``.
        field:    Leaf name being collected.
        request:  Called with each index; must send the request for that item.
        total_of: Reads the item count from the first frame.
        timeout:  Per-response timeout, normally the saga's ``step_timeout``.
        envelope: ``LubaSubMsg`` member the frames arrive on.

    Raises:
        CommandTimeoutError: The device didn't answer a request.

    """
    await request(0)
    first = await _await_frame(queue, field=field, envelope=envelope, timeout=timeout, current_frame=1)

    total = total_of(first)
    if total == 0:
        _logger.debug("indexed_fetch(%s): device has nothing stored", field)
        return

    yield first

    for index in range(1, total):
        _logger.debug("indexed_fetch(%s): requesting %d/%d", field, index + 1, total)
        await request(index)
        yield await _await_frame(queue, field=field, envelope=envelope, timeout=timeout, current_frame=index + 1)
