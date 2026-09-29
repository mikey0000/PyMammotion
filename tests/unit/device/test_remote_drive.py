"""``RemoteDriveSession`` lifecycle: token grant, keep-alive, confirmation, exits and token renewal.

A port of ``RemoteDriveControllerImpl`` (app 2.3.20.30).  Frame pacing and ack handling live in
``test_remote_drive_frames.py``.  Time only moves when a test calls ``FakeDriveClock.advance``;
the session's cloud send is a ``FrameSink`` that decodes and records every payload.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

from pymammotion.device import remote_drive
from pymammotion.device.remote_drive import (
    DriveClock,
    FpvTokenSource,
    LoopDriveClock,
    RemoteDriveError,
    RemoteDriveEventKind,
    RemoteDrivePhase,
    mask_account,
)
from pymammotion.http.model.fpv_control import FpvControl
from pymammotion.http.model.http import Response, UnauthorizedExceptionError
from pymammotion.proto import DrvCtrlLink, DrvSessionExitNfty, LubaMsg, MctlDriver
from pymammotion.transport.base import NoTransportAvailableError, TransportType
from tests._helpers import wait_until
from tests.unit.device._drive_helpers import DriveRig, make_active_rig, make_drive_rig, make_grant
from tests.unit.device._fakes import FakeDriveClock, ScriptedTokens

#: Upper bound on a call that must return on its own; only reached if the session hangs.
_TEST_BOUND_S = 2.0


async def test_a_grant_enters_the_safety_notice_and_sends_a_keep_alive_at_once() -> None:
    rig = make_drive_rig()

    assert await rig.session.start() is True

    assert rig.session.phase is RemoteDrivePhase.SAFETY_NOTICE
    frames = [(f.ctrl_seq, f.set_linear_speed, f.set_angular_speed, f.token) for f in rig.sink.ctrl]
    assert frames == [(0, 0, 0, "ctl-1")]
    assert rig.sink.ctrl[0].channel is DrvCtrlLink.DRV_CTRL_IOT


async def test_keep_alives_repeat_every_three_seconds_with_sequence_zero() -> None:
    rig = make_drive_rig()
    await rig.session.start()

    await rig.clock.advance(2.999)
    assert len(rig.sink.ctrl) == 1
    await rig.clock.advance(6.001)

    assert [f.ctrl_seq for f in rig.sink.ctrl] == [0, 0, 0, 0]


async def test_an_unconfirmed_safety_notice_gives_up_after_three_minutes() -> None:
    rig = make_drive_rig(grant=make_grant(expireIn=3600))
    await rig.session.start()

    await rig.clock.advance(179.999)
    assert rig.session.phase is RemoteDrivePhase.SAFETY_NOTICE
    await rig.clock.advance(0.001)

    assert rig.session.phase is RemoteDrivePhase.IDLE
    assert rig.kinds == [RemoteDriveEventKind.SAFETY_NOTICE_TIMEOUT]
    assert rig.sink.kinds[-1] == "exit", "the session is released with an exit notify"
    assert all(f.set_linear_speed == 0 and f.ctrl_seq == 0 for f in rig.sink.ctrl), "no forced stop outside ACTIVE"


async def test_confirming_stops_the_keep_alive() -> None:
    rig = make_drive_rig()
    await rig.session.start()

    await rig.session.confirm()
    assert rig.clock.armed == 2, "only the token renewal and the idle countdown stay scheduled"
    await rig.clock.advance(9)

    assert rig.session.phase is RemoteDrivePhase.ACTIVE
    assert len(rig.sink.ctrl) == 1


async def test_an_occupied_device_refuses_the_session_and_names_who_holds_it() -> None:
    rig = make_drive_rig(grant=make_grant(deviceResult=9, token=None, preemptUser="other@example.com"))

    assert await rig.session.start() is False

    assert rig.session.phase is RemoteDrivePhase.IDLE
    assert [(e.kind, e.detail) for e in rig.events] == [(RemoteDriveEventKind.OCCUPIED_BY_OTHER, "other@example.com")]
    assert rig.sink.sent == []


async def test_an_unavailable_token_refuses_the_session_with_the_server_code() -> None:
    rig = make_drive_rig(grant=Response(code=1001, msg="no", data=FpvControl(device_result=0, token="x")))

    assert await rig.session.start() is False

    assert [(e.kind, e.detail) for e in rig.events] == [(RemoteDriveEventKind.TOKEN_UNAVAILABLE, "1001")]
    assert rig.sink.sent == []


async def test_a_rejected_login_on_the_token_request_propagates() -> None:
    rig = make_drive_rig()
    rig.tokens.requests = [UnauthorizedExceptionError("dead login")]

    with pytest.raises(UnauthorizedExceptionError):
        await rig.session.start()

    assert rig.session.phase is RemoteDrivePhase.IDLE


async def test_a_ble_only_device_refuses_before_asking_for_a_token() -> None:
    """The app drives a Bluetooth-only mower with the legacy DrvMotionCtrl, not a session."""
    rig = make_drive_rig(transports=(TransportType.BLE,))

    with pytest.raises(NoTransportAvailableError):
        await rig.session.start()

    assert rig.tokens.request_count == 0


async def test_a_device_the_cloud_called_offline_can_still_start() -> None:
    rig = make_drive_rig()
    handle = rig.handle
    handle.update_availability(TransportType.CLOUD_ALIYUN, handle.availability.mqtt, mqtt_reported_offline=True)
    assert handle.availability.mqtt_reported_offline is True

    assert await rig.session.start() is True
    assert len(rig.sink.ctrl) == 1, "the keep-alive went out"


async def test_starting_a_running_session_is_an_error() -> None:
    rig = make_drive_rig()
    await rig.session.start()

    with pytest.raises(RemoteDriveError):
        await rig.session.start()


async def test_confirming_outside_the_safety_notice_is_an_error() -> None:
    rig = make_drive_rig()

    with pytest.raises(RemoteDriveError):
        await rig.session.confirm()


async def test_stopping_an_active_session_forces_a_stop_then_releases_the_token() -> None:
    rig = await make_active_rig()
    await rig.session.drive(200, 0)

    await rig.session.stop()

    assert rig.sink.kinds[-2:] == ["frame", "exit"]
    stop = rig.sink.ctrl[-1]
    assert (stop.set_linear_speed, stop.set_angular_speed) == (0, 0)
    assert (rig.sink.exits[0].token, rig.sink.exits[0].channel) == ("ctl-1", DrvCtrlLink.DRV_CTRL_IOT)
    assert rig.session.phase is RemoteDrivePhase.IDLE


async def test_the_forced_stop_does_not_wait_for_the_in_flight_ack() -> None:
    rig = await make_active_rig()
    await rig.session.drive(200, 0)

    await rig.session.stop()

    assert [f.set_linear_speed for f in rig.sink.ctrl[1:]] == [200, 0]


async def test_stopping_during_the_safety_notice_only_releases_the_token() -> None:
    rig = make_drive_rig()
    await rig.session.start()

    await rig.session.stop()

    assert rig.sink.kinds == ["frame", "exit"], "the keep-alive, then the exit notify; no stop frame"


async def test_a_stopped_session_ignores_later_acks_and_timers() -> None:
    rig = await make_active_rig()
    await rig.session.drive(200, 0)
    await rig.session.stop()
    sent = len(rig.sink.sent)

    await rig.ack(1)
    await rig.clock.advance(700)

    assert len(rig.sink.sent) == sent
    assert rig.clock.armed == 0


async def test_a_stopped_session_can_start_again() -> None:
    rig = make_drive_rig()
    await rig.session.start()
    await rig.session.stop()
    rig.tokens.requests = [make_grant(token="ctl-2")]

    assert await rig.session.start() is True
    assert rig.sink.ctrl[-1].token == "ctl-2"


def _gate_requests(rig: DriveRig, count: int) -> list[asyncio.Event]:
    """Hold the next *count* token requests until the test sets their gates, in order."""
    rig.tokens.request_gates = [asyncio.Event() for _ in range(count)]
    return list(rig.tokens.request_gates)


async def _start_in_background(rig: DriveRig, *, requests: int = 1) -> asyncio.Task[bool]:
    """Start the session on its own task and return once its token request (the *requests*-th) is in flight."""
    task = asyncio.create_task(rig.session.start())
    await wait_until(lambda: rig.tokens.request_count == requests)
    return task


@pytest.mark.regression
async def test_a_token_granted_after_stopping_is_released_at_once() -> None:
    """Stopping while the token request was in flight released nothing, and the grant that then
    arrived was dropped without an exit notify, so the server held it for ``expireIn`` and the
    next start was refused as occupied."""
    rig = make_drive_rig()
    gate = _gate_requests(rig, 1)[0]
    starting = await _start_in_background(rig)

    await rig.session.stop()
    gate.set()

    assert await asyncio.wait_for(starting, _TEST_BOUND_S) is False
    assert [e.token for e in rig.sink.exits] == ["ctl-1"]
    assert rig.sink.ctrl == []
    assert rig.session.phase is RemoteDrivePhase.IDLE
    assert rig.session.grant is None
    assert rig.kinds == []


@pytest.mark.parametrize(
    "answer",
    [
        make_grant(deviceResult=9, token=None, preemptUser="other@example.com"),
        Response(code=500, msg="internal", data=None),
    ],
    ids=["occupied", "unavailable"],
)
async def test_a_refusal_arriving_after_stopping_sends_nothing_and_reports_nothing(
    answer: Response[FpvControl],
) -> None:
    rig = make_drive_rig(grant=answer)
    gate = _gate_requests(rig, 1)[0]
    starting = await _start_in_background(rig)

    await rig.session.stop()
    gate.set()

    assert await asyncio.wait_for(starting, _TEST_BOUND_S) is False
    assert rig.sink.sent == []
    assert rig.kinds == []
    assert rig.session.phase is RemoteDrivePhase.IDLE


async def test_a_token_request_failing_after_stopping_leaves_the_session_idle() -> None:
    rig = make_drive_rig()
    rig.tokens.requests = [ConnectionError("down")]
    gate = _gate_requests(rig, 1)[0]
    starting = await _start_in_background(rig)

    await rig.session.stop()
    gate.set()

    with pytest.raises(ConnectionError):
        await asyncio.wait_for(starting, _TEST_BOUND_S)
    assert rig.sink.sent == []
    assert rig.session.phase is RemoteDrivePhase.IDLE


@pytest.mark.regression
async def test_a_stale_grant_does_not_start_the_session_a_later_start_is_requesting() -> None:
    """start, stop, start: the first request's grant landed while the second was requesting and
    was taken for the second's, so a stopped start returned True and the real start was refused."""
    rig = make_drive_rig()
    rig.tokens.requests = [make_grant(token="ctl-1"), make_grant(token="ctl-2")]
    first_gate, second_gate = _gate_requests(rig, 2)
    first = await _start_in_background(rig)
    await rig.session.stop()
    second = await _start_in_background(rig, requests=2)

    first_gate.set()
    assert await asyncio.wait_for(first, _TEST_BOUND_S) is False
    second_gate.set()
    assert await asyncio.wait_for(second, _TEST_BOUND_S) is True

    assert [e.token for e in rig.sink.exits] == ["ctl-1"]
    assert [f.token for f in rig.sink.ctrl] == ["ctl-2"]
    assert rig.session.phase is RemoteDrivePhase.SAFETY_NOTICE
    await rig.session.stop()


