"""Batch runner: execute every scenario against a device and dump one JSON file."""

from __future__ import annotations

from typing import TYPE_CHECKING

from examples.scenarios._report import ScenarioReport, dump_aggregate
from examples.scenarios.cancel_resume import scenario_cancel_resume
from examples.scenarios.map_fetch import scenario_map_fetch
from examples.scenarios.mow_path import scenario_mow_path, scenario_mow_path_skip_planning

if TYPE_CHECKING:
    from pymammotion.client import MammotionClient


async def run_all(
    client: MammotionClient,
    device_name: str,
    *,
    include_cancel_resume: bool = True,
    print_summary: bool = True,
) -> dict[str, ScenarioReport]:
    """Run every scenario sequentially and write a single aggregated JSON report.

    Each scenario runs in its own ``run_scenario`` wrapper so a failure in one
    does not prevent the rest from running.  Returns the per-name report map.
    """
    results: dict[str, ScenarioReport] = {}

    results["map_fetch"] = await scenario_map_fetch(client, device_name, print_summary=print_summary)
    results["mow_path_planning"] = await scenario_mow_path(client, device_name, print_summary=print_summary)
    results["mow_path_skip_planning"] = await scenario_mow_path_skip_planning(
        client, device_name, print_summary=print_summary
    )
    if include_cancel_resume:
        results["cancel_resume_mow_path"] = await scenario_cancel_resume(
            client, device_name, print_summary=print_summary
        )

    path = dump_aggregate(results)
    if print_summary:
        ok_count = sum(1 for r in results.values() if r.ok)
        print(f"\nrun_all: {ok_count}/{len(results)} ok — wrote {path}")  # noqa: T201

    return results
