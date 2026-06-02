"""Live MowPathSaga scenarios — planning and skip_planning modes."""

from __future__ import annotations

import pytest

from examples.scenarios import scenario_mow_path, scenario_mow_path_skip_planning
from pymammotion.client import MammotionClient


@pytest.mark.live
async def test_mow_path_planning(
    live_client: tuple[MammotionClient, str],
    prefer_ble: bool,  # noqa: ARG001
) -> None:
    client, device_name = live_client
    report = await scenario_mow_path(client, device_name, print_summary=False)
    assert report.ok, report.failure
    assert report.result_counts["frames"] > 0
    assert report.result_counts["missing_frames_total"] == 0


@pytest.mark.live
async def test_mow_path_skip_planning(
    live_client: tuple[MammotionClient, str],
    prefer_ble: bool,  # noqa: ARG001
) -> None:
    """skip_planning relies on the device having a running job.

    On a docked/idle device the saga short-circuits with zero frames — that
    is a *clean* outcome (no exception), so the test only asserts ``report.ok``
    and lets the JSON report capture the count for inspection.
    """
    client, device_name = live_client
    report = await scenario_mow_path_skip_planning(client, device_name, print_summary=False)
    assert report.ok, report.failure
