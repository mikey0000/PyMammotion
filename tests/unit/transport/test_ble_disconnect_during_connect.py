"""A disconnect that lands while ``connect()`` is still establishing the link.

The host detaches BLE (Home Assistant's Bluetooth switch) while an advertisement-driven
connect is in flight on a proxy.  ``establish_connection`` cannot be interrupted, so the
link it returns must be dropped instead of kept on a transport nobody holds.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pymammotion.transport.base import BLEUnavailableError, TransportAvailability
from pymammotion.transport.ble import BLETransport, BLETransportConfig
from tests.unit.transport._fakes import make_ble_device, make_fake_ble_client, make_fake_ble_message


def _transport() -> BLETransport:
    transport = BLETransport(BLETransportConfig(device_id="Luba-VS123456", ble_address="AA:BB:CC:DD:EE:FF"))
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))
    return transport


async def _connect_with_disconnect_mid_establish(transport: BLETransport, client: MagicMock) -> None:
    """Run connect(); call disconnect() while establish_connection is still pending."""
    establishing = asyncio.Event()
    release = asyncio.Event()

    async def fake_establish(*_args: Any, **_kwargs: Any) -> MagicMock:
        establishing.set()
        await release.wait()
        return client

    with (
        patch("pymammotion.transport.ble.establish_connection", new=fake_establish),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
    ):
        connecting = asyncio.create_task(transport.connect())
        await asyncio.wait_for(establishing.wait(), timeout=2.0)
        await asyncio.wait_for(transport.disconnect(), timeout=2.0)
        release.set()
        await asyncio.wait_for(connecting, timeout=2.0)


@pytest.mark.regression
async def test_a_link_established_after_disconnect_is_dropped() -> None:
    """The link came up after disconnect() had returned and stayed open on the proxy.

    disconnect() saw no client yet, so it had nothing to close; connect() then stored
    the client it was handed, holding a proxy slot on a transport the host had let go.
    """
    transport = _transport()
    client = make_fake_ble_client()

    with pytest.raises(BLEUnavailableError, match="disconnected while connecting"):
        await _connect_with_disconnect_mid_establish(transport, client)

    client.disconnect.assert_awaited()
    client.start_notify.assert_not_awaited()
    assert not transport.is_connected
    assert transport.availability is TransportAvailability.DISCONNECTED


@pytest.mark.regression
async def test_an_abandoned_connect_is_not_a_connect_failure() -> None:
    """Dropping the link on purpose must not count toward the failure cooldown."""
    transport = _transport()

    with pytest.raises(BLEUnavailableError):
        await _connect_with_disconnect_mid_establish(transport, make_fake_ble_client())

    assert transport.is_usable


async def test_a_connect_after_the_disconnect_still_connects() -> None:
    """Only connects already under way are abandoned; a fresh one proceeds."""
    transport = _transport()
    with pytest.raises(BLEUnavailableError):
        await _connect_with_disconnect_mid_establish(transport, make_fake_ble_client())
    client = make_fake_ble_client()

    async def fake_establish(*_args: Any, **_kwargs: Any) -> MagicMock:
        return client

    with (
        patch("pymammotion.transport.ble.establish_connection", new=fake_establish),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
    ):
        await asyncio.wait_for(transport.connect(), timeout=2.0)

    assert transport.is_connected
    assert transport.availability is TransportAvailability.CONNECTED
