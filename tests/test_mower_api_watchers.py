"""Tests for MammotionClient.setup_device_watchers auto-trigger logic."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pymammotion.client import MammotionClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_snapshot(
    handle: MagicMock,
    *,
    ub_path_hash: int = 0,
    path_hash: int = 0,
    current_mow_path: dict | None = None,
) -> None:
    """Populate ``handle.snapshot.raw`` to the state the handler will read."""
    device = MagicMock()
    device.report_data.work.ub_path_hash = ub_path_hash
    device.report_data.work.path_hash = path_hash
    device.map.current_mow_path = current_mow_path if current_mow_path is not None else {}
    handle.snapshot.raw = device


def _make_client_with_handle(
    device_name: str = "Luba-Test",
    *,
    saga_active: bool = False,
) -> tuple[MammotionClient, MagicMock, list]:
    """Return (client, handle_mock, captured_handlers) for the path-hashes watcher.

    ``captured_handlers[0]`` is the handler passed to ``handle.watch_field`` for
    the (ub_path_hash, path_hash) getter.
    """
    client = MammotionClient.__new__(MammotionClient)
    client._watcher_subscriptions = {}

    handle = MagicMock()
    handle.device_name = device_name
    handle.queue.is_saga_active = saga_active

    captured_handlers: list = []

    def _watch_field(_getter, handler):
        captured_handlers.append(handler)
        sub = MagicMock()
        sub.cancel = MagicMock()
        return sub

    handle.watch_field = _watch_field

    registry = MagicMock()
    registry.get_by_name.return_value = handle
    client._device_registry = registry

    client.start_mow_path_saga = AsyncMock()
    client.send_command_with_args = AsyncMock()

    client.setup_device_watchers(device_name)

    return client, handle, captured_handlers


# ---------------------------------------------------------------------------
# Test: no active job (hashes are 0) → no saga triggered
# ---------------------------------------------------------------------------


async def test_watcher_no_trigger_when_hashes_are_zero() -> None:
    """When both ub_path_hash and path_hash are 0 the watcher must not trigger."""
    client, handle, handlers = _make_client_with_handle()
    _set_snapshot(handle, ub_path_hash=0, path_hash=0)

    await handlers[0]((0, 0))

    client.start_mow_path_saga.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: path_hash == 1 is treated as "job ended" (no trigger)
# ---------------------------------------------------------------------------


async def test_watcher_no_trigger_when_path_hash_is_one() -> None:
    """path_hash==1 is a sentinel for "no active job" and must not trigger the saga."""
    client, handle, handlers = _make_client_with_handle()
    _set_snapshot(handle, ub_path_hash=0, path_hash=1)

    await handlers[0]((0, 1))

    client.start_mow_path_saga.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: cover path already loaded → no saga
# ---------------------------------------------------------------------------


async def test_watcher_no_trigger_when_path_already_loaded() -> None:
    """When current_mow_path is already populated the watcher must not trigger."""
    client, handle, handlers = _make_client_with_handle()
    _set_snapshot(
        handle,
        ub_path_hash=99,
        path_hash=42,
        current_mow_path={123: {0: MagicMock()}},
    )

    await handlers[0]((99, 42))

    client.start_mow_path_saga.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: active job (non-zero ub_path_hash) + empty mow path → saga triggered
# ---------------------------------------------------------------------------


async def test_watcher_triggers_on_ub_path_hash_change() -> None:
    """Saga must fire when ub_path_hash becomes non-zero and no path is cached."""
    from pymammotion.data.model import GenerateRouteInformation

    client, handle, handlers = _make_client_with_handle()
    _set_snapshot(handle, ub_path_hash=99, path_hash=0, current_mow_path={})

    await handlers[0]((99, 0))

    client.start_mow_path_saga.assert_awaited_once()
    call = client.start_mow_path_saga.await_args
    assert call.args == ("Luba-Test",)
    assert call.kwargs["zone_hashs"] == []
    assert call.kwargs["skip_planning"] is True
    assert isinstance(call.kwargs["route_info"], GenerateRouteInformation)


# ---------------------------------------------------------------------------
# Test: path_hash changing to a "real" value (not 0 or 1) triggers fetch
# ---------------------------------------------------------------------------


async def test_watcher_triggers_on_path_hash_change() -> None:
    """Saga must fire when path_hash transitions to a value that is not 0 or 1."""
    from pymammotion.data.model import GenerateRouteInformation

    client, handle, handlers = _make_client_with_handle()
    _set_snapshot(handle, ub_path_hash=0, path_hash=42, current_mow_path={})

    await handlers[0]((0, 42))

    client.start_mow_path_saga.assert_awaited_once()
    call = client.start_mow_path_saga.await_args
    assert call.args == ("Luba-Test",)
    assert call.kwargs["zone_hashs"] == []
    assert call.kwargs["skip_planning"] is True
    assert isinstance(call.kwargs["route_info"], GenerateRouteInformation)


# ---------------------------------------------------------------------------
# Test: saga_active guard prevents double-queueing
# ---------------------------------------------------------------------------


async def test_watcher_skips_when_saga_already_active() -> None:
    """If a saga is already active the watcher must not enqueue another."""
    client, handle, handlers = _make_client_with_handle(saga_active=True)
    _set_snapshot(handle, ub_path_hash=42, path_hash=0, current_mow_path={})

    await handlers[0]((42, 0))

    client.start_mow_path_saga.assert_not_awaited()


# ---------------------------------------------------------------------------
# sys_status watcher: starts/stops the rapid report subscription
# ---------------------------------------------------------------------------


async def test_sys_status_working_starts_rapid_stream() -> None:
    """Transition into MODE_WORKING must send request_iot_sys(RPT_START)."""
    from pymammotion.proto import RptAct
    from pymammotion.utility.constant import WorkMode

    client, handle, handlers = _make_client_with_handle()

    # handlers[2] is the sys_status watcher (order: path_hashes, progress, sys_status)
    await handlers[2](WorkMode.MODE_WORKING.value)

    client.send_command_with_args.assert_awaited_once()
    call = client.send_command_with_args.await_args
    assert call.args == ("Luba-Test", "request_iot_sys")
    assert call.kwargs["rpt_act"] == RptAct.RPT_START
    assert call.kwargs["count"] == 0
    assert call.kwargs["period"] == 1000


async def test_sys_status_returning_also_starts_rapid_stream() -> None:
    """MODE_RETURNING is treated as an active state — stream must start."""
    from pymammotion.proto import RptAct
    from pymammotion.utility.constant import WorkMode

    client, _handle, handlers = _make_client_with_handle()

    await handlers[2](WorkMode.MODE_RETURNING.value)

    call = client.send_command_with_args.await_args
    assert call.kwargs["rpt_act"] == RptAct.RPT_START


async def test_sys_status_pause_stops_rapid_stream() -> None:
    """Transition into MODE_PAUSE must send request_iot_sys(RPT_STOP)."""
    from pymammotion.proto import RptAct
    from pymammotion.utility.constant import WorkMode

    client, _handle, handlers = _make_client_with_handle()

    await handlers[2](WorkMode.MODE_PAUSE.value)

    call = client.send_command_with_args.await_args
    assert call.kwargs["rpt_act"] == RptAct.RPT_STOP


async def test_sys_status_charging_stops_rapid_stream() -> None:
    """Transition into MODE_CHARGING (docked) must send RPT_STOP."""
    from pymammotion.proto import RptAct
    from pymammotion.utility.constant import WorkMode

    client, _handle, handlers = _make_client_with_handle()

    await handlers[2](WorkMode.MODE_CHARGING.value)

    call = client.send_command_with_args.await_args
    assert call.kwargs["rpt_act"] == RptAct.RPT_STOP


# ---------------------------------------------------------------------------
# Saga subscription hooks (stop continuous during saga, restart after)
# ---------------------------------------------------------------------------
# The saga hooks are now wired in DeviceHandle.__init__, not by
# setup_device_watchers.  Tests here verify handle-level hook behaviour.


async def test_saga_hooks_installed_on_handle_init() -> None:
    """DeviceHandle.__init__ must wire queue.on_saga_start / on_saga_end."""
    from pymammotion.device.handle import DeviceHandle

    initial = MagicMock()
    handle = DeviceHandle(device_id="dev1", device_name="Luba-SH", initial_device=initial)
    assert handle.queue.on_saga_start is not None
    assert handle.queue.on_saga_end is not None


async def test_on_saga_start_calls_stop_continuous_subscription() -> None:
    """The on_saga_start hook calls _stop_continuous_subscription on the handle."""
    from unittest.mock import patch

    from pymammotion.device.handle import DeviceHandle

    initial = MagicMock()
    handle = DeviceHandle(device_id="dev1", device_name="Luba-SH2", initial_device=initial)

    with patch.object(handle, "_stop_continuous_subscription", new_callable=AsyncMock) as mock_stop:
        await handle.queue.on_saga_start()

    mock_stop.assert_awaited_once()


async def test_on_saga_end_calls_refire_continuous_subscription() -> None:
    """The on_saga_end hook calls _refire_continuous_subscription on the handle."""
    from unittest.mock import patch

    from pymammotion.device.handle import DeviceHandle

    initial = MagicMock()
    handle = DeviceHandle(device_id="dev1", device_name="Luba-SH3", initial_device=initial)

    with patch.object(handle, "_refire_continuous_subscription", new_callable=AsyncMock) as mock_refire:
        await handle.queue.on_saga_end()

    mock_refire.assert_awaited_once()
