"""Tests for DeviceHandle and DeviceRegistry."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.aliyun.exceptions import DeviceOfflineException, DeviceUnboundException
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.proto import LubaMsg as RealLubaMsg
from pymammotion.state.device_state import DeviceAvailability, DeviceConnectionState, TransportAvailability
from pymammotion.transport.base import NoTransportAvailableError, TransportType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_device(online: bool = True, enabled: bool = True) -> MagicMock:
    """Return a MagicMock shaped like a MowingDevice."""
    device = MagicMock()
    device.online = online
    device.enabled = enabled
    device.report_data.dev.battery_val = 80
    device.report_data.dev.sys_status = "idle"
    device.report_data.work.knife_height = 50
    return device


def make_transport(transport_type: TransportType, *, connected: bool = True) -> MagicMock:
    """Return a MagicMock shaped like a Transport."""
    transport = MagicMock()
    transport.transport_type = transport_type
    transport.is_connected = connected
    transport.send = AsyncMock()
    transport.disconnect = AsyncMock()
    transport.on_message = None
    return transport


def make_handle(
    device_id: str = "dev1",
    device_name: str = "Mower One",
    *,
    mqtt_transport: MagicMock | None = None,
    ble_transport: MagicMock | None = None,
) -> DeviceHandle:
    """Build a DeviceHandle with a mock MowingDevice."""
    device = make_device()
    return DeviceHandle(
        device_id=device_id,
        device_name=device_name,
        initial_device=device,
        mqtt_transport=mqtt_transport,
        ble_transport=ble_transport,
    )


# ---------------------------------------------------------------------------
# test 1: add_transport sets on_message
# ---------------------------------------------------------------------------


async def test_add_transport_sets_on_message() -> None:
    """transport.on_message must be a callable closure after add_transport.

    _wire_transport now sets a per-transport closure (not _on_raw_message directly)
    so that the transport type is captured and forwarded to _on_raw_message.
    """
    handle = make_handle()
    transport = make_transport(TransportType.CLOUD_ALIYUN)

    await handle.add_transport(transport)

    assert callable(transport.on_message)


# ---------------------------------------------------------------------------
# test 3: update_availability changes state
# ---------------------------------------------------------------------------


async def test_update_availability_changes_state() -> None:
    """After marking MQTT as connected, availability.is_available must be True."""
    handle = make_handle()
    assert handle.availability.is_available is False

    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED)

    assert handle.availability.is_available is True
    assert handle.availability.connection_state == DeviceConnectionState.CONNECTED


# ---------------------------------------------------------------------------
# test 4: stop cancels queue and broker
# ---------------------------------------------------------------------------


async def test_stop_cancels_queue_and_broker() -> None:
    """stop() must call queue.stop() and broker.close()."""
    handle = make_handle()

    queue_stop = AsyncMock()
    broker_close = AsyncMock()

    handle.queue.stop = queue_stop  # type: ignore[method-assign]
    handle.broker.close = broker_close  # type: ignore[method-assign]

    await handle.stop()

    queue_stop.assert_awaited_once()
    broker_close.assert_awaited_once()


# ---------------------------------------------------------------------------
# test 5: registry register and get
# ---------------------------------------------------------------------------


async def test_registry_register_and_get() -> None:
    """Registering a handle makes it retrievable via get()."""
    registry = DeviceRegistry()
    handle = make_handle(device_id="abc123", device_name="Luba One")

    await registry.register(handle)

    result = registry.get("abc123")
    assert result is handle
    assert registry.get("nonexistent") is None


# ---------------------------------------------------------------------------
# test 6: registry unregister calls stop
# ---------------------------------------------------------------------------


async def test_registry_unregister_calls_stop() -> None:
    """unregister() must call handle.stop() and remove it from the registry."""
    registry = DeviceRegistry()
    handle = make_handle(device_id="dev99")
    handle.stop = AsyncMock()  # type: ignore[method-assign]

    await registry.register(handle)
    await registry.unregister("dev99")

    handle.stop.assert_awaited_once()
    assert registry.get("dev99") is None


# ---------------------------------------------------------------------------
# test 7: _active_transport preference order
# ---------------------------------------------------------------------------


async def test_active_transport_prefers_connected_ble_by_default() -> None:
    """With both connected, BLE wins unconditionally (lower latency, bypasses cloud throttle)."""
    ble_transport = make_transport(TransportType.BLE, connected=True)
    mqtt_transport = make_transport(TransportType.CLOUD_ALIYUN, connected=True)

    handle = make_handle()
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    active = handle.active_transport()
    assert active.transport_type == TransportType.BLE


async def test_active_transport_prefer_ble_flag_reverses_order() -> None:
    """When prefer_ble=True, BLE is chosen over MQTT when both are connected."""
    from pymammotion.device.handle import DeviceHandle

    ble_transport = make_transport(TransportType.BLE, connected=True)
    mqtt_transport = make_transport(TransportType.CLOUD_ALIYUN, connected=True)

    handle = DeviceHandle(
        device_id="dev-ble",
        device_name="BLE-Preferred",
        initial_device=make_device(),
        prefer_ble=True,
    )
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    active = handle.active_transport()
    assert active.transport_type == TransportType.BLE


async def test_active_transport_prefers_connected_ble_over_disconnected_mqtt() -> None:
    """Connected BLE always wins, even over a disconnected MQTT — BLE is the faster path."""
    ble_transport = make_transport(TransportType.BLE, connected=True)
    mqtt_transport = make_transport(TransportType.CLOUD_ALIYUN, connected=False)

    handle = make_handle()
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    active = handle.active_transport()
    assert active.transport_type == TransportType.BLE


async def test_active_transport_falls_back_to_mqtt_when_ble_disconnected() -> None:
    """If BLE is registered but not actively connected, MQTT is used."""
    ble_transport = make_transport(TransportType.BLE, connected=False)
    mqtt_transport = make_transport(TransportType.CLOUD_ALIYUN, connected=True)

    handle = make_handle()
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    active = handle.active_transport()
    assert active.transport_type == TransportType.CLOUD_ALIYUN


async def test_active_transport_prefers_working_mqtt_over_disconnected_ble() -> None:
    """With prefer_ble=True but BLE merely usable-and-disconnected, a connected MQTT wins.

    BLE connection is now a background task: active_transport() only returns BLE when it is
    *actively connected*.  A disconnected-but-usable BLE no longer pre-empts a working MQTT —
    the send goes over the working connection while BLE reconnects in the background.
    """
    from pymammotion.device.handle import DeviceHandle

    ble_transport = make_transport(TransportType.BLE, connected=False)
    mqtt_transport = make_transport(TransportType.CLOUD_ALIYUN, connected=True)

    handle = DeviceHandle(
        device_id="dev-ble2",
        device_name="BLE-Preferred-2",
        initial_device=make_device(),
        prefer_ble=True,
    )
    await handle.add_transport(mqtt_transport)
    await handle.add_transport(ble_transport)

    active = handle.active_transport()
    assert active.transport_type == TransportType.CLOUD_ALIYUN


async def test_active_transport_raises_when_none_registered() -> None:
    """NoTransportAvailableError is raised when no transport is registered at all."""
    handle = make_handle()

    with pytest.raises(NoTransportAvailableError):
        handle.active_transport()


# ---------------------------------------------------------------------------
# Helpers for offline / online tests
# ---------------------------------------------------------------------------


def _patch_raw_message_internals(handle: DeviceHandle) -> None:
    """Stub out the state-machine internals so _on_raw_message doesn't crash."""
    handle._reducer.apply = MagicMock(return_value=make_device())  # type: ignore[method-assign]
    handle.state_machine.apply = MagicMock(return_value=(MagicMock(), False))  # type: ignore[method-assign]
    handle.broker.on_message = AsyncMock()  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# test 8: DeviceOfflineException marks mqtt_reported_offline — CLOUD_ALIYUN
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "transport_type",
    [TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION],
    ids=["aliyun", "mammotion"],
)
async def test_device_offline_marks_reported_offline(transport_type: TransportType) -> None:
    """DeviceOfflineException from either MQTT transport sets mqtt_reported_offline=True
    and makes the device unavailable (no BLE fallback present → the exception re-raises)."""
    handle = make_handle()
    mqtt = make_transport(transport_type, connected=True)
    await handle.add_transport(mqtt)
    handle.update_availability(transport_type, TransportAvailability.CONNECTED)

    handle._send_marked = AsyncMock(  # type: ignore[method-assign]
        side_effect=DeviceOfflineException(6205, "iot-id")
    )

    with pytest.raises(DeviceOfflineException):
        await handle.send_raw(b"\x01")

    assert handle.availability.mqtt_reported_offline is True
    assert handle.availability.is_available is False


