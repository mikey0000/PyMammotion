"""Mock integration tests exercising the full DeviceHandle → broker → transport stack."""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.device.handle import DeviceHandle
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_queue import Priority
from pymammotion.transport.base import CommandTimeoutError
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
    transport.is_rate_limited = False
    transport.is_send_blocked = MagicMock(return_value=False)
    transport.seconds_until_send_available = MagicMock(return_value=0.0)
    transport.last_send_monotonic = 0.0  # 0.0 = never sent (matches Transport base default)
    transport.send = AsyncMock()
    transport.send_heartbeat = AsyncMock()
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


# ---------------------------------------------------------------------------
# Test 1: Happy-path MQTT command round-trip
# ---------------------------------------------------------------------------


async def test_happy_path_mqtt_command_round_trip() -> None:
    """send_raw sends the payload over the sole (MQTT) transport."""
    mqtt_transport = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    handle = _make_handle(mqtt_transport=mqtt_transport)

    # Capture the bytes sent so we can verify send() was called
    sent_payloads: list[bytes] = []

    async def fake_send(payload: bytes, iot_id: str = "", firmware_version: str = "") -> None:
        sent_payloads.append(payload)

    mqtt_transport.send.side_effect = fake_send

    try:
        await handle.send_raw(b"\x01\x02\x03")
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

    try:
        await handle.send_raw(b"\xca\xfe")
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

    try:
        await handle.send_raw(b"\xca\xfe", prefer_ble=True)
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
# MQTT sync prepend — debounced against the last *sync*, not the last command,
# because the device's ~10 s sync window is only reset by a sync (ordinary
# command traffic does not keep it synced).  See _MQTT_SYNC_INTERVAL.
# ---------------------------------------------------------------------------


async def test_mqtt_sync_sent_before_payload_when_sync_window_lapsed() -> None:
    """_send_marked must prepend a sync (awaited, before the payload) once it's been
    longer than _MQTT_SYNC_INTERVAL since the last sync to this transport."""
    import time

    from pymammotion.device.handle import _MQTT_SYNC_INTERVAL

    mqtt_transport = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    handle = _make_handle(mqtt_transport=mqtt_transport)

    # Last sync just outside the window — a command burst keeps last_send fresh, but the
    # device still desyncs because only a *sync* resets its timer.
    handle._last_mqtt_sync_monotonic[TransportType.CLOUD_ALIYUN] = (  # noqa: SLF001
        time.monotonic() - (_MQTT_SYNC_INTERVAL + 1.0)
    )
    mqtt_transport.last_send_monotonic = time.monotonic() - 1  # recent command — must NOT suppress the sync

    sent: list[bytes] = []

    async def capture_send(payload: bytes, iot_id: str = "", firmware_version: str = "") -> None:  # noqa: ARG001
        sent.append(payload)

    mqtt_transport.send.side_effect = capture_send

    await handle._send_marked(mqtt_transport, b"\xde\xad")  # noqa: SLF001

    # Sync goes through send_heartbeat (quota-exempt path); payload goes through send.
    mqtt_transport.send_heartbeat.assert_awaited_once()
    sync_payload = mqtt_transport.send_heartbeat.call_args[0][0]
    assert sync_payload != b"\xde\xad", "Heartbeat arg should be the sync, not the payload"
    assert len(sent) == 1, f"Expected only payload via send, got {len(sent)}: {sent}"
    assert sent[0] == b"\xde\xad", "send() should carry the actual payload"
    # The sync timestamp is advanced so the next send within the window won't re-sync.
    assert handle._last_mqtt_sync_monotonic[TransportType.CLOUD_ALIYUN] > 0.0  # noqa: SLF001


async def test_no_mqtt_sync_when_synced_recently() -> None:
    """_send_marked must NOT prepend a sync when the last sync was within _MQTT_SYNC_INTERVAL,
    even if many commands have been sent in between."""
    import time

    mqtt_transport = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    handle = _make_handle(mqtt_transport=mqtt_transport)

    # Synced 1 s ago — well within the window — so no fresh sync regardless of command volume.
    handle._last_mqtt_sync_monotonic[TransportType.CLOUD_ALIYUN] = time.monotonic() - 1.0  # noqa: SLF001

    sent: list[bytes] = []

    async def capture_send(payload: bytes, iot_id: str = "", firmware_version: str = "") -> None:  # noqa: ARG001
        sent.append(payload)

    mqtt_transport.send.side_effect = capture_send

    await handle._send_marked(mqtt_transport, b"\xca\xfe")  # noqa: SLF001

    mqtt_transport.send_heartbeat.assert_not_awaited()
    assert len(sent) == 1, f"Expected only payload (1 send), got {len(sent)}: {sent}"
    assert sent[0] == b"\xca\xfe"


async def test_mqtt_sync_fires_on_first_ever_send() -> None:
    """_send_marked must prepend a sync on the first send — with no prior sync the device is
    assumed desynced (this is the change from the old last-send-based gate)."""
    mqtt_transport = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    handle = _make_handle(mqtt_transport=mqtt_transport)

    # No recorded sync for this transport yet.
    assert TransportType.CLOUD_ALIYUN not in handle._last_mqtt_sync_monotonic  # noqa: SLF001

    sent: list[bytes] = []

    async def capture_send(payload: bytes, iot_id: str = "", firmware_version: str = "") -> None:  # noqa: ARG001
        sent.append(payload)

    mqtt_transport.send.side_effect = capture_send

    await handle._send_marked(mqtt_transport, b"\x01\x02")  # noqa: SLF001

    mqtt_transport.send_heartbeat.assert_awaited_once()
    assert len(sent) == 1
    assert sent[0] == b"\x01\x02"


async def test_mqtt_sync_re_fires_during_sustained_command_burst() -> None:
    """Regression: a continuous command burst must keep re-syncing.

    Reproduces the field log where the device stopped responding ~10 s into a burst:
    the old gate debounced against the last *command*, so a steady stream of commands
    kept ``last_send`` fresh and only ONE sync ever fired — the device then desynced
    after its ~10 s window and ignored everything.  The gate now debounces against the
    last *sync*, so a long burst re-syncs every ``_MQTT_SYNC_INTERVAL`` seconds.
    """
    from unittest.mock import patch

    from pymammotion.device.handle import _MQTT_SYNC_INTERVAL

    mqtt_transport = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    handle = _make_handle(mqtt_transport=mqtt_transport)
    mqtt_transport.send = AsyncMock()

    clock = {"now": 1000.0}

    with patch("pymammotion.device.handle.time.monotonic", side_effect=lambda: clock["now"]):
        # t=0: first command — no prior sync, so a sync fires.
        await handle._send_marked(mqtt_transport, b"\x01")  # noqa: SLF001
        # A few commands well within the window — last_send stays fresh, but no extra sync.
        clock["now"] += _MQTT_SYNC_INTERVAL / 2
        await handle._send_marked(mqtt_transport, b"\x02")  # noqa: SLF001
        assert mqtt_transport.send_heartbeat.await_count == 1, "burst within window must not re-sync"
        # Past the window despite the steady command flow — the device would have desynced,
        # so a second sync must fire.
        clock["now"] += _MQTT_SYNC_INTERVAL + 0.1
        await handle._send_marked(mqtt_transport, b"\x03")  # noqa: SLF001
        assert mqtt_transport.send_heartbeat.await_count == 2, "burst past window must re-sync"
