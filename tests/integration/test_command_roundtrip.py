"""Mock integration tests exercising the full DeviceHandle → broker → transport stack."""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.data.model.hash_list import HashList
from pymammotion.device.handle import DeviceHandle
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_queue import Priority
from pymammotion.messaging.map_saga import MapFetchSaga
from pymammotion.transport.base import CommandTimeoutError, SagaFailedError
from pymammotion.state.device_state import DeviceConnectionState, TransportAvailability
from pymammotion.transport.base import TransportType


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_device() -> MagicMock:
    """Return a MagicMock shaped like a MowingDevice."""
    device = MagicMock()
    device.online = True
    device.enabled = True
    device.report_data.dev.battery_val = 75
    device.report_data.dev.sys_status = "idle"
    device.report_data.work.knife_height = 40
    return device


def _make_transport(transport_type: TransportType, *, connected: bool = True) -> MagicMock:
    """Return a MagicMock shaped like a Transport."""
    transport = MagicMock()
    transport.transport_type = transport_type
    transport.is_connected = connected
    transport.send = AsyncMock()
    transport.disconnect = AsyncMock()
    transport.on_message = None
    return transport


def _make_handle(
    device_id: str = "dev-001",
    device_name: str = "Mower One",
    *,
    mqtt_transport: MagicMock | None = None,
    ble_transport: MagicMock | None = None,
) -> DeviceHandle:
    """Build a DeviceHandle with a mock MowingDevice."""
    return DeviceHandle(
        device_id=device_id,
        device_name=device_name,
        initial_device=_make_device(),
        mqtt_transport=mqtt_transport,
        ble_transport=ble_transport,
    )


def _make_mock_response(field_name: str) -> MagicMock:
    """Return a MagicMock that looks like a LubaMsg with the given payload field set."""
    msg = MagicMock()
    return msg


def _make_command_builder() -> MagicMock:
    """Return a mock command builder returning dummy bytes for every method."""
    builder = MagicMock()
    builder.get_area_name_list.return_value = b"area_name_cmd"
    builder.get_all_boundary_hash_list.return_value = b"hash_list_cmd"
    builder.get_hash_response.return_value = b"hash_response_cmd"
    return builder


def _make_hash_list_ack_response(
    total_frame: int = 1,
    current_frame: int = 1,
    data_couple: list[int] | None = None,
) -> MagicMock:
    """Return a MagicMock resembling a LubaMsg with toapp_gethash_ack populated."""
    ack = MagicMock()
    ack.pver = 1
    ack.sub_cmd = 1
    ack.total_frame = total_frame
    ack.current_frame = current_frame
    ack.data_hash = 0
    ack.hash_len = len(data_couple or [])
    ack.result = 0
    ack.data_couple = data_couple or []

    nav = MagicMock()
    nav.toapp_gethash_ack = ack

    msg = MagicMock()
    msg.nav = nav
    return msg


def _make_area_name_response(names: list[tuple[int, str]]) -> MagicMock:
    """Return a MagicMock resembling a LubaMsg with toapp_all_hash_name populated."""
    hashnames = []
    for h, n in names:
        item = MagicMock()
        item.hash = h
        item.name = n
        hashnames.append(item)

    area_name_msg = MagicMock()
    area_name_msg.hashnames = hashnames

    nav = MagicMock()
    nav.toapp_all_hash_name = area_name_msg

    msg = MagicMock()
    msg.nav = nav
    return msg


# ---------------------------------------------------------------------------
# Test 1: Happy-path MQTT command round-trip
# ---------------------------------------------------------------------------


async def test_happy_path_mqtt_command_round_trip() -> None:
    """send_command resolves successfully when broker.on_message delivers the expected field."""
    mqtt_transport = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    handle = _make_handle(mqtt_transport=mqtt_transport)

    broker = handle.broker
    mock_response = _make_mock_response("toapp_gethash_ack")

    # Capture the bytes sent so we can verify send() was called
    sent_payloads: list[bytes] = []

    async def fake_send(payload: bytes, iot_id: str = "") -> None:
        sent_payloads.append(payload)
        # Simulate the device responding after a small delay
        async def _deliver() -> None:
            await asyncio.sleep(0.05)
            await broker.on_message(mock_response)

        asyncio.get_running_loop().create_task(_deliver())

    mqtt_transport.send.side_effect = fake_send

    handle.queue.start()
    try:
        with patch("betterproto2.which_one_of", return_value=("toapp_gethash_ack", MagicMock())):
            await handle.send_command(b"\x01\x02\x03", "toapp_gethash_ack", priority=Priority.NORMAL)
            # Give the queue processor time to execute the enqueued work
            await asyncio.sleep(0.3)
    finally:
        await handle.stop()

    assert len(sent_payloads) == 1
    assert sent_payloads[0] == b"\x01\x02\x03"


