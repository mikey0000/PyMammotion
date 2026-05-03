"""Regression test for H3: BLETransport._handle_disconnect must work when
invoked by bleak from a non-asyncio thread.

The bug: the original implementation called ``asyncio.get_running_loop()``
inside ``_handle_disconnect``. That raises ``RuntimeError`` when invoked
from a thread without a running loop, silently dropping the disconnect
notification.

The fix: capture the loop at ``connect()`` time and dispatch via
``call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.transport.ble import BLETransport, BLETransportConfig
from pymammotion.transport.base import TransportAvailability


@pytest.mark.asyncio
async def test_handle_disconnect_from_non_asyncio_thread_fires_listener() -> None:
    """Invoking _handle_disconnect from a worker thread must still fire listeners."""
    transport = BLETransport(BLETransportConfig(device_id="Luba-THREAD-TEST"))

    # Simulate the post-connect state the way connect() would leave it.
    transport._loop = asyncio.get_running_loop()
    transport._availability = TransportAvailability.CONNECTED

    fired = asyncio.Event()
    received_state: list[TransportAvailability] = []

    async def listener(state: TransportAvailability) -> None:
        received_state.append(state)
        fired.set()

    transport.add_availability_listener(listener)

    # Invoke from a non-asyncio thread (no running loop on that thread).
    error_box: list[BaseException] = []

    def worker() -> None:
        try:
            transport._handle_disconnect(MagicMock())
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


@pytest.mark.asyncio
async def test_handle_disconnect_without_loop_does_not_raise() -> None:
    """If the transport never connected, _handle_disconnect must not raise."""
    transport = BLETransport(BLETransportConfig(device_id="Luba-NO-LOOP"))

    listener = AsyncMock()
    transport.add_availability_listener(listener)

    # _loop has never been set; calling from a thread must not raise.
    error_box: list[BaseException] = []

    def worker() -> None:
        try:
            transport._handle_disconnect(MagicMock())
        except BaseException as exc:  # noqa: BLE001
            error_box.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=2.0)

    assert not error_box, f"_handle_disconnect raised: {error_box}"
    # State is updated synchronously even when the loop is missing.
    assert transport.availability is TransportAvailability.DISCONNECTED
