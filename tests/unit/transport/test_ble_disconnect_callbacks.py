"""Disconnect callbacks: off-loop delivery, and callbacks from links we replaced.

Split out of ``test_ble.py``.  bleak decides when a disconnect callback runs and on
which thread, and an ESPHome proxy delivers them over its API connection, so they can
arrive long after ``connect()`` has moved on to another client.  Both halves of that
— the threading and the staleness — are one concern.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from bleak import BLEDevice
import pytest

from pymammotion.transport.base import TransportAvailability
from pymammotion.transport.ble import BLETransport, BLETransportConfig
from tests.unit.transport._fakes import make_ble_device, make_fake_ble_client
from tests.unit.transport._fakes import make_fake_ble_message


@pytest.fixture
def config() -> BLETransportConfig:
    return BLETransportConfig(device_id="test-device-001", ble_address="AA:BB:CC:DD:EE:FF")


# _handle_disconnect — thread safety (disconnect callbacks may run off-loop)


class TestHandleDisconnectThreadSafety:
    async def test_fires_listener_from_non_asyncio_thread(self) -> None:
        """Invoking _handle_disconnect from a worker thread must still fire listeners."""
        transport = BLETransport(BLETransportConfig(device_id="Luba-THREAD-TEST"))
        transport._loop = asyncio.get_running_loop()  # noqa: SLF001 — post-connect state
        transport._availability = TransportAvailability.CONNECTED  # noqa: SLF001

        fired = asyncio.Event()
        received_state: list[TransportAvailability] = []

        async def listener(state: TransportAvailability) -> None:
            received_state.append(state)
            fired.set()

        transport.add_availability_listener(listener)

        error_box: list[BaseException] = []

        def worker() -> None:
            try:
                transport._handle_disconnect(transport._client_generation, MagicMock())  # noqa: SLF001
            except BaseException as exc:  # noqa: BLE001
                error_box.append(exc)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=2.0)

        assert not thread.is_alive(), "worker thread did not exit"
        assert not error_box, f"_handle_disconnect raised: {error_box}"
        await asyncio.wait_for(fired.wait(), timeout=2.0)
        assert received_state == [TransportAvailability.DISCONNECTED]
        assert transport.availability is TransportAvailability.DISCONNECTED

    async def test_does_not_raise_when_never_connected(self) -> None:
        """If the transport never connected (_loop unset), _handle_disconnect must not raise."""
        transport = BLETransport(BLETransportConfig(device_id="Luba-NO-LOOP"))
        transport.add_availability_listener(AsyncMock())

        error_box: list[BaseException] = []

        def worker() -> None:
            try:
                transport._handle_disconnect(transport._client_generation, MagicMock())  # noqa: SLF001
            except BaseException as exc:  # noqa: BLE001
                error_box.append(exc)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=2.0)

        assert not error_box, f"_handle_disconnect raised: {error_box}"
        assert transport.availability is TransportAvailability.DISCONNECTED


async def _run_disconnect_callback(transport: BLETransport, callback: Any) -> None:
    """Fire a disconnect callback and let its handler run to completion.

    ``_handle_disconnect`` hops the loop via ``call_soon_threadsafe`` before creating
    the task, so one turn is needed to create it and a gather to finish it.
    """
    callback(MagicMock())
    await asyncio.sleep(0)
    await asyncio.wait_for(asyncio.gather(*transport._disconnect_tasks), timeout=2.0)  # noqa: SLF001


async def _connect_through_the_purge_path(
    transport: BLETransport, clients: list[MagicMock]
) -> list[Any]:
    """Drive connect() across *clients*, returning each pass's disconnect callback."""
    callbacks: list[Any] = []
    remaining = list(clients)

    async def fake_establish(_cls: Any, _device: Any, _name: Any, callback: Any, **_kwargs: Any) -> MagicMock:
        callbacks.append(callback)
        return remaining.pop(0)

    with (
        patch("pymammotion.transport.ble.establish_connection", new=fake_establish),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
    ):
        await transport.connect()
    return callbacks


@pytest.mark.regression
async def test_a_replaced_links_disconnect_does_not_clear_the_live_client(config: BLETransportConfig) -> None:
    """A late callback from a torn-down link used to null the client that replaced it.

    ``connect()``'s recovery pass drops a client and builds another, and the backend
    decides how late the first one's disconnect callback arrives.  The handler cleared
    whatever was installed at the time, so a callback landing after the new client was
    in place left ``_client``/``_message`` None on a healthy transport — and the next
    characteristic access then raised ``AttributeError`` straight out of ``connect()``,
    past the ``(BleakError, TimeoutError, OSError)`` handler and the documented contract.
    """
    from bleak.exc import BleakError

    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    moved = make_fake_ble_client()
    moved.start_notify = AsyncMock(side_effect=BleakError("Characteristic 0000ff02 was not found"))
    healthy = make_fake_ble_client()
    callbacks = await _connect_through_the_purge_path(transport, [moved, healthy])

    assert len(callbacks) == 2  # the retry registered its own callback
    assert transport.is_connected is True

    await _run_disconnect_callback(transport, callbacks[0])

    assert transport.is_connected is True, "the replaced link's callback cleared the live one"
    assert transport._client is healthy  # noqa: SLF001
    assert transport.availability is TransportAvailability.CONNECTED


async def test_the_live_links_disconnect_is_still_honoured(config: BLETransportConfig) -> None:
    """The generation guard must not deafen the transport to real disconnects."""
    from bleak.exc import BleakError

    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    moved = make_fake_ble_client()
    moved.start_notify = AsyncMock(side_effect=BleakError("Characteristic 0000ff02 was not found"))
    healthy = make_fake_ble_client()
    callbacks = await _connect_through_the_purge_path(transport, [moved, healthy])

    await _run_disconnect_callback(transport, callbacks[-1])

    assert transport._client is None  # noqa: SLF001
    assert transport.availability is TransportAvailability.DISCONNECTED


@pytest.mark.regression
async def test_a_disconnect_seen_during_connect_does_not_clear_the_new_client(
    config: BLETransportConfig,
) -> None:
    """The generation counter cannot see an attempt establish_connection abandoned.

    ``establish_connection`` runs up to ``max_attempts`` internally against **one**
    habluetooth wrapper, and a failed attempt fires the consumer's disconnect callback
    via ``loop.call_soon``.  That callback therefore carries the same generation as the
    attempt that goes on to succeed, so the generation check passes it through and it
    clears the client we just installed.  ``connect()`` owns the client's lifecycle
    while it holds ``_connect_lock``, so a disconnect observed then is not ours to act on.
    """
    transport = BLETransport(config)
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))

    healthy = make_fake_ble_client()

    async def establish_with_an_abandoned_attempt(
        _cls: Any, _device: Any, _name: Any, callback: Any, **_kwargs: Any
    ) -> MagicMock:
        # An internal attempt failed and habluetooth gave up on it, bearing the identity
        # (and so the generation) the successful attempt will also carry.
        callback(MagicMock())
        return healthy

    with (
        patch("pymammotion.transport.ble.establish_connection", new=establish_with_an_abandoned_attempt),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
    ):
        await transport.connect()

    await asyncio.sleep(0)
    if transport._disconnect_tasks:  # noqa: SLF001 — none expected; drain if the guard regressed
        await asyncio.wait_for(asyncio.gather(*transport._disconnect_tasks), timeout=2.0)  # noqa: SLF001

    assert transport.is_connected is True, "an abandoned attempt's callback cleared the live client"
    assert transport._client is healthy  # noqa: SLF001
    assert transport.availability is TransportAvailability.CONNECTED
