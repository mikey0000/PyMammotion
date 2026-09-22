"""A completed plan fetch replaces the cached schedule set (Mammotion-HA #892).

The saga's result is everything the device holds, but ``_on_plan_complete``
used to drop it and only set the stale/fetched flags — so a schedule deleted on
the mower stayed in ``map.plan`` for good.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.hash_list import Plan


def _plan(plan_id: str, name: str) -> Plan:
    return Plan(plan_id=plan_id, task_name=name, total_plan_num=1)


def _client_with(device: MowingDevice) -> tuple[MammotionClient, dict[str, Any]]:
    """A client wired to a fake handle that captures the enqueued saga."""
    captured: dict[str, Any] = {}

    async def _enqueue_saga(saga: Any, on_complete: Any = None) -> None:
        captured["saga"] = saga
        captured["on_complete"] = on_complete

    handle = MagicMock()
    handle.commands = MagicMock()
    handle.send_raw = AsyncMock()
    handle.enqueue_saga = _enqueue_saga

    client = MammotionClient.__new__(MammotionClient)
    client._device_registry = MagicMock()  # noqa: SLF001
    client._device_registry.get_by_name.return_value = handle  # noqa: SLF001
    client.get_device_by_name = MagicMock(return_value=device)  # type: ignore[method-assign]
    return client, captured


async def test_a_completed_fetch_drops_a_schedule_deleted_on_the_device() -> None:
    """The reported symptom: four stored schedules, three on the mower."""
    device = MowingDevice()
    device.map.update_plan(_plan("818260", "Garage"))
    device.map.update_plan(_plan("885782", "Garage"))
    client, captured = _client_with(device)

    await client.start_plan_sync("Luba-TEST")
    captured["saga"].result = {"885782": _plan("885782", "Garage")}
    await captured["on_complete"]()

    assert set(device.map.plan) == {"885782"}


async def test_the_flags_still_move() -> None:
    """Pruning must not cost the stale/fetched bookkeeping it sits beside."""
    device = MowingDevice()
    device.map.plans_stale = True
    client, captured = _client_with(device)

    await client.start_plan_sync("Luba-TEST")
    captured["saga"].result = {}
    await captured["on_complete"]()

    assert device.map.plans_stale is False
    assert device.map.plans_fetched is True


async def test_nothing_is_pruned_before_the_saga_completes() -> None:
    """Enqueuing alone must not touch the cache — the fetch may still fail."""
    device = MowingDevice()
    device.map.update_plan(_plan("818260", "Garage"))
    client, _ = _client_with(device)

    await client.start_plan_sync("Luba-TEST")

    assert set(device.map.plan) == {"818260"}
