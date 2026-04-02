"""Tests for BLETransport."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BLEDevice

from pymammotion.transport.base import NoBLEAddressKnownError, TransportAvailability, TransportType
from pymammotion.transport.ble import BLETransport, BLETransportConfig


@pytest.fixture
def config() -> BLETransportConfig:
    return BLETransportConfig(device_id="test-device-001", ble_address="AA:BB:CC:DD:EE:FF")


@pytest.fixture
def transport(config: BLETransportConfig) -> BLETransport:
    return BLETransport(config)


def _make_fake_client(*, connected: bool = True) -> MagicMock:
    """Return a MagicMock shaped like a BleakClientWithServiceCache."""
    client = MagicMock()
    client.is_connected = connected
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.disconnect = AsyncMock()
    client.write_gatt_char = AsyncMock()
    return client


def _make_fake_ble_message() -> MagicMock:
    """Return a MagicMock shaped like BleMessage."""
    msg = MagicMock()
    msg.post_custom_data_bytes = AsyncMock()
    msg.parseNotification = MagicMock(return_value=0)
    msg.parseBlufiNotifyData = AsyncMock(return_value=b"\x01\x02")
    msg.clear_notification = MagicMock()
    return msg


# ---------------------------------------------------------------------------
# transport_type
# ---------------------------------------------------------------------------


def test_transport_type(transport: BLETransport) -> None:
    assert transport.transport_type is TransportType.BLE


# ---------------------------------------------------------------------------
# is_connected when no client
# ---------------------------------------------------------------------------


def test_is_connected_false_when_no_client(transport: BLETransport) -> None:
    assert transport.is_connected is False


# ---------------------------------------------------------------------------
# set_ble_device stores the device
# ---------------------------------------------------------------------------


def test_set_ble_device_stores_device(transport: BLETransport) -> None:
    fake_device = MagicMock(spec=BLEDevice)
    transport.set_ble_device(fake_device)
    assert transport._ble_device is fake_device  # noqa: SLF001


# ---------------------------------------------------------------------------
# connect() raises NoBLEAddressKnownError when no BLEDevice set
# ---------------------------------------------------------------------------


async def test_connect_raises_when_no_ble_device(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    with pytest.raises(NoBLEAddressKnownError):
        await transport.connect()


# ---------------------------------------------------------------------------
# connect() creates BleMessage, sends initial sync, starts notify
# ---------------------------------------------------------------------------


async def test_connect_succeeds_with_ble_device(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    fake_client = _make_fake_client()
    fake_msg = _make_fake_ble_message()

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.bluetooth.ble_message.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()

    assert transport.is_connected is True
    fake_client.start_notify.assert_awaited_once()
    # Initial BLE sync must be sent on connect
    fake_msg.post_custom_data_bytes.assert_awaited_once()


# ---------------------------------------------------------------------------
# disconnect() sends final sync, clears client and message
# ---------------------------------------------------------------------------


async def test_disconnect_resets_is_connected(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    fake_client = _make_fake_client()
    fake_msg = _make_fake_ble_message()

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.bluetooth.ble_message.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()
        assert transport.is_connected is True

        await transport.disconnect()

    assert transport.is_connected is False
    assert transport._message is None  # noqa: SLF001
    # sync sent on connect (1) + sync sent on disconnect (2)
    assert fake_msg.post_custom_data_bytes.await_count == 2


# ---------------------------------------------------------------------------
# send() routes through BleMessage.post_custom_data_bytes
# ---------------------------------------------------------------------------


async def test_send_uses_ble_message(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    fake_client = _make_fake_client()
    fake_msg = _make_fake_ble_message()

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.bluetooth.ble_message.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()
        fake_msg.post_custom_data_bytes.reset_mock()

        await transport.send(b"\xDE\xAD\xBE\xEF")

    fake_msg.post_custom_data_bytes.assert_awaited_once_with(b"\xDE\xAD\xBE\xEF")
    # write_gatt_char must NOT be called directly — BleMessage handles it
    fake_client.write_gatt_char.assert_not_awaited()


# ---------------------------------------------------------------------------
# _notification_handler only forwards complete frames (result == 0)
# ---------------------------------------------------------------------------


async def test_notification_handler_forwards_complete_frame(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    received: list[bytes] = []

    async def _on_message(data: bytes) -> None:
        received.append(data)

    transport.on_message = _on_message

    fake_msg = _make_fake_ble_message()
    fake_msg.parseNotification.return_value = 0  # complete frame
    fake_msg.parseBlufiNotifyData.return_value = b"\xAB\xCD"
    transport._message = fake_msg  # noqa: SLF001

    await transport._notification_handler(MagicMock(), bytearray(b"\x00"))  # noqa: SLF001

    assert received == [b"\xAB\xCD"]
    fake_msg.clear_notification.assert_called_once()


async def test_notification_handler_ignores_fragments(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    received: list[bytes] = []

    async def _on_message(data: bytes) -> None:
        received.append(data)

    transport.on_message = _on_message

    fake_msg = _make_fake_ble_message()
    fake_msg.parseNotification.return_value = 1  # fragment — not yet complete
    transport._message = fake_msg  # noqa: SLF001

    await transport._notification_handler(MagicMock(), bytearray(b"\x00"))  # noqa: SLF001

    assert received == []
    fake_msg.parseBlufiNotifyData.assert_not_awaited()


# ---------------------------------------------------------------------------
# availability transitions
# ---------------------------------------------------------------------------


async def test_availability_transitions_on_connect_disconnect(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))
    states: list[TransportAvailability] = []
    transport.add_availability_listener(lambda s: states.append(s))

    fake_client = _make_fake_client()
    fake_msg = _make_fake_ble_message()

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.bluetooth.ble_message.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()
        await transport.disconnect()

    assert TransportAvailability.CONNECTING in states
    assert TransportAvailability.CONNECTED in states
    assert TransportAvailability.DISCONNECTED in states
