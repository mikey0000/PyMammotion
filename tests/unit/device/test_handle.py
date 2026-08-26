"""Tests for DeviceHandle and DeviceRegistry."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.aliyun.exceptions import DeviceOfflineException, DeviceUnboundException
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.proto import LubaMsg as RealLubaMsg
from pymammotion.state.device_state import DeviceAvailability, DeviceConnectionState, TransportAvailability
from pymammotion.transport.base import NoTransportAvailableError, TransportType
from tests.unit._helpers import make_mock_mowing_device, make_mock_transport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_device(online: bool = True, enabled: bool = True) -> MagicMock:
    """Return a MagicMock shaped like a MowingDevice."""
    return make_mock_mowing_device(online=online, enabled=enabled)


def make_transport(transport_type: TransportType, *, connected: bool = True) -> MagicMock:
    """Return a MagicMock shaped like a Transport."""
    return make_mock_transport(transport_type, connected=connected)


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
    # The raw bytes belong in the message — they are what the traceback cannot supply.
    assert payload.hex() in error_records[0].getMessage()
    # The offending field and bad value must still reach the log; logger.exception puts
    # them in the attached traceback rather than the message, so assert on the rendered
    # output as an operator would actually read it.
    assert error_records[0].exc_info is not None
    assert 'Field "bp_pos_y"' in caplog.text
    assert "invalid value [114, 30]" in caplog.text


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
from pymammotion.transport.base import TransportRateLimitedError, TransportType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rl_handle() -> DeviceHandle:
    return DeviceHandle(
        device_id="dev1",
        device_name="Luba-RL",
        initial_device=make_mock_mowing_device(),
    )


def _make_mqtt_transport(*, connected: bool = True) -> MagicMock:
    return make_mock_transport(TransportType.CLOUD_ALIYUN, connected=connected)


# ---------------------------------------------------------------------------
# _send_marked raises TransportRateLimitedError when transport is rate-limited
# ---------------------------------------------------------------------------


async def test_send_marked_raises_when_transport_rate_limited() -> None:
    """_send_marked() must raise TransportRateLimitedError without calling transport.send()."""
    handle = _make_rl_handle()
    mqtt = _make_mqtt_transport()
    mqtt.is_rate_limited = True
    mqtt.is_send_blocked = MagicMock(return_value=True)
    await handle.add_transport(mqtt)

    with pytest.raises(TransportRateLimitedError):
        await handle._send_marked(mqtt, b"\x01\x02\x03")  # noqa: SLF001

    mqtt.send.assert_not_awaited()


async def test_send_marked_passes_through_when_not_rate_limited() -> None:
    """_send_marked() calls transport.send() when the transport is not rate-limited."""
    handle = _make_rl_handle()
    mqtt = _make_mqtt_transport()
    mqtt.is_rate_limited = False
    await handle.add_transport(mqtt)

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
    await handle.add_transport(mqtt)

    await handle.send_raw(b"\x00")

    mqtt.set_rate_limited.assert_called_once()


async def test_send_raw_blocked_silently_when_already_rate_limited() -> None:
    """send_raw must silently drop the send (not call transport.send) when already rate-limited."""
    handle = _make_rl_handle()
    mqtt = _make_mqtt_transport()
    mqtt.is_rate_limited = True
    mqtt.is_send_blocked = MagicMock(return_value=True)
    await handle.add_transport(mqtt)

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
    await handle.add_transport(ble)

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
    mqtt.is_send_blocked = MagicMock(return_value=True)
    await handle.add_transport(mqtt)

    # Call send_raw three times while the transport is already rate-limited.
    await handle.send_raw(b"\x01")
    await handle.send_raw(b"\x02")
    await handle.send_raw(b"\x03")

    mqtt.set_rate_limited.assert_not_called()
    mqtt.send.assert_not_awaited()


# ===========================================================================
# RPT_START verification: two attempts, each waiting _RPT_ACK_TIMEOUT for the
# device's report stream to tick, with a quota-free re-sync before the retry.
# ===========================================================================
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.device.handle import DeviceHandle


@pytest.fixture
def rpt_handle(monkeypatch: pytest.MonkeyPatch) -> DeviceHandle:
    """Bare DeviceHandle with just the state ``_send_rpt_start_verified`` touches.

    We bypass ``DeviceHandle.__init__`` entirely (it brings up a queue, reducer
    etc. that aren't relevant here).  ``commands`` is a ``@property``, so we
    monkeypatch the descriptor at the class level to return our mock.
    """
    h = DeviceHandle.__new__(DeviceHandle)
    h.device_name = "Luba-TEST"
    h._last_report_data_at = 0.0
    h._report_data_event = asyncio.Event()
    mocked_commands = MagicMock()
    mocked_commands.send_todev_ble_sync = MagicMock(return_value=b"\xAAsync")
    monkeypatch.setattr(DeviceHandle, "commands", property(lambda self: mocked_commands))
    return h


def _feed_report(handle: DeviceHandle) -> None:
    """Simulate a ``toapp_report_data`` frame landing, as ``on_raw_message`` would."""
    handle._last_report_data_at = handle._last_report_data_at + 1.0
    handle._report_data_event.set()


@pytest.fixture(autouse=True)
def _fast_ack_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the 5 s ack window so timeout paths don't stall the suite."""
    monkeypatch.setattr("pymammotion.device.handle._RPT_ACK_TIMEOUT", 0.05)


async def test_success_returns_true_and_sends_once(rpt_handle: DeviceHandle) -> None:
    """A report frame during attempt 1 → True, one send, no sync."""
    cmd_bytes = b"\xBBcmd"
    sync_fn = AsyncMock()

    async def transport_send(_payload: bytes) -> None:
        _feed_report(rpt_handle)

    send_spy = AsyncMock(side_effect=transport_send)

    result = await rpt_handle._send_rpt_start_verified(cmd_bytes, send_spy, sync_fn)

    assert result is True
    send_spy.assert_awaited_once_with(cmd_bytes)
    sync_fn.assert_not_awaited()


async def test_retry_syncs_before_resending(rpt_handle: DeviceHandle) -> None:
    """Attempt 1 draws nothing → re-sync, then re-send; report on attempt 2 → True."""
    cmd_bytes = b"\xBBcmd"
    calls: list[str] = []

    async def sync_fn() -> None:
        calls.append("sync")

    async def transport_send(_payload: bytes) -> None:
        calls.append("cmd")
        if calls.count("cmd") == 2:  # only the retry draws a report
            _feed_report(rpt_handle)

    result = await rpt_handle._send_rpt_start_verified(cmd_bytes, transport_send, sync_fn)

    assert result is True
    assert calls == ["cmd", "sync", "cmd"], f"Send order wrong; got {calls!r}"


async def test_no_report_after_both_attempts_returns_false(rpt_handle: DeviceHandle) -> None:
    """Neither attempt draws a report frame → False, no raise, two sends."""
    cmd_bytes = b"\xBBcmd"
    transport_send = AsyncMock()

    result = await rpt_handle._send_rpt_start_verified(cmd_bytes, transport_send, AsyncMock())

    assert result is False
    assert transport_send.await_count == 2


async def test_sync_failure_does_not_abort_retry(rpt_handle: DeviceHandle) -> None:
    """A flaky re-sync must not block the retry send itself."""
    cmd_bytes = b"\xBBcmd"
    sync_fn = AsyncMock(side_effect=RuntimeError("flaky sync write"))

    async def transport_send(_payload: bytes) -> None:
        if send_spy.await_count == 2:
            _feed_report(rpt_handle)

    send_spy = AsyncMock(side_effect=transport_send)

    result = await rpt_handle._send_rpt_start_verified(cmd_bytes, send_spy, sync_fn)

    assert result is True
    assert send_spy.await_count == 2


async def test_defaults_to_quota_free_force_sync(rpt_handle: DeviceHandle, monkeypatch: pytest.MonkeyPatch) -> None:
    """Omitting sync_fn routes the retry nudge through _force_sync, not a quota-counted send.

    Regression guard for the original bug: the nudge used to go out via ``send_raw``,
    charging the cloud send quota for what is a keep-alive.
    """
    forced = AsyncMock()
    monkeypatch.setattr(DeviceHandle, "_force_sync", forced)
    transport_send = AsyncMock()

    result = await rpt_handle._send_rpt_start_verified(b"\xBBcmd", transport_send)

    assert result is False
    forced.assert_awaited_once()


async def test_frame_already_in_flight_counts(rpt_handle: DeviceHandle) -> None:
    """A report landing concurrently with the send resolves the wait.

    The broker-key approach missed these: a frame that arrived microseconds before the
    request was registered did not resolve it, so a healthily-streaming device still ate
    a redundant retry.
    """
    cmd_bytes = b"\xBBcmd"

    async def transport_send(_payload: bytes) -> None:
        asyncio.get_running_loop().call_soon(_feed_report, rpt_handle)

    result = await rpt_handle._send_rpt_start_verified(cmd_bytes, AsyncMock(side_effect=transport_send), AsyncMock())

    assert result is True


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
    return make_mock_transport(transport_type, connected=connected)


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
# active_transport() selection matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ble", "mqtt", "prefer_ble", "expected"),
    [
        pytest.param(True, True, False, TransportType.BLE, id="both-connected-default-picks-ble"),
        pytest.param(True, True, True, TransportType.BLE, id="both-connected-prefer-ble-picks-ble"),
        pytest.param(True, False, False, TransportType.BLE, id="connected-ble-beats-disconnected-mqtt"),
        pytest.param(False, True, False, TransportType.CLOUD_ALIYUN, id="disconnected-ble-yields-to-mqtt"),
        pytest.param(False, True, True, TransportType.CLOUD_ALIYUN, id="prefer-ble-still-yields-when-ble-down"),
        pytest.param(True, None, True, TransportType.BLE, id="ble-only-connected"),
        pytest.param(False, None, True, TransportType.BLE, id="ble-only-disconnected-still-selected"),
        pytest.param(None, True, False, TransportType.CLOUD_ALIYUN, id="mqtt-only-connected"),
        pytest.param(None, False, False, TransportType.CLOUD_ALIYUN, id="mqtt-only-disconnected-still-selected"),
    ],
)
async def test_active_transport_selection_matrix(
    ble: bool | None, mqtt: bool | None, prefer_ble: bool, expected: TransportType
) -> None:
    """The full active_transport() decision table.

    Connected BLE always wins (lower latency, bypasses the cloud throttle); a
    disconnected-but-registered BLE only wins when it is the sole transport —
    otherwise a working MQTT takes the send while BLE reconnects in the
    background.  A disconnected transport is still selected when it is all
    there is: send_raw owns the reconnect, so routing stays deterministic.
    """
    handle = _make_handle(prefer_ble=prefer_ble)
    if mqtt is not None:
        await handle.add_transport(_make_transport(TransportType.CLOUD_ALIYUN, connected=mqtt))
    if ble is not None:
        await handle.add_transport(_make_transport(TransportType.BLE, connected=ble))

    assert handle.active_transport().transport_type is expected

