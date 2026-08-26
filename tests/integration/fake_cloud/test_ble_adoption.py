"""BLE is per device: a cloud login adopts a BLE-first handle, and sign-out gives it back."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pymammotion.account.registry import BLE_ONLY_ACCOUNT
from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowingDevice
from pymammotion.transport.base import TransportType
from tests.fakeserver.cloud import FakeMammotionCloud

from .conftest import wait_for

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _ble_device(address: str = "AA:BB:CC:DD:EE:FF") -> MagicMock:
    dev = MagicMock()
    dev.address = address
    return dev


async def test_ble_first_then_login_adopts_the_same_handle(fake_cloud: FakeMammotionCloud, client: MammotionClient) -> None:
    scenario = fake_cloud.scenario
    name = scenario.device.device_name
    ble_handle = await client.add_ble_only_device(name, name, MowingDevice(name=name), ble_device=_ble_device())
    ble_transport = ble_handle.get_transport(TransportType.BLE)
    assert ble_handle.account_id == BLE_ONLY_ACCOUNT

    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    handle = client.mower(name)
    assert handle is ble_handle
    assert handle.account_id == scenario.account
    assert client._device_registry.get(BLE_ONLY_ACCOUNT, name) is None
    assert handle.get_transport(TransportType.BLE) is ble_transport
    assert handle.has_transport(TransportType.CLOUD_MAMMOTION)
    assert handle.iot_id == scenario.device.iot_id
    assert handle.prefer_ble is True
    assert len(client._device_registry.all_devices) == 1
    session = client._account_registry.get(scenario.account)
    assert session is not None and session.device_ids == {name}
    await wait_for(lambda: len(fake_cloud.mammotion_broker.sessions) == 1)
    assert handle.has_usable_transport


async def test_login_then_ble_attaches_without_a_second_handle(fake_cloud: FakeMammotionCloud, client: MammotionClient) -> None:
    scenario = fake_cloud.scenario
    name = scenario.device.device_name
    await client.login_and_initiate_cloud(scenario.account, scenario.password)
    handle = client.mower(name)
    assert handle is not None

    await client.add_ble_device(name, _ble_device(), rssi=-55)
    assert handle.has_transport(TransportType.BLE)
    ble = handle.get_transport(TransportType.BLE)

    # A BLE-only registration for the same device lands on the cloud handle too.
    returned = await client.add_ble_only_device(name, name, MowingDevice(name=name), ble_device=_ble_device())
    assert returned is handle
    assert handle.get_transport(TransportType.BLE) is ble
    assert len(client._device_registry.all_devices) == 1


async def test_sign_out_keeps_ble_running_and_relogin_adopts_again(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    scenario = fake_cloud.scenario
    name = scenario.device.device_name
    await client.login_and_initiate_cloud(scenario.account, scenario.password)
    handle = client.mower(name)
    assert handle is not None
    await client.add_ble_device(name, _ble_device())
    ble = handle.get_transport(TransportType.BLE)

    await client._sign_out_existing_session(revoke=False)

    assert handle.account_id == BLE_ONLY_ACCOUNT
    assert client._device_registry.get(BLE_ONLY_ACCOUNT, name) is handle
    assert handle.get_transport(TransportType.BLE) is ble
    assert not handle.has_transport(TransportType.CLOUD_MAMMOTION)
    assert handle.is_started
    assert client._account_registry.all_sessions == []

    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    assert client.mower(name) is handle
    assert handle.account_id == scenario.account
    assert handle.get_transport(TransportType.BLE) is ble
    assert handle.has_transport(TransportType.CLOUD_MAMMOTION)
    assert len(client._device_registry.all_devices) == 1


async def test_restore_adopts_a_ble_first_handle(fake_cloud: FakeMammotionCloud, client: MammotionClient) -> None:
    """The HA restart path: BLE advertisement registered before the cached login is restored."""
    scenario = fake_cloud.scenario
    name = scenario.device.device_name
    await client.login_and_initiate_cloud(scenario.account, scenario.password)
    cache = client.to_cache()
    await client.stop()

    fresh = MammotionClient()
    try:
        ble_handle = await fresh.add_ble_only_device(name, name, MowingDevice(name=name), ble_device=_ble_device())
        await fresh.restore_credentials(scenario.account, scenario.password, cache)

        handle = fresh.mower(name)
        assert handle is ble_handle
        assert handle.account_id == scenario.account
        assert handle.has_transport(TransportType.BLE)
        assert handle.has_transport(TransportType.CLOUD_MAMMOTION)
        assert len(fresh._device_registry.all_devices) == 1
    finally:
        await fresh.stop()