# ---------------------------------------------------------------------------
# test 9: message arriving clears mqtt_reported_offline — both MQTT transports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "transport_type",
    [TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION],
    ids=["aliyun", "mammotion"],
)
async def test_incoming_message_clears_reported_offline(transport_type: TransportType) -> None:
    """Any message arriving over the cloud transport resets mqtt_reported_offline=False
    and makes the device available again."""
    handle = make_handle()
    mqtt = make_transport(transport_type, connected=True)
    await handle.add_transport(mqtt)
    handle.update_availability(transport_type, TransportAvailability.CONNECTED)

    # Put the device into the offline state directly
    handle.update_availability(transport_type, TransportAvailability.CONNECTED, mqtt_reported_offline=True)
    assert handle.availability.mqtt_reported_offline is True
    assert handle.availability.is_available is False

    # Simulate a message arriving from the device over the cloud transport
    _patch_raw_message_internals(handle)
    with patch("pymammotion.device.handle.LubaMsg") as mock_luba:
        mock_luba.return_value.parse.return_value = RealLubaMsg()
        await handle.on_raw_message(b"\x00", transport_type)

    assert handle.availability.mqtt_reported_offline is False
    assert handle.availability.is_available is True


# ---------------------------------------------------------------------------
# test 10: BLE message does NOT clear mqtt_reported_offline
# ---------------------------------------------------------------------------


async def test_ble_message_does_not_clear_reported_offline() -> None:
    """A message arriving over BLE must not touch mqtt_reported_offline — the
    cloud transport is still reporting the device as offline."""
    handle = make_handle()
    mqtt = make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble = make_transport(TransportType.BLE, connected=True)
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)
    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED)

    handle.update_availability(
        TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED, mqtt_reported_offline=True
    )
    assert handle.availability.mqtt_reported_offline is True

    _patch_raw_message_internals(handle)
    with patch("pymammotion.device.handle.LubaMsg") as mock_luba:
        mock_luba.return_value.parse.return_value = MagicMock()
        await handle.on_raw_message(b"\x00", TransportType.BLE)

    # BLE message must not clear the MQTT offline flag
    assert handle.availability.mqtt_reported_offline is True


# ---------------------------------------------------------------------------
# test 11: BLE fallback when MQTT is used and reports the device offline
#
# With the current transport-selection rule (connected BLE always wins), this
# fallback only fires when BLE is *not* connected at selection time — MQTT
# is picked, it raises DeviceOfflineException, and BLE has since come online
# (or is available to retry on).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "transport_type",
    [TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION],
    ids=["aliyun", "mammotion"],
)
async def test_ble_fallback_used_when_mqtt_offline(transport_type: TransportType) -> None:
    """When MQTT raises DeviceOfflineException and BLE becomes connected, retry over BLE."""
    handle = make_handle()
    mqtt = make_transport(transport_type, connected=True)
    ble = make_transport(TransportType.BLE, connected=False)  # not connected → MQTT chosen
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)
    handle.update_availability(transport_type, TransportAvailability.CONNECTED)

    call_count = 0

    async def _send_marked_side_effect(transport: object, payload: bytes) -> None:  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Simulate BLE coming online between MQTT failure and retry
            ble.is_connected = True
            raise DeviceOfflineException(6205, "iot-id")
        # Second call (BLE) succeeds

    handle._send_marked = AsyncMock(side_effect=_send_marked_side_effect)  # type: ignore[method-assign]

    await handle.send_raw(b"\x01")

    # _send_marked must have been called twice: MQTT then BLE
    assert handle._send_marked.call_count == 2
    assert handle._send_marked.await_args_list[0].args[0] is mqtt
    assert handle._send_marked.await_args_list[1].args[0] is ble
    # The MQTT offline flag stays set — BLE carried the command
    assert handle.availability.mqtt_reported_offline is True


# ---------------------------------------------------------------------------
# snapshot.raw reflects updated device state after on_raw_message
# ---------------------------------------------------------------------------


async def test_snapshot_raw_updates_after_on_raw_message() -> None:
    """snapshot.raw must reflect new field values after a real LubaMsg is processed."""
    from pymammotion.data.model.device import MowerDevice
    from pymammotion.proto import LubaMsg, MctlSys, ReportInfoData, RptDevStatus

    handle = DeviceHandle(
        device_id="dev-snap",
        device_name="Luba-Test",
        initial_device=MowerDevice(name="Luba-Test"),
    )

    msg = LubaMsg(sys=MctlSys(toapp_report_data=ReportInfoData(dev=RptDevStatus(battery_val=42))))
    await handle.on_raw_message(bytes(msg))

    assert handle.snapshot.raw.report_data.dev.battery_val == 42


async def test_on_raw_message_drops_frame_with_malformed_report_data(caplog: pytest.LogCaptureFixture) -> None:
    """A corrupt frame whose deserialization raises must be dropped + logged, not propagated.

    Reproduces the field crash where a garbled BLE notification parsed as a LubaMsg but
    WorkData.from_dict raised mashumaro InvalidFieldValue (a ValueError) deep in the reducer,
    killing the transport receive task ("Task exception was never retrieved").
    """
    import logging

    from mashumaro.exceptions import InvalidFieldValue

    from pymammotion.data.model.device import MowerDevice
    from pymammotion.proto import LubaMsg, MctlSys, ReportInfoData, RptDevStatus

    handle = DeviceHandle(
        device_id="dev-bad",
        device_name="Luba-Bad",
        initial_device=MowerDevice(name="Luba-Bad"),
    )

    # First a clean frame so we have a known-good baseline state.
    await handle.on_raw_message(bytes(LubaMsg(sys=MctlSys(toapp_report_data=ReportInfoData(dev=RptDevStatus(battery_val=55))))))
    assert handle.snapshot.raw.report_data.dev.battery_val == 55

    emitted: list[object] = []
    handle.subscribe_state_changed(lambda s: emitted.append(s))  # type: ignore[arg-type,return-value]

    # Now the reducer chokes on a malformed sub-message — must not escape on_raw_message.
    handle._reducer.apply = MagicMock(  # type: ignore[method-assign]
        side_effect=InvalidFieldValue("bp_pos_y", int, [114, 30], object)
    )

    payload = bytes(LubaMsg(sys=MctlSys(toapp_report_data=ReportInfoData())))
    with caplog.at_level(logging.ERROR):
        await handle.on_raw_message(payload)

    # State preserved, no snapshot emitted for the bad frame, and the drop was logged at ERROR.
    assert handle.snapshot.raw.report_data.dev.battery_val == 55
    assert emitted == []
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR and "dropping frame" in r.getMessage()]
    assert error_records, "expected an ERROR log for the dropped frame"
    rendered = error_records[0].getMessage()
    # The exception message (offending field + bad value) and the raw bytes must be logged
    # so the bad data can be investigated.
    assert 'Field "bp_pos_y"' in rendered
    assert "invalid value [114, 30]" in rendered
    assert payload.hex() in rendered


