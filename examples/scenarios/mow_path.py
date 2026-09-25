"""Scenario: MowPathSaga in both planning and skip_planning modes.

The planning mode fetches the cover path for a chosen zone by sending
``generate_route_information`` then collecting ``cover_path_upload`` frames.

The skip_planning mode reuses the device's currently-running job's route
info (sub_cmd=2 query path inside MowPathSaga).  This only succeeds when a
job is actually running on the device; if no job is active the saga
short-circuits and the scenario reports that under ``details``.
"""

from __future__ import annotations

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


async def _ensure_map_populated(runner: ScenarioRunner, client: MammotionClient, device_name: str) -> None:
    """Run a map_sync if the device has no areas yet."""
    handle = runner.handle
    if snapshot_map(handle)["areas"] > 0:
        return

    async def _sync() -> None:
        await client.start_map_sync(device_name)
        await await_saga_idle(handle, timeout=300.0)

    await runner.step("preflight_map_sync", _sync, details={"reason": "no areas in cached map"})


async def _impl_mow_path_planning(
    runner: ScenarioRunner,
    client: MammotionClient,
    device_name: str,
    zone_hash: int | None,
) -> None:
    handle = runner.handle

    await _ensure_map_populated(runner, client, device_name)

    if zone_hash is None:
        zone_hash = pick_any_zone(handle)
    if zone_hash is None:
        msg = "device map has no areas — cannot pick a zone for mow_path_planning"
        raise RuntimeError(msg)

    # Clear any stale frames so we observe convergence on this attempt only.
    device = get_device(handle)
    device.map.current_mow_path = {}

    before = snapshot_mow_path(handle)
    await runner.step("snapshot_before", details={"mow_path": before, "zone_hash": zone_hash})

    async def _planning_run() -> None:
        await client.start_mow_path_saga(device_name, zone_hashs=[zone_hash], skip_planning=False)
        await await_saga_idle(handle, timeout=300.0)

    await runner.step("planning_run", _planning_run)

    after = snapshot_mow_path(handle)
    if after["frames"] == 0:
        msg = f"planning mow_path produced no frames: {after}"
        raise RuntimeError(msg)
    if after["missing_frames_total"] != 0:
        msg = f"planning mow_path left missing frames: {after}"
        raise RuntimeError(msg)
    await runner.step("verify_planning_complete", details={"mow_path": after})


async def _impl_mow_path_skip_planning(
    runner: ScenarioRunner,
    client: MammotionClient,
    device_name: str,
) -> None:
    handle = runner.handle

    await _ensure_map_populated(runner, client, device_name)

    # Clear current_mow_path so we know any frames we see came from this run.
    device = get_device(handle)
    device.map.current_mow_path = {}

    before = snapshot_mow_path(handle)
    await runner.step("snapshot_before", details={"mow_path": before})

    async def _skip_run() -> None:
        await client.start_mow_path_saga(device_name, zone_hashs=[], skip_planning=True)
        await await_saga_idle(handle, timeout=300.0)

    await runner.step("skip_planning_run", _skip_run)

    after = snapshot_mow_path(handle)
    # skip_planning depends on the device having an active job.  If it doesn't,
    # the saga returns cleanly with zero frames — that's not a hard failure for
    # the scenario, but the report should reflect what happened.
    await runner.step(
        "verify_skip_planning_complete",
        details={
            "mow_path": after,
            "had_active_job": after["frames"] > 0,
        },
    )


async def scenario_mow_path(
    client: MammotionClient,
    device_name: str,
    *,
    zone_hash: int | None = None,
    print_summary: bool = True,
) -> ScenarioReport:
    """Run MowPathSaga in planning mode against a single zone."""
    get_handle(client, device_name)

    async def _wrap(runner: ScenarioRunner) -> None:
        await _impl_mow_path_planning(runner, client, device_name, zone_hash)

    return await run_scenario(
        "mow_path_planning",
        client,
        device_name,
        _wrap,
        which="mow_path",
        print_summary=print_summary,
    )


async def scenario_mow_path_skip_planning(
    client: MammotionClient,
    device_name: str,
    *,
    print_summary: bool = True,
) -> ScenarioReport:
    """Run MowPathSaga in skip_planning mode (queries device's running job)."""
    get_handle(client, device_name)

    async def _wrap(runner: ScenarioRunner) -> None:
        await _impl_mow_path_skip_planning(runner, client, device_name)

    return await run_scenario(
        "mow_path_skip_planning",
        client,
        device_name,
        _wrap,
        which="mow_path",
        print_summary=print_summary,
    )