@pytest.mark.parametrize(
    "refusal",
    [
        make_grant(deviceResult=9, token=None, preemptUser="other@example.com"),
        Response(code=500, msg="internal", data=None),
    ],
    ids=["occupied", "unavailable"],
)
async def test_a_stale_refusal_does_not_end_a_later_start(refusal: Response[FpvControl]) -> None:
    rig = make_drive_rig()
    rig.tokens.requests = [refusal, make_grant(token="ctl-2")]
    first_gate, second_gate = _gate_requests(rig, 2)
    first = await _start_in_background(rig)
    await rig.session.stop()
    second = await _start_in_background(rig, requests=2)

    first_gate.set()
    assert await asyncio.wait_for(first, _TEST_BOUND_S) is False
    assert rig.kinds == []
    assert rig.session.phase is RemoteDrivePhase.REQUESTING_TOKEN
    second_gate.set()

    assert await asyncio.wait_for(second, _TEST_BOUND_S) is True
    assert rig.sink.exits == []
    assert [f.token for f in rig.sink.ctrl] == ["ctl-2"]
    await rig.session.stop()


@pytest.mark.regression
async def test_a_stale_request_failing_does_not_idle_a_later_start() -> None:
    """start, stop, start: the first request failing reset the phase the second was requesting in."""
    rig = make_drive_rig()
    rig.tokens.requests = [ConnectionError("down"), make_grant(token="ctl-2")]
    first_gate, second_gate = _gate_requests(rig, 2)
    first = await _start_in_background(rig)
    await rig.session.stop()
    second = await _start_in_background(rig, requests=2)

    first_gate.set()
    with pytest.raises(ConnectionError):
        await asyncio.wait_for(first, _TEST_BOUND_S)
    assert rig.session.phase is RemoteDrivePhase.REQUESTING_TOKEN
    second_gate.set()

    assert await asyncio.wait_for(second, _TEST_BOUND_S) is True
    assert [f.token for f in rig.sink.ctrl] == ["ctl-2"]
    await rig.session.stop()


