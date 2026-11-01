"""MammotionClient.start_map_sync — how the MapFetchSaga is configured."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion import client as client_module
from pymammotion.client import MammotionClient
from pymammotion.messaging.map_saga import MapFetchSaga
from tests._helpers import make_mock_handle, make_mock_transport, wait_until


async def _saga_device_id(iot_id: str) -> str:
    """Run start_map_sync for a handle with *iot_id* and return the saga's device_id."""
    client = MammotionClient()
    handle = make_mock_handle("Yuka-Names", "Yuka-Names")
    handle.iot_id = iot_id
    await handle.add_transport(make_mock_transport())
    await handle.start()
    await client._device_registry.register(handle)

    saga = MagicMock(spec=MapFetchSaga)
    saga.name = "map_fetch"
    saga.max_attempts = 1
    saga.execute = AsyncMock()
    saga.result = None
    try:
        with patch.object(client_module, "MapFetchSaga", autospec=True, return_value=saga) as saga_cls:
            await client.start_map_sync("Yuka-Names")
            await wait_until(lambda: saga.execute.await_count == 1, message="saga never ran")
        return saga_cls.call_args.kwargs["device_id"]
    finally:
        await handle.stop()


@pytest.mark.regression
async def test_area_names_are_requested_by_iot_id() -> None:
    """The area-name request must carry the device's iot_id, as the APK sends it.

    start_map_sync passed ``handle.device_id`` — the device name for cloud devices —
    and a Yuka did not answer the request.
    """
    assert await _saga_device_id("iot-yuka") == "iot-yuka"


async def test_area_names_fall_back_to_device_id_without_iot_id() -> None:
    """A BLE-only handle has no iot_id, so the request falls back to device_id."""
    assert await _saga_device_id("") == "Yuka-Names"
