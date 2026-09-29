"""AutoFetchWatchers — "when this field changes, go fetch that".

Extracted from MammotionClient: a rule set needing only the device registry and the
three saga entry points.  It owns its own subscription bookkeeping, and owns nothing
about cadence — how often the device is asked for state lives in DeviceHandle.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock, PropertyMock, create_autospec, patch

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import LINE_HASH_SUB_CMD, MowPath, MowPathPacket, NavGetHashListData
from pymammotion.data.model.report_info import LocationData
from pymammotion.device.auto_fetch import AutoFetchWatchers
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.messaging.command_queue import DeviceCommandQueue
from tests._helpers import make_mock_handle


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
    registered: list[Callable[[int], Awaitable[bool]]] = []

    def _until_handled(_getter: object, handler: Callable[[int], Awaitable[bool]]) -> MagicMock:
        registered.append(handler)
        return MagicMock(cancel=MagicMock())

    handle.watch_until_handled = _until_handled  # type: ignore[method-assign]
    handle.watch_field = lambda _getter, _handler: MagicMock(cancel=MagicMock())  # type: ignore[method-assign]
    registry = create_autospec(DeviceRegistry, instance=True)
    registry.get_by_name.return_value = handle
    AutoFetchWatchers(
        registry, start_map_sync=AsyncMock(), start_plan_sync=AsyncMock(), start_mow_path_saga=start_saga
    ).setup_device_watchers("Luba-Test")
    assert len(registered) == 1, "expected exactly one path_hash watcher registered via watch_until_handled"

    async def _handle_change(path_hash: int) -> bool:
        with patch.object(DeviceCommandQueue, "is_saga_active", new_callable=PropertyMock, return_value=saga_active):
            return await registered[0](path_hash)

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
