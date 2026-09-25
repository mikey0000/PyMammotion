"""Shared helpers used by every scenario.

Kept deliberately small: anything substantial belongs on ``DeviceHandle``,
``MammotionClient``, or the saga itself.  These are *test/REPL plumbing*,
not product code.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, cast

from pymammotion.data.model.device import MowingDevice
from pymammotion.transport.base import TransportType

if TYPE_CHECKING:
    from pymammotion.client import MammotionClient
    from pymammotion.device.handle import DeviceHandle


def get_handle(client: MammotionClient, device_name: str) -> DeviceHandle:
    """Return the ``DeviceHandle`` for *device_name* or raise ``KeyError``."""
    handle = client.device_registry.get_by_name(device_name)
    if handle is None:
        msg = f"device '{device_name}' not registered"
        raise KeyError(msg)
    return handle


def get_device(handle: DeviceHandle) -> MowingDevice:
    """Return the current ``MowingDevice`` snapshot from *handle*."""
    return cast(MowingDevice, handle.snapshot.raw)


def transport_label(handle: DeviceHandle) -> str:
    """Best-effort transport-in-use label for the report."""
    if handle.is_transport_connected(TransportType.BLE):
        # BLE is preferred whenever connected, regardless of the prefer_ble flag.
        return "ble"
    if handle.is_transport_connected(TransportType.MQTT):
        return "mqtt"
    return "unknown"


async def await_saga_idle(
    handle: DeviceHandle,
    *,
    timeout: float = 300.0,  # noqa: ASYNC109 - this *is* a wall-clock budget, not an external cancel signal
    start_within: float = 3.0,
    poll_interval: float = 0.5,
) -> bool:
    """Wait for the device's command queue to be idle of sagas.

    Returns True if a saga completed during the wait, False if no saga ever
    started (a fast no-op completion before we started polling).  Raises
    ``asyncio.TimeoutError`` if the saga doesn't finish within *timeout*.

    *start_within* is the grace window for the queue to dequeue the saga
    after ``enqueue_saga()`` returns.  *timeout* covers the saga's total
    execution time.
    """
    deadline = time.monotonic() + timeout
    start_deadline = time.monotonic() + start_within

    # ASYNC110: the command queue exposes no event surface to wait on, so we poll.
    while time.monotonic() < start_deadline and not handle.queue.is_saga_active:  # noqa: ASYNC110
        await asyncio.sleep(0.05)

    if not handle.queue.is_saga_active:
        return False

    while handle.queue.is_saga_active:
        if time.monotonic() > deadline:
            msg = "saga did not complete within timeout"
            raise TimeoutError(msg)
        await asyncio.sleep(poll_interval)
    return True


def snapshot_map(handle: DeviceHandle) -> dict[str, Any]:
    """Compact map-state snapshot for assertions + failure-depth reporting."""
    device = get_device(handle)
    hl = device.map
    return {
        "areas": len(hl.area),
        "obstacles": len(hl.obstacle),
        "paths": len(hl.path),
        "svgs": len(hl.svg),
        "root_hash_lists": len(hl.root_hash_lists),
        "missing_hashlist": len(hl.missing_hashlist(0)),
        "incomplete_hashes": len(hl.find_incomplete_hashes(0)),
    }


def snapshot_mow_path(handle: DeviceHandle) -> dict[str, Any]:
    """Compact mow-path snapshot for assertions + failure-depth reporting."""
    device = get_device(handle)
    hl = device.map
    missing_by_tx = hl.find_missing_mow_path_frames()
    total_frames = sum(len(frames) for frames in hl.current_mow_path.values())
    return {
        "transactions": len(hl.current_mow_path),
        "frames": total_frames,
        "missing_frames_total": sum(len(v) for v in missing_by_tx.values()),
        "missing_by_transaction": {tx: len(frames) for tx, frames in missing_by_tx.items()},
    }


def pick_any_zone(handle: DeviceHandle) -> int | None:
    """Return one area hash from the device's current map, or None if empty."""
    device = get_device(handle)
    keys = list(device.map.area.keys())
    return keys[0] if keys else None
