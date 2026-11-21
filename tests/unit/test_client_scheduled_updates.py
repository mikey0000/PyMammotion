"""``MammotionClient.set_scheduled_updates``: what the HA 'schedule updates' switch does to a device's links."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pymammotion.client import MammotionClient
from pymammotion.transport.base import TransportAvailability, TransportType
from tests._helpers import make_bare_client, make_mock_handle, make_mock_transport


async def _client_with_ble(*, usable: bool) -> tuple[MammotionClient, MagicMock]:
    client = make_bare_client()
    handle = make_mock_handle("dev1", "Luba-Sched3")
    # UNKNOWN availability: add_transport would otherwise replay CONNECTED and start the BLE loops.
    ble = make_mock_transport(TransportType.BLE, usable=usable, availability=TransportAvailability.UNKNOWN)
    await handle.add_transport(ble)
    await client.device_registry.register(handle)
    return client, ble


async def test_set_scheduled_updates_connects_a_usable_ble() -> None:
    client, ble = await _client_with_ble(usable=True)

    await client.set_scheduled_updates("Luba-Sched3", enabled=True)

    ble.connect.assert_awaited_once()


async def test_set_scheduled_updates_does_not_connect_an_unusable_ble() -> None:
    """A BLE in cooldown or below the RSSI floor is not woken by enabling updates."""
    client, ble = await _client_with_ble(usable=False)

    await client.set_scheduled_updates("Luba-Sched3", enabled=True)

    ble.connect.assert_not_awaited()


@pytest.mark.regression
async def test_set_scheduled_updates_disconnects_an_unusable_ble() -> None:
    """Disabling updates left BLE connected whenever ``is_usable`` was False.

    A link below the RSSI floor or in cooldown can still be up, so turning updates off
    kept it streaming.
    """
    client, ble = await _client_with_ble(usable=False)

    await client.set_scheduled_updates("Luba-Sched3", enabled=False)

    ble.disconnect.assert_awaited_once()


async def test_set_scheduled_updates_does_not_raise_for_an_unknown_device() -> None:
    client = make_bare_client()

    await client.set_scheduled_updates("ghost-device", enabled=False)
    await client.set_scheduled_updates("ghost-device", enabled=True)