async def test_hands_off_for_the_granted_timeout_exits_the_session() -> None:
    rig = await make_active_rig(grant=make_grant(timeoutExit=4))

    await rig.clock.advance(3.999)
    assert rig.session.phase is RemoteDrivePhase.ACTIVE
    await rig.clock.advance(0.001)

    assert rig.session.phase is RemoteDrivePhase.IDLE
    assert rig.kinds == [RemoteDriveEventKind.IDLE_TIMEOUT]
    assert rig.sink.kinds[-2:] == ["frame", "exit"]


async def test_the_idle_timeout_defaults_to_ten_seconds() -> None:
    rig = await make_active_rig(grant=make_grant(timeoutExit=None))

    await rig.clock.advance(9.999)
    assert rig.session.phase is RemoteDrivePhase.ACTIVE
    await rig.clock.advance(0.001)

    assert rig.session.phase is RemoteDrivePhase.IDLE


async def test_driving_holds_off_the_idle_exit_and_letting_go_restarts_it() -> None:
    rig = await make_active_rig(grant=make_grant(timeoutExit=4))

    await rig.clock.advance(3)
    await rig.session.drive(200, 0)
    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms())
    await rig.clock.advance(5)
    assert rig.session.phase is RemoteDrivePhase.ACTIVE, "input cancelled the countdown"
    await rig.ack(len(rig.sink.ctrl) - 2, app_send_ts_ms=rig.clock.now_ms())
    await rig.session.drive(0, 0)
    await rig.clock.advance(4)

    assert rig.session.phase is RemoteDrivePhase.IDLE
    assert rig.kinds == [RemoteDriveEventKind.IDLE_TIMEOUT]


