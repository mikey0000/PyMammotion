"""A disconnect that lands while ``connect()`` is still setting the link up.

The host detaches BLE (Home Assistant's Bluetooth switch) while an advertisement-driven
connect is in flight on a proxy.  ``establish_connection`` cannot be interrupted, so the
link it returns must be dropped instead of kept on a transport nobody holds.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import contextlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pymammotion.transport import ble as ble_module
from pymammotion.transport.base import BLEUnavailableError, TransportAvailability
from pymammotion.transport.ble import BLETransport, BLETransportConfig
from tests.unit.transport._fakes import make_ble_device, make_fake_ble_client, make_fake_ble_message

_WAIT = 2.0


def _transport() -> BLETransport:
    transport = BLETransport(BLETransportConfig(device_id="Luba-VS123456", ble_address="AA:BB:CC:DD:EE:FF"))
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))
    return transport


class _Gate:
    """Hold one connect step open until released, and say when it was reached."""

    def __init__(self) -> None:
        self.reached = asyncio.Event()
        self.release = asyncio.Event()

    async def hold(self, *_args: Any, **_kwargs: Any) -> None:
        self.reached.set()
        await self.release.wait()


@contextlib.asynccontextmanager
async def _fake_link(
    client: MagicMock, message: MagicMock, *, hold_establish: _Gate | None = None
) -> AsyncIterator[MagicMock]:
    """Patch the connector to hand out *client*; yields the establish_connection mock."""

    async def fake_establish(*_args: Any, **_kwargs: Any) -> MagicMock:
        if hold_establish is not None:
            await hold_establish.hold()
        return client

    with (
        patch.object(ble_module, "establish_connection", side_effect=fake_establish) as establish,
        patch.object(ble_module, "BleMessage", return_value=message),
    ):
        yield establish


def _record_availability(transport: BLETransport) -> list[TransportAvailability]:
    seen: list[TransportAvailability] = []

    async def listener(state: TransportAvailability) -> None:
        seen.append(state)

    transport.add_availability_listener(listener)
    return seen


async def _disconnect_while_held(transport: BLETransport, gate: _Gate, connecting: asyncio.Task[None]) -> None:
    await asyncio.wait_for(gate.reached.wait(), timeout=_WAIT)
    await asyncio.wait_for(transport.disconnect(), timeout=_WAIT)
    gate.release.set()
    with pytest.raises(BLEUnavailableError, match="disconnected while connecting"):
        await asyncio.wait_for(connecting, timeout=_WAIT)


@pytest.mark.regression
@pytest.mark.parametrize(
    ("step", "subscribed", "announced_connected"),
    [
        pytest.param("establishing", False, False, id="establishing"),
        pytest.param("notify setup", True, False, id="notify-setup"),
        pytest.param("initial sync", True, True, id="initial-sync"),
    ],
)
async def test_a_link_set_up_after_disconnect_is_dropped(
    step: str, subscribed: bool, announced_connected: bool
) -> None:
    """The link came up after disconnect() had returned and stayed open on the proxy.

    disconnect() saw no client yet, so it had nothing to close; connect() then stored
    the client it was handed, holding a proxy slot on a transport the host had let go.
    Setup also stops at the next step: no notify subscription on a link already
    abandoned, and no CONNECTED for one abandoned during the subscription.
    """
    transport = _transport()
    seen = _record_availability(transport)
    client = make_fake_ble_client()
    message = make_fake_ble_message()
    gate = _Gate()
    client.start_notify.side_effect = gate.hold if step == "notify setup" else None
    message.post_custom_data_bytes.side_effect = gate.hold if step == "initial sync" else None

    async with _fake_link(client, message, hold_establish=gate if step == "establishing" else None):
        await _disconnect_while_held(transport, gate, asyncio.create_task(transport.connect()))

    client.disconnect.assert_awaited()
    assert client.start_notify.await_count == int(subscribed)
    assert (TransportAvailability.CONNECTED in seen) is announced_connected
    assert not transport.is_connected
    assert transport.availability is TransportAvailability.DISCONNECTED
    assert seen[-1] is TransportAvailability.DISCONNECTED


@pytest.mark.regression
async def test_a_connect_queued_behind_the_disconnected_one_does_not_connect() -> None:
    """A connect waiting on the lock when disconnect() ran must not start a fresh link."""
    transport = _transport()
    gate = _Gate()

    async with _fake_link(make_fake_ble_client(), make_fake_ble_message(), hold_establish=gate) as establish:
        first = asyncio.create_task(transport.connect())
        await asyncio.wait_for(gate.reached.wait(), timeout=_WAIT)
        queued = asyncio.create_task(transport.connect())
        await asyncio.sleep(0)
        await _disconnect_while_held(transport, gate, first)
        with pytest.raises(BLEUnavailableError, match="disconnected while connecting"):
            await asyncio.wait_for(queued, timeout=_WAIT)

    assert establish.await_count == 1
    assert not transport.is_connected


@pytest.mark.regression
async def test_an_abandoned_connect_is_not_a_connect_failure() -> None:
    """Dropping the link on purpose must not count toward the failure cooldown."""
    transport = _transport()
    gate = _Gate()

    async with _fake_link(make_fake_ble_client(), make_fake_ble_message(), hold_establish=gate):
        await _disconnect_while_held(transport, gate, asyncio.create_task(transport.connect()))

    # One failure never trips the cooldown on its own, so the counter is the only witness.
    assert transport._consecutive_failures == 0  # noqa: SLF001


async def test_a_connect_after_the_disconnect_still_connects() -> None:
    """Only connects already under way are abandoned; a fresh one proceeds."""
    transport = _transport()
    gate = _Gate()
    async with _fake_link(make_fake_ble_client(), make_fake_ble_message(), hold_establish=gate):
        await _disconnect_while_held(transport, gate, asyncio.create_task(transport.connect()))

    async with _fake_link(make_fake_ble_client(), make_fake_ble_message()):
        await asyncio.wait_for(transport.connect(), timeout=_WAIT)

    assert transport.is_connected
    assert transport.availability is TransportAvailability.CONNECTED
