"""Builders for the ``HomeAssistantMowerApi`` tests."""

from __future__ import annotations

from pymammotion.data.model.device import MowerDevice
from pymammotion.device.handle import DeviceHandle
from pymammotion.homeassistant.mower_api import HomeAssistantMowerApi
from pymammotion.transport.base import TransportAvailability, TransportType
from tests._helpers import make_mock_handle, make_mock_transport

NAME = "Luba-VSHATEST"


async def make_api(
    device: MowerDevice | None = None, *, name: str = NAME, reachable: bool = True
) -> tuple[HomeAssistantMowerApi, DeviceHandle]:
    """An api whose real client holds one real handle for *name*, reachable over a mocked cloud link.

    The link's availability is UNKNOWN so registering it replays nothing: no report request is queued.
    """
    api = HomeAssistantMowerApi(ha_version="2026.11.0")
    handle = make_mock_handle(device_name=name, device=device if device is not None else MowerDevice(name=name))
    if reachable:
        await handle.add_transport(
            make_mock_transport(TransportType.CLOUD_ALIYUN, availability=TransportAvailability.UNKNOWN)
        )
    await api.mammotion.device_registry.register(handle)
    return api, handle
