"""``stop_polling`` must be reversible, and must stop the BLE loops too.

``restart_keep_alive`` deliberately respects ``_polling_stopped``, and only
``start()`` cleared it — behind an ``is_started`` guard that stays True. A host
that turned polling off and back on therefore never got its loops back, and a
BLE-connected device kept streaming the whole time because the BLE loops exit
only on disconnect or handle stop.
"""

from __future__ import annotations

import asyncio

from pymammotion.device.handle import DeviceHandle


class _Sleeper:
    """Stand-in for a poll loop: runs until cancelled."""

    def __init__(self) -> None:
        self.cancelled = False

    async def run(self, _handle: object) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def _handle() -> DeviceHandle:
    handle = DeviceHandle.__new__(DeviceHandle)
    handle._stopping = False  # noqa: SLF001
    handle._polling_stopped = False  # noqa: SLF001
    handle._skips_activity_loops = False  # noqa: SLF001
    handle._keep_alive_task = None  # noqa: SLF001
    handle._ble_keep_alive_task = None  # noqa: SLF001
    handle._ble_polling_task = None  # noqa: SLF001
    handle._dynamics_line_task = None  # noqa: SLF001
    handle._transports = {}  # noqa: SLF001
    handle.device_name = "Luba-TEST"
    return handle


async def test_stop_polling_cancels_the_ble_loops_as_well() -> None:
    """A BLE-connected device must actually go quiet, not just stop MQTT polls."""
    handle = _handle()
    loops = [_Sleeper() for _ in range(3)]
    handle._keep_alive_task = asyncio.create_task(loops[0].run(handle))  # noqa: SLF001
    handle._ble_keep_alive_task = asyncio.create_task(loops[1].run(handle))  # noqa: SLF001
    handle._ble_polling_task = asyncio.create_task(loops[2].run(handle))  # noqa: SLF001
    await asyncio.sleep(0)

    await handle.stop_polling()

    assert all(loop.cancelled for loop in loops)
    assert handle._keep_alive_task is None  # noqa: SLF001
    assert handle._ble_keep_alive_task is None  # noqa: SLF001
    assert handle._ble_polling_task is None  # noqa: SLF001


async def test_restart_keep_alive_still_respects_a_stop() -> None:
    """A reconnect must not override the host's "polling off"."""
    handle = _handle()
    await handle.stop_polling()

    await handle.restart_keep_alive()

    assert handle._keep_alive_task is None  # noqa: SLF001


async def test_resume_polling_clears_the_stop_and_restarts_mqtt() -> None:
    """The explicit way back that only ``start()`` used to provide."""
    handle = _handle()
    await handle.stop_polling()

    await handle.resume_polling()

    assert handle._polling_stopped is False  # noqa: SLF001
    assert handle._keep_alive_task is not None  # noqa: SLF001
    handle._keep_alive_task.cancel()  # noqa: SLF001


async def test_resume_polling_leaves_ble_alone_when_it_is_not_connected() -> None:
    """No BLE link means no BLE loops to bring back."""
    handle = _handle()
    await handle.stop_polling()

    await handle.resume_polling()

    assert handle._ble_polling_task is None  # noqa: SLF001
    assert handle._ble_keep_alive_task is None  # noqa: SLF001
    handle._keep_alive_task.cancel()  # noqa: SLF001


async def test_resume_polling_is_inert_while_stopping() -> None:
    """A handle on its way down must not spawn fresh loops."""
    handle = _handle()
    await handle.stop_polling()
    handle._stopping = True  # noqa: SLF001

    await handle.resume_polling()

    assert handle._polling_stopped is True  # noqa: SLF001
    assert handle._keep_alive_task is None  # noqa: SLF001


async def test_a_ble_reconnect_does_not_resurrect_stopped_loops() -> None:
    """_on_ble_connected restarts all three loops; the stop has to survive that."""
    handle = _handle()
    await handle.stop_polling()

    handle._start_ble_loop()  # noqa: SLF001
    handle._start_ble_polling_loop()  # noqa: SLF001
    handle._start_dynamics_line_loop()  # noqa: SLF001

    assert handle._ble_keep_alive_task is None  # noqa: SLF001
    assert handle._ble_polling_task is None  # noqa: SLF001
    assert handle._dynamics_line_task is None  # noqa: SLF001