async def test_the_control_token_is_renewed_a_minute_before_it_expires() -> None:
    rig = make_drive_rig(grant=make_grant(expireIn=100))
    rig.tokens.refreshes = [make_grant(token="ctl-2", expireIn=100)]
    await rig.session.start()

    await rig.clock.advance(39.999)
    assert rig.tokens.refreshed_with == []
    await rig.clock.advance(0.001)
    await rig.clock.advance(3)

    assert rig.tokens.refreshed_with == ["ctl-1"]
    assert rig.sink.ctrl[-1].token == "ctl-2"


@pytest.mark.parametrize(
    ("answer", "kind"),
    [
        (make_grant(deviceResult=2, token=None), RemoteDriveEventKind.TOKEN_EXPIRED),
        (TimeoutError("slow"), RemoteDriveEventKind.TOKEN_EXPIRED),
    ],
    ids=["unavailable", "raised"],
)
async def test_a_failed_renewal_ends_the_session(
    answer: Response[FpvControl] | BaseException, kind: RemoteDriveEventKind
) -> None:
    rig = make_drive_rig(grant=make_grant(expireIn=100))
    rig.tokens.refreshes = [answer]
    await rig.session.start()

    await rig.clock.advance(40)

    assert rig.kinds == [kind]
    assert rig.session.phase is RemoteDrivePhase.IDLE
    assert rig.sink.kinds[-1] == "exit"


