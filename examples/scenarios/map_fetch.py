"""Scenario: MapFetchSaga — happy path + retry-after-invalidate.

Usage from the REPL::

    from examples.scenarios import scenario_map_fetch
    report = await scenario_map_fetch(client, "Luba-XYZ")
    print(report)        # pretty stdout summary
    report.to_dict()     # serialisable for JSON inspection
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from examples.scenarios._common import await_saga_idle, get_device, get_handle, snapshot_map
from examples.scenarios._runner import ScenarioRunner, run_scenario

if TYPE_CHECKING:
    from examples.scenarios._report import ScenarioReport
    from pymammotion.client import MammotionClient


async def _impl_map_fetch(runner: ScenarioRunner, client: MammotionClient, device_name: str) -> None:
    handle = runner.handle

    await runner.step(
        "snapshot_before",
        details={"map": snapshot_map(handle)},
    )

    async def _first_sync() -> None:
        await client.start_map_sync(device_name)
        await await_saga_idle(handle, timeout=300.0)

    await runner.step("first_map_sync", _first_sync)

    after_first = snapshot_map(handle)
    if after_first["areas"] == 0 and after_first["paths"] == 0 and after_first["obstacles"] == 0:
        msg = f"first map_sync completed but map is still empty: {after_first}"
        raise RuntimeError(msg)
    if after_first["missing_hashlist"] != 0:
        msg = f"first map_sync left missing hashlist entries: {after_first}"
        raise RuntimeError(msg)
    await runner.step("verify_first_complete", details={"map": after_first})

    # Force a re-fetch by invalidating root_hash_lists.  ``invalidate_maps``
    # only clears when the supplied bol_hash mismatches; passing 0 guarantees
    # a mismatch for any real map.
    device = get_device(handle)
    device.map.invalidate_maps(0)
    after_invalidate = snapshot_map(handle)
    await runner.step("invalidate", details={"map": after_invalidate})

    async def _second_sync() -> None:
        await client.start_map_sync(device_name)
        await await_saga_idle(handle, timeout=300.0)

    await runner.step("second_map_sync", _second_sync)

    after_second = snapshot_map(handle)
    if after_second["root_hash_lists"] == 0:
        msg = f"second map_sync did not repopulate root_hash_lists: {after_second}"
        raise RuntimeError(msg)
    if after_second["missing_hashlist"] != 0:
        msg = f"second map_sync left missing hashlist entries: {after_second}"
        raise RuntimeError(msg)
    await runner.step("verify_second_complete", details={"map": after_second})


async def scenario_map_fetch(
    client: MammotionClient,
    device_name: str,
    *,
    print_summary: bool = True,
) -> ScenarioReport:
    """Run the map-fetch happy + retry-after-invalidate scenario."""
    # Touch the handle to validate registration before run_scenario binds.
    get_handle(client, device_name)

    async def _wrap(runner: ScenarioRunner) -> None:
        await _impl_map_fetch(runner, client, device_name)

    return await run_scenario(
        "map_fetch",
        client,
        device_name,
        _wrap,
        which="map",
        print_summary=print_summary,
    )
