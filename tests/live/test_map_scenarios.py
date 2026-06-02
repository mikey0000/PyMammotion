"""Live MapFetchSaga scenarios — runs over MQTT and (if available) BLE."""

from __future__ import annotations

import pytest

from examples.scenarios import scenario_map_fetch
from pymammotion.client import MammotionClient


@pytest.mark.live
async def test_map_fetch(
    live_client: tuple[MammotionClient, str],
    prefer_ble: bool,  # noqa: ARG001 - parametrises the test
) -> None:
    client, device_name = live_client
    report = await scenario_map_fetch(client, device_name, print_summary=False)
    assert report.ok, report.failure
    assert report.result_counts["root_hash_lists"] > 0
    assert report.result_counts["missing_hashlist"] == 0