async def test_a_renewal_refused_as_occupied_is_a_bluetooth_preempt() -> None:
    """The app reads an occupied device on renewal as someone taking over over Bluetooth."""
    rig = make_drive_rig(grant=make_grant(expireIn=100))
    rig.tokens.refreshes = [make_grant(deviceResult=9, token=None, preemptUser="123456789")]
    await rig.session.start()

    await rig.clock.advance(40)

    assert [(e.kind, e.detail) for e in rig.events] == [(RemoteDriveEventKind.BLE_PREEMPT, "12****789")]
    assert rig.session.phase is RemoteDrivePhase.IDLE


async def test_a_renewal_that_raises_carries_the_error() -> None:
    rig = make_drive_rig(grant=make_grant(expireIn=100))
    rig.tokens.refreshes = [UnauthorizedExceptionError("dead login")]
    await rig.session.start()

    await rig.clock.advance(40)

    assert rig.kinds == [RemoteDriveEventKind.TOKEN_EXPIRED]
    assert isinstance(rig.events[0].error, UnauthorizedExceptionError)


async def test_a_token_without_an_expiry_is_never_renewed() -> None:
    rig = make_drive_rig(grant=make_grant(expireIn=None))
    await rig.session.start()

    assert rig.clock.armed == 2, "only the keep-alive and the safety timeout are scheduled"
    await rig.clock.advance(179)
    assert rig.tokens.refreshed_with == []


async def test_with_video_required_a_session_will_not_start_before_the_first_frame() -> None:
    rig = make_drive_rig(require_video=True)

    with pytest.raises(RemoteDriveError):
        await rig.session.start()

    assert rig.tokens.request_count == 0


async def test_with_video_required_a_session_starts_once_video_is_ready() -> None:
    rig = make_drive_rig(require_video=True)
    await rig.session.set_video_ready(ready=True)

    assert await rig.session.start() is True


async def test_with_video_required_losing_video_ends_an_active_session() -> None:
    rig = make_drive_rig(require_video=True)
    await rig.session.set_video_ready(ready=True)
    await rig.session.start()
    await rig.session.confirm()

    await rig.session.set_video_ready(ready=False)

    assert rig.kinds == [RemoteDriveEventKind.VIDEO_UNAVAILABLE]
    assert rig.session.phase is RemoteDrivePhase.IDLE
    assert rig.sink.kinds[-2:] == ["frame", "exit"]


async def test_without_video_required_video_state_is_ignored() -> None:
    rig = make_drive_rig()
    assert await rig.session.start() is True
    await rig.session.confirm()

    await rig.session.set_video_ready(ready=False)

    assert rig.session.phase is RemoteDrivePhase.ACTIVE
    assert rig.events == []


