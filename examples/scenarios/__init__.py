"""REPL-loadable scenario runners for live-device integration testing.

Every scenario function takes ``(client, device_name)`` and returns a
:class:`~examples.scenarios._report.ScenarioReport`.  Transport selection
is the caller's responsibility — set ``client.set_prefer_ble(device_id, ...)``
before invocation.

Typical REPL usage::

    from examples.scenarios import run_all, scenario_map_fetch
    report = await scenario_map_fetch(client, "Luba-XYZ")
    print(report)
    reports = await run_all(client, "Luba-XYZ")
"""

from examples.scenarios._report import ScenarioReport, ScenarioStep, dump_aggregate, dump_report
from examples.scenarios.all_scenarios import run_all
from examples.scenarios.cancel_resume import scenario_cancel_resume
from examples.scenarios.map_fetch import scenario_map_fetch
from examples.scenarios.mow_path import scenario_mow_path, scenario_mow_path_skip_planning

__all__ = [
    "ScenarioReport",
    "ScenarioStep",
    "dump_aggregate",
    "dump_report",
    "run_all",
    "scenario_cancel_resume",
    "scenario_map_fetch",
    "scenario_mow_path",
    "scenario_mow_path_skip_planning",
]
