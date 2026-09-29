"""``MammotionClient.check_and_get_mow_path`` — the stale-route clear that precedes a cover-path fetch."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import LINE_HASH_SUB_CMD, NavGetHashListData
from tests._helpers import make_bare_client, make_mock_handle

_NAME = "Luba-Test"
_LINES = [5000000000000000001, 5000000000000000002]
_LIVE_PATH_HASH = 7372458040660269014


async def _client_with_stored_route() -> tuple[MammotionClient, MowerDevice]:
    device = MowerDevice(name=_NAME)
    device.map.update_root_hash_list(
        NavGetHashListData(sub_cmd=LINE_HASH_SUB_CMD, current_frame=1, total_frame=1, data_couple=_LINES)
    )
    device.report_data.work.path_hash = _LIVE_PATH_HASH
    client = make_bare_client()
    await client._device_registry.register(make_mock_handle("dev1", _NAME, device=device))  # noqa: SLF001
    return client, device


@pytest.mark.regression
async def test_a_stored_line_list_for_another_route_is_dropped_even_without_cover_paths() -> None:
    """The clear was skipped whenever no cover path was cached, leaving the old route's line list in place."""
    client, device = await _client_with_stored_route()
    assert device.map.computed_path_hash != _LIVE_PATH_HASH

    with patch.object(MammotionClient, "start_mow_path_saga", autospec=True, return_value=True):
        await client.check_and_get_mow_path(_NAME)

    assert device.map.line_root_hashlist == []
