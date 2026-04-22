"""Tests for DeviceHandle and DeviceRegistry."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.aliyun.exceptions import DeviceOfflineException
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
    """transport.on_message must be a callable closure after add_transport.

    _wire_transport now sets a per-transport closure (not _on_raw_message directly)
    so that the transport type is captured and forwarded to _on_raw_message.
    """
    handle = make_handle()
    transport = make_transport(TransportType.CLOUD_ALIYUN)

    await handle.add_transport(transport)

    assert callable(transport.on_message)


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


async def test_active_transport_prefers_connected_ble_by_default() -> None:
    """With both connected, BLE wins unconditionally (lower latency, bypasses cloud throttle)."""
    ble_transport = make_transport(TransportType.BLE, connected=True)
    mqtt_transport = make_transport(TransportType.CLOUD_ALIYUN, connected=True)

    handle = make_handle()
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    active = handle.active_transport()
    assert active.transport_type == TransportType.BLE


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


async def test_active_transport_prefers_connected_ble_over_disconnected_mqtt() -> None:
    """Connected BLE always wins, even over a disconnected MQTT — BLE is the faster path."""
    ble_transport = make_transport(TransportType.BLE, connected=True)
    mqtt_transport = make_transport(TransportType.CLOUD_ALIYUN, connected=False)

    handle = make_handle()
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    active = handle.active_transport()
    assert active.transport_type == TransportType.BLE


async def test_active_transport_falls_back_to_mqtt_when_ble_disconnected() -> None:
    """If BLE is registered but not actively connected, MQTT is used."""
    ble_transport = make_transport(TransportType.BLE, connected=False)
    mqtt_transport = make_transport(TransportType.CLOUD_ALIYUN, connected=True)

    handle = make_handle()
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    active = handle.active_transport()
    assert active.transport_type == TransportType.CLOUD_ALIYUN


async def test_active_transport_returns_ble_even_when_disconnected() -> None:
    """When prefer_ble=True and BLE is registered (even disconnected), active_transport() returns BLE.

    ble_ok = ble is not None — registration alone makes BLE eligible.
    send_raw() is responsible for calling ble.connect() before the send; active_transport()
    does not gate on is_connected so that send_raw can always route through BLE when preferred.
    """
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
    assert active.transport_type == TransportType.BLE


async def test_active_transport_raises_when_none_registered() -> None:
    """NoTransportAvailableError is raised when no transport is registered at all."""
    handle = make_handle()

    with pytest.raises(NoTransportAvailableError):
        handle.active_transport()


# ---------------------------------------------------------------------------
# Helpers for offline / online tests
# ---------------------------------------------------------------------------


def _patch_raw_message_internals(handle: DeviceHandle) -> None:
    """Stub out the state-machine internals so _on_raw_message doesn't crash."""
    handle._reducer.apply = MagicMock(return_value=make_device())  # type: ignore[method-assign]
    handle.state_machine.apply = MagicMock(return_value=(MagicMock(), False))  # type: ignore[method-assign]
    handle.broker.on_message = AsyncMock()  # type: ignore[method-assign]


async def _drain_queue(handle: DeviceHandle) -> None:
    """Start queue, wait for all enqueued items to finish, then stop."""
    handle.queue.start()
    await handle.queue._queue.join()
    await handle.queue.stop()


# ---------------------------------------------------------------------------
# test 8: DeviceOfflineException marks mqtt_reported_offline — CLOUD_ALIYUN
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "transport_type",
    [TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION],
    ids=["aliyun", "mammotion"],
)
async def test_device_offline_marks_reported_offline(transport_type: TransportType) -> None:
    """DeviceOfflineException from either MQTT transport sets mqtt_reported_offline=True
    and makes the device unavailable (no BLE fallback present)."""
    handle = make_handle()
    mqtt = make_transport(transport_type, connected=True)
    await handle.add_transport(mqtt)
    handle.update_availability(transport_type, TransportAvailability.CONNECTED)

    handle.broker.send_and_wait = AsyncMock(  # type: ignore[method-assign]
        side_effect=DeviceOfflineException(6205, "iot-id")
    )

    await handle.send_command(b"\x01", "some_field")
    await _drain_queue(handle)

    assert handle.availability.mqtt_reported_offline is True
    assert handle.availability.is_available is False


# ---------------------------------------------------------------------------
# test 9: message arriving clears mqtt_reported_offline — both MQTT transports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "transport_type",
    [TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION],
    ids=["aliyun", "mammotion"],
)
async def test_incoming_message_clears_reported_offline(transport_type: TransportType) -> None:
    """Any message arriving over the cloud transport resets mqtt_reported_offline=False
    and makes the device available again."""
    handle = make_handle()
    mqtt = make_transport(transport_type, connected=True)
    await handle.add_transport(mqtt)
    handle.update_availability(transport_type, TransportAvailability.CONNECTED)

    # Put the device into the offline state directly
    handle.update_availability(transport_type, TransportAvailability.CONNECTED, mqtt_reported_offline=True)
    assert handle.availability.mqtt_reported_offline is True
    assert handle.availability.is_available is False

    # Simulate a message arriving from the device over the cloud transport
    _patch_raw_message_internals(handle)
    with patch("pymammotion.device.handle.LubaMsg") as mock_luba:
        mock_luba.return_value.parse.return_value = MagicMock()
        await handle.on_raw_message(b"\x00", transport_type)

    assert handle.availability.mqtt_reported_offline is False
    assert handle.availability.is_available is True


# ---------------------------------------------------------------------------
# test 10: BLE message does NOT clear mqtt_reported_offline
# ---------------------------------------------------------------------------


