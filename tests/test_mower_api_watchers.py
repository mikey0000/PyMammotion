"""Tests for HomeAssistantMowerApi.setup_device_watchers auto-trigger logic."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.homeassistant.mower_api import HomeAssistantMowerApi


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot(
    path_hash: int = 0,
    job_id: int = 0,
    zone_hashs: list[int] | None = None,
    current_mow_path: dict | None = None,
) -> MagicMock:
    """Return a DeviceSnapshot-shaped MagicMock."""
    device = MagicMock()
    device.work.path_hash = path_hash
    device.work.job_id = job_id
    device.work.zone_hashs = zone_hashs or []
    device.map.current_mow_path = current_mow_path if current_mow_path is not None else {}
    return MagicMock(raw=device)


def _make_api_with_handle(
    device_name: str = "Luba-Test",
    *,
    saga_active: bool = False,
) -> tuple[HomeAssistantMowerApi, MagicMock, MagicMock]:
    """Return (api, handle_mock, start_mow_path_saga_mock).

    The api has a patched _mammotion.mower() returning handle_mock.
    handle.queue.is_saga_active is pre-set to saga_active.
    """
    api = HomeAssistantMowerApi.__new__(HomeAssistantMowerApi)
    api._active_work_ids = {}
    api._mow_path_subscriptions = {}

    handle = MagicMock()
    handle.queue.is_saga_active = saga_active

    captured_handlers: list = []

    def _subscribe(handler):
        captured_handlers.append(handler)
        sub = MagicMock()
        sub.cancel = MagicMock()
        return sub

    handle.subscribe_state_changed = _subscribe

    mammotion = MagicMock()
    mammotion.mower.return_value = handle
    mammotion.start_mow_path_saga = AsyncMock()
    api._mammotion = mammotion

    api.setup_device_watchers(device_name)

    return api, handle, captured_handlers


# ---------------------------------------------------------------------------
# Test: path_hash=0 → no saga triggered
# ---------------------------------------------------------------------------


async def test_watcher_no_trigger_when_path_hash_zero() -> None:
    """When path_hash is 0 the watcher must not trigger the saga."""
    api, handle, handlers = _make_api_with_handle()

    snapshot = _make_snapshot(path_hash=0, job_id=1)
    await handlers[0](snapshot)

    api._mammotion.start_mow_path_saga.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: new job ID triggers saga
# ---------------------------------------------------------------------------


async def test_watcher_triggers_on_new_job_id() -> None:
    """A new job_id combined with a non-zero path_hash triggers the saga."""
    api, handle, handlers = _make_api_with_handle()

    snapshot = _make_snapshot(path_hash=42, job_id=7, zone_hashs=[1, 2])
    await handlers[0](snapshot)

    api._mammotion.start_mow_path_saga.assert_awaited_once_with(
        "Luba-Test",
        zone_hashs=[1, 2],
        skip_planning=True,
    )


# ---------------------------------------------------------------------------
# Test: plan_missing triggers saga (same job_id, empty mow path)
# ---------------------------------------------------------------------------


async def test_watcher_triggers_when_plan_missing() -> None:
    """Saga must fire when device is working (path_hash != 0) but current_mow_path is empty."""
    api, handle, handlers = _make_api_with_handle()

    # Same job_id as default (0) so new_job is False; but path_hash != 0 and plan empty
    snapshot = _make_snapshot(path_hash=99, job_id=0, current_mow_path={})
    await handlers[0](snapshot)

    api._mammotion.start_mow_path_saga.assert_awaited_once()
    assert api._mammotion.start_mow_path_saga.call_args.kwargs["skip_planning"] is True


# ---------------------------------------------------------------------------
# Test: plan_missing NOT triggered when mow path already present
# ---------------------------------------------------------------------------


async def test_watcher_no_trigger_when_plan_present() -> None:
    """No duplicate saga when current_mow_path is already populated and job_id unchanged."""
    api, handle, handlers = _make_api_with_handle()
    api._active_work_ids["Luba-Test"] = 5  # same as current

    snapshot = _make_snapshot(
        path_hash=99,
        job_id=5,
        current_mow_path={123: {0: MagicMock()}},  # non-empty
    )
    await handlers[0](snapshot)

    api._mammotion.start_mow_path_saga.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: saga_active guard prevents double-queueing
# ---------------------------------------------------------------------------


async def test_watcher_skips_when_saga_already_active() -> None:
    """If a saga is already active the watcher must not enqueue another."""
    api, handle, handlers = _make_api_with_handle(saga_active=True)

    snapshot = _make_snapshot(path_hash=42, job_id=7)
    await handlers[0](snapshot)

    api._mammotion.start_mow_path_saga.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: active_work_ids is updated on trigger
# ---------------------------------------------------------------------------


async def test_watcher_updates_active_work_id_on_trigger() -> None:
    """_active_work_ids must be set to current_job_id when the saga is triggered."""
    api, handle, handlers = _make_api_with_handle()

    snapshot = _make_snapshot(path_hash=1, job_id=42)
    await handlers[0](snapshot)

    assert api._active_work_ids["Luba-Test"] == 42