"""AutoFetchWatchers — "when this field changes, go fetch that".

Extracted from MammotionClient: a rule set needing only the device registry and the
three saga entry points.  It owns its own subscription bookkeeping, and owns nothing
about cadence — how often the device is asked for state lives in DeviceHandle.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import AsyncMock, MagicMock, PropertyMock, create_autospec, patch

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.function_codes import FunctionCodes
from pymammotion.data.model.hash_list import LINE_HASH_SUB_CMD, MowPath, MowPathPacket, NavGetHashListData
from pymammotion.data.model.report_info import LocationData
from pymammotion.device.auto_fetch import AutoFetchWatchers
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.messaging.command_queue import DeviceCommandQueue
from pymammotion.transport.base import TransportType
from pymammotion.utility.constant.device_enums import WorkMode
from tests._helpers import make_mock_handle, make_mock_transport, make_mower_with_synced_map


def _watchers(handle: MagicMock | None = None) -> tuple[AutoFetchWatchers, MagicMock, list]:
    captured: list = []

    if handle is None:
        handle = create_autospec(DeviceHandle, instance=True)
        handle.device_name = "Luba-Test"
        handle.queue = create_autospec(DeviceCommandQueue, instance=True)
        handle.queue.is_saga_active = False

    def _watch_field(_getter, handler):
        captured.append(handler)
        return MagicMock(cancel=MagicMock())

    handle.watch_field = _watch_field
    handle.watch_until_handled = _watch_field
    registry = MagicMock()
    registry.get_by_name.return_value = handle
    return (
        AutoFetchWatchers(
            registry,
            start_map_sync=AsyncMock(),
            start_plan_sync=AsyncMock(),
            start_mow_path_saga=AsyncMock(),
        ),
        handle,
        captured,
    )


def test_the_client_no_longer_owns_the_watcher_bookkeeping() -> None:
    from pymammotion.client import MammotionClient

    assert not hasattr(MammotionClient, "_watcher_subscriptions")


def test_setup_registers_watchers_for_the_device() -> None:
    watchers, _, captured = _watchers()

    watchers.setup_device_watchers("Luba-Test")

    assert captured, "expected at least one watch_field subscription"
    assert "Luba-Test" in watchers._watcher_subscriptions


def test_setup_is_idempotent_and_replaces_prior_subscriptions() -> None:
    """Re-running setup must not leave two sets of handlers firing per change."""
    watchers, _, _ = _watchers()

    watchers.setup_device_watchers("Luba-Test")
    first = list(watchers._watcher_subscriptions["Luba-Test"])
    watchers.setup_device_watchers("Luba-Test")
    second = watchers._watcher_subscriptions["Luba-Test"]

    assert len(second) == len(first)
    for sub in first:
        sub.cancel.assert_called_once()


def test_teardown_cancels_and_forgets() -> None:
    watchers, _, _ = _watchers()
    watchers.setup_device_watchers("Luba-Test")
    subs = list(watchers._watcher_subscriptions["Luba-Test"])

    watchers.teardown_device_watchers("Luba-Test")

    assert "Luba-Test" not in watchers._watcher_subscriptions
    for sub in subs:
        sub.cancel.assert_called_once()


def test_teardown_is_safe_for_an_unknown_device() -> None:
    watchers, _, _ = _watchers()
    watchers.teardown_device_watchers("never-set-up")  # must not raise


def test_setup_for_an_unknown_device_is_a_noop() -> None:
    watchers, _, captured = _watchers()
    watchers._device_registry.get_by_name.return_value = None

    watchers.setup_device_watchers("ghost")

    assert not captured
    assert "ghost" not in watchers._watcher_subscriptions


_LINES = [5000000000000000001, 5000000000000000002]
_AREA = 4053101126662577264
_LIVE_PATH_HASH = 7372458040660269014


def _path_hash_watcher(
    *, saga_active: bool = False, bol_in_sync: bool = True, start_saga: AsyncMock | None = None
) -> tuple[Callable[[int], Awaitable[bool]], MowerDevice, AsyncMock]:
    """The registered ``path_hash`` handler, wired to a real handle and mower state."""
    device = MowerDevice(name="Luba-Test")
    device.map.update_root_hash_list(NavGetHashListData(sub_cmd=0, current_frame=1, total_frame=1, data_couple=[_AREA]))
    bol_hash = device.map.computed_bol_hash
    device.report_data.locations = [LocationData(bol_hash=bol_hash if bol_in_sync else bol_hash + 1)]
    handle = make_mock_handle("dev1", "Luba-Test", device=device)
    start_saga = start_saga or AsyncMock()
    registered: list[tuple[Callable[[object], object], Callable[[int], Awaitable[bool]]]] = []

    def _until_handled(getter: Callable[[object], object], handler: Callable[[int], Awaitable[bool]]) -> MagicMock:
        registered.append((getter, handler))
        return MagicMock(cancel=MagicMock())

    handle.watch_until_handled = _until_handled  # type: ignore[method-assign]
    handle.watch_field = lambda _getter, _handler: MagicMock(cancel=MagicMock())  # type: ignore[method-assign]
    registry = create_autospec(DeviceRegistry, instance=True)
    registry.get_by_name.return_value = handle
    AutoFetchWatchers(
        registry, start_map_sync=AsyncMock(), start_plan_sync=AsyncMock(), start_mow_path_saga=start_saga
    ).setup_device_watchers("Luba-Test")
    path_handlers = [
        handler for getter, handler in registered if getter(handle.snapshot) == device.report_data.work.path_hash
    ]
    assert len(path_handlers) == 1, "expected exactly one path_hash watcher registered via watch_until_handled"

    async def _handle_change(path_hash: int) -> bool:
        with patch.object(DeviceCommandQueue, "is_saga_active", new_callable=PropertyMock, return_value=saga_active):
            return await path_handlers[0](path_hash)

    return _handle_change, handle.snapshot.raw, start_saga  # type: ignore[return-value]


def _store_line_list(device: MowerDevice) -> None:
    device.map.update_root_hash_list(
        NavGetHashListData(sub_cmd=LINE_HASH_SUB_CMD, current_frame=1, total_frame=1, data_couple=_LINES)
    )


@pytest.mark.regression
async def test_a_route_change_seen_while_a_saga_runs_stays_pending() -> None:
    """The handler must report "not handled" so the change is retried once the saga has finished.

    The path_hash watcher fired once per change and dropped it when a saga was active, so a route
    that changed mid map-sync was never fetched; the APK keeps the change pending and retries it on
    every report until its gate opens.
    """
    handle_change, _, start_saga = _path_hash_watcher(saga_active=True)

    assert await handle_change(_LIVE_PATH_HASH) is False
    start_saga.assert_not_awaited()


async def test_a_route_change_seen_before_the_map_is_in_sync_stays_pending() -> None:
    handle_change, _, start_saga = _path_hash_watcher(bol_in_sync=False)

    assert await handle_change(_LIVE_PATH_HASH) is False
    start_saga.assert_not_awaited()


async def test_a_route_change_with_the_gate_open_starts_one_fetch_and_is_handled() -> None:
    handle_change, _, start_saga = _path_hash_watcher()

    assert await handle_change(_LIVE_PATH_HASH) is True
    start_saga.assert_awaited_once()
    assert start_saga.await_args.kwargs["skip_planning"] is True


@pytest.mark.parametrize("path_hash", [0, 1])
async def test_no_route_is_handled_without_a_fetch(path_hash: int) -> None:
    """A path_hash of 0 or 1 has nothing to fetch, so it must not stay pending forever."""
    handle_change, _, start_saga = _path_hash_watcher(saga_active=True)

    assert await handle_change(path_hash) is True
    start_saga.assert_not_awaited()


async def test_a_change_to_the_cached_route_is_handled_without_a_fetch() -> None:
    handle_change, device, start_saga = _path_hash_watcher()
    _store_line_list(device)
    device.map.update_mow_path(
        MowPath(
            transaction_id=1,
            total_frame=1,
            current_frame=1,
            path_packets=[MowPathPacket(path_hash=line, path_total=1, path_cur=1) for line in _LINES],
        )
    )

    assert await handle_change(device.map.computed_path_hash) is True
    start_saga.assert_not_awaited()


@pytest.mark.regression
async def test_a_line_list_for_another_route_is_dropped_before_the_fetch() -> None:
    """A stored line list with no cover paths survived the route change and was reused by the fetch."""
    handle_change, device, _ = _path_hash_watcher()
    _store_line_list(device)

    await handle_change(_LIVE_PATH_HASH)

    assert device.map.line_root_hashlist == []


async def test_a_fetch_that_fails_to_start_is_still_handled() -> None:
    """One attempt per change, like the APK: a failing start must not be retried on every report."""
    handle_change, _, _ = _path_hash_watcher(start_saga=AsyncMock(side_effect=RuntimeError("no transport")))

    assert await handle_change(_LIVE_PATH_HASH) is True


_PK = "a1BmXWlsdbA"
_FW = "1.12.3.10"
_DRAIN_TIMEOUT = 1.0


def _function_code_watchers(
    *, firmware: str = _FW, refresh: AsyncMock | None = None, ready: Callable[[DeviceHandle], bool] | None = None
) -> tuple[AutoFetchWatchers, DeviceHandle, AsyncMock]:
    """Watchers over a real handle whose device reports *firmware*, with a canned refresh entry point."""
    device = MowerDevice(name="Luba-Test")
    device.device_firmwares.device_version = firmware
    handle = make_mock_handle("dev1", "Luba-Test", device=device)
    handle.product_key = _PK
    registry = create_autospec(DeviceRegistry, instance=True)
    registry.get_by_name.return_value = handle
    refresh = refresh or AsyncMock(return_value=True)
    watchers = AutoFetchWatchers(
        registry,
        start_map_sync=AsyncMock(),
        start_plan_sync=AsyncMock(),
        start_mow_path_saga=AsyncMock(),
        refresh_function_codes=refresh,
        **({} if ready is None else {"function_codes_ready": ready}),
    )
    watchers.setup_device_watchers("Luba-Test")
    return watchers, handle, refresh


async def _emit(watchers: AutoFetchWatchers, handle: DeviceHandle) -> None:
    await handle.emit_state_changed(handle.snapshot)
    await asyncio.wait_for(watchers.drain(), timeout=_DRAIN_TIMEOUT)


async def test_the_first_snapshot_with_a_known_firmware_fetches_the_function_set() -> None:
    """Unlike ``watch_field``, the first snapshot counts: a restored device already knows its firmware."""
    watchers, handle, refresh = _function_code_watchers()

    await _emit(watchers, handle)

    refresh.assert_awaited_once_with("Luba-Test")


async def test_the_same_firmware_is_fetched_once_even_when_the_fetch_failed() -> None:
    """One attempt per (product key, firmware), like the app: nothing may retry it on every report."""
    watchers, handle, refresh = _function_code_watchers(refresh=AsyncMock(side_effect=ConnectionError("down")))

    await _emit(watchers, handle)
    await _emit(watchers, handle)

    refresh.assert_awaited_once()


async def test_a_firmware_change_fetches_again() -> None:
    watchers, handle, refresh = _function_code_watchers()
    await _emit(watchers, handle)

    handle.snapshot.raw.device_firmwares.device_version = "1.12.4.0"
    await _emit(watchers, handle)

    assert refresh.await_count == 2


async def test_an_unknown_firmware_fetches_nothing() -> None:
    watchers, handle, refresh = _function_code_watchers(firmware="")

    await _emit(watchers, handle)

    refresh.assert_not_awaited()


async def test_a_set_already_current_fetches_nothing() -> None:
    watchers, handle, refresh = _function_code_watchers()
    handle.snapshot.raw.function_codes = FunctionCodes(_PK, _FW, ["002.002"])

    await _emit(watchers, handle)

    refresh.assert_not_awaited()


async def test_a_fetch_that_cannot_be_attempted_yet_is_offered_again_once_it_can() -> None:
    """No login yet is not an attempt: the pair must still be fetched once one exists."""
    logged_in: list[bool] = []
    watchers, handle, refresh = _function_code_watchers(ready=lambda _handle: bool(logged_in))
    await _emit(watchers, handle)
    refresh.assert_not_awaited()

    logged_in.append(True)
    await _emit(watchers, handle)
    await _emit(watchers, handle)

    refresh.assert_awaited_once_with("Luba-Test")


async def test_a_failed_automatic_fetch_is_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    watchers, handle, _ = _function_code_watchers(refresh=AsyncMock(side_effect=ConnectionError("down")))

    with caplog.at_level(logging.WARNING, logger="pymammotion.device.auto_fetch"):
        await _emit(watchers, handle)
        await _emit(watchers, handle)

    assert [r.levelno for r in caplog.records] == [logging.WARNING]


_LUBA_2 = "Luba-VSTest"
_LUBA_MINI_2 = "Luba-MSTest"


def _map_watchers(
    name: str = _LUBA_MINI_2, *, sys_status: int = WorkMode.MODE_WORKING, ble: bool = False
) -> tuple[DeviceHandle, AsyncMock, AsyncMock]:
    """Watchers over a real handle whose mower holds a synced map, baselined on its first snapshot."""
    device = make_mower_with_synced_map(name, sys_status=sys_status)
    handle = make_mock_handle(
        "dev1", name, device=device, ble_transport=make_mock_transport(TransportType.BLE) if ble else None
    )
    registry = create_autospec(DeviceRegistry, instance=True)
    registry.get_by_name.return_value = handle
    start_map_sync, start_mow_path_saga = AsyncMock(), AsyncMock()
    AutoFetchWatchers(
        registry, start_map_sync=start_map_sync, start_plan_sync=AsyncMock(), start_mow_path_saga=start_mow_path_saga
    ).setup_device_watchers(name)
    return handle, start_map_sync, start_mow_path_saga


async def _report(handle: DeviceHandle, *, bol_hash: int | None = None, sys_status: int | None = None) -> None:
    device = cast(MowerDevice, handle.snapshot.raw)
    if bol_hash is not None:
        device.report_data.locations[0].bol_hash = bol_hash
    if sys_status is not None:
        device.report_data.dev.sys_status = sys_status
    await handle.emit_state_changed(handle.snapshot)


def _synced_hash(handle: DeviceHandle) -> int:
    return cast(MowerDevice, handle.snapshot.raw).map.computed_bol_hash


@pytest.mark.regression
@pytest.mark.parametrize("name", [_LUBA_2, _LUBA_MINI_2])
async def test_map_changes_during_a_job_start_no_map_sync(name: str) -> None:
    """A mower re-hashes its map as it mows; each change cost a whole map fetch over the cloud.

    Only dynamics-line models skipped the fetch mid-job; every other model fetched on each change.
    """
    handle, start_map_sync, _ = _map_watchers(name)
    await _report(handle)

    for offset in (1, 2, 3):
        await _report(handle, bol_hash=_synced_hash(handle) + offset)

    start_map_sync.assert_not_awaited()


@pytest.mark.regression
async def test_the_end_of_a_job_syncs_the_map_it_changed_once() -> None:
    """Changes made during a job are fetched once, when it ends.

    The mid-job change was dropped and nothing looked again when the job ended, so the map stayed
    stale until something else synced it.
    """
    handle, start_map_sync, _ = _map_watchers()
    await _report(handle)
    for offset in (1, 2, 3):
        await _report(handle, bol_hash=_synced_hash(handle) + offset)

    await _report(handle, sys_status=WorkMode.MODE_READY)
    await _report(handle)

    start_map_sync.assert_awaited_once_with(_LUBA_MINI_2)


@pytest.mark.regression
async def test_a_map_changed_back_during_a_job_is_not_synced_when_it_ends() -> None:
    """A hash that returns to the synced value needs no fetch, mid-job or after it.

    Non-dynamics-line models fetched on both changes.
    """
    handle, start_map_sync, _ = _map_watchers(_LUBA_2)
    await _report(handle)
    await _report(handle, bol_hash=_synced_hash(handle) + 1)
    await _report(handle, bol_hash=_synced_hash(handle))

    await _report(handle, sys_status=WorkMode.MODE_READY)

    start_map_sync.assert_not_awaited()


async def test_a_ble_link_does_not_lift_the_deferral() -> None:
    """The sync holds the command queue on any link, so it would stall the job's live fetches too."""
    handle, start_map_sync, _ = _map_watchers(ble=True)
    await _report(handle)

    await _report(handle, bol_hash=_synced_hash(handle) + 1)

    start_map_sync.assert_not_awaited()


async def test_a_map_change_while_idle_syncs_at_once() -> None:
    handle, start_map_sync, _ = _map_watchers(sys_status=WorkMode.MODE_READY)
    await _report(handle)

    await _report(handle, bol_hash=_synced_hash(handle) + 1)

    start_map_sync.assert_awaited_once_with(_LUBA_MINI_2)


async def test_a_map_change_seen_while_a_saga_runs_is_synced_once_it_has_finished() -> None:
    handle, start_map_sync, _ = _map_watchers(sys_status=WorkMode.MODE_READY)
    await _report(handle)
    with patch.object(DeviceCommandQueue, "is_saga_active", new_callable=PropertyMock, return_value=True):
        await _report(handle, bol_hash=_synced_hash(handle) + 1)
    start_map_sync.assert_not_awaited()

    await _report(handle)

    start_map_sync.assert_awaited_once_with(_LUBA_MINI_2)


async def test_a_route_change_during_a_job_still_fetches_the_cover_path() -> None:
    """The deferral covers the map only: live mow progress keeps its own fetch."""
    handle, start_map_sync, start_mow_path_saga = _map_watchers(_LUBA_2)
    await _report(handle)

    cast(MowerDevice, handle.snapshot.raw).report_data.work.path_hash = _LIVE_PATH_HASH
    await _report(handle)

    start_mow_path_saga.assert_awaited_once()
    start_map_sync.assert_not_awaited()