# ---------------------------------------------------------------------------
# Regression: protobuf path must emit even when no snapshot-level field changes.
# DeviceSnapshot._diff only looks at connection_state/online/enabled/battery.
# A nav message updating mower_state.rain_detection (or any other deep field)
# must still propagate to state_changed_bus subscribers.
# ---------------------------------------------------------------------------


async def test_on_raw_message_emits_even_when_diff_is_empty() -> None:
    """state_changed_bus must fire for every protobuf message.

    Subscribers (watch_field, HA coordinators) inspect snapshot.raw fields
    that _diff() deliberately skips. If we gate emission on _diff, updates
    to deep fields like mower_state.rain_detection never reach HA.
    """
    from pymammotion.data.model.device import MowerDevice
    from pymammotion.proto import LubaMsg, MctlNav, NavSysParamMsg

    handle = DeviceHandle(
        device_id="dev-emit",
        device_name="Luba-Emit",
        initial_device=MowerDevice(name="Luba-Emit"),
    )

    received: list[object] = []

    async def _handler(snapshot: object) -> None:
        received.append(snapshot)

    handle.subscribe_state_changed(_handler)

    # A nav_sys_param_cmd only mutates mower_state.rain_detection — no snapshot
    # top-level field changes, so _diff returns an empty frozenset.
    msg = LubaMsg(nav=MctlNav(nav_sys_param_cmd=NavSysParamMsg(id=3, context=1)))
    await handle.on_raw_message(bytes(msg))

    assert len(received) == 1
    assert handle.snapshot.raw.mower_state.rain_detection is True


# ---------------------------------------------------------------------------
# MQTT unusable when mqtt_reported_offline: active_transport skips MQTT
# ---------------------------------------------------------------------------


async def test_active_transport_skips_mqtt_when_reported_offline() -> None:
    """mqtt_reported_offline=True → MQTT treated as unusable; BLE used if registered."""
    mqtt = make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble = make_transport(TransportType.BLE, connected=False)  # registered, not connected

    handle = make_handle()
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)

    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED, mqtt_reported_offline=True)

    active = handle.active_transport()
    assert active.transport_type == TransportType.BLE


async def test_active_transport_raises_when_only_mqtt_and_offline() -> None:
    """mqtt_reported_offline=True and no BLE → NoTransportAvailableError."""
    mqtt = make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    handle = make_handle()
    await handle.add_transport(mqtt)

    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED, mqtt_reported_offline=True)

    with pytest.raises(NoTransportAvailableError):
        handle.active_transport()


# ---------------------------------------------------------------------------
# _sleep_or_rearm: signals delivered between iterations must wake the next call
# ---------------------------------------------------------------------------


async def test_sleep_or_rearm_returns_immediately_if_event_pre_set() -> None:
    """Regression: if `_rearm_event.set()` happens between two `_sleep_or_rearm`
    calls, the next call must observe the signal and return immediately rather
    than clearing it and sleeping the full interval."""
    handle = make_handle()

    # Simulate the bug scenario: event is set before _sleep_or_rearm runs.
    handle._rearm_event.set()  # noqa: SLF001

    # A 30-second sleep would block the test if the bug were still present.
    started = asyncio.get_event_loop().time()
    woke = await asyncio.wait_for(handle.sleep_or_rearm(30.0), timeout=1.0)
    elapsed = asyncio.get_event_loop().time() - started

    assert woke is True
    assert elapsed < 0.5, f"_sleep_or_rearm should have returned immediately, took {elapsed:.2f}s"
    # Event must have been consumed so the next call waits for a fresh signal.
    assert not handle._rearm_event.is_set()  # noqa: SLF001


async def test_sleep_or_rearm_times_out_when_no_signal() -> None:
    """When no signal arrives the function returns False after the full sleep."""
    handle = make_handle()
    assert not handle._rearm_event.is_set()  # noqa: SLF001

    woke = await handle.sleep_or_rearm(0.05)
    assert woke is False


async def test_sleep_or_rearm_wakes_on_signal_during_wait() -> None:
    """A signal delivered while sleeping wakes the call early."""
    handle = make_handle()

    async def signal_after_delay() -> None:
        await asyncio.sleep(0.05)
        handle._rearm_event.set()  # noqa: SLF001

    asyncio.create_task(signal_after_delay())
    woke = await asyncio.wait_for(handle.sleep_or_rearm(5.0), timeout=1.0)
    assert woke is True
    assert not handle._rearm_event.is_set()  # noqa: SLF001


# ---------------------------------------------------------------------------
# map_updated emission — area-name changes must notify HA
# ---------------------------------------------------------------------------


async def _emit_via_raw_message(handle: DeviceHandle, msg: RealLubaMsg) -> None:
    """Drive *msg* through on_raw_message with state internals stubbed out."""
    _patch_raw_message_internals(handle)
    with patch("pymammotion.device.handle.LubaMsg") as mock_luba:
        mock_luba.return_value.parse.return_value = msg
        await handle.on_raw_message(b"\x00", TransportType.CLOUD_ALIYUN)


async def test_map_updated_emitted_on_area_name_list() -> None:
    """The wholesale area-name list (toapp_all_hash_name) fires map_updated (existing behaviour)."""
    from pymammotion.proto import AppGetAllAreaHashName, AreaHashName, MctlNav

    handle = make_handle()
    fired: list[bool] = []
    handle.subscribe_map_updated(lambda: _record(fired))

    msg = RealLubaMsg(
        nav=MctlNav(toapp_all_hash_name=AppGetAllAreaHashName(hashnames=[AreaHashName(hash=1, name="A")]))
    )
    await _emit_via_raw_message(handle, msg)

    assert fired == [True]


async def test_map_updated_emitted_on_single_area_rename() -> None:
    """A single-area rename (toapp_map_name_msg) must fire map_updated so HA refreshes names."""
    from pymammotion.proto import MctlNav, NavMapNameMsg

    handle = make_handle()
    fired: list[bool] = []
    handle.subscribe_map_updated(lambda: _record(fired))

    msg = RealLubaMsg(nav=MctlNav(toapp_map_name_msg=NavMapNameMsg(hash=123, name="Front Lawn")))
    await _emit_via_raw_message(handle, msg)

    assert fired == [True]


