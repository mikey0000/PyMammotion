"""Tests for AccountRegistry and AccountSession."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock


from pymammotion.account.registry import BLE_ONLY_ACCOUNT, AccountRegistry, AccountSession
from pymammotion.data.model.device import MowingDevice


# Helpers


def _make_session(account_id: str = "user@example.com") -> AccountSession:
    token_manager = MagicMock()
    return AccountSession(
        account_id=account_id,
        token_manager=token_manager,
    )


def _make_ble_device(address: str = "AA:BB:CC:DD:EE:FF") -> MagicMock:
    dev = MagicMock()
    dev.address = address
    return dev


# AccountRegistry — basic CRUD


async def test_register_and_get() -> None:
    """register() stores a session; get() retrieves it by account_id."""
    registry = AccountRegistry()
    session = _make_session("alice@example.com")

    await registry.register(session)

    result = registry.get("alice@example.com")
    assert result is session


async def test_unregister_removes_session() -> None:
    """unregister() removes the session; get() returns None afterwards."""
    registry = AccountRegistry()
    session = _make_session("bob@example.com")

    await registry.register(session)
    assert registry.get("bob@example.com") is session

    await registry.unregister("bob@example.com")
    assert registry.get("bob@example.com") is None


async def test_unregister_missing_is_noop() -> None:
    """unregister() on a non-existent account_id does not raise."""
    registry = AccountRegistry()
    await registry.unregister("nobody@example.com")  # must not raise


async def test_concurrent_register_safe() -> None:
    """Two concurrent register() calls both store their sessions safely."""
    registry = AccountRegistry()

    session_a = _make_session("a@example.com")
    session_b = _make_session("b@example.com")

    await asyncio.gather(
        registry.register(session_a),
        registry.register(session_b),
    )

    assert registry.get("a@example.com") is session_a
    assert registry.get("b@example.com") is session_b
    assert len(registry.sessions) == 2


async def test_all_sessions_returns_list() -> None:
    """all_sessions returns every registered session."""
    registry = AccountRegistry()
    s1 = _make_session("x@example.com")
    s2 = _make_session("y@example.com")
    await registry.register(s1)
    await registry.register(s2)

    sessions = registry.all_sessions
    assert set(s.account_id for s in sessions) == {"x@example.com", "y@example.com"}


# find_by_device — device_name as unique identifier


async def test_find_by_device_returns_owning_session() -> None:
    """find_by_device() returns the session whose device_ids contains the name."""
    registry = AccountRegistry()
    session = AccountSession(account_id="owner@example.com")
    session.device_ids.add("Luba-VS563L6H")
    await registry.register(session)

    result = registry.find_by_device("Luba-VS563L6H")
    assert result is session


async def test_find_by_device_returns_none_when_absent() -> None:
    """find_by_device() returns None when no session owns the device."""
    registry = AccountRegistry()
    await registry.register(AccountSession(account_id="other@example.com"))

    assert registry.find_by_device("Luba-XXXXXX") is None


async def test_find_by_device_multiple_accounts() -> None:
    """find_by_device() correctly locates the owning session among several accounts."""
    registry = AccountRegistry()

    cloud_session = AccountSession(account_id="cloud@example.com")
    cloud_session.device_ids.update({"Luba-111111", "Yuka-222222"})

    ble_session = AccountSession(account_id=BLE_ONLY_ACCOUNT)
    ble_session.device_ids.add("Luba-333333")

    await registry.register(cloud_session)
    await registry.register(ble_session)

    assert registry.find_by_device("Yuka-222222") is cloud_session
    assert registry.find_by_device("Luba-333333") is ble_session
    assert registry.find_by_device("Unknown-X") is None


# BLE-only devices — registered under the BLE_ONLY_ACCOUNT key, never as a session


async def test_ble_only_account_id_constant() -> None:
    """BLE_ONLY_ACCOUNT sentinel has the expected value."""
    assert BLE_ONLY_ACCOUNT == "__ble__"


async def test_add_ble_only_device_registers_no_account_session() -> None:
    """A BLE-only device is a registry entry under the sentinel key — no AccountSession is created."""
    from pymammotion.client import MammotionClient
    from pymammotion.transport.base import TransportType

    client = MammotionClient("test")
    ble_dev = _make_ble_device("CC:64:1A:49:37:95")

    handle = await client.add_ble_only_device(
        device_id="Luba-VS563L6H",
        device_name="Luba-VS563L6H",
        initial_device=MowingDevice(name="Luba-VS563L6H"),
        ble_device=ble_dev,
    )

    assert client._account_registry.all_sessions == []
    assert handle.account_id == BLE_ONLY_ACCOUNT
    assert client._device_registry.get(BLE_ONLY_ACCOUNT, "Luba-VS563L6H") is handle
    assert handle.has_transport(TransportType.BLE)
    assert handle.is_started
    await handle.stop()


async def test_add_ble_only_device_idempotent_same_client() -> None:
    """Calling add_ble_only_device twice with the same device_id on the same client
    returns the existing handle and does not create a second one."""
    from pymammotion.client import MammotionClient

    client = MammotionClient("test")
    ble_dev_1 = _make_ble_device("CC:64:1A:49:37:95")
    ble_dev_2 = _make_ble_device("CC:64:1A:49:37:95")

    handle_1 = await client.add_ble_only_device(
        device_id="Luba-VS563L6H",
        device_name="Luba-VS563L6H",
        initial_device=MowingDevice(name="Luba-VS563L6H"),
        ble_device=ble_dev_1,
    )
    handle_2 = await client.add_ble_only_device(
        device_id="Luba-VS563L6H",
        device_name="Luba-VS563L6H",
        initial_device=MowingDevice(name="Luba-VS563L6H"),
        ble_device=ble_dev_2,
    )

    assert handle_1 is handle_2, "second call must return the existing handle"
    assert len(client._device_registry.all_devices) == 1
    await handle_1.stop()


async def test_add_ble_only_device_idempotent_updates_ble_device() -> None:
    """When the same device_id is registered twice the second BLEDevice is applied
    to the existing transport so the transport uses the fresher advertisement."""
    from pymammotion.client import MammotionClient
    from pymammotion.transport.base import TransportType

    client = MammotionClient("test")
    ble_dev_1 = _make_ble_device("CC:64:1A:49:37:95")
    ble_dev_2 = _make_ble_device("CC:64:1A:49:37:95")

    await client.add_ble_only_device(
        device_id="Luba-VS563L6H",
        device_name="Luba-VS563L6H",
        initial_device=MowingDevice(name="Luba-VS563L6H"),
        ble_device=ble_dev_1,
    )
    await client.add_ble_only_device(
        device_id="Luba-VS563L6H",
        device_name="Luba-VS563L6H",
        initial_device=MowingDevice(name="Luba-VS563L6H"),
        ble_device=ble_dev_2,
    )

    handle = client._device_registry.get("Luba-VS563L6H")
    assert handle is not None
    transport = handle.get_transport(TransportType.BLE)
    assert transport is not None
    assert transport.ble_address == ble_dev_2.address
    await handle.stop()


async def test_multiple_ble_devices_each_get_own_handle() -> None:
    """Two distinct BLE-only devices are two sentinel-keyed handles and still zero sessions."""
    from pymammotion.client import MammotionClient

    client = MammotionClient("test")

    a = await client.add_ble_only_device(
        device_id="Luba-VS563L6H",
        device_name="Luba-VS563L6H",
        initial_device=MowingDevice(name="Luba-VS563L6H"),
        ble_device=_make_ble_device("CC:64:1A:49:37:95"),
    )
    b = await client.add_ble_only_device(
        device_id="Yuka-TESTDEV1",
        device_name="Yuka-TESTDEV1",
        initial_device=MowingDevice(name="Yuka-TESTDEV1"),
        ble_device=_make_ble_device("02:00:00:12:34:57"),
    )

    assert client._account_registry.all_sessions == []
    assert {h.account_id for h in client._device_registry.all_devices} == {BLE_ONLY_ACCOUNT}
    assert len(client._device_registry.all_devices) == 2
    await a.stop()
    await b.stop()