# ---------------------------------------------------------------------------
# BLE-only
# ---------------------------------------------------------------------------


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
    await handle.add_transport(ble)

    new_device = MagicMock()
    await client.update_ble_device("Luba-UPD", new_device)

    assert ble._ble_device is new_device


# ===========================================================================
# The method waits for a transport to be ready: BLE counts the instant it
# ===========================================================================

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


# ---------------------------------------------------------------------------
# Firmware exemption — is_send_blocked must agree at every layer
# (regression: _send_marked used to check is_rate_limited without the firmware
# exemption that transport.send() applies, permanently blocking all commands
# and sagas for quota-free-firmware devices once the window filled or a 429
# set the ban — while telemetry kept flowing.)
# ---------------------------------------------------------------------------


async def test_send_marked_allows_exempt_firmware_while_rate_limited() -> None:
    """_send_marked() must send when the transport exempts this firmware.

    The pre-check must use the same is_send_blocked predicate as
    transport.send() — it must never block a send the transport would allow.
    """
    handle = _make_rl_handle()
    mqtt = _make_mqtt_transport()
    mqtt.is_rate_limited = True  # quota/ban active...
    mqtt.is_send_blocked = MagicMock(return_value=False)  # ...but firmware is exempt
    await handle.add_transport(mqtt)

    await handle._send_marked(mqtt, b"\x01\x02\x03")  # noqa: SLF001

    mqtt.send.assert_awaited_once()