async def test_the_devices_own_exit_notice_changes_nothing() -> None:
    """The app logs ``toapp_session_exit_nfty`` and otherwise ignores it."""
    rig = await make_active_rig()

    await rig.handle.broker.on_message(LubaMsg(driver=MctlDriver(toapp_session_exit_nfty=DrvSessionExitNfty())))
    await rig.clock.advance(0)

    assert rig.session.phase is RemoteDrivePhase.ACTIVE
    assert rig.events == []


async def test_the_grant_is_exposed_while_the_session_holds_it() -> None:
    rig = make_drive_rig(grant=make_grant(fps4G=12.5))
    await rig.session.start()

    assert rig.session.grant is not None
    assert rig.session.grant.fps_4g == 12.5
    await rig.session.stop()
    assert rig.session.grant is None


def test_the_loop_clock_is_the_monotonic_clock_anchored_to_the_epoch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app's ``MonotonicClock``: epoch time at creation, advanced by the monotonic clock only."""
    fake = SimpleNamespace(time=lambda: 1_700_000_000.0, monotonic=lambda: 100.0)
    monkeypatch.setattr(remote_drive, "time", fake)
    clock = LoopDriveClock()

    fake.time = lambda: 1_600_000_000.0
    fake.monotonic = lambda: 100.25

    assert clock.now_ms() == 1_700_000_000_250


async def test_the_loop_clock_runs_a_callback_and_honours_cancel() -> None:
    clock = LoopDriveClock()
    ran: list[str] = []

    async def _mark(name: str) -> None:
        ran.append(name)

    clock.call_later(0, lambda: _mark("cancelled")).cancel()
    clock.call_later(0, lambda: _mark("kept"))
    await wait_until(lambda: "kept" in ran)

    assert ran == ["kept"]


async def test_input_before_confirmation_is_ignored() -> None:
    rig = make_drive_rig()
    await rig.session.start()

    await rig.session.drive(100, 0)
    await rig.clock.advance(1)

    assert [f.set_linear_speed for f in rig.sink.ctrl] == [0], "only the keep-alive"
    assert rig.session.phase is RemoteDrivePhase.SAFETY_NOTICE


@pytest.mark.parametrize(
    ("account", "masked"),
    [
        ("123456789", "12****789"),
        ("12345", "12345"),
        ("1234", "1234"),
        ("user@x.y", "user@x.y"),
        (" ", None),
        (None, None),
    ],
)
def test_an_account_is_masked_the_way_the_app_masks_it(account: str | None, masked: str | None) -> None:
    assert mask_account(account) == masked


async def test_stopping_survives_an_exit_notify_that_fails() -> None:
    rig = make_drive_rig()
    await rig.session.start()
    rig.sink.failures = [RuntimeError("cloud said no")]

    await rig.session.stop()

    assert rig.sink.kinds[-1] == "exit"
    assert rig.session.phase is RemoteDrivePhase.IDLE


async def test_stopping_is_bounded_when_the_exit_notify_hangs() -> None:
    rig = make_drive_rig(invoke_timeout=0)
    await rig.session.start()
    rig.sink.failures = ["hang"]

    await asyncio.wait_for(rig.session.stop(), _TEST_BOUND_S)

    assert rig.session.phase is RemoteDrivePhase.IDLE


@pytest.mark.parametrize(
    ("fake", "protocol"),
    [(FakeDriveClock, DriveClock), (ScriptedTokens, FpvTokenSource)],
    ids=["clock", "tokens"],
)
def test_the_fakes_keep_the_protocols_signatures(fake: type, protocol: type) -> None:
    members = [name for name, _ in inspect.getmembers(protocol, inspect.isfunction) if not name.startswith("_")]
    assert members, "the protocol declares methods"
    for name in members:
        assert hasattr(fake, name), f"{fake.__name__} lacks {name}"
        expected = list(inspect.signature(getattr(protocol, name)).parameters)
        assert list(inspect.signature(getattr(fake, name)).parameters) == expected, name
