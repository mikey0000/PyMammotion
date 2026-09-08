"""InboundRouter — (account_id, iot_id) -> DeviceHandle demux for cloud frames.

A cloud transport is shared by every device on an account, so frames arrive
labelled with an iotId rather than addressed to a handle.  This was seven methods
and a dict on MammotionClient.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pymammotion.device.handle import DeviceRegistry
from pymammotion.device.inbound_router import InboundRouter
from tests.unit._helpers import make_mock_handle

ACCOUNT = "user@example.com"


async def _router_with_handle() -> tuple[InboundRouter, DeviceRegistry, object]:
    registry = DeviceRegistry()
    handle = make_mock_handle("dev1", "Luba-Route")
    await registry.register(handle, ACCOUNT)
    router = InboundRouter(registry)
    router.bind(ACCOUNT, "iot-1", (ACCOUNT, "dev1"))
    return router, registry, handle


async def test_bound_iot_id_resolves_to_its_handle() -> None:
    router, _, handle = await _router_with_handle()
    assert router.handle_for(ACCOUNT, "iot-1", "test") is handle


async def test_unbound_iot_id_resolves_to_nothing() -> None:
    router, _, _ = await _router_with_handle()
    assert router.handle_for(ACCOUNT, "iot-unknown", "test") is None


async def test_iot_ids_do_not_leak_across_accounts() -> None:
    """The key is (account, iot_id): a second account must not inherit the binding."""
    router, _, _ = await _router_with_handle()
    assert router.handle_for("other@example.com", "iot-1", "test") is None


async def test_unbind_stops_routing() -> None:
    router, _, _ = await _router_with_handle()
    router.unbind(ACCOUNT, "iot-1")
    assert router.handle_for(ACCOUNT, "iot-1", "test") is None


async def test_unbind_is_safe_when_not_bound() -> None:
    router, _, _ = await _router_with_handle()
    router.unbind(ACCOUNT, "never-bound")  # must not raise


async def test_router_resolves_through_the_registry_not_a_cached_handle() -> None:
    """A handle can be re-keyed between accounts, so the registry stays authoritative."""
    registry = DeviceRegistry()
    router = InboundRouter(registry)
    router.bind(ACCOUNT, "iot-1", (ACCOUNT, "dev1"))
    # Bound, but nothing registered yet.
    assert router.handle_for(ACCOUNT, "iot-1", "test") is None

    handle = make_mock_handle("dev1", "Luba-Late")
    await registry.register(handle, ACCOUNT)
    assert router.handle_for(ACCOUNT, "iot-1", "test") is handle


@pytest.mark.parametrize(
    ("route", "forwards_to", "payload"),
    [
        ("route_message", "on_raw_message", b"\x08\x01"),
        ("route_event", "on_device_event", object()),
        ("route_properties", "on_device_properties", object()),
        ("route_mammotion_properties", "on_mammotion_properties", object()),
    ],
)
async def test_routes_forward_to_the_handle(route: str, forwards_to: str, payload: object) -> None:
    router, _, handle = await _router_with_handle()
    setattr(handle, forwards_to, AsyncMock())

    await getattr(router, route)(ACCOUNT, "iot-1", payload)

    getattr(handle, forwards_to).assert_awaited_once_with(payload)


@pytest.mark.parametrize(
    ("route", "must_not_call", "payload"),
    [
        ("route_message", "on_raw_message", b"\x08\x01"),
        ("route_event", "on_device_event", object()),
        ("route_properties", "on_device_properties", object()),
        ("route_mammotion_properties", "on_mammotion_properties", object()),
    ],
)
async def test_unroutable_frame_is_dropped_silently(route: str, must_not_call: str, payload: object) -> None:
    """An unknown iotId must not reach any handle — the 2c mis-routing lesson."""
    router, _, handle = await _router_with_handle()
    setattr(handle, must_not_call, AsyncMock())

    await getattr(router, route)(ACCOUNT, "iot-unknown", payload)

    getattr(handle, must_not_call).assert_not_awaited()


async def test_binding_follows_the_handle_the_registry_actually_holds() -> None:
    """The router resolves through the registry, so the bound key must be the registry's.

    ``_ensure_device_handle`` can adopt an existing handle found *by name* whose
    ``device_id`` differs from the one it was called with (a BLE-only handle keyed on
    a MAC, later claimed by a cloud login keyed on the device name).  Binding the
    argument instead of ``handle.device_id`` left every inbound cloud frame for that
    device resolving to None and being dropped.
    """
    registry = DeviceRegistry()
    handle = make_mock_handle("mac-abc123", "Luba-XYZ")
    await registry.register(handle, ACCOUNT)
    router = InboundRouter(registry)

    # Bound with the handle's real registry id, not the name the caller used.
    router.bind(ACCOUNT, "iot-1", (ACCOUNT, handle.device_id))
    assert router.handle_for(ACCOUNT, "iot-1", "test") is handle

    # The bug: binding a key the registry does not hold silently routes nowhere.
    router.bind(ACCOUNT, "iot-2", (ACCOUNT, "Luba-XYZ"))
    assert router.handle_for(ACCOUNT, "iot-2", "test") is None


async def test_notification_is_forwarded_to_the_handle_with_its_value() -> None:
    router, _, handle = await _router_with_handle()
    handle.on_device_notification = AsyncMock()

    await router.route_notification(ACCOUNT, "iot-1", "device_warning_code_event", {"data": "[]"})

    handle.on_device_notification.assert_awaited_once_with("device_warning_code_event", {"data": "[]"})


async def test_notification_for_unknown_iot_id_is_dropped() -> None:
    router, _, handle = await _router_with_handle()
    handle.on_device_notification = AsyncMock()

    await router.route_notification(ACCOUNT, "iot-unknown", "device_warning_code_event")

    handle.on_device_notification.assert_not_awaited()
