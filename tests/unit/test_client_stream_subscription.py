"""``MammotionClient`` stream subscription — the all-cameras request reaches the HTTP layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pymammotion.client import MammotionClient


async def test_fetch_stream_subscription_passes_all_cameras_through() -> None:
    """Only the HTTP layer knows which slots that means."""
    client = MammotionClient()
    http = MagicMock()
    http.get_stream_subscription = AsyncMock(return_value=MagicMock(data=MagicMock()))

    await client._fetch_stream_subscription(http, "iot-1", True, all_cameras=True)

    http.get_stream_subscription.assert_awaited_once_with("iot-1", True, all_cameras=True)
