"""MammotionClient._ensure_device_handle and friends: BLE is per device, accounts adopt handles."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.account.registry import BLE_ONLY_ACCOUNT, AccountSession
from pymammotion.client import MammotionClient, _CloudBinding
from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import TransportAvailability, TransportType
from pymammotion.transport.ble import BLETransport
from tests.unit._helpers import make_mock_mowing_device, make_mock_transport

NAME = "Luba-ADOPT"


def _cloud(transport: MagicMock | None = None, *, iot_id: str = "iot-1", token_manager: MagicMock | None = None) -> _CloudBinding:
    t = transport if transport is not None else make_mock_transport(TransportType.CLOUD_MAMMOTION, availability=TransportAvailability.UNKNOWN)
    return _CloudBinding(t, iot_id, "pk", 42, token_manager)


def _session(account: str = "acct") -> AccountSession:
    return AccountSession(account_id=account, email=account, password="pw")


def _ble_device(address: str = "AA:BB:CC:DD:EE:FF") -> MagicMock:
    dev = MagicMock()
    dev.address = address
    return dev


@pytest.fixture
async def client() -> MammotionClient:
    c = MammotionClient()
    yield c
    await c.stop()


async def test_cloud_registration_creates_started_handle_on_the_account(client: MammotionClient) -> None:
    session = _session()
    tm = MagicMock()
    handle = await client._ensure_device_handle(
        acct_session=session, device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud(token_manager=tm)
    )

    assert handle.account_id == "acct"
    assert client._device_registry.get("acct", NAME) is handle
    assert handle.is_started
    assert handle.iot_id == "iot-1"
    assert handle.user_account == 42
    assert handle.readiness_checker is not None
    assert handle.on_device_unbound == client._on_device_unbound
    assert session.device_ids == {NAME}
    assert client._inbound.handle_for("acct", "iot-1", "test") is handle
    tm.subscribe_handle.assert_called_once_with(handle)


async def test_cloud_login_adopts_ble_only_handle(client: MammotionClient) -> None:
    """BLE first, then cloud: the same object is re-keyed, keeps BLE and prefer_ble, gains cloud."""
    ble_handle = await client.add_ble_only_device(NAME, NAME, make_mock_mowing_device(), ble_address="AA:BB:CC:DD:EE:FF")
    assert ble_handle.account_id == BLE_ONLY_ACCOUNT
    assert ble_handle.prefer_ble is True
    ble_transport = ble_handle.get_transport(TransportType.BLE)

    session = _session()
    cloud_t = make_mock_transport(TransportType.CLOUD_MAMMOTION, availability=TransportAvailability.UNKNOWN)
    adopted = await client._ensure_device_handle(
        acct_session=session, device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud(cloud_t)
    )

    assert adopted is ble_handle
    assert adopted.account_id == "acct"
    assert client._device_registry.get(BLE_ONLY_ACCOUNT, NAME) is None
    assert client._device_registry.get("acct", NAME) is adopted
    assert adopted.get_transport(TransportType.BLE) is ble_transport
    assert adopted.get_transport(TransportType.CLOUD_MAMMOTION) is cloud_t
    assert adopted.prefer_ble is True
    assert session.device_ids == {NAME}
    assert len(client._device_registry.all_devices) == 1


async def test_registering_twice_on_the_same_account_is_idempotent(client: MammotionClient) -> None:
    """Same shared transport twice: no re-wire, no disconnect, one token-manager subscription."""
    session = _session()
    tm = MagicMock()
    cloud_t = make_mock_transport(TransportType.CLOUD_MAMMOTION, availability=TransportAvailability.UNKNOWN)
    first = await client._ensure_device_handle(
        acct_session=session, device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud(cloud_t, token_manager=tm)
    )
    second = await client._ensure_device_handle(
        acct_session=session, device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud(cloud_t, token_manager=tm)
    )

    assert first is second
    cloud_t.disconnect.assert_not_awaited()
    assert len(cloud_t.add_availability_listener.call_args_list) == 1
    assert tm.subscribe_handle.call_count == 2  # dedup lives inside TokenManager.subscribe_handle


async def test_second_account_gets_its_own_handle_and_leaves_the_first_alone(client: MammotionClient) -> None:
    a_t = make_mock_transport(TransportType.CLOUD_MAMMOTION, availability=TransportAvailability.UNKNOWN)
    b_t = make_mock_transport(TransportType.CLOUD_MAMMOTION, availability=TransportAvailability.UNKNOWN)
    a = await client._ensure_device_handle(
        acct_session=_session("a"), device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud(a_t)
    )
    b = await client._ensure_device_handle(
        acct_session=_session("b"), device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud(b_t)
    )

    assert a is not b
    assert a.get_transport(TransportType.CLOUD_MAMMOTION) is a_t
    assert b.get_transport(TransportType.CLOUD_MAMMOTION) is b_t
    a_t.disconnect.assert_not_awaited()
    assert client.mower(NAME, account_id="b") is b


async def test_cached_advertisement_is_attached_when_the_cloud_handle_is_created(client: MammotionClient) -> None:
    """add_ble_device before login caches the advertisement; cloud registration consumes it."""
    await client.add_ble_device(NAME, _ble_device(), rssi=-60)
    assert client._device_registry.all_devices == []

    handle = await client._ensure_device_handle(
        acct_session=_session(), device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud()
    )

    ble = handle.get_transport(TransportType.BLE)
    assert isinstance(ble, BLETransport)
    assert ble.ble_address == "AA:BB:CC:DD:EE:FF"


async def test_add_ble_device_onto_a_live_transport_only_refreshes_it(client: MammotionClient) -> None:
    handle = await client._ensure_device_handle(
        acct_session=_session(), device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud()
    )
    await client.add_ble_device(NAME, _ble_device("11:22:33:44:55:66"))
    ble = handle.get_transport(TransportType.BLE)
    assert isinstance(ble, BLETransport)
    ble.disconnect = AsyncMock()

    changed = await client.update_ble_device(NAME, _ble_device("11:22:33:44:55:66"))
    assert changed is False
    changed = await client.update_ble_device(NAME, _ble_device("AA:BB:CC:DD:EE:00"))
    assert changed is True

    assert handle.get_transport(TransportType.BLE) is ble
    ble.disconnect.assert_not_awaited()


async def test_add_ble_only_device_after_login_attaches_to_the_cloud_handle(client: MammotionClient) -> None:
    cloud_handle = await client._ensure_device_handle(
        acct_session=_session(), device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud()
    )

    returned = await client.add_ble_only_device(NAME, NAME, make_mock_mowing_device(), ble_device=_ble_device())

    assert returned is cloud_handle
    assert cloud_handle.has_transport(TransportType.BLE)
    assert client._device_registry.get(BLE_ONLY_ACCOUNT, NAME) is None


async def test_move_ble_to_account_hands_over_without_disconnecting(client: MammotionClient) -> None:
    ble_handle = await client.add_ble_only_device(NAME, NAME, make_mock_mowing_device(), ble_address="AA:BB:CC:DD:EE:FF")
    ble = ble_handle.get_transport(TransportType.BLE)
    assert isinstance(ble, BLETransport)
    ble.disconnect = AsyncMock()
    # A second account holds the device in the cloud while the sentinel handle owns BLE.
    target = await client._ensure_device_handle(
        acct_session=_session("b"), device_id="Other", device_name="Other", initial_device=make_mock_mowing_device(), cloud=_cloud()
    )
    await client._device_registry.rekey(ble_handle, "a")  # now account a owns BLE
    b_handle = await client._ensure_device_handle(
        acct_session=_session("b"), device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud()
    )
    assert not b_handle.has_transport(TransportType.BLE)

    await client.move_ble_to_account(NAME, "b")

    assert b_handle.get_transport(TransportType.BLE) is ble
    assert not ble_handle.has_transport(TransportType.BLE)
    ble.disconnect.assert_not_awaited()
    assert client._device_registry.find_ble_owner(NAME) is b_handle
    with pytest.raises(KeyError):
        await client.move_ble_to_account(NAME, "nobody")
    del target


async def test_sign_out_rekeys_ble_owner_to_sentinel_and_stops_cloud_only_handles(client: MammotionClient) -> None:
    session = _session()
    await client._account_registry.register(session)
    shared = make_mock_transport(TransportType.CLOUD_MAMMOTION, availability=TransportAvailability.UNKNOWN)
    session.mammotion_transport = shared
    hybrid = await client._ensure_device_handle(
        acct_session=session, device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud(shared)
    )
    await client.add_ble_device(NAME, _ble_device())
    cloud_only = await client._ensure_device_handle(
        acct_session=session, device_id="Luba-CO", device_name="Luba-CO", initial_device=make_mock_mowing_device(), cloud=_cloud(shared, iot_id="iot-2")
    )
    ble = hybrid.get_transport(TransportType.BLE)
    assert isinstance(ble, BLETransport)
    ble.disconnect = AsyncMock()

    await client._sign_out_existing_session(revoke=False)

    assert hybrid.account_id == BLE_ONLY_ACCOUNT
    assert client._device_registry.get(BLE_ONLY_ACCOUNT, NAME) is hybrid
    assert hybrid.is_started
    assert hybrid.get_transport(TransportType.BLE) is ble
    assert not hybrid.has_transport(TransportType.CLOUD_MAMMOTION)
    ble.disconnect.assert_not_awaited()
    shared.disconnect.assert_awaited_once()  # the session disconnects its shared transport exactly once
    assert cloud_only.is_started is False
    assert client._device_registry.get_any("Luba-CO") == []
    assert session.device_ids == set()
    assert client._account_registry.all_sessions == []
    assert not shared.add_availability_listener.call_args_list or shared.remove_availability_listener.call_count == 2


async def test_quiesce_detaches_cloud_but_keeps_the_account_key(client: MammotionClient) -> None:
    session = _session()
    await client._account_registry.register(session)
    shared = make_mock_transport(TransportType.CLOUD_MAMMOTION, availability=TransportAvailability.UNKNOWN)
    session.mammotion_transport = shared
    hybrid = await client._ensure_device_handle(
        acct_session=session, device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud(shared)
    )
    await client.add_ble_device(NAME, _ble_device())
    ble = hybrid.get_transport(TransportType.BLE)
    assert isinstance(ble, BLETransport)
    ble.disconnect = AsyncMock()
    hybrid.notify_critical_error = AsyncMock()

    await client._quiesce_account(session, "dead", RuntimeError("dead"))

    assert hybrid.account_id == "acct"  # a re-authentication adopts it back
    assert not hybrid.has_transport(TransportType.CLOUD_MAMMOTION)
    assert hybrid.get_transport(TransportType.BLE) is ble
    ble.disconnect.assert_not_awaited()
    shared.mark_unrecoverable_auth_failure.assert_called_once()
    hybrid.notify_critical_error.assert_awaited_once()


async def test_device_id_name_mismatch_falls_back_to_the_named_handle(client: MammotionClient, caplog: pytest.LogCaptureFixture) -> None:
    ble_handle = await client.add_ble_only_device("aa:bb:cc", NAME, make_mock_mowing_device(), ble_address="AA:BB:CC:DD:EE:FF")

    handle = await client._ensure_device_handle(
        acct_session=_session(), device_id=NAME, device_name=NAME, initial_device=make_mock_mowing_device(), cloud=_cloud()
    )

    assert handle is ble_handle
    assert "registered under device_id" in caplog.text


def test_handle_default_account_is_the_sentinel() -> None:
    handle = DeviceHandle("x", "x", make_mock_mowing_device())
    assert handle.account_id == BLE_ONLY_ACCOUNT
