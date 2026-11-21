"""``DeviceHandle``'s saga hooks on its command queue: what happens when a saga ends."""

from __future__ import annotations

from pymammotion.data.model.device import MowingDevice
from tests._helpers import make_mock_handle


async def test_the_end_of_a_saga_wakes_the_poll_loop() -> None:
    """So the loop polls right after the saga rather than waiting out the rest of its interval.

    ``_rearm_event`` is read directly: the handle exposes no observable for "poll loop woken".
    """
    handle = make_mock_handle(device=MowingDevice())
    handle._rearm_event.clear()  # noqa: SLF001

    await handle.queue.on_saga_end()

    assert handle._rearm_event.is_set()  # noqa: SLF001
