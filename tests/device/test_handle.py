"""Tests for DeviceHandle and DeviceRegistry."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.messaging.command_queue import Priority
from pymammotion.state.device_state import DeviceAvailability, DeviceConnectionState, TransportAvailability
from pymammotion.transport.base import NoTransportAvailableError, TransportType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_device(online: bool = True, enabled: bool = True) -> MagicMock:
    """Return a MagicMock shaped like a MowingDevice."""
    device = MagicMock()
    device.online = online
    device.enabled = enabled
    device.report_data.dev.battery_val = 80
    device.report_data.dev.sys_status = "idle"
    device.report_data.work.knife_height = 50
    return device


def make_transport(transport_type: TransportType, *, connected: bool = True) -> MagicMock:
    """Return a MagicMock shaped like a Transport."""
    transport = MagicMock()
    transport.transport_type = transport_type
    transport.is_connected = connected
    transport.send = AsyncMock()
    transport.disconnect = AsyncMock()
    transport.on_message = None
    return transport


def make_handle(
    device_id: str = "dev1",
    device_name: str = "Mower One",
    *,
    mqtt_transport: MagicMock | None = None,
    ble_transport: MagicMock | None = None,
) -> DeviceHandle:
    """Build a DeviceHandle with a mock MowingDevice."""
    device = make_device()
    return DeviceHandle(
        device_id=device_id,
        device_name=device_name,
        initial_device=device,
        mqtt_transport=mqtt_transport,
        ble_transport=ble_transport,
    )


# ---------------------------------------------------------------------------
# test 1: add_transport sets on_message
# ---------------------------------------------------------------------------


async def test_add_transport_sets_on_message() -> None:
    """transport.on_message must be set to handle._on_raw_message after add_transport."""
    handle = make_handle()
    transport = make_transport(TransportType.CLOUD_ALIYUN)

    await handle.add_transport(transport)

    # _on_raw_message is a bound method on the handle; compare __func__ and __self__
    # to avoid the identity issue that arises from bound method re-creation on each access.
    raw_message_method = handle._on_raw_message
    set_on_message = transport.on_message
    assert set_on_message.__func__ is raw_message_method.__func__
    assert set_on_message.__self__ is raw_message_method.__self__


# ---------------------------------------------------------------------------
# test 2: send_command enqueues work
# ---------------------------------------------------------------------------


async def test_send_command_enqueues_work() -> None:
    """send_command should add an item to the queue (queue size grows)."""
    handle = make_handle()
    # Add a connected transport so _active_transport doesn't raise
    transport = make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    await handle.add_transport(transport)

    # Don't start the queue so items accumulate
    initial_size = handle.queue._queue.qsize()
    await handle.send_command(b"\x01\x02", "some_field", priority=Priority.NORMAL)
    assert handle.queue._queue.qsize() == initial_size + 1


# ---------------------------------------------------------------------------
# test 3: update_availability changes state
# ---------------------------------------------------------------------------


async def test_update_availability_changes_state() -> None:
    """After marking MQTT as connected, availability.is_available must be True."""
    handle = make_handle()
    assert handle.availability.is_available is False

    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED)

    assert handle.availability.is_available is True
    assert handle.availability.connection_state == DeviceConnectionState.CONNECTED


# ---------------------------------------------------------------------------
# test 4: stop cancels queue and broker
# ---------------------------------------------------------------------------


async def test_stop_cancels_queue_and_broker() -> None:
    """stop() must call queue.stop() and broker.close()."""
    handle = make_handle()

    queue_stop = AsyncMock()
    broker_close = AsyncMock()

    handle.queue.stop = queue_stop  # type: ignore[method-assign]
    handle.broker.close = broker_close  # type: ignore[method-assign]

    await handle.stop()

    queue_stop.assert_awaited_once()
    broker_close.assert_awaited_once()


# ---------------------------------------------------------------------------
# test 5: registry register and get
# ---------------------------------------------------------------------------


async def test_registry_register_and_get() -> None:
    """Registering a handle makes it retrievable via get()."""
    registry = DeviceRegistry()
    handle = make_handle(device_id="abc123", device_name="Luba One")

    await registry.register(handle)

    result = registry.get("abc123")
    assert result is handle
    assert registry.get("nonexistent") is None


# ---------------------------------------------------------------------------
# test 6: registry unregister calls stop
# ---------------------------------------------------------------------------


async def test_registry_unregister_calls_stop() -> None:
    """unregister() must call handle.stop() and remove it from the registry."""
    registry = DeviceRegistry()
    handle = make_handle(device_id="dev99")
    handle.stop = AsyncMock()  # type: ignore[method-assign]

    await registry.register(handle)
    await registry.unregister("dev99")

    handle.stop.assert_awaited_once()
    assert registry.get("dev99") is None


# ---------------------------------------------------------------------------
# test 7: _active_transport preference order
# ---------------------------------------------------------------------------


async def test_active_transport_prefers_mqtt_by_default() -> None:
    """With both connected, MQTT is preferred by default (longer range, no proximity needed)."""
    ble_transport = make_transport(TransportType.BLE, connected=True)
    mqtt_transport = make_transport(TransportType.CLOUD_ALIYUN, connected=True)

    handle = make_handle()
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    active = handle.active_transport()
    assert active.transport_type == TransportType.CLOUD_ALIYUN


async def test_active_transport_prefer_ble_flag_reverses_order() -> None:
    """When prefer_ble=True, BLE is chosen over MQTT when both are connected."""
    from pymammotion.device.handle import DeviceHandle

    ble_transport = make_transport(TransportType.BLE, connected=True)
    mqtt_transport = make_transport(TransportType.CLOUD_ALIYUN, connected=True)

    handle = DeviceHandle(
        device_id="dev-ble",
        device_name="BLE-Preferred",
        initial_device=make_device(),
        prefer_ble=True,
    )
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    active = handle.active_transport()
    assert active.transport_type == TransportType.BLE


async def test_active_transport_falls_back_to_ble_when_mqtt_disconnected() -> None:
    """When MQTT is disconnected, BLE is used as fallback (default MQTT-preference mode)."""
    ble_transport = make_transport(TransportType.BLE, connected=True)
    mqtt_transport = make_transport(TransportType.CLOUD_ALIYUN, connected=False)

    handle = make_handle()
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    active = handle.active_transport()
    assert active.transport_type == TransportType.BLE


async def test_active_transport_falls_back_to_mqtt_when_ble_disconnected() -> None:
    """When prefer_ble=True but BLE is disconnected, MQTT is used as fallback."""
    from pymammotion.device.handle import DeviceHandle

    ble_transport = make_transport(TransportType.BLE, connected=False)
    mqtt_transport = make_transport(TransportType.CLOUD_ALIYUN, connected=True)

    handle = DeviceHandle(
        device_id="dev-ble2",
        device_name="BLE-Preferred-2",
        initial_device=make_device(),
        prefer_ble=True,
    )
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    active = handle.active_transport()
    assert active.transport_type == TransportType.CLOUD_ALIYUN


async def test_active_transport_raises_when_none_connected() -> None:
    """NoTransportAvailableError is raised when no transport is connected."""
    handle = make_handle()
    transport = make_transport(TransportType.CLOUD_ALIYUN, connected=False)
    await handle.add_transport(transport)

    with pytest.raises(NoTransportAvailableError):
        handle.active_transport()
