"""Tests for MammotionClient.setup_device_watchers auto-trigger logic."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pymammotion.client import MammotionClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot(
    task_ids: list[int] | None = None,
    work_path_hash: int = 0,
    current_mow_path: dict | None = None,
    now_index: int = 0,
) -> MagicMock:
    """Return a DeviceSnapshot-shaped MagicMock."""
    device = MagicMock()
    device.events.work_tasks_event.ids = task_ids or []
    device.report_data.work.ub_path_hash = work_path_hash
    device.report_data.work.now_index = now_index
    device.map.current_mow_path = current_mow_path if current_mow_path is not None else {}
    return MagicMock(raw=device)


def _make_client_with_handle(
    device_name: str = "Luba-Test",
    *,
    saga_active: bool = False,
) -> tuple[MammotionClient, MagicMock, list]:
    """Return (client, handle_mock, captured_handlers).

    The client has a patched _device_registry returning handle_mock.
    handle.queue.is_saga_active is pre-set to saga_active.
    """
    client = MammotionClient.__new__(MammotionClient)
    client._watcher_subscriptions = {}

    handle = MagicMock()
    handle.device_name = device_name
    handle.queue.is_saga_active = saga_active

    captured_handlers: list = []

    def _subscribe(handler):
        captured_handlers.append(handler)
        sub = MagicMock()
        sub.cancel = MagicMock()
        return sub

    handle.subscribe_state_changed = _subscribe

    registry = MagicMock()
    registry.get_by_name.return_value = handle
    client._device_registry = registry

    client.start_mow_path_saga = AsyncMock()

    client.setup_device_watchers(device_name)

    return client, handle, captured_handlers


# ---------------------------------------------------------------------------
# Test: no task_ids → no saga triggered
# ---------------------------------------------------------------------------


async def test_watcher_no_trigger_when_no_task_ids() -> None:
    """When work_tasks_event.ids is empty the watcher must not trigger the saga."""
    client, handle, handlers = _make_client_with_handle()

    snapshot = _make_snapshot(task_ids=[], work_path_hash=42)
    await handlers[0](snapshot)

    client.start_mow_path_saga.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: task_ids present but path_hash zero → no saga
# ---------------------------------------------------------------------------


async def test_watcher_no_trigger_when_path_hash_zero() -> None:
    """When report_data.work.path_hash is 0 the watcher must not trigger the saga."""
    client, handle, handlers = _make_client_with_handle()

    snapshot = _make_snapshot(task_ids=[1, 2], work_path_hash=0)
    await handlers[0](snapshot)

    client.start_mow_path_saga.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: actively working with empty mow path → saga triggered
# ---------------------------------------------------------------------------


async def test_watcher_triggers_when_path_missing_and_actively_working() -> None:
    """Saga must fire when device is actively working but current_mow_path is empty."""
    client, handle, handlers = _make_client_with_handle()

    snapshot = _make_snapshot(task_ids=[1, 2], work_path_hash=99, current_mow_path={})
    await handlers[0](snapshot)

    client.start_mow_path_saga.assert_awaited_once_with(
        "Luba-Test",
        zone_hashs=[1, 2],
        skip_planning=True,
    )


# ---------------------------------------------------------------------------
# Test: mow path already present → no duplicate saga
# ---------------------------------------------------------------------------


async def test_watcher_no_trigger_when_plan_present() -> None:
    """No saga when current_mow_path is already populated."""
    client, handle, handlers = _make_client_with_handle()

    snapshot = _make_snapshot(
        task_ids=[1, 2],
        work_path_hash=99,
        current_mow_path={123: {0: MagicMock()}},  # non-empty
    )
    await handlers[0](snapshot)

    client.start_mow_path_saga.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: saga_active guard prevents double-queueing
# ---------------------------------------------------------------------------


async def test_watcher_skips_when_saga_already_active() -> None:
    """If a saga is already active the watcher must not enqueue another."""
    client, handle, handlers = _make_client_with_handle(saga_active=True)

    snapshot = _make_snapshot(task_ids=[1], work_path_hash=42)
    await handlers[0](snapshot)

    client.start_mow_path_saga.assert_not_awaited()