"""Live cancel-then-resume scenario for MowPathSaga."""

from __future__ import annotations

import pytest

from examples.scenarios import scenario_cancel_resume
from pymammotion.client import MammotionClient


@pytest.mark.live
async def test_cancel_resume_mow_path(
    live_client: tuple[MammotionClient, str],
    prefer_ble: bool,  # noqa: ARG001
) -> None:
    """Start MowPathSaga, cancel via device-side cancel_job, restart, verify convergence.

    The first attempt's depth is captured in the report's
    ``send_cancel_job`` step under ``details.partial_at_cancel``.
    """
    client, device_name = live_client
    report = await scenario_cancel_resume(client, device_name, print_summary=False)
    assert report.ok, report.failure
    assert report.result_counts["frames"] > 0
    assert report.result_counts["missing_frames_total"] == 0
