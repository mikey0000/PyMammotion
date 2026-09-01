"""AutoFetchWatchers — "when this field changes, go fetch that".

Extracted from MammotionClient: a rule set needing only the device registry and the
three saga entry points.  It owns its own subscription bookkeeping, and owns nothing
about cadence — how often the device is asked for state lives in DeviceHandle.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pymammotion.device.auto_fetch import AutoFetchWatchers


def _watchers(handle: MagicMock | None = None) -> tuple[AutoFetchWatchers, MagicMock, list]:
    captured: list = []

    if handle is None:
        handle = MagicMock()
        handle.device_name = "Luba-Test"
        handle.queue.is_saga_active = False

    def _watch_field(_getter, handler):
        captured.append(handler)
        return MagicMock(cancel=MagicMock())

    handle.watch_field = _watch_field
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
