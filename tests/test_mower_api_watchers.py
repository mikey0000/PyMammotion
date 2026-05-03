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
# sys_status watcher was removed — cadence/streaming now lives in DeviceHandle
# (BLE polling loop + MQTT cadence table).  No client-side watcher fires
# request_iot_sys on sys_status transitions any more.
# ---------------------------------------------------------------------------


async def test_setup_device_watchers_does_not_register_sys_status_watcher() -> None:
    """setup_device_watchers must not install a sys_status watcher.

    Stream lifecycle is owned by DeviceHandle._ble_polling_loop; the client
    used to install a watcher that toggled request_iot_sys here, but that has
    been moved.  Three watchers should be registered: path-hashes, progress,
    bol_hash.
    """
    _client, _handle, handlers = _make_client_with_handle()
    assert len(handlers) == 3


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


async def test_on_saga_start_is_noop() -> None:
    """The on_saga_start hook is a no-op in the new poll-based design.

    Poll items use skip_if_saga_active=True so no explicit subscription stop is needed.
    """
    from pymammotion.device.handle import DeviceHandle

    initial = MagicMock()
    handle = DeviceHandle(device_id="dev1", device_name="Luba-SH2", initial_device=initial)

    # Should complete without error and without touching any transport or subscription state.
    await handle.queue.on_saga_start()


async def test_on_saga_end_sets_rearm_event() -> None:
    """The on_saga_end hook sets _rearm_event to wake the poll loop immediately.

    This lets the loop re-evaluate and send a poll right after the saga finishes
    instead of waiting out the remainder of the poll interval.
    """
    from pymammotion.device.handle import DeviceHandle

    initial = MagicMock()
    handle = DeviceHandle(device_id="dev1", device_name="Luba-SH3", initial_device=initial)

    handle._rearm_event.clear()  # noqa: SLF001
    assert not handle._rearm_event.is_set()  # noqa: SLF001

    await handle.queue.on_saga_end()

    assert handle._rearm_event.is_set()  # noqa: SLF001
