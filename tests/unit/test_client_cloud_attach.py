"""Tests for attaching and detaching a device's account-shared cloud transports."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pymammotion.account.registry import AccountSession
from pymammotion.client import MammotionClient
from pymammotion.transport.base import TransportAvailability, TransportType
from tests._helpers import make_mock_handle, make_mock_transport

ACCOUNT = "user@test.com"


def _transport(transport_type: TransportType) -> MagicMock:
    """Build a connected transport whose availability is UNKNOWN.

    add_transport replays a CONNECTED availability through the live handler,
    which would start loops and sends these assertions don't expect.
    """
    return make_mock_transport(transport_type, availability=TransportAvailability.UNKNOWN)


async def test_set_cloud_attached_false_leaves_other_devices_on_the_account() -> None:
    """Turning cloud off for one device must not take the account's others down.

    The cloud transports are one object per account, so disconnecting them for a
    single mower silently killed inbound cloud for every mower on that account,
    with nothing to bring it back short of a restart.
    """
    client = MammotionClient()
    shared = _transport(TransportType.CLOUD_MAMMOTION)
    first = make_mock_handle("dev1", "Luba-One")
    second = make_mock_handle("dev2", "Luba-Two")
    for handle in (first, second):
        handle.account_id = ACCOUNT
        await handle.add_transport(shared)
        await client._device_registry.register(handle)

    await client.set_cloud_attached("Luba-One", attached=False)

    assert not first.has_transport(TransportType.CLOUD_MAMMOTION)
    assert second.get_transport(TransportType.CLOUD_MAMMOTION) is shared
    shared.disconnect.assert_not_awaited()
    assert shared.is_connected


async def test_set_cloud_attached_true_restores_the_session_transports() -> None:
    """Re-attaching hands back the same shared objects and connects them."""
    client = MammotionClient()
    handle = make_mock_handle("dev1", "Luba-Back")
    handle.account_id = ACCOUNT
    await client._device_registry.register(handle)

    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
    session.mammotion_transport = _transport(TransportType.CLOUD_MAMMOTION)
    session.aliyun_transport = _transport(TransportType.CLOUD_ALIYUN)
    await client._account_registry.register(session)

    await client.set_cloud_attached("Luba-Back", attached=True)

    assert handle.get_transport(TransportType.CLOUD_MAMMOTION) is session.mammotion_transport
    assert handle.get_transport(TransportType.CLOUD_ALIYUN) is session.aliyun_transport
    session.mammotion_transport.connect.assert_awaited()
    session.aliyun_transport.connect.assert_awaited()


async def test_set_scheduled_updates_false_detaches_cloud_without_disconnecting() -> None:
    """The schedule-updates switch shares the hazard: detach, never disconnect."""
    client = MammotionClient()
    handle = make_mock_handle("dev1", "Luba-Sched")
    ble = _transport(TransportType.BLE)
    ble.connect = AsyncMock()
    cloud = _transport(TransportType.CLOUD_MAMMOTION)
    await handle.add_transport(ble)
    await handle.add_transport(cloud)
    await client._device_registry.register(handle)

    await client.set_scheduled_updates("Luba-Sched", enabled=False)

    assert not handle.has_transport(TransportType.CLOUD_MAMMOTION)
    cloud.disconnect.assert_not_awaited()
    ble.disconnect.assert_awaited_once()
    ble.connect.assert_not_awaited()


async def test_set_scheduled_updates_true_reattaches_cloud_and_connects_ble() -> None:
    """Re-enabling brings BLE back up and re-attaches the account's cloud transports."""
    client = MammotionClient()
    handle = make_mock_handle("dev1", "Luba-Sched2")
    handle.account_id = ACCOUNT
    ble = _transport(TransportType.BLE)
    ble.connect = AsyncMock()
    await handle.add_transport(ble)
    await client._device_registry.register(handle)

    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
    session.mammotion_transport = _transport(TransportType.CLOUD_MAMMOTION)
    await client._account_registry.register(session)

    await client.set_scheduled_updates("Luba-Sched2", enabled=True)

    assert handle.get_transport(TransportType.CLOUD_MAMMOTION) is session.mammotion_transport
    ble.connect.assert_awaited_once()
    ble.disconnect.assert_not_awaited()
