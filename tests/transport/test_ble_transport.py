"""Tests for BLETransport."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BLEDevice

from pymammotion.transport.base import NoBLEAddressKnownError, TransportType
from pymammotion.transport.ble import BLETransport, BLETransportConfig


@pytest.fixture
def config() -> BLETransportConfig:
    return BLETransportConfig(device_id="test-device-001", ble_address="AA:BB:CC:DD:EE:FF")


@pytest.fixture
def transport(config: BLETransportConfig) -> BLETransport:
    return BLETransport(config)


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


@pytest.mark.asyncio
async def test_connect_raises_when_no_ble_device(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    # Deliberately do NOT call set_ble_device()
    with pytest.raises(NoBLEAddressKnownError):
        await transport.connect()


# ---------------------------------------------------------------------------
# connect() succeeds when BLEDevice is provided (mocked establish_connection)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_succeeds_with_ble_device(config: BLETransportConfig) -> None:
    from unittest.mock import patch

    transport = BLETransport(config)
    fake_device = MagicMock(spec=BLEDevice)
    transport.set_ble_device(fake_device)

    fake_client = MagicMock()
    fake_client.is_connected = True
    fake_client.start_notify = AsyncMock()

    with patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)):
        await transport.connect()

    assert transport.is_connected is True


# ---------------------------------------------------------------------------
# disconnect() resets is_connected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_resets_is_connected(config: BLETransportConfig) -> None:
    from unittest.mock import patch

    transport = BLETransport(config)
    fake_device = MagicMock(spec=BLEDevice)
    transport.set_ble_device(fake_device)

    fake_client = MagicMock()
    fake_client.is_connected = True
    fake_client.start_notify = AsyncMock()
    fake_client.disconnect = AsyncMock()

    with patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)):
        await transport.connect()
        assert transport.is_connected is True

    # Simulate bleak reporting disconnected after disconnect() call
    fake_client.is_connected = False
    await transport.disconnect()
    assert transport.is_connected is False
