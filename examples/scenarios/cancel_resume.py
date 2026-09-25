"""Scenario: interrupt a running mow_path saga, then re-run and verify it converges.

The interrupt is the device-side ``cancel_job`` command (the same approach
used by ``examples/test_mow_path_saga.py``).  MapFetchSaga has no analogous
device-side interrupt, so this scenario targets MowPathSaga only.

The report captures *how far the first attempt got* before the cancel by
snapshotting ``current_mow_path`` between the interrupt and the restart.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from examples.scenarios._common import (
    await_saga_idle,
    get_device,
    get_handle,
    pick_any_zone,
    snapshot_map,
    snapshot_mow_path,
)
from examples.scenarios._runner import ScenarioRunner, run_scenario

if TYPE_CHECKING:
    from examples.scenarios._report import ScenarioReport
    from pymammotion.client import MammotionClient
    from pymammotion.device.handle import DeviceHandle

_logger = logging.getLogger(__name__)


async def _wait_for_partial_progress(
    handle: DeviceHandle,
    *,
    timeout: float = 30.0,  # noqa: ASYNC109 - wall-clock budget, no external cancel signal
    poll: float = 0.5,
) -> dict:
    """Poll until at least one mow_path frame has arrived, or timeout.

    Returns the snapshot at the moment progress was first observed (or the
    final snapshot at timeout — caller decides whether that's a failure).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = snapshot_mow_path(handle)
        if snap["frames"] > 0:
            return snap
        await asyncio.sleep(poll)
    return snapshot_mow_path(handle)


async def _impl_cancel_resume_mow_path(
    runner: ScenarioRunner,
    client: MammotionClient,
    device_name: str,
    zone_hash: int | None,
) -> None:
    handle = runner.handle

    if snapshot_map(handle)["areas"] == 0:

        async def _sync() -> None:
            await client.start_map_sync(device_name)
            await await_saga_idle(handle, timeout=300.0)

        await runner.step("preflight_map_sync", _sync, details={"reason": "no areas in cached map"})

    if zone_hash is None:
        zone_hash = pick_any_zone(handle)
    if zone_hash is None:
        msg = "device map has no areas — cannot pick a zone for cancel_resume"
        raise RuntimeError(msg)

    device = get_device(handle)
    device.map.current_mow_path = {}

    async def _enqueue_first() -> None:
        await client.start_mow_path_saga(device_name, zone_hashs=[zone_hash], skip_planning=False)

    await runner.step("start_first_attempt", _enqueue_first, details={"zone_hash": zone_hash})

    async def _wait_progress() -> dict:
        return await _wait_for_partial_progress(handle, timeout=30.0)

    partial = await runner.step("wait_for_partial_progress", _wait_progress)
    partial_at_cancel = partial if partial is not None else snapshot_mow_path(handle)

    async def _cancel() -> None:
        try:
            await client.send_command_with_args(device_name, "cancel_job")
        except Exception as exc:  # noqa: BLE001 - device may not have an active job
            _logger.debug("cancel_job send failed (often expected for static testing): %s", exc)

    await runner.step("send_cancel_job", _cancel, details={"partial_at_cancel": partial_at_cancel})

    # Wait for the saga to settle after the cancel (either it errors and
    # the queue moves on, or it completes naturally).  Use a tighter
    # timeout — we expect the cancel to terminate it quickly.
    async def _wait_settle() -> None:
        try:
            await await_saga_idle(handle, timeout=60.0, start_within=0.5)
        except TimeoutError:
            _logger.debug("first attempt did not settle within 60s — proceeding with restart anyway")

    await runner.step("wait_first_attempt_settled", _wait_settle)

    # Reset for a clean re-run.
    device.map.current_mow_path = {}

    async def _restart() -> None:
        await client.start_mow_path_saga(device_name, zone_hashs=[zone_hash], skip_planning=False)
        await await_saga_idle(handle, timeout=300.0)

    await runner.step("resume_second_attempt", _restart)

    after = snapshot_mow_path(handle)
    if after["frames"] == 0:
        msg = f"resume mow_path produced no frames: {after}"
        raise RuntimeError(msg)
    if after["missing_frames_total"] != 0:
        msg = f"resume mow_path left missing frames: {after}"
        raise RuntimeError(msg)
    await runner.step("verify_resume_complete", details={"mow_path": after})


async def scenario_cancel_resume(
    client: MammotionClient,
    device_name: str,
    *,
    zone_hash: int | None = None,
    print_summary: bool = True,
) -> ScenarioReport:
    """Interrupt a planning-mode mow_path via cancel_job, then re-run."""
    get_handle(client, device_name)

    async def _wrap(runner: ScenarioRunner) -> None:
        await _impl_cancel_resume_mow_path(runner, client, device_name, zone_hash)

    return await run_scenario(
        "cancel_resume_mow_path",
        client,
        device_name,
        _wrap,
        which="mow_path",
        print_summary=print_summary,
    )