async def test_ble_message_does_not_clear_reported_offline() -> None:
    """A message arriving over BLE must not touch mqtt_reported_offline — the
    cloud transport is still reporting the device as offline."""
    handle = make_handle()
    mqtt = make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble = make_transport(TransportType.BLE, connected=True)
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)
    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED)

    handle.update_availability(
        TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED, mqtt_reported_offline=True
    )
    assert handle.availability.mqtt_reported_offline is True

    _patch_raw_message_internals(handle)
    with patch("pymammotion.device.handle.LubaMsg") as mock_luba:
        mock_luba.return_value.parse.return_value = MagicMock()
        await handle.on_raw_message(b"\x00", TransportType.BLE)

    # BLE message must not clear the MQTT offline flag
    assert handle.availability.mqtt_reported_offline is True


# ---------------------------------------------------------------------------
# test 11: BLE fallback when MQTT is used and reports the device offline
#
# With the current transport-selection rule (connected BLE always wins), this
# fallback only fires when BLE is *not* connected at selection time — MQTT
# is picked, it raises DeviceOfflineException, and BLE has since come online
# (or is available to retry on).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "transport_type",
    [TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION],
    ids=["aliyun", "mammotion"],
)
async def test_ble_fallback_used_when_mqtt_offline(transport_type: TransportType) -> None:
    """When MQTT raises DeviceOfflineException and BLE becomes connected, retry over BLE."""
    handle = make_handle()
    mqtt = make_transport(transport_type, connected=True)
    ble = make_transport(TransportType.BLE, connected=False)  # not connected → MQTT chosen
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)
    handle.update_availability(transport_type, TransportAvailability.CONNECTED)

    call_count = 0

    async def _send_and_wait_side_effect(**kwargs: object) -> None:  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Simulate BLE coming online between MQTT failure and retry
            ble.is_connected = True
            raise DeviceOfflineException(6205, "iot-id")
        # Second call (BLE) succeeds

    handle.broker.send_and_wait = AsyncMock(side_effect=_send_and_wait_side_effect)  # type: ignore[method-assign]

    await handle.send_command(b"\x01", "some_field")
    await _drain_queue(handle)

    # send_and_wait must have been called twice: MQTT then BLE
    assert handle.broker.send_and_wait.call_count == 2
    # Device must NOT be marked offline — BLE carried the command
    assert handle.availability.mqtt_reported_offline is True


# ---------------------------------------------------------------------------
# snapshot.raw reflects updated device state after on_raw_message
# ---------------------------------------------------------------------------


async def test_snapshot_raw_updates_after_on_raw_message() -> None:
    """snapshot.raw must reflect new field values after a real LubaMsg is processed."""
    from pymammotion.data.model.device import MowerDevice
    from pymammotion.proto import LubaMsg, MctlSys, ReportInfoData, RptDevStatus

    handle = DeviceHandle(
        device_id="dev-snap",
        device_name="Luba-Test",
        initial_device=MowerDevice(name="Luba-Test"),
    )

    msg = LubaMsg(sys=MctlSys(toapp_report_data=ReportInfoData(dev=RptDevStatus(battery_val=42))))
    await handle.on_raw_message(bytes(msg))

    assert handle.snapshot.raw.report_data.dev.battery_val == 42


# ---------------------------------------------------------------------------
# Regression: protobuf path must emit even when no snapshot-level field changes.
# DeviceSnapshot._diff only looks at connection_state/online/enabled/battery.
# A nav message updating mower_state.rain_detection (or any other deep field)
# must still propagate to state_changed_bus subscribers.
# ---------------------------------------------------------------------------


async def test_on_raw_message_emits_even_when_diff_is_empty() -> None:
    """state_changed_bus must fire for every protobuf message.

    Subscribers (watch_field, HA coordinators) inspect snapshot.raw fields
    that _diff() deliberately skips. If we gate emission on _diff, updates
    to deep fields like mower_state.rain_detection never reach HA.
    """
    from pymammotion.data.model.device import MowerDevice
    from pymammotion.proto import LubaMsg, MctlNav, NavSysParamMsg

    handle = DeviceHandle(
        device_id="dev-emit",
        device_name="Luba-Emit",
        initial_device=MowerDevice(name="Luba-Emit"),
    )

    received: list[object] = []

    async def _handler(snapshot: object) -> None:
        received.append(snapshot)

    handle.subscribe_state_changed(_handler)

    # A nav_sys_param_cmd only mutates mower_state.rain_detection — no snapshot
    # top-level field changes, so _diff returns an empty frozenset.
    msg = LubaMsg(nav=MctlNav(nav_sys_param_cmd=NavSysParamMsg(id=3, context=1)))
    await handle.on_raw_message(bytes(msg))

    assert len(received) == 1
    assert handle.snapshot.raw.mower_state.rain_detection is True


# ---------------------------------------------------------------------------
# MQTT unusable when mqtt_reported_offline: active_transport skips MQTT
# ---------------------------------------------------------------------------


async def test_active_transport_skips_mqtt_when_reported_offline() -> None:
    """mqtt_reported_offline=True → MQTT treated as unusable; BLE used if registered."""
    mqtt = make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble = make_transport(TransportType.BLE, connected=False)  # registered, not connected

    handle = make_handle()
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)

    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED, mqtt_reported_offline=True)

    active = handle.active_transport()
    assert active.transport_type == TransportType.BLE


async def test_active_transport_raises_when_only_mqtt_and_offline() -> None:
    """mqtt_reported_offline=True and no BLE → NoTransportAvailableError."""
    mqtt = make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    handle = make_handle()
    await handle.add_transport(mqtt)

    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED, mqtt_reported_offline=True)

    with pytest.raises(NoTransportAvailableError):
        handle.active_transport()