# ---------------------------------------------------------------------------
# Test 2: Command timeout raises CommandTimeoutError
# ---------------------------------------------------------------------------


async def test_command_timeout_raises_command_timeout_error() -> None:
    """When transport never delivers a response, CommandTimeoutError is raised after retries."""
    mqtt_transport = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    # send() just silently drops the payload — no on_message callback is ever delivered
    mqtt_transport.send = AsyncMock()

    broker = DeviceMessageBroker()

    errors: list[Exception] = []

    async def _work() -> None:
        try:
            await broker.send_and_wait(
                send_fn=lambda: mqtt_transport.send(b"\xde\xad\xbe\xef"),
                expected_field="toapp_gethash_ack",
                send_timeout=0.05,
                retries=1,
            )
        except CommandTimeoutError as exc:
            errors.append(exc)

    await _work()

    assert len(errors) == 1
    assert isinstance(errors[0], CommandTimeoutError)
    assert errors[0].expected_field == "toapp_gethash_ack"
    assert errors[0].attempts == 1


# ---------------------------------------------------------------------------
# Test 3: BLE preferred over MQTT
# ---------------------------------------------------------------------------


async def test_ble_preferred_when_connected() -> None:
    """With both connected, BLE wins unconditionally (lower latency, bypasses cloud throttle)."""
    mqtt_transport = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble_transport = _make_transport(TransportType.BLE, connected=True)

    handle = _make_handle(mqtt_transport=mqtt_transport)
    await handle.add_transport(ble_transport)

    broker = handle.broker
    mock_response = _make_mock_response("toapp_gethash_ack")

    async def ble_fake_send(payload: bytes, iot_id: str = "") -> None:  # noqa: ARG001
        async def _deliver() -> None:
            await asyncio.sleep(0.05)
            await broker.on_message(mock_response)

        asyncio.get_running_loop().create_task(_deliver())

    ble_transport.send.side_effect = ble_fake_send

    handle.queue.start()
    try:
        with patch("betterproto2.which_one_of", return_value=("toapp_gethash_ack", MagicMock())):
            await handle.send_command(b"\xca\xfe", "toapp_gethash_ack", priority=Priority.NORMAL)
            await asyncio.sleep(0.3)
    finally:
        await handle.stop()

    ble_transport.send.assert_awaited_once()
    mqtt_transport.send.assert_not_awaited()


async def test_ble_used_when_prefer_ble_set() -> None:
    """When prefer_ble=True, BLE is chosen over MQTT even when both are connected."""
    from pymammotion.device.handle import DeviceHandle

    mqtt_transport = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble_transport = _make_transport(TransportType.BLE, connected=True)

    handle = DeviceHandle(
        device_id="dev-ble",
        device_name="BLE-Preferred",
        initial_device=_make_device(),
        prefer_ble=True,
    )
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    broker = handle.broker
    mock_response = _make_mock_response("toapp_gethash_ack")

    async def ble_fake_send(payload: bytes) -> None:
        async def _deliver() -> None:
            await asyncio.sleep(0.05)
            await broker.on_message(mock_response)

        asyncio.get_running_loop().create_task(_deliver())

    ble_transport.send.side_effect = ble_fake_send

    handle.queue.start()
    try:
        with patch("betterproto2.which_one_of", return_value=("toapp_gethash_ack", MagicMock())):
            await handle.send_command(b"\xca\xfe", "toapp_gethash_ack", priority=Priority.NORMAL)
            await asyncio.sleep(0.3)
    finally:
        await handle.stop()

    ble_transport.send.assert_awaited_once()
    mqtt_transport.send.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 4: Saga blocks normal commands with skip_if_saga_active=True
# ---------------------------------------------------------------------------


