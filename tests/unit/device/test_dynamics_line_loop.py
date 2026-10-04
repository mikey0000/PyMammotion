"""When the lidar dynamics line is polled.

Over BLE, which has no send quota, for the whole job, as the APK does, until the link
drops.  Over the cloud a fetch costs a request plus one ack per frame from the 600-send
budget, so only inside a viewing window that each map poll opens or extends.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.device.dynamics_line_loop import DYNAMICS_LINE_WATCH_SECONDS
from pymammotion.device.handle import DeviceHandle
from pymammotion.messaging.command_queue import DeviceCommandQueue
from pymammotion.messaging.common_data_saga import CommonDataSaga
from pymammotion.transport.base import TransportAvailability, TransportType
from pymammotion.utility.constant.device_enums import WorkMode
from tests._helpers import let_others_run, make_mock_handle, make_mock_transport

_LIDAR = "Luba-LA123"


class _Clock:
    """``time.monotonic`` shifted by a controllable offset; it keeps ticking so asyncio timers still fire."""

    def __init__(self, real: object) -> None:
        self._real = real
        self.offset = 0.0

    def __call__(self) -> float:
        return self._real() + self.offset  # type: ignore[operator]

    async def advance(self, seconds: float) -> None:
        self.offset += seconds
        await let_others_run()


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Clock]:
    fake = _Clock(time.monotonic)
    monkeypatch.setattr(time, "monotonic", fake)
    yield fake


async def _mower(
    *,
    name: str = _LIDAR,
    transport: TransportType = TransportType.CLOUD_ALIYUN,
    sys_status: WorkMode = WorkMode.MODE_WORKING,
    usable: bool = True,
    firmware: str = "",
) -> tuple[DeviceHandle, AsyncMock]:
    device = MowerDevice(name=name)
    device.report_data.dev.sys_status = sys_status.value
    device.device_firmwares.device_version = firmware
    handle = make_mock_handle("dev1", name, device=device)
    await handle.add_transport(make_mock_transport(transport, usable=usable))
    enqueue = AsyncMock()
    handle.enqueue_saga = enqueue  # type: ignore[method-assign]
    await let_others_run()
    return handle, enqueue


def _polls(enqueue: AsyncMock) -> int:
    return sum(isinstance(call.args[0], CommonDataSaga) for call in enqueue.await_args_list)


async def _drop_ble(handle: DeviceHandle) -> None:
    ble = handle.get_transport(TransportType.BLE)
    assert ble is not None
    ble.is_connected = False  # type: ignore[misc]
    await handle._make_availability_handler(TransportType.BLE)(TransportAvailability.DISCONNECTED)  # noqa: SLF001
    await let_others_run()


async def _ble_and_cloud_mower() -> tuple[DeviceHandle, AsyncMock]:
    handle, enqueue = await _mower()
    await handle.add_transport(make_mock_transport(TransportType.BLE))
    await let_others_run()
    return handle, enqueue


async def test_a_ble_link_polls_the_whole_job_without_a_viewer(clock: _Clock) -> None:
    handle, enqueue = await _mower(transport=TransportType.BLE)
    assert _polls(enqueue) == 1

    await clock.advance(10)
    assert _polls(enqueue) == 2
    await clock.advance(DYNAMICS_LINE_WATCH_SECONDS)

    assert _polls(enqueue) > 2
    await handle.stop()


async def test_a_ble_disconnect_stops_the_poll(clock: _Clock) -> None:
    handle, enqueue = await _ble_and_cloud_mower()
    await _drop_ble(handle)
    polled = _polls(enqueue)

    await clock.advance(120)

    assert _polls(enqueue) == polled
    await handle.stop()


async def test_a_ble_disconnect_falls_back_to_the_cloud_cadence_while_watched(clock: _Clock) -> None:
    handle, enqueue = await _ble_and_cloud_mower()
    handle.watch_dynamics_line()
    await _drop_ble(handle)
    polled = _polls(enqueue)

    await clock.advance(10)
    assert _polls(enqueue) == polled
    await clock.advance(50)

    assert _polls(enqueue) == polled + 1
    await handle.stop()


async def test_the_cloud_is_not_polled_without_a_viewer(clock: _Clock) -> None:
    """A whole job polled over the cloud would spend the 600-send quota on a line nobody sees."""
    handle, enqueue = await _mower()

    await clock.advance(120)

    assert _polls(enqueue) == 0
    await handle.stop()


async def test_looking_at_the_map_fetches_at_once(clock: _Clock) -> None:
    handle, enqueue = await _mower()

    handle.watch_dynamics_line()
    await let_others_run()

    assert _polls(enqueue) == 1
    await handle.stop()


async def test_the_cloud_polls_once_a_minute_while_watched(clock: _Clock) -> None:
    handle, enqueue = await _mower()
    handle.watch_dynamics_line()
    await let_others_run()

    await clock.advance(10)
    assert _polls(enqueue) == 1
    await clock.advance(50)

    assert _polls(enqueue) == 2
    await handle.stop()


async def test_polling_stops_when_the_window_lapses(clock: _Clock) -> None:
    handle, enqueue = await _mower()
    handle.watch_dynamics_line()
    await let_others_run()

    await clock.advance(DYNAMICS_LINE_WATCH_SECONDS + 1)
    polled = _polls(enqueue)
    await clock.advance(120)

    assert _polls(enqueue) == polled
    await handle.stop()


async def test_another_map_poll_reopens_a_lapsed_window(clock: _Clock) -> None:
    handle, enqueue = await _mower()
    handle.watch_dynamics_line()
    await let_others_run()
    await clock.advance(DYNAMICS_LINE_WATCH_SECONDS + 1)
    polled = _polls(enqueue)

    handle.watch_dynamics_line()
    await let_others_run()

    assert _polls(enqueue) == polled + 1
    await handle.stop()


async def test_a_shorter_watch_never_shortens_an_open_window(clock: _Clock) -> None:
    handle, _enqueue = await _mower()
    handle.watch_dynamics_line()

    handle.watch_dynamics_line(duration=10)
    await clock.advance(200)

    assert handle.dynamics_line_watched
    await handle.stop()


async def test_nothing_is_fetched_outside_a_job(clock: _Clock) -> None:
    handle, enqueue = await _mower(transport=TransportType.BLE, sys_status=WorkMode.MODE_READY)

    handle.watch_dynamics_line()
    await clock.advance(10)

    assert _polls(enqueue) == 0
    await handle.stop()


async def test_the_cloud_is_not_polled_while_mow_path_fetching_is_off(clock: _Clock) -> None:
    handle, enqueue = await _mower()
    handle.set_mow_path_fetch_enabled(value=False)

    handle.watch_dynamics_line()
    await let_others_run()

    assert _polls(enqueue) == 0
    await handle.stop()


async def test_a_mower_without_a_dynamics_line_is_never_polled(clock: _Clock) -> None:
    handle, enqueue = await _mower(name="Luba-VS563L6H", transport=TransportType.BLE)

    handle.watch_dynamics_line()
    await clock.advance(10)

    assert _polls(enqueue) == 0
    await handle.stop()


@pytest.mark.parametrize(("firmware", "polls"), [("1.15.3.4421", 0), ("1.15.3.4422", 1)])
async def test_luba_va_is_polled_from_its_firmware(clock: _Clock, firmware: str, polls: int) -> None:
    handle, enqueue = await _mower(name="Luba-VA123", firmware=firmware)

    handle.watch_dynamics_line()
    await let_others_run()

    assert _polls(enqueue) == polls
    await handle.stop()


async def test_a_running_saga_is_not_interrupted(clock: _Clock) -> None:
    with patch.object(DeviceCommandQueue, "is_saga_active", new_callable=PropertyMock, return_value=True):
        handle, enqueue = await _mower(transport=TransportType.BLE)
        await clock.advance(10)

    assert _polls(enqueue) == 0
    await handle.stop()


async def test_nothing_is_sent_without_a_usable_transport(clock: _Clock) -> None:
    handle, enqueue = await _mower(usable=False)

    handle.watch_dynamics_line()
    await let_others_run()

    assert _polls(enqueue) == 0
    await handle.stop()


async def test_watching_does_not_override_stopped_polling(clock: _Clock) -> None:
    handle, enqueue = await _mower()
    await handle.stop_polling()

    handle.watch_dynamics_line()
    await let_others_run()

    assert _polls(enqueue) == 0
    await handle.stop()


async def test_resuming_polling_picks_an_open_window_back_up(clock: _Clock) -> None:
    handle, enqueue = await _mower()
    handle.watch_dynamics_line()
    await let_others_run()
    await handle.stop_polling()
    polled = _polls(enqueue)

    await handle.resume_polling()
    await let_others_run()

    assert _polls(enqueue) == polled + 1
    await handle.stop()


async def test_resuming_polling_after_the_window_lapsed_stays_quiet(clock: _Clock) -> None:
    handle, enqueue = await _mower()
    handle.watch_dynamics_line()
    await let_others_run()
    await handle.stop_polling()
    await clock.advance(DYNAMICS_LINE_WATCH_SECONDS + 1)
    polled = _polls(enqueue)

    await handle.resume_polling()
    await let_others_run()

    assert _polls(enqueue) == polled
    await handle.stop()


async def test_resuming_polling_restarts_the_ble_poll(clock: _Clock) -> None:
    handle, enqueue = await _mower(transport=TransportType.BLE)
    await handle.stop_polling()
    polled = _polls(enqueue)

    await handle.resume_polling()
    await let_others_run()

    assert _polls(enqueue) == polled + 1
    await handle.stop()


async def test_ble_is_polled_even_while_cloud_mow_path_fetching_is_off(clock: _Clock) -> None:
    """The flag spares the cloud quota; BLE has none to spare."""
    device = MowerDevice(name=_LIDAR)
    device.report_data.dev.sys_status = WorkMode.MODE_WORKING.value
    handle = make_mock_handle("dev1", _LIDAR, device=device)
    handle.set_mow_path_fetch_enabled(value=False)
    enqueue = AsyncMock()
    handle.enqueue_saga = enqueue  # type: ignore[method-assign]

    await handle.add_transport(make_mock_transport(TransportType.BLE))
    await let_others_run()

    assert _polls(enqueue) == 1
    await handle.stop()