async def test_map_updated_not_emitted_on_rename_request_with_zero_hash() -> None:
    """hash == 0 is the get-list request shape (not a rename) — must NOT fire map_updated."""
    from pymammotion.proto import MctlNav, NavMapNameMsg

    handle = make_handle()
    fired: list[bool] = []
    handle.subscribe_map_updated(lambda: _record(fired))

    msg = RealLubaMsg(nav=MctlNav(toapp_map_name_msg=NavMapNameMsg(hash=0, name="")))
    await _emit_via_raw_message(handle, msg)

    assert fired == []


async def test_map_updated_not_emitted_on_area_geometry() -> None:
    """Area geometry (toapp_get_commondata_ack) must NOT fire map_updated.

    It arrives per-frame in bulk; the MapFetchSaga's on_complete emits once instead.
    """
    from pymammotion.proto import MctlNav, NavGetCommDataAck

    handle = make_handle()
    fired: list[bool] = []
    handle.subscribe_map_updated(lambda: _record(fired))

    msg = RealLubaMsg(
        nav=MctlNav(toapp_get_commondata_ack=NavGetCommDataAck(type=0, hash=123, total_frame=1, current_frame=1))
    )
    await _emit_via_raw_message(handle, msg)

    assert fired == []


async def _record(sink: list[bool]) -> None:
    """Async map_updated subscriber that records a firing."""
    sink.append(True)


# ===========================================================================
# Rate limiting is now owned by the Transport base class (_rate_limited_until timestamp).
# ===========================================================================
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.aliyun.exceptions import TooManyRequestsException
from pymammotion.device.handle import DeviceHandle
from pymammotion.device.mqtt_loop import _RATE_LIMITED_BACKOFF
from pymammotion.transport.base import Transport, TransportRateLimitedError, TransportType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mowing_device() -> MagicMock:
    device = MagicMock()
    device.online = True
    device.enabled = True
    device.report_data.dev.battery_val = 75
    device.report_data.dev.sys_status = 0
    return device


def _make_rl_handle() -> DeviceHandle:
    return DeviceHandle(
        device_id="dev1",
        device_name="Luba-RL",
        initial_device=_make_mowing_device(),
    )


def _make_mqtt_transport(*, connected: bool = True) -> MagicMock:
    t = MagicMock()
    t.transport_type = TransportType.CLOUD_ALIYUN
    t.is_connected = connected
    t.is_rate_limited = False
    t.send = AsyncMock()
    t.send_heartbeat = AsyncMock()
    t.set_rate_limited = MagicMock()
    t.disconnect = AsyncMock()
    t.on_message = None
    t.add_availability_listener = MagicMock()
    t.last_received_monotonic = 0.0
    t.last_send_monotonic = 0.0
    return t


# ---------------------------------------------------------------------------
# Transport base class — is_rate_limited / set_rate_limited
# ---------------------------------------------------------------------------


def _make_concrete_transport() -> Transport:
    """Return a minimal concrete Transport (abstract methods stubbed out)."""

    class _Stub(Transport):
        @property
        def transport_type(self) -> TransportType:
            return TransportType.CLOUD_ALIYUN

        @property
        def is_connected(self) -> bool:
            return True

        @property
        def availability(self):  # type: ignore[override]
            from pymammotion.transport.base import TransportAvailability
            return TransportAvailability.CONNECTED

        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def send(self, payload: bytes, iot_id: str = "") -> None:
            pass

    return _Stub()


def test_transport_not_rate_limited_initially() -> None:
    """A freshly created Transport is not rate-limited."""
    t = _make_concrete_transport()
    assert t.is_rate_limited is False


def test_transport_set_rate_limited_blocks_for_duration() -> None:
    """After set_rate_limited(), is_rate_limited is True until the ban expires."""
    t = _make_concrete_transport()
    t.set_rate_limited()
    assert t.is_rate_limited is True


def test_transport_rate_limit_expires_after_12_hours() -> None:
    """is_rate_limited returns False once _rate_limited_until is in the past."""
    t = _make_concrete_transport()
    t.set_rate_limited()
    assert t.is_rate_limited is True

    # Simulate the 12-hour ban having expired.
    t._rate_limited_until = time.monotonic() - 1  # noqa: SLF001
    assert t.is_rate_limited is False


def test_transport_rate_limit_duration_is_12_hours() -> None:
    """set_rate_limited() sets a ban of exactly _RATE_LIMIT_DURATION seconds."""
    t = _make_concrete_transport()
    before = time.monotonic()
    t.set_rate_limited()
    after = time.monotonic()

    # Ban should expire roughly 12 hours from now.
    expected = 43200.0  # 12 h
    assert before + expected <= t._rate_limited_until <= after + expected  # noqa: SLF001


def test_transport_rate_limit_constant_matches_handle_backoff() -> None:
    """Transport._RATE_LIMIT_DURATION and handle._RATE_LIMITED_BACKOFF must agree."""
    t = _make_concrete_transport()
    assert t._RATE_LIMIT_DURATION == _RATE_LIMITED_BACKOFF  # noqa: SLF001


def test_quota_block_self_clears_when_window_slides_under_limit() -> None:
    """The self-imposed send-quota must release the instant the rolling window drops back
    under the limit — no fixed-duration ban (that is reserved for cloud 429s)."""
    from unittest.mock import patch

    t = _make_concrete_transport()
    limit = t._SEND_LIMIT  # noqa: SLF001
    window = t._SEND_WINDOW  # noqa: SLF001
    clock = {"now": 100_000.0}

    with patch("pymammotion.transport.base.time.monotonic", side_effect=lambda: clock["now"]):
        for _ in range(limit):
            t.record_send()

        # Quota exhausted — blocked — but NO fixed cloud ban was imposed.
        assert t.is_rate_limited is True
        assert t._rate_limited_until == 0.0  # noqa: SLF001 — quota path must not set the cloud timer
        # Release is exactly one window after the oldest send.
        assert t.seconds_until_send_available() == window

        # Slide the window so the oldest send ages out → count drops to limit-1.
        clock["now"] += window + 1.0
        assert t.is_rate_limited is False
        assert t.seconds_until_send_available() == 0.0


def test_seconds_until_send_available_is_max_of_cloud_ban_and_quota() -> None:
    """When both a cloud ban and the quota are active, the longer release time wins."""
    from unittest.mock import patch

    t = _make_concrete_transport()
    clock = {"now": 0.0}

    with patch("pymammotion.transport.base.time.monotonic", side_effect=lambda: clock["now"]):
        t._rate_limited_until = 100.0  # noqa: SLF001 — short cloud ban
        for _ in range(t._SEND_LIMIT):  # noqa: SLF001 — full window, release a whole window away
            t.record_send()

        # Quota release (_SEND_WINDOW) dominates the 100 s cloud ban.
        assert t.seconds_until_send_available() == t._SEND_WINDOW  # noqa: SLF001

        # Clear the quota; the cloud ban now dominates.
        t._send_timestamps.clear()  # noqa: SLF001
        assert t.seconds_until_send_available() == 100.0
        assert t.is_rate_limited is True  # cloud ban still active


# ---------------------------------------------------------------------------
# _send_marked raises TransportRateLimitedError when transport is rate-limited
# ---------------------------------------------------------------------------


