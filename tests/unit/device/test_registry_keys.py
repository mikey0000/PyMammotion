"""DeviceRegistry keyed by (account_id, device_id): no overwrites, re-keying, name resolution."""

from __future__ import annotations

import logging

import pytest

from pymammotion.account.registry import BLE_ONLY_ACCOUNT
from pymammotion.device.handle import DeviceAlreadyRegisteredError, DeviceHandle, DeviceRegistry
from pymammotion.transport.base import TransportType
from tests._helpers import make_mock_mowing_device, make_mock_transport


def _handle(device_id: str = "Luba-1", name: str | None = None, *, ble: bool = False) -> DeviceHandle:
    ble_t = make_mock_transport(TransportType.BLE) if ble else None
    return DeviceHandle(device_id, name or device_id, make_mock_mowing_device(), ble_transport=ble_t)


async def test_register_defaults_to_sentinel_and_is_idempotent_for_same_object() -> None:
    registry = DeviceRegistry()
    handle = _handle()

    await registry.register(handle)
    await registry.register(handle)

    assert handle.account_id == BLE_ONLY_ACCOUNT
    assert registry.get(BLE_ONLY_ACCOUNT, "Luba-1") is handle
    assert registry.all_devices == [handle]


async def test_register_refuses_to_overwrite_a_different_handle() -> None:
    registry = DeviceRegistry()
    await registry.register(_handle(), "acct")

    with pytest.raises(DeviceAlreadyRegisteredError):
        await registry.register(_handle(), "acct")


async def test_two_accounts_hold_the_same_device_as_two_handles() -> None:
    """Handles are per (account, device): a second account never displaces the first."""
    registry = DeviceRegistry()
    a, b = _handle(), _handle()
    await registry.register(a, "acct-a")
    await registry.register(b, "acct-b")

    assert registry.get("acct-a", "Luba-1") is a
    assert registry.get("acct-b", "Luba-1") is b
    assert set(registry.get_any("Luba-1")) == {a, b}
    assert registry.for_account("acct-a") == [a]


async def test_rekey_moves_the_same_object_and_refuses_an_occupied_target() -> None:
    registry = DeviceRegistry()
    orphan = _handle(ble=True)
    await registry.register(orphan)

    await registry.rekey(orphan, "acct")

    assert orphan.account_id == "acct"
    assert registry.get(BLE_ONLY_ACCOUNT, "Luba-1") is None
    assert registry.get("acct", "Luba-1") is orphan

    other = _handle()
    await registry.register(other, "other")
    with pytest.raises(DeviceAlreadyRegisteredError):
        await registry.rekey(orphan, "other")


async def test_find_ble_owner_returns_the_one_handle_with_ble() -> None:
    registry = DeviceRegistry()
    cloud_only = _handle()
    with_ble = _handle(ble=True)
    await registry.register(cloud_only, "acct-a")
    await registry.register(with_ble, "acct-b")

    assert registry.find_ble_owner("Luba-1") is with_ble
    assert registry.find_ble_owner("Nope") is None


async def test_get_by_name_resolution_rule(caplog: pytest.LogCaptureFixture) -> None:
    """Unique holder → it; several → the BLE owner; several without BLE → first cloud holder + warning."""
    registry = DeviceRegistry()
    sole = _handle("Luba-Solo")
    await registry.register(sole, "acct-a")
    assert registry.get_by_name("Luba-Solo") is sole
    assert registry.get_by_name("Luba-Solo", "acct-a") is sole
    assert registry.get_by_name("Luba-Solo", "acct-b") is None
    assert registry.get_by_name("Unknown") is None

    with_ble = _handle(ble=True)
    plain = _handle()
    await registry.register(with_ble, BLE_ONLY_ACCOUNT)
    await registry.register(plain, "acct-a")
    assert registry.get_by_name("Luba-1") is with_ble
    assert registry.get("Luba-1") is with_ble  # single positional resolves the same way

    second_plain = _handle()
    await registry.register(second_plain, "acct-b")
    with_ble.detach_transport(TransportType.BLE)
    with caplog.at_level(logging.WARNING):
        chosen = registry.get_by_name("Luba-1")
    assert chosen is plain  # first cloud (non-sentinel) holder
    assert "held by 3 accounts" in caplog.text


async def test_unregister_by_key_stops_only_that_handle() -> None:
    registry = DeviceRegistry()
    a, b = _handle(), _handle()
    await registry.register(a, "acct-a")
    await registry.register(b, "acct-b")

    await registry.unregister("acct-a", "Luba-1")

    assert registry.get("acct-a", "Luba-1") is None
    assert registry.get("acct-b", "Luba-1") is b
    assert a.is_started is False