async def test_saga_blocks_normal_commands() -> None:
    """NORMAL commands with skip_if_saga_active=True are dropped while a saga runs."""
    from pymammotion.messaging.command_queue import DeviceCommandQueue

    queue = DeviceCommandQueue()
    executed_normal: list[str] = []

    # Manually mark the exclusive slot as active before enqueueing the NORMAL items.
    # This simulates the state that exists while an EXCLUSIVE saga work item is running.
    queue._exclusive_active.clear()  # clear = saga active

    # Enqueue NORMAL commands while the saga slot is held
    for i in range(3):
        label = f"cmd-{i}"

        async def _normal_work(lbl: str = label) -> None:
            executed_normal.append(lbl)

        await queue.enqueue(_normal_work, priority=Priority.NORMAL, skip_if_saga_active=True)

    # All three items should have been silently dropped — queue should still be empty
    assert queue._queue.qsize() == 0
    assert len(executed_normal) == 0


# ---------------------------------------------------------------------------
# Test 5: update_availability propagates to snapshot
# ---------------------------------------------------------------------------


async def test_device_availability_propagates_to_snapshot() -> None:
    """update_availability(BLE, CONNECTED) must change snapshot.connection_state to CONNECTED."""
    handle = _make_handle()

    # Initially no transport is connected → state should not be CONNECTED
    assert handle.snapshot.connection_state != DeviceConnectionState.CONNECTED

    # Give the event loop a chance to process the state_changed task that will be created
    loop = asyncio.get_running_loop()
    handle.update_availability(TransportType.BLE, TransportAvailability.CONNECTED)
    await asyncio.sleep(0)  # yield to event loop

    assert handle.availability.ble == TransportAvailability.CONNECTED
    assert handle.availability.is_available is True
    assert handle.snapshot.connection_state == DeviceConnectionState.CONNECTED


# ---------------------------------------------------------------------------
# Test 6: MapFetchSaga caches area names across two runs
# ---------------------------------------------------------------------------


async def test_map_saga_refetches_area_names_on_each_run() -> None:
    """Area name command is called on each MapFetchSaga.execute() call (no cross-run caching)."""
    from unittest.mock import patch

    builder = _make_command_builder()

    area_response = _make_area_name_response([(1, "Front Lawn"), (2, "Back Yard")])
    # sub_cmd=1 (default) → missing_hashlist(0) returns [] so step 4 is skipped
    hash_response = _make_hash_list_ack_response(total_frame=1, current_frame=1, data_couple=[])

    mock_broker = AsyncMock(spec=DeviceMessageBroker)
    mock_broker.send_and_wait.return_value = area_response

    _active: list[Any] = []

    class _Ctx:
        def __init__(self, cb: Any) -> None:
            self._cb = cb

        def __enter__(self) -> "_Ctx":
            _active.append(self._cb)
            return self

        def __exit__(self, *args: Any) -> None:
            if _active and _active[-1] is self._cb:
                _active.pop()

    mock_broker.subscribe_unsolicited.side_effect = lambda cb: _Ctx(cb)

    async def send_command(cmd: bytes) -> None:
        if _active:
            await _active[-1](hash_response)

    def _which_hash(obj: Any, group: str) -> tuple[str, Any]:
        if group == "LubaSubMsg":
            return ("nav", obj.nav)
        return ("toapp_gethash_ack", obj.toapp_gethash_ack)

    with patch("betterproto2.which_one_of", side_effect=_which_hash):
        _map = HashList()
        saga = MapFetchSaga(
            device_id="dev-006",
            device_name="Luba2Test",
            is_luba1=False,
            command_builder=builder,
            send_command=send_command,
            get_map=lambda: _map,
        )

        # First run
        await saga.execute(mock_broker)
        assert saga.result is not None
        assert len(saga.result.area_name) == 2

        # Reset result to simulate a second run on the same saga instance
        saga.result = None

        # Second run — area names are re-fetched (no caching across runs)
        await saga.execute(mock_broker)
        assert saga.result is not None

    # send_and_wait called once per execute() call = 2 total
    area_name_calls = [
        call for call in mock_broker.send_and_wait.call_args_list
        if call[1].get("expected_field") == "toapp_all_hash_name"
    ]
    assert len(area_name_calls) == 2, (
        f"Expected area name command called once per run (2 total), got {len(area_name_calls)}"
    )