async def test_send_marked_raises_when_transport_rate_limited() -> None:
    """_send_marked() must raise TransportRateLimitedError without calling transport.send()."""
    handle = _make_rl_handle()
    mqtt = _make_mqtt_transport()
    mqtt.is_rate_limited = True
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    with pytest.raises(TransportRateLimitedError):
        await handle._send_marked(mqtt, b"\x01\x02\x03")  # noqa: SLF001

    mqtt.send.assert_not_awaited()


async def test_send_marked_passes_through_when_not_rate_limited() -> None:
    """_send_marked() calls transport.send() when the transport is not rate-limited."""
    handle = _make_rl_handle()
    mqtt = _make_mqtt_transport()
    mqtt.is_rate_limited = False
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    await handle._send_marked(mqtt, b"\x01\x02\x03")  # noqa: SLF001

    mqtt.send.assert_awaited_once()


# ---------------------------------------------------------------------------
# send_raw — 429 from transport.send() triggers set_rate_limited()
# ---------------------------------------------------------------------------


async def test_send_raw_calls_set_rate_limited_on_429() -> None:
    """send_raw must call transport.set_rate_limited() when TooManyRequestsException is raised."""
    handle = _make_rl_handle()
    mqtt = _make_mqtt_transport()
    mqtt.send = AsyncMock(side_effect=TooManyRequestsException("rate limited", "iot-id"))
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    await handle.send_raw(b"\x00")

    mqtt.set_rate_limited.assert_called_once()


async def test_send_raw_blocked_silently_when_already_rate_limited() -> None:
    """send_raw must silently drop the send (not call transport.send) when already rate-limited."""
    handle = _make_rl_handle()
    mqtt = _make_mqtt_transport()
    mqtt.is_rate_limited = True
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    await handle.send_raw(b"\x00")

    mqtt.send.assert_not_awaited()
    # set_rate_limited must NOT be called again — the ban is already active.
    mqtt.set_rate_limited.assert_not_called()


# ---------------------------------------------------------------------------
# BLE is unaffected by rate limiting
# ---------------------------------------------------------------------------


async def test_ble_transport_not_blocked_by_rate_limited_flag() -> None:
    """BLE transport with is_rate_limited=False is never blocked by _send_marked."""
    handle = _make_rl_handle()

    ble = MagicMock()
    ble.transport_type = TransportType.BLE
    ble.is_connected = True
    ble.is_rate_limited = False
    ble.last_send_monotonic = 0.0
    ble.send = AsyncMock()
    ble.set_rate_limited = MagicMock()
    ble.disconnect = AsyncMock()
    ble.on_message = None
    ble.add_availability_listener = MagicMock()
    ble.last_received_monotonic = 0.0
    handle._transports[TransportType.BLE] = ble  # noqa: SLF001

    await handle._send_marked(ble, b"\xAA\xBB")  # noqa: SLF001

    ble.send.assert_awaited_once()


# ---------------------------------------------------------------------------
# Rate limit does NOT reset the ban timestamp on repeated calls
# (first 429 sets it; guard-triggered TransportRateLimitedError is not a new 429)
# ---------------------------------------------------------------------------


async def test_send_raw_guard_does_not_call_set_rate_limited_again() -> None:
    """If a transport is already rate-limited, send_raw must not call set_rate_limited() again."""
    handle = _make_rl_handle()
    mqtt = _make_mqtt_transport()
    mqtt.is_rate_limited = True
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    # Call send_raw three times while the transport is already rate-limited.
    await handle.send_raw(b"\x01")
    await handle.send_raw(b"\x02")
    await handle.send_raw(b"\x03")

    mqtt.set_rate_limited.assert_not_called()
    mqtt.send.assert_not_awaited()


# ===========================================================================
# Verifies that every RPT_START goes through ``broker.send_and_wait`` expecting
# ===========================================================================
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import CommandTimeoutError, ConcurrentRequestError


@pytest.fixture
def rpt_handle(monkeypatch: pytest.MonkeyPatch) -> DeviceHandle:
    """Bare DeviceHandle with broker + commands mocked.

    We bypass ``DeviceHandle.__init__`` entirely (it brings up a queue, reducer
    etc. that aren't relevant here) and set just the attributes the helper
    touches.  ``commands`` is a ``@property``, so we monkeypatch the descriptor
    at the class level to return our mock.
    """
    h = DeviceHandle.__new__(DeviceHandle)
    h.device_name = "Luba-TEST"
    h.broker = MagicMock()
    h.broker.send_and_wait = AsyncMock()
    mocked_commands = MagicMock()
    mocked_commands.send_todev_ble_sync = MagicMock(return_value=b"\xAAsync")
    monkeypatch.setattr(DeviceHandle, "commands", property(lambda self: mocked_commands))
    return h


async def test_success_returns_true_and_sends_once(rpt_handle: DeviceHandle) -> None:
    """First attempt succeeds: send_fn runs once with cmd_bytes only, no ble_sync."""
    cmd_bytes = b"\xBBcmd"
    transport_send = AsyncMock()

    # Drive send_and_wait to invoke our _send exactly once and "succeed"
    async def _drive(send_fn, expected_field, **kwargs) -> None:
        assert expected_field == "toapp_report_data"
        await send_fn()  # one attempt, no exception

    rpt_handle.broker.send_and_wait.side_effect = _drive

    result = await rpt_handle._send_rpt_start_verified(cmd_bytes, transport_send)

    assert result is True
    # send_fn ran once → transport_send called once with cmd_bytes (no ble_sync)
    transport_send.assert_awaited_once_with(cmd_bytes)


async def test_retry_prefixes_ble_sync_then_cmd(rpt_handle: DeviceHandle) -> None:
    """On the broker's 2nd attempt the send order is: ble_sync, then RPT_START.

    The broker's retry budget is 2 attempts by default; we simulate that by
    invoking _send twice from inside send_and_wait, then "succeeding".
    """
    cmd_bytes = b"\xBBcmd"
    sync_bytes = b"\xAAsync"
    rpt_handle.commands.send_todev_ble_sync.return_value = sync_bytes
    transport_send = AsyncMock()

    async def _drive(send_fn, expected_field, **kwargs) -> None:
        # Attempt 1
        await send_fn()
        # Attempt 2 (broker's retry)
        await send_fn()

    rpt_handle.broker.send_and_wait.side_effect = _drive

    result = await rpt_handle._send_rpt_start_verified(cmd_bytes, transport_send)

    assert result is True
    # Expect three sends total: attempt 1 (cmd), attempt 2 (sync + cmd)
    sends = [c.args[0] for c in transport_send.await_args_list]
    assert sends == [cmd_bytes, sync_bytes, cmd_bytes], (
        f"Send order wrong; got {sends!r}"
    )


async def test_command_timeout_returns_false(rpt_handle: DeviceHandle) -> None:
    """CommandTimeoutError from the broker → helper returns False (no raise)."""
    cmd_bytes = b"\xBBcmd"
    transport_send = AsyncMock()

    rpt_handle.broker.send_and_wait.side_effect = CommandTimeoutError("toapp_report_data", 2)

    result = await rpt_handle._send_rpt_start_verified(cmd_bytes, transport_send)

    assert result is False


