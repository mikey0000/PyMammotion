"""Unit tests for pymammotion.transport.ble (BLETransport)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BLEDevice

from pymammotion.transport.base import NoBLEAddressKnownError, TransportAvailability, TransportType
from tests._helpers import block_forever
from pymammotion.transport.ble import BLETransport, BLETransportConfig
from tests.unit.transport._fakes import make_ble_device
from tests.unit.transport._fakes import make_fake_ble_client
from tests.unit.transport._fakes import make_fake_ble_message


@pytest.fixture
def config() -> BLETransportConfig:
    return BLETransportConfig(device_id="test-device-001", ble_address="AA:BB:CC:DD:EE:FF")


@pytest.fixture
def transport(config: BLETransportConfig) -> BLETransport:
    return BLETransport(config)




# transport_type


def test_transport_type(transport: BLETransport) -> None:
    assert transport.transport_type is TransportType.BLE


# is_connected when no client


def test_is_connected_false_when_no_client(transport: BLETransport) -> None:
    assert transport.is_connected is False


# set_ble_device stores the device


def test_set_ble_device_stores_device(transport: BLETransport) -> None:
    fake_device = MagicMock(spec=BLEDevice)
    transport.set_ble_device(fake_device)
    assert transport._ble_device is fake_device  # noqa: SLF001


# connect() raises NoBLEAddressKnownError when no BLEDevice set


async def test_connect_raises_when_no_ble_device(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    with pytest.raises(NoBLEAddressKnownError):
        await transport.connect()


# connect() creates BleMessage, sends initial sync, starts notify


async def test_connect_succeeds_with_ble_device(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    fake_client = make_fake_ble_client()
    fake_msg = make_fake_ble_message()

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.transport.ble.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()

    assert transport.is_connected is True
    fake_client.start_notify.assert_awaited_once()
    # Initial BLE sync must be sent on connect
    fake_msg.post_custom_data_bytes.assert_awaited_once()


# connect() converts a failing initial sync into BLEUnavailableError


async def test_connect_wraps_bleak_error_from_initial_sync(config: BLETransportConfig) -> None:
    """A BleakError from the post-connect sync must surface as BLEUnavailableError.

    connect() documents that it only raises TransportError subclasses.  The final
    _ble_sync() used to be unguarded, so a GATT write failure escaped as a raw
    BleakError and callers catching TransportError aborted instead of falling back.
    """
    from bleak.exc import BleakError

    from pymammotion.transport.base import BLEUnavailableError

    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    fake_client = make_fake_ble_client()
    fake_msg = make_fake_ble_message()
    fake_msg.post_custom_data_bytes = AsyncMock(side_effect=BleakError("GATT Error: Unlikely error"))

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.transport.ble.BleMessage", return_value=fake_msg),
    ):
        with pytest.raises(BLEUnavailableError):
            await transport.connect()

    # The half-open link must be torn down, not left looking connected.
    assert transport.is_connected is False
    assert transport.availability is TransportAvailability.DISCONNECTED
    fake_client.disconnect.assert_awaited()


# disconnect() sends final sync, clears client and message


async def test_disconnect_resets_is_connected(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    fake_client = make_fake_ble_client()
    fake_msg = make_fake_ble_message()

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.transport.ble.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()
        assert transport.is_connected is True

        await transport.disconnect()

    assert transport.is_connected is False
    assert transport._message is None  # noqa: SLF001
    # sync sent on connect only
    assert fake_msg.post_custom_data_bytes.await_count == 1


# send() routes through BleMessage.post_custom_data_bytes


async def test_send_uses_ble_message(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    fake_client = make_fake_ble_client()
    fake_msg = make_fake_ble_message()

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.transport.ble.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()
        fake_msg.post_custom_data_bytes.reset_mock()

        await transport.send(b"\xDE\xAD\xBE\xEF")

    fake_msg.post_custom_data_bytes.assert_awaited_once_with(b"\xDE\xAD\xBE\xEF")
    # write_gatt_char must NOT be called directly — BleMessage handles it
    fake_client.write_gatt_char.assert_not_awaited()


# H4: send() must surface BleakError as TransportError AND mark availability


async def test_send_propagates_bleak_error_and_marks_disconnected(config: BLETransportConfig) -> None:
    """A BleakError raised by post_custom_data_bytes must:

    1. Bubble up as a TransportError to the caller (not get swallowed).
    2. Flip the transport's availability to DISCONNECTED.
    3. Fire registered availability listeners with DISCONNECTED.
    """
    from bleak.exc import BleakError

    from pymammotion.transport.base import TransportError

    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    fake_client = make_fake_ble_client()
    fake_msg = make_fake_ble_message()

    listener_states: list[TransportAvailability] = []

    async def _listener(state: TransportAvailability) -> None:
        listener_states.append(state)

    transport.add_availability_listener(_listener)

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.transport.ble.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()
        fake_msg.post_custom_data_bytes.reset_mock()
        listener_states.clear()  # discard CONNECTING/CONNECTED from connect()
        fake_msg.post_custom_data_bytes.side_effect = BleakError("MTU too small")

        with pytest.raises(TransportError, match="MTU too small"):
            await transport.send(b"\xDE\xAD\xBE\xEF")

    assert transport.availability is TransportAvailability.DISCONNECTED
    assert TransportAvailability.DISCONNECTED in listener_states


async def test_send_raises_when_client_disconnected_during_write(config: BLETransportConfig) -> None:
    """If the client is torn down mid-write (no exception raised), send() must
    still raise TransportError and mark the transport DISCONNECTED.
    """
    from pymammotion.transport.base import TransportError

    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    fake_client = make_fake_ble_client()
    fake_msg = make_fake_ble_message()

    async def _silent_disconnect(_: bytes) -> None:
        # Simulate a write that returns normally but tears down the client
        # underneath (e.g. concurrent disconnect callback).
        fake_client.is_connected = False

    fake_msg.post_custom_data_bytes.side_effect = _silent_disconnect

    listener_states: list[TransportAvailability] = []

    async def _listener(state: TransportAvailability) -> None:
        listener_states.append(state)

    transport.add_availability_listener(_listener)

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.transport.ble.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()
        listener_states.clear()

        with pytest.raises(TransportError, match="client disconnected during write"):
            await transport.send(b"\xDE\xAD\xBE\xEF")

    assert transport.availability is TransportAvailability.DISCONNECTED
    assert TransportAvailability.DISCONNECTED in listener_states


# _notification_handler only forwards complete frames (result == 0)


async def test_notification_handler_forwards_complete_frame(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    received: list[bytes] = []

    async def _on_message(data: bytes) -> None:
        received.append(data)

    transport.on_message = _on_message

    fake_msg = make_fake_ble_message()
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

    fake_msg = make_fake_ble_message()
    fake_msg.parseNotification.return_value = 1  # fragment — not yet complete
    transport._message = fake_msg  # noqa: SLF001

    await transport._notification_handler(MagicMock(), bytearray(b"\x00"))  # noqa: SLF001

    assert received == []
    fake_msg.parseBlufiNotifyData.assert_not_awaited()


# availability transitions


async def test_availability_transitions_on_connect_disconnect(config: BLETransportConfig) -> None:
    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))
    states: list[TransportAvailability] = []
    transport.add_availability_listener(lambda s: states.append(s))

    fake_client = make_fake_ble_client()
    fake_msg = make_fake_ble_message()

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.transport.ble.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()
        await transport.disconnect()

    assert TransportAvailability.CONNECTING in states
    assert TransportAvailability.CONNECTED in states
    assert TransportAvailability.DISCONNECTED in states


# Self-managed scanning


async def test_self_managed_scanning_discovers_device() -> None:
    """When self_managed_scanning=True and no device cached, connect() runs a scan."""
    config = BLETransportConfig(
        device_id="self-managed",
        ble_address="AA:BB:CC:DD:EE:FF",
        self_managed_scanning=True,
    )
    transport = BLETransport(config)

    discovered = make_ble_device("AA:BB:CC:DD:EE:FF")
    fake_client = make_fake_ble_client()
    fake_msg = make_fake_ble_message()
    with (
        patch(
            "pymammotion.transport.ble.BleakScanner.find_device_by_address",
            new=AsyncMock(return_value=discovered),
        ),
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.transport.ble.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()

    assert transport._ble_device is discovered  # noqa: SLF001
    assert transport.is_connected is True


async def test_self_managed_scanning_off_raises_when_no_device() -> None:
    """When self_managed_scanning=False (default) and no device cached, connect() raises."""
    config = BLETransportConfig(device_id="ha-managed", ble_address="AA:BB:CC:DD:EE:FF")
    transport = BLETransport(config)

    scan = AsyncMock()
    with patch("pymammotion.transport.ble.BleakScanner.find_device_by_address", new=scan):
        with pytest.raises(NoBLEAddressKnownError):
            await transport.connect()

    scan.assert_not_awaited()  # never tried to scan in HA-managed mode


async def test_self_managed_scanning_raises_when_scan_finds_nothing() -> None:
    """If the scan finds no device, connect() raises NoBLEAddressKnownError."""
    config = BLETransportConfig(
        device_id="self-managed",
        ble_address="AA:BB:CC:DD:EE:FF",
        self_managed_scanning=True,
    )
    transport = BLETransport(config)

    with patch(
        "pymammotion.transport.ble.BleakScanner.find_device_by_address",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(NoBLEAddressKnownError):
            await transport.connect()


@pytest.mark.regression
async def test_an_unexpected_exception_does_not_strand_availability_at_connecting(
    config: BLETransportConfig,
) -> None:
    """connect() announced CONNECTING and only cleared it on the paths it anticipated.

    Anything outside ``(BleakError, TimeoutError, OSError)`` escaped with the
    announcement still standing, and nothing else ever retracts it — so
    ``DeviceState`` reported the mower as connecting for the life of the process.
    """
    transport = BLETransport(config)
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))

    client = make_fake_ble_client()
    client.start_notify = AsyncMock(side_effect=RuntimeError("backend bug"))

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=client)),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
        pytest.raises(RuntimeError),  # unchanged: connect() must not swallow it
    ):
        await transport.connect()

    assert transport.availability is TransportAvailability.DISCONNECTED


@pytest.mark.regression
async def test_cancelling_a_connect_leaves_the_transport_disconnected(config: BLETransportConfig) -> None:
    """A cancelled connect left CONNECTING standing for the same reason.

    DeviceHandle cancels in-flight connects on stop, so this is an ordinary exit,
    not an exotic one.
    """
    transport = BLETransport(config)
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))

    establishing = asyncio.Event()

    async def hang(*_args: object, **_kwargs: object) -> None:
        establishing.set()
        await block_forever()

    with patch("pymammotion.transport.ble.establish_connection", new=hang):
        task = asyncio.create_task(transport.connect())
        await asyncio.wait_for(establishing.wait(), timeout=2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert transport.availability is TransportAvailability.DISCONNECTED


async def test_a_second_connect_reuses_the_link_the_first_established(config: BLETransportConfig) -> None:
    """Two callers racing connect() must produce one link, not two.

    The second waits on _connect_lock, and by the time it gets in the first has
    already connected — establishing again would strand the first client and burn
    a proxy connection slot.
    """
    transport = BLETransport(config)
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))

    first_inside = asyncio.Event()
    let_it_finish = asyncio.Event()
    client = make_fake_ble_client()
    attempts = 0

    async def gated_establish(*_args: object, **_kwargs: object) -> MagicMock:
        nonlocal attempts
        attempts += 1
        first_inside.set()
        await let_it_finish.wait()
        return client

    with (
        patch("pymammotion.transport.ble.establish_connection", new=gated_establish),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
    ):
        first = asyncio.create_task(transport.connect())
        await asyncio.wait_for(first_inside.wait(), timeout=2.0)

        second = asyncio.create_task(transport.connect())
        await asyncio.sleep(0)  # let the second reach the lock and block there

        let_it_finish.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=2.0)

    assert attempts == 1, "the second caller established a second link"
    assert transport.is_connected is True
    assert transport._client is client  # noqa: SLF001


async def test_self_managed_scanning_survives_a_failing_scan() -> None:
    """A scan that raises leaves no device, so connect() reports the address problem.

    BleakScanner raises on adapter trouble as readily as it returns None, and letting
    a BleakError out of connect() here would break its documented contract.
    """
    from bleak.exc import BleakError

    config = BLETransportConfig(
        device_id="self-managed",
        ble_address="AA:BB:CC:DD:EE:FF",
        self_managed_scanning=True,
    )
    transport = BLETransport(config)

    with (
        patch(
            "pymammotion.transport.ble.BleakScanner.find_device_by_address",
            new=AsyncMock(side_effect=BleakError("no adapter")),
        ),
        pytest.raises(NoBLEAddressKnownError),
    ):
        await transport.connect()

    assert transport.ble_address is None


async def test_self_managed_scanning_without_an_address_does_not_scan() -> None:
    """self_managed_scanning with no ble_address is a config error, not a scan."""
    config = BLETransportConfig(device_id="self-managed", self_managed_scanning=True)
    transport = BLETransport(config)
    scan = AsyncMock()

    with (
        patch("pymammotion.transport.ble.BleakScanner.find_device_by_address", new=scan),
        pytest.raises(NoBLEAddressKnownError),
    ):
        await transport.connect()

    scan.assert_not_awaited()
