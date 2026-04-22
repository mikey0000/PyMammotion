"""Tests covering BLE-only, WiFi-only, and hybrid transport modes.

Also covers add_ble_device() wiring a BLETransport onto an existing handle.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowingDevice
from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import NoTransportAvailableError, TransportType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transport(transport_type: TransportType, *, connected: bool = True) -> MagicMock:
    t = MagicMock()
    t.transport_type = transport_type
    t.is_connected = connected
    t.send = AsyncMock()
    t.connect = AsyncMock()
    t.disconnect = AsyncMock()
    t.on_message = None
    t.add_availability_listener = MagicMock()
    return t


def _make_handle(
    device_id: str = "Luba-TEST",
    device_name: str = "Luba-TEST",
    *,
    prefer_ble: bool = False,
) -> DeviceHandle:
    return DeviceHandle(
        device_id=device_id,
        device_name=device_name,
        initial_device=MowingDevice(name=device_name),
        prefer_ble=prefer_ble,
    )


# ---------------------------------------------------------------------------
# BLE-only
# ---------------------------------------------------------------------------


async def test_ble_only_active_transport_is_ble() -> None:
    """With only a connected BLE transport, active_transport() returns it."""
    handle = _make_handle(prefer_ble=True)
    ble = _make_transport(TransportType.BLE, connected=True)
    await handle.add_transport(ble)

    assert handle.active_transport() is ble


async def test_ble_only_returns_ble_even_when_disconnected() -> None:
    """When the only BLE transport is registered (but disconnected), active_transport returns it.

    ble_ok = ble is not None — registration alone makes BLE eligible.
    send_raw() calls ble.connect() before sending; active_transport() does not gate on
    is_connected so routing is always deterministic.
    """
    handle = _make_handle(prefer_ble=True)
    ble = _make_transport(TransportType.BLE, connected=False)
    await handle.add_transport(ble)

    assert handle.active_transport() is ble


async def test_ble_only_reconnects_before_send() -> None:
    """send_raw() must call ble.connect() when BLE is the only transport and it's disconnected."""
    handle = _make_handle(prefer_ble=True)
    ble = _make_transport(TransportType.BLE, connected=False)

    # After connect() is called, simulate the transport becoming connected.
    async def _do_connect() -> None:
        ble.is_connected = True

    ble.connect.side_effect = _do_connect
    await handle.add_transport(ble)

    await handle.send_raw(b"\x00\x01", prefer_ble=True)

    ble.connect.assert_awaited_once()
    ble.send.assert_awaited_once_with(b"\x00\x01", iot_id="")


# ---------------------------------------------------------------------------
# WiFi-only (MQTT)
# ---------------------------------------------------------------------------


async def test_wifi_only_active_transport_is_mqtt() -> None:
    """With only a connected MQTT transport, active_transport() returns it."""
    handle = _make_handle()
    mqtt = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    await handle.add_transport(mqtt)

    assert handle.active_transport() is mqtt


async def test_wifi_only_disconnected_mqtt_still_selected() -> None:
    """A disconnected MQTT transport is still returned — send_raw handles the actual send."""
    handle = _make_handle()
    mqtt = _make_transport(TransportType.CLOUD_ALIYUN, connected=False)
    await handle.add_transport(mqtt)

    assert handle.active_transport() is mqtt


async def test_wifi_only_send_uses_mqtt() -> None:
    """send_raw() routes the payload through the MQTT transport."""
    handle = _make_handle()
    mqtt = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    await handle.add_transport(mqtt)

    await handle.send_raw(b"\xAB\xCD")

    mqtt.send.assert_awaited_once_with(b"\xAB\xCD", iot_id="")


# ---------------------------------------------------------------------------
# Hybrid — connected BLE always wins
# ---------------------------------------------------------------------------


async def test_hybrid_default_prefers_connected_ble() -> None:
    """When both are connected, BLE is chosen unconditionally (lower latency)."""
    handle = _make_handle(prefer_ble=False)
    mqtt = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble = _make_transport(TransportType.BLE, connected=True)
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)

    assert handle.active_transport() is ble