async def test_concurrent_request_falls_back_to_plain_send(rpt_handle: DeviceHandle) -> None:
    """When another verified RPT_START is in flight, the helper:
    1. Catches ConcurrentRequestError silently
    2. Falls back to a fire-and-forget send of cmd_bytes
    3. Returns False (we can't claim verification)
    """
    cmd_bytes = b"\xBBcmd"
    transport_send = AsyncMock()

    rpt_handle.broker.send_and_wait.side_effect = ConcurrentRequestError("Already waiting")

    result = await rpt_handle._send_rpt_start_verified(cmd_bytes, transport_send)

    assert result is False
    # Fallback fire-and-forget send did happen
    transport_send.assert_awaited_once_with(cmd_bytes)


async def test_retry_prefix_send_failure_does_not_abort(rpt_handle: DeviceHandle) -> None:
    """If the ble_sync prefix send itself raises, the helper logs DEBUG and
    still re-issues the RPT_START on that attempt — a flaky sync write must
    not block the actual retry."""
    cmd_bytes = b"\xBBcmd"
    sync_bytes = b"\xAAsync"
    rpt_handle.commands.send_todev_ble_sync.return_value = sync_bytes

    # First send (attempt 1, cmd): ok.  Second send (attempt 2, ble_sync prefix): raises.
    # Third send (attempt 2, cmd after the failed prefix): ok.
    transport_send = AsyncMock(
        side_effect=[None, RuntimeError("flaky sync write"), None],
    )

    async def _drive(send_fn, expected_field, **kwargs) -> None:
        await send_fn()  # attempt 1
        await send_fn()  # attempt 2 (prefix raises, cmd should still go)

    rpt_handle.broker.send_and_wait.side_effect = _drive

    result = await rpt_handle._send_rpt_start_verified(cmd_bytes, transport_send)

    assert result is True
    sends = [c.args[0] for c in transport_send.await_args_list]
    assert sends == [cmd_bytes, sync_bytes, cmd_bytes]


# ===========================================================================
# The 2026-05-22 HA log showed 130+ identical
# ===========================================================================
import contextlib
import logging
from unittest.mock import MagicMock

import pytest

from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import NoTransportAvailableError, TransportAvailability, TransportType


@pytest.fixture
def dedup_handle() -> DeviceHandle:
    """Minimal DeviceHandle — just enough for active_transport() to run."""
    from pymammotion.data.model.device import MowerDevice

    h = DeviceHandle(
        device_id="dev-test",
        device_name="Luba-VAAAYRNG",
        initial_device=MowerDevice(),
    )
    return h


def _add_mqtt(dedup_handle: DeviceHandle, *, usable: bool = True) -> MagicMock:
    mqtt = MagicMock()
    mqtt.transport_type = TransportType.CLOUD_MAMMOTION
    mqtt.is_connected = True
    mqtt.is_usable = usable
    mqtt.availability = TransportAvailability.CONNECTED
    dedup_handle._transports[TransportType.CLOUD_MAMMOTION] = mqtt  # noqa: SLF001
    return mqtt


def _add_unusable_ble(dedup_handle: DeviceHandle) -> MagicMock:
    ble = MagicMock()
    ble.transport_type = TransportType.BLE
    ble.is_connected = False
    ble.is_usable = False
    ble.availability = TransportAvailability.DISCONNECTED
    dedup_handle._transports[TransportType.BLE] = ble  # noqa: SLF001
    return ble


def test_identical_selections_emit_one_log_line(dedup_handle: DeviceHandle, caplog: pytest.LogCaptureFixture) -> None:
    """Repeat calls with the same selection state must produce only one DEBUG line.

    Regression for the 130× log-spam observed in the HA log when BLE was
    unusable for the full session and every send hit the fallback path.
    """
    _add_mqtt(dedup_handle, usable=True)
    _add_unusable_ble(dedup_handle)

    caplog.set_level(logging.DEBUG, logger="pymammotion.device.handle")

    # Call active_transport 50 times with BLE preferred but unusable (→ MQTT selected).
    for _ in range(50):
        dedup_handle.active_transport(prefer_ble=True)

    selection_lines = [
        r for r in caplog.records if "selected" in r.getMessage() and "active_transport" in r.getMessage()
    ]
    assert len(selection_lines) == 1, (
        f"Expected 1 selection log line, got {len(selection_lines)}.  "
        f"The de-dupe in active_transport regressed."
    )


def test_state_transition_re_emits_log(dedup_handle: DeviceHandle, caplog: pytest.LogCaptureFixture) -> None:
    """When the (selection-path, prefer_ble, ble_usable, mqtt_usable) tuple
    actually changes, the new state MUST be logged."""
    mqtt = _add_mqtt(dedup_handle, usable=True)
    ble = _add_unusable_ble(dedup_handle)

    caplog.set_level(logging.DEBUG, logger="pymammotion.device.handle")

    # First call: BLE preferred but unusable → MQTT fallback
    dedup_handle.active_transport(prefer_ble=True)
    # Second call: same state → SHOULD NOT re-log
    dedup_handle.active_transport(prefer_ble=True)
    # BLE becomes usable → DIFFERENT state → MUST re-log
    ble.is_usable = True
    dedup_handle.active_transport(prefer_ble=True)

    # Snapshot rule-match logs from these three calls (no error path yet).
    rule_lines = [
        r for r in caplog.records
        if r.name == "pymammotion.device.handle"
        and (
            "BLE preferred" in r.getMessage()
            or "selected " in r.getMessage()
            or "MQTT unusable" in r.getMessage()
        )
    ]
    # Expect exactly 2 transitions logged: (1) BLE-unusable-fallback,
    # (2) BLE-usable.  The repeat in between is suppressed.
    assert len(rule_lines) == 2, (
        f"Expected 2 transition logs, got {len(rule_lines)}.  "
        f"Messages: {[r.getMessage() for r in rule_lines]}"
    )

    # Sanity: when both transports go unusable, active_transport raises
    # (we don't assert on that log here — the error path uses a different
    # logger call that's not under _log_selection's dedup).
    mqtt.is_usable = False
    ble.is_usable = False
    with contextlib.suppress(NoTransportAvailableError):
        dedup_handle.active_transport(prefer_ble=True)


def test_prefer_ble_change_is_a_transition(dedup_handle: DeviceHandle, caplog: pytest.LogCaptureFixture) -> None:
    """Switching prefer_ble between calls counts as a state change and re-logs."""
    _add_mqtt(dedup_handle, usable=True)
    _add_unusable_ble(dedup_handle)

    caplog.set_level(logging.DEBUG, logger="pymammotion.device.handle")

    dedup_handle.active_transport(prefer_ble=True)  # BLE preferred + fallback
    dedup_handle.active_transport(prefer_ble=False)  # MQTT selected directly
    dedup_handle.active_transport(prefer_ble=True)  # back to BLE preferred + fallback

    rule_lines = [
        r for r in caplog.records
        if "BLE preferred but not usable" in r.getMessage() or "selected " in r.getMessage()
    ]
    # 3 distinct (selection-path, prefer_ble) combinations → at least 3 logs
    assert len(rule_lines) >= 3


# ===========================================================================
# Also covers add_ble_device() wiring a BLETransport onto an existing handle.
# ===========================================================================
import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch

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
    t.is_rate_limited = False
    t.last_send_monotonic = 0.0
    t.send = AsyncMock()
    t.send_heartbeat = AsyncMock()
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


