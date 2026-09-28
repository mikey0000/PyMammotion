"""``MammotionClient`` stream subscription — the all-cameras request reaches the HTTP layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from pymammotion.client import MammotionClient


async def test_fetch_stream_subscription_passes_all_cameras_through() -> None:
    """Only the HTTP layer knows which slots that means."""
    client = MammotionClient()
    http = MagicMock()
    http.get_stream_subscription = AsyncMock(return_value=MagicMock(data=MagicMock()))

    await client._fetch_stream_subscription(http, "iot-1", True, all_cameras=True)

    http.get_stream_subscription.assert_awaited_once_with("iot-1", True, all_cameras=True)


@pytest.mark.parametrize(
    ("device_name", "has_rear"),
    [("Yuka-ABC123", True), ("Yuka-MNTXVHBE", False), ("Yuka-YM1234", False), ("Luba-VS563L6H", False)],
)
async def test_only_the_full_size_yuka_asks_for_the_rear_camera(device_name: str, has_rear: bool) -> None:
    """The Yuka Minis have no rear camera; the app requests it for LUBA_YUKA alone."""
    client = MammotionClient()
    client._fetch_stream_subscription = AsyncMock(return_value=MagicMock(data=MagicMock()))

    with patch.object(type(client), "mammotion_http", PropertyMock(return_value=MagicMock())):
        await client.get_stream_subscription(device_name, "iot-1", all_cameras=True)

    assert client._fetch_stream_subscription.await_args.args[2] is has_rear