async def test_send_marked_passes_firmware_version_to_is_send_blocked() -> None:
    """The pre-check must consult is_send_blocked with the handle's firmware version."""
    handle = _make_rl_handle()
    mqtt = _make_mqtt_transport()
    await handle.add_transport(mqtt)

    await handle._send_marked(mqtt, b"\x01")  # noqa: SLF001

    mqtt.is_send_blocked.assert_called_once_with(handle.firmware_version)


# ---------------------------------------------------------------------------
# Queue gate symmetry on BLE loss
# (BLE CONNECTED opens the gate as a fallback send path; if BLE then drops
# while MQTT is still mid-reconnect, nothing re-closed it and every queued
# command was dispatched into a window with no usable transport.)
# ---------------------------------------------------------------------------


async def test_ble_disconnect_repauses_gate_while_mqtt_reconnecting() -> None:
    """Losing the BLE fallback must re-close the gate when MQTT is not connected."""
    mqtt = make_transport(TransportType.CLOUD_ALIYUN, connected=False)
    mqtt.availability = TransportAvailability.CONNECTING
    ble = make_transport(TransportType.BLE)
    handle = make_handle(mqtt_transport=mqtt, ble_transport=ble)
    handler = handle._make_availability_handler(TransportType.BLE)  # noqa: SLF001
    assert handle.queue._transport_gate.is_set() is True  # noqa: SLF001

    await handler(TransportAvailability.DISCONNECTED)

    assert handle.queue._transport_gate.is_set() is False  # noqa: SLF001


async def test_ble_disconnect_leaves_gate_open_when_mqtt_connected() -> None:
    """A BLE drop must not gate the queue while MQTT can still carry commands."""
    mqtt = make_transport(TransportType.CLOUD_ALIYUN)
    ble = make_transport(TransportType.BLE)
    handle = make_handle(mqtt_transport=mqtt, ble_transport=ble)
    handler = handle._make_availability_handler(TransportType.BLE)  # noqa: SLF001

    await handler(TransportAvailability.DISCONNECTED)

    assert handle.queue._transport_gate.is_set() is True  # noqa: SLF001


async def test_on_ble_connected_is_noop_while_stopping() -> None:
    """_on_ble_connected runs detached, so it can land after stop() latched _stopping.

    start() clears that flag, which would restart the queue and the MQTT activity
    loop on a handle that is shutting down.
    """
    handle = make_handle()
    handle._stopping = True  # noqa: SLF001

    await handle._on_ble_connected()  # noqa: SLF001

    assert handle._stopping is True  # noqa: SLF001
    assert handle.queue._task is None  # noqa: SLF001
    assert handle._keep_alive_task is None  # noqa: SLF001