async def test_ble_only_sends_and_reconnects_in_background() -> None:
    """BLE-only + disconnected: the send goes over BLE now, and a reconnect runs in the background.

    Connecting is no longer awaited inline before the send; it is scheduled as a background
    task so a slow/failing BLE connect can't block the command path.
    """
    handle = _make_handle(prefer_ble=True)
    ble = _make_transport(TransportType.BLE, connected=False)

    async def _do_connect() -> None:
        ble.is_connected = True

    ble.connect.side_effect = _do_connect
    await handle.add_transport(ble)

    await handle.send_raw(b"\x00\x01", prefer_ble=True)
    await asyncio.sleep(0)  # let the background connect task run

    ble.send.assert_awaited_once_with(b"\x00\x01", iot_id="", firmware_version=ANY)
    ble.connect.assert_awaited_once()  # reconnect attempted in the background


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

    mqtt.send.assert_awaited_once_with(b"\xAB\xCD", iot_id="", firmware_version=ANY)


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


async def test_hybrid_disconnected_ble_yields_to_connected_mqtt() -> None:
    """When prefer_ble=True but BLE is disconnected and MQTT is connected, MQTT is selected.

    A disconnected-but-usable BLE no longer pre-empts a working MQTT; BLE reconnects in the
    background and only wins once it is actively connected.
    """
    handle = _make_handle(prefer_ble=True)
    mqtt = _make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble = _make_transport(TransportType.BLE, connected=False)
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)

    active = handle.active_transport()
    assert active is mqtt


async def test_hybrid_ble_disconnected_reconnects_in_background_when_no_mqtt() -> None:
    """With prefer_ble=True and MQTT absent, send_raw() sends over BLE and reconnects in background."""
    handle = _make_handle(prefer_ble=True)
    ble = _make_transport(TransportType.BLE, connected=False)

    async def _do_connect() -> None:
        ble.is_connected = True

    ble.connect.side_effect = _do_connect
    await handle.add_transport(ble)

    await handle.send_raw(b"\xDE\xAD", prefer_ble=True)
    await asyncio.sleep(0)  # let the background connect task run

    ble.send.assert_awaited_once_with(b"\xDE\xAD", iot_id="", firmware_version=ANY)
    ble.connect.assert_awaited_once()  # reconnect attempted in the background


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
    mock_transport.set_ble_device.assert_called_once_with(fake_ble_device, None)
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


# ===========================================================================
# The method waits for a transport to be ready: BLE counts the instant it
# ===========================================================================
from types import SimpleNamespace

import pytest

from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import TransportType


def _fake_handle(connected: set[TransportType]) -> SimpleNamespace:
    """A stand-in exposing just what wait_until_connected touches."""
    return SimpleNamespace(
        device_name="Luba-TEST",
        is_transport_connected=lambda tt: tt in connected,
    )


async def _wait(fake: SimpleNamespace, **kwargs: float) -> bool:
    # Call the unbound coroutine with our stand-in as ``self``.
    return await DeviceHandle.wait_until_connected(fake, **kwargs)


@pytest.mark.asyncio
async def test_ble_connected_returns_true_immediately() -> None:
    fake = _fake_handle({TransportType.BLE})
    # Large stability window is irrelevant — BLE needs no settling.
    assert await _wait(fake, timeout=5.0, mqtt_stable_for=10.0) is True


@pytest.mark.asyncio
async def test_mqtt_ready_when_stability_window_is_zero() -> None:
    fake = _fake_handle({TransportType.CLOUD_MAMMOTION})
    assert await _wait(fake, timeout=5.0, mqtt_stable_for=0.0) is True


@pytest.mark.asyncio
async def test_mqtt_aliyun_also_counts() -> None:
    fake = _fake_handle({TransportType.CLOUD_ALIYUN})
    assert await _wait(fake, timeout=5.0, mqtt_stable_for=0.0) is True


@pytest.mark.asyncio
async def test_mqtt_not_stable_long_enough_times_out() -> None:
    # MQTT is connected but the stability window can't be met before give-up,
    # so the method returns False (caller continues anyway).
    fake = _fake_handle({TransportType.CLOUD_MAMMOTION})
    assert await _wait(fake, timeout=0.3, mqtt_stable_for=5.0) is False


@pytest.mark.asyncio
async def test_no_transport_times_out_false() -> None:
    fake = _fake_handle(set())
    assert await _wait(fake, timeout=0.3, mqtt_stable_for=10.0) is False


@pytest.mark.asyncio
async def test_ble_beats_unstable_mqtt() -> None:
    # BLE connected wins immediately even with a huge MQTT stability window.
    fake = _fake_handle({TransportType.BLE, TransportType.CLOUD_MAMMOTION})
    assert await _wait(fake, timeout=5.0, mqtt_stable_for=999.0) is True


# ===========================================================================
# Issue #130: `params.time` (Unix ms) reflects cloud-side generation time and
# ===========================================================================
import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport, _STALE_EVENT_THRESHOLD_MS


@pytest.fixture
def transport():
    """AliyunMQTTTransport with a mocked cloud gateway."""
    config = AliyunMQTTConfig(
        host="test.iot-as-mqtt.cn-shanghai.aliyuncs.com",
        client_id_base="testpk&testdn",
        username="testdn&testpk",
        device_name="testdn",
        product_key="testpk",
        device_secret="testsecret",
        iot_token="testtoken",
    )
    gateway = MagicMock()
    t = AliyunMQTTTransport(config, gateway)
    t.on_device_event = AsyncMock()
    t.on_device_properties = AsyncMock()
    return t


def _make_event_envelope(envelope_time_ms: int, identifier: str = "device_protobuf_msg_event") -> bytes:
    """Build a raw JSON thing/events envelope with the given params.time."""
    sample_bytes = b'\x08\xf4\x01\x10\x01\x18\x07(\x010\x01R\x08\xba\x02\x05\x12\x03\x08\x05\x10K'
    encoded = base64.b64encode(sample_bytes).decode("ascii")

    payload = {
        "method": "thing.events",
        "id": "test-event-id",
        "version": "1.0",
        "params": {
            "identifier": identifier,
            "type": "info",
            "time": envelope_time_ms,
            "iotId": "test_iot_id",
            "productKey": "testpk",
            "deviceName": "testdn",
            "gmtCreate": 1714000000000,
            "groupIdList": [],
            "groupId": "",
            "categoryKey": "LawnMower",
            "batchId": "",
            "checkLevel": 0,
            "namespace": "",
            "tenantId": "",
            "name": "",
            "thingType": "DEVICE",
            "tenantInstanceId": "",
            "value": {
                "content": encoded,
            },
        },
    }
    return json.dumps(payload).encode()


@pytest.mark.asyncio
async def test_fresh_event_forwarded(transport: AliyunMQTTTransport):
    """Events with params.time within the threshold are forwarded."""
    now_ms = int(time.time() * 1000)
    raw = _make_event_envelope(now_ms - 5_000)  # 5 seconds old

    await transport._dispatch_aliyun_event("/sys/testpk/testdn/app/down/thing/events", raw)

    transport.on_device_event.assert_called_once()


@pytest.mark.asyncio
async def test_stale_event_dropped(transport: AliyunMQTTTransport):
    """Events older than the threshold are silently dropped."""
    now_ms = int(time.time() * 1000)
    raw = _make_event_envelope(now_ms - _STALE_EVENT_THRESHOLD_MS - 10_000)  # well past threshold

    await transport._dispatch_aliyun_event("/sys/testpk/testdn/app/down/thing/events", raw)

    transport.on_device_event.assert_not_called()


