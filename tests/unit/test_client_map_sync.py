"""MammotionClient.start_map_sync — how the MapFetchSaga is configured."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion import client as client_module
from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle
from pymammotion.messaging.map_saga import MapFetchSaga
from pymammotion.utility.constant.device_enums import WorkMode
from tests._helpers import make_mock_handle, make_mock_transport, make_mower_with_synced_map, wait_until


async def _run_map_sync(handle: DeviceHandle) -> MagicMock:
    """Run start_map_sync for *handle* until its saga executes; return the patched saga class."""
    client = MammotionClient()
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
            await client.start_map_sync(handle.device_name)
            await wait_until(lambda: saga.execute.await_count == 1, message="saga never ran")
        return saga_cls
    finally:
        await handle.stop()


async def _saga_device_id(iot_id: str) -> str:
    """Run start_map_sync for a handle with *iot_id* and return the saga's device_id."""
    handle = make_mock_handle("Yuka-Names", "Yuka-Names")
    handle.iot_id = iot_id
    return (await _run_map_sync(handle)).call_args.kwargs["device_id"]


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


async def test_a_requested_sync_runs_during_a_job() -> None:
    """Only automatic syncs wait for the job to end; a user's request is never deferred."""
    device = make_mower_with_synced_map("Luba-MSTest", sys_status=WorkMode.MODE_WORKING)
    device.report_data.locations[0].bol_hash += 1

    saga_cls = await _run_map_sync(make_mock_handle("Luba-MSTest", "Luba-MSTest", device=device))

    assert saga_cls.call_args.kwargs["device_name"] == "Luba-MSTest"