async def test_hybrid_prefer_ble_chooses_ble() -> None:
    """When both are connected and prefer_ble=True, BLE is chosen."""
    handle = _make_handle(prefer_ble=True)
    mqtt = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble = _make_transport(TransportType.BLE, connected=True)
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)

    assert handle.active_transport() is ble


async def test_hybrid_ble_disconnected_still_selected_when_preferred() -> None:
    """When prefer_ble=True and BLE is registered (disconnected), active_transport() returns BLE.

    ble_ok = ble is not None — registration alone makes BLE eligible even when disconnected.
    send_raw() is responsible for reconnecting before the payload is sent.
    """
    handle = _make_handle(prefer_ble=True)
    mqtt = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble = _make_transport(TransportType.BLE, connected=False)
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)

    active = handle.active_transport()
    assert active is ble


async def test_hybrid_ble_disconnected_reconnects_when_no_mqtt() -> None:
    """With prefer_ble=True and MQTT absent, send_raw() reconnects BLE before sending."""
    handle = _make_handle(prefer_ble=True)
    ble = _make_transport(TransportType.BLE, connected=False)

    async def _do_connect() -> None:
        ble.is_connected = True

    ble.connect.side_effect = _do_connect
    await handle.add_transport(ble)

    await handle.send_raw(b"\xDE\xAD", prefer_ble=True)

    ble.connect.assert_awaited_once()
    ble.send.assert_awaited_once_with(b"\xDE\xAD", iot_id="")


async def test_hybrid_per_call_prefer_ble_override() -> None:
    """send_raw(prefer_ble=True) picks BLE even when the handle default is MQTT."""
    handle = _make_handle(prefer_ble=False)
    mqtt = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble = _make_transport(TransportType.BLE, connected=True)
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)

    await handle.send_raw(b"\x01", prefer_ble=True)

    ble.send.assert_awaited_once()
    mqtt.send.assert_not_awaited()


# ---------------------------------------------------------------------------
# add_ble_device() wiring
# ---------------------------------------------------------------------------


async def test_add_ble_device_wires_transport_when_handle_exists() -> None:
    """add_ble_device() must create and wire a BLETransport when the handle is already registered."""
    client = MammotionClient()

    handle = _make_handle(device_id="Luba-WIRE", device_name="Luba-WIRE")
    await client._device_registry.register(handle)

    fake_ble_device = MagicMock()

    with patch("pymammotion.client.BLETransport") as MockBLETransport:
        mock_transport = MagicMock()
        mock_transport.transport_type = TransportType.BLE
        mock_transport.is_connected = False
        mock_transport.disconnect = AsyncMock()
        mock_transport.add_availability_listener = MagicMock()
        MockBLETransport.return_value = mock_transport

        await client.add_ble_device("Luba-WIRE", fake_ble_device)

    MockBLETransport.assert_called_once()
    mock_transport.set_ble_device.assert_called_once_with(fake_ble_device)
    assert handle._transports.get(TransportType.BLE) is mock_transport


async def test_add_ble_device_stores_in_manager_when_no_handle() -> None:
    """add_ble_device() must store in BLETransportManager when handle is not yet registered."""
    client = MammotionClient()
    fake_ble_device = MagicMock()

    with patch("pymammotion.client.BLETransport") as MockBLETransport:
        await client.add_ble_device("Luba-NOPE", fake_ble_device)
        # No handle registered → BLETransport must NOT be constructed
        MockBLETransport.assert_not_called()

    # Device should be stored in the manager for later use
    assert client._ble_manager._entries.get("Luba-NOPE") is not None


async def test_update_ble_device_updates_live_transport() -> None:
    """update_ble_device() must call set_ble_device() on the wired BLETransport."""
    from pymammotion.transport.ble import BLETransport, BLETransportConfig

    client = MammotionClient()
    handle = _make_handle(device_id="Luba-UPD", device_name="Luba-UPD")
    await client._device_registry.register(handle)

    # Wire a real BLETransport (but with no actual device set yet)
    ble = BLETransport(BLETransportConfig(device_id="Luba-UPD"))
    handle._transports[TransportType.BLE] = ble

    new_device = MagicMock()
    await client.update_ble_device("Luba-UPD", new_device)

    assert ble._ble_device is new_device