@pytest.mark.asyncio
async def test_event_without_any_timestamp_forwarded(transport: AliyunMQTTTransport):
    """Events with no usable envelope timestamp (time/generateTime/gmtCreate) are not dropped."""
    payload = json.loads(_make_event_envelope(0))
    payload["params"]["gmtCreate"] = 0  # the helper's fixture value would trip the fallback
    raw = json.dumps(payload).encode()

    await transport._dispatch_aliyun_event("/sys/testpk/testdn/app/down/thing/events", raw)

    transport.on_device_event.assert_called_once()


@pytest.mark.asyncio
async def test_event_without_time_falls_back_to_gmt_create(transport: AliyunMQTTTransport):
    """Events missing params.time are filtered via gmtCreate (stale fixture value → dropped)."""
    raw = _make_event_envelope(0)  # helper sets gmtCreate=1714000000000 (ancient)

    await transport._dispatch_aliyun_event("/sys/testpk/testdn/app/down/thing/events", raw)

    transport.on_device_event.assert_not_called()


def _make_properties_envelope(generate_time_ms: int) -> bytes:
    """Realistic thing/properties envelope: carries generateTime/gmtCreate, NO params.time."""
    payload = {
        "method": "thing.properties",
        "id": "test-props-id",
        "version": "1.0",
        "params": {
            "deviceType": "LawnMower",
            "checkFailedData": {},
            "groupIdList": [],
            "_tenantId": "",
            "groupId": "",
            "categoryKey": "LawnMower",
            "batchId": "",
            "gmtCreate": generate_time_ms,
            "productKey": "testpk",
            "generateTime": generate_time_ms,
            "deviceName": "testdn",
            "_traceId": "",
            "iotId": "test_iot_id",
            "JMSXDeliveryCount": 1,
            "checkLevel": 0,
            "qos": 1,
            "requestId": "1",
            "_categoryKey": "TmallGenie.LawnMower",
            "namespace": "",
            "tenantId": "",
            "thingType": "DEVICE",
            "items": {"batteryPercentage": {"time": generate_time_ms, "value": 80}},
            "tenantInstanceId": "",
        },
    }
    return json.dumps(payload).encode()


@pytest.mark.asyncio
async def test_stale_properties_dropped(transport: AliyunMQTTTransport):
    """Stale thing/properties are dropped via generateTime (they carry no params.time)."""
    now_ms = int(time.time() * 1000)
    raw = _make_properties_envelope(now_ms - _STALE_EVENT_THRESHOLD_MS - 30_000)

    await transport._dispatch_aliyun_event("/sys/testpk/testdn/app/down/thing/properties", raw)

    transport.on_device_properties.assert_not_called()


@pytest.mark.asyncio
async def test_fresh_properties_forwarded(transport: AliyunMQTTTransport):
    """Fresh thing/properties (recent generateTime, no params.time) are forwarded."""
    now_ms = int(time.time() * 1000)
    raw = _make_properties_envelope(now_ms - 5_000)

    await transport._dispatch_aliyun_event("/sys/testpk/testdn/app/down/thing/properties", raw)

    transport.on_device_properties.assert_called_once()


@pytest.mark.asyncio
async def test_event_at_threshold_boundary_forwarded(transport: AliyunMQTTTransport):
    """Events exactly at the threshold age are forwarded (not strictly greater)."""
    now_ms = int(time.time() * 1000)
    # Subtract threshold minus a small margin to stay within bounds
    raw = _make_event_envelope(now_ms - _STALE_EVENT_THRESHOLD_MS + 1_000)

    await transport._dispatch_aliyun_event("/sys/testpk/testdn/app/down/thing/events", raw)

    transport.on_device_event.assert_called_once()


# ---------------------------------------------------------------------------
# Device-unbound (Aliyun 29004): detach (non-disconnecting) + migrate/remove hook
# ---------------------------------------------------------------------------


async def test_detach_transport_pops_without_disconnect() -> None:
    """detach_transport removes the transport from the handle WITHOUT disconnecting it.

    The Aliyun transport is account-shared; disconnecting it would kill cloud for
    every other device on the account.  Idempotent: a second call returns None.
    """
    handle = make_handle()
    aliyun = make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    await handle.add_transport(aliyun)

    removed = handle.detach_transport(TransportType.CLOUD_ALIYUN)

    assert removed is aliyun
    assert handle.get_transport(TransportType.CLOUD_ALIYUN) is None
    aliyun.disconnect.assert_not_awaited()
    # Idempotent — already gone.
    assert handle.detach_transport(TransportType.CLOUD_ALIYUN) is None


async def test_device_unbound_detaches_aliyun_and_schedules_hook() -> None:
    """A 29004 detaches the Aliyun transport (not disconnect) and fires the unbound hook once.

    No BLE present → send_raw re-raises the DeviceUnboundException; the
    permanent detach must NOT set mqtt_reported_offline.
    """
    handle = make_handle()
    aliyun = make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    await handle.add_transport(aliyun)
    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED)
    hook = AsyncMock()
    handle.on_device_unbound = hook

    handle._send_marked = AsyncMock(  # type: ignore[method-assign]
        side_effect=DeviceUnboundException(29004, "iot-id")
    )

    with pytest.raises(DeviceUnboundException):
        await handle.send_raw(b"\x01")
    await asyncio.sleep(0)  # let the fire-and-forget hook task run

    assert handle.get_transport(TransportType.CLOUD_ALIYUN) is None
    aliyun.disconnect.assert_not_awaited()
    hook.assert_awaited_once_with(handle)
    assert handle.availability.mqtt_reported_offline is False
    await handle.stop()


async def test_device_unbound_retries_over_ble() -> None:
    """A 29004 (always from Aliyun) detaches Aliyun and the command retries over BLE.

    BLE starts disconnected so Aliyun is chosen first; it comes online for the retry
    (mirrors the device-offline fallback test).
    """
    handle = make_handle()
    aliyun = make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble = make_transport(TransportType.BLE, connected=False)  # not connected → Aliyun chosen
    await handle.add_transport(aliyun)
    await handle.add_transport(ble)
    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED)
    handle.on_device_unbound = AsyncMock()

    call_count = 0

    async def _side_effect(transport: object, payload: bytes) -> None:  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            ble.is_connected = True  # BLE comes online between Aliyun failure and retry
            raise DeviceUnboundException(29004, "iot-id")
        # second call (BLE) succeeds

    handle._send_marked = AsyncMock(side_effect=_side_effect)  # type: ignore[method-assign]

    await handle.send_raw(b"\x01")

    assert handle._send_marked.call_count == 2
    assert handle._send_marked.await_args_list[1].args[0] is ble
    assert handle.get_transport(TransportType.CLOUD_ALIYUN) is None
    await handle.stop()


async def test_device_unbound_hook_fires_only_once() -> None:
    """A second _on_device_unbound (transport already detached) must not re-fire the hook."""
    handle = make_handle()
    aliyun = make_transport(TransportType.CLOUD_ALIYUN, connected=True)
    await handle.add_transport(aliyun)
    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED)
    hook = AsyncMock()
    handle.on_device_unbound = hook

    await handle._on_device_unbound(aliyun)  # noqa: SLF001
    await handle._on_device_unbound(aliyun)  # noqa: SLF001 — already detached
    await asyncio.sleep(0)

    hook.assert_awaited_once_with(handle)
