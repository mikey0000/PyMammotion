"""``RemoteDriveSession`` frame traffic: pacing, sequence numbers, acks and the faults they carry.

Ports ``enqueueRemoteSpeed`` / ``onSessionCtrlAck`` / ``onSessionIotInvokeResult`` of the app's
``RemoteDriveControllerImpl`` (2.3.20.30): one frame in flight, at least 150 ms between frames,
the last non-zero speed held after each ack, the sequence restarted after a 1 s gap or an invoke
timeout, three consecutive timeouts a fault.  Every rig here starts ACTIVE with only its
keep-alive sent, so ``sink.ctrl[1:]`` are the frames under test.
"""

from __future__ import annotations

import asyncio

import pytest

from pymammotion.aliyun.exceptions import GatewayTimeoutException
from pymammotion.device.remote_drive import INVOKE_TIMEOUT_S, RemoteDriveEventKind, RemoteDrivePhase
from pymammotion.transport.base import TransportRateLimitedError
from tests.unit.device._drive_helpers import DriveRig, make_active_rig, make_grant, make_session_ack
from tests.unit.device._fakes import FAKE_CLOCK_START_MS

#: Upper bound on a call that must return on its own; only reached if the session hangs.
_TEST_BOUND_S = 2.0


def _speeds(rig: DriveRig) -> list[tuple[int, int, int]]:
    """``(ctrl_seq, linear, angular)`` of every frame after the keep-alive."""
    return [(f.ctrl_seq, f.set_linear_speed, f.set_angular_speed) for f in rig.sink.ctrl[1:]]


async def test_the_first_frame_goes_out_at_once_with_sequence_zero() -> None:
    rig = await make_active_rig()

    await rig.session.drive(300, 45)

    assert _speeds(rig) == [(0, 300, 45)]
    frame = rig.sink.ctrl[1]
    assert (frame.app_send_ts_ms, frame.vehicle_send_ts_ms, frame.token) == (FAKE_CLOCK_START_MS, 0, "ctl-1")


async def test_only_one_frame_is_in_flight_and_the_latest_input_wins() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)

    await rig.session.drive(200, 0)
    await rig.session.drive(300, 0)
    await rig.clock.advance(0.5)
    assert _speeds(rig) == [(0, 100, 0)], "nothing more until the ack"
    await rig.ack(0, app_send_ts_ms=FAKE_CLOCK_START_MS)

    assert _speeds(rig) == [(0, 100, 0), (1, 300, 0)]


async def test_input_after_the_interval_still_waits_for_the_outstanding_ack() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)
    await rig.clock.advance(0.5)

    await rig.session.drive(200, 0)
    await rig.clock.advance(0.5)

    assert _speeds(rig) == [(0, 100, 0)]


async def test_the_next_frame_waits_out_150_ms_from_the_last_send() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)
    await rig.session.drive(200, 0)
    await rig.clock.advance(0.05)

    await rig.ack(0, app_send_ts_ms=FAKE_CLOCK_START_MS)
    await rig.clock.advance(0.099)
    assert len(_speeds(rig)) == 1
    await rig.clock.advance(0.001)

    assert _speeds(rig)[-1] == (1, 200, 0)


async def test_input_during_an_in_flight_hold_repeat_waits_for_its_ack() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)
    await rig.clock.advance(0.03)
    await rig.ack(0, app_send_ts_ms=FAKE_CLOCK_START_MS)
    await rig.clock.advance(0.2)
    sent = len(_speeds(rig))

    await rig.session.drive(250, 0)
    assert len(_speeds(rig)) == sent, "the hold-repeat frame is still in flight"
    await rig.ack(sent - 1, app_send_ts_ms=rig.clock.now_ms())
    assert len(_speeds(rig)) == sent, "and after its ack the next frame still waits out 150 ms"
    await rig.clock.advance(0.15)

    assert _speeds(rig)[-1][1:] == (250, 0)


async def test_a_held_speed_is_repeated_after_each_ack() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 20)

    for seq in range(3):
        await rig.ack(seq, app_send_ts_ms=rig.clock.now_ms())
        await rig.clock.advance(0.15)

    assert _speeds(rig) == [(0, 100, 20), (1, 100, 20), (2, 100, 20), (3, 100, 20)]


async def test_a_zero_speed_is_not_repeated() -> None:
    rig = await make_active_rig()
    await rig.session.drive(0, 0)

    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms())
    await rig.clock.advance(1)

    assert _speeds(rig) == [(0, 0, 0)]


async def test_the_vehicle_timestamp_of_an_ack_is_echoed_in_the_next_frame() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)

    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms(), vehicle_send_ts_ms=777)
    await rig.clock.advance(0.15)

    assert rig.sink.ctrl[-1].vehicle_send_ts_ms == 777


async def test_an_ack_for_another_sequence_is_ignored() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)
    await rig.session.drive(200, 0)

    await rig.ack(5, app_send_ts_ms=rig.clock.now_ms())
    await rig.clock.advance(1)

    assert _speeds(rig) == [(0, 100, 0)]


async def test_a_reverse_request_is_sent_as_zero_linear_speed() -> None:
    """The app refuses to reverse over IoT (``applyNoReverseLinearSpeed``)."""
    rig = await make_active_rig()

    await rig.session.drive(-300, 30)

    assert _speeds(rig) == [(0, 0, 30)]


async def test_the_sequence_restarts_after_more_than_a_second_without_a_frame() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)
    await rig.clock.advance(1.5)

    await rig.ack(0, app_send_ts_ms=FAKE_CLOCK_START_MS)

    assert _speeds(rig) == [(0, 100, 0), (0, 100, 0)]


async def test_letting_go_and_driving_again_restarts_the_sequence() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)
    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms())
    await rig.clock.advance(0.15)
    await rig.session.drive(0, 0)
    await rig.ack(1, app_send_ts_ms=rig.clock.now_ms())
    await rig.clock.advance(0.2)
    await rig.ack(2, app_send_ts_ms=rig.clock.now_ms())

    await rig.session.drive(100, 0)

    assert _speeds(rig) == [(0, 100, 0), (1, 100, 0), (2, 0, 0), (0, 100, 0)]


async def test_an_invoke_timeout_resends_from_sequence_zero() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)
    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms())
    rig.sink.failures = [TimeoutError()]
    await rig.clock.advance(0.15)

    await rig.clock.advance(0)

    assert _speeds(rig) == [(0, 100, 0), (1, 100, 0), (0, 100, 0)]
    assert rig.session.phase is RemoteDrivePhase.ACTIVE


async def test_a_gateway_timeout_counts_as_an_invoke_timeout() -> None:
    rig = await make_active_rig()
    rig.sink.failures = [GatewayTimeoutException(20056, "iot")]

    await rig.session.drive(100, 0)
    await rig.clock.advance(0)

    assert _speeds(rig) == [(0, 100, 0), (0, 100, 0)]


async def test_a_send_that_hangs_is_bounded_by_the_invoke_timeout() -> None:
    rig = await make_active_rig(invoke_timeout=0)
    rig.sink.failures = ["hang"]

    # The send honours the timeout the session hands it; the outer bound only guards the test.
    await asyncio.wait_for(rig.session.drive(100, 0), _TEST_BOUND_S)
    await rig.clock.advance(0)

    assert _speeds(rig) == [(0, 100, 0), (0, 100, 0)]


async def test_every_send_is_bounded_by_the_one_second_invoke_timeout() -> None:
    """The send is given the bound rather than wrapped in it, so a refresh between attempts runs untimed."""
    rig = await make_active_rig()
    await rig.session.drive(100, 0)

    await rig.session.stop()

    assert rig.sink.kinds == ["frame", "frame", "frame", "exit"]
    assert rig.sink.timeouts == [INVOKE_TIMEOUT_S] * 4
    assert INVOKE_TIMEOUT_S == 1.0


async def test_three_consecutive_invoke_timeouts_are_a_poor_network_fault() -> None:
    rig = await make_active_rig()
    rig.sink.failures = [TimeoutError(), TimeoutError(), TimeoutError()]

    await rig.session.drive(100, 0)
    await rig.clock.advance(0)

    assert rig.kinds == [RemoteDriveEventKind.NETWORK_POOR]
    assert _speeds(rig) == [(0, 100, 0), (0, 100, 0), (0, 100, 0), (1, 0, 0)]
    assert rig.sink.kinds[-1] == "exit"
    assert rig.session.phase is RemoteDrivePhase.IDLE


async def test_a_delivered_frame_resets_the_timeout_count() -> None:
    rig = await make_active_rig()
    rig.sink.failures = [TimeoutError(), TimeoutError(), None, TimeoutError(), TimeoutError()]

    await rig.session.drive(100, 0)
    await rig.clock.advance(0)
    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms())
    await rig.clock.advance(0.15)
    await rig.clock.advance(0)

    assert rig.events == []
    assert rig.session.phase is RemoteDrivePhase.ACTIVE


async def test_a_send_that_fails_outright_ends_the_session_with_the_error() -> None:
    rig = await make_active_rig()
    refusal = TransportRateLimitedError("banned")
    rig.sink.failures = [refusal]

    await rig.session.drive(100, 0)
    await rig.clock.advance(0)

    assert rig.kinds == [RemoteDriveEventKind.SEND_FAILED]
    assert rig.events[0].error is refusal
    assert rig.session.phase is RemoteDrivePhase.IDLE


@pytest.mark.parametrize(
    ("result", "kind", "detail"),
    [
        (4, RemoteDriveEventKind.NETWORK_POOR, None),
        (11, RemoteDriveEventKind.NETWORK_POOR, None),
        (6, RemoteDriveEventKind.TOKEN_EXPIRED, "6"),
        (7, RemoteDriveEventKind.TOKEN_EXPIRED, "7"),
        (8, RemoteDriveEventKind.OUT_OF_FENCE, None),
        (10, RemoteDriveEventKind.NO_LOC_MILEAGE_EXHAUSTED, None),
        (1, RemoteDriveEventKind.ENV_NOT_READY, "1"),
        (2, RemoteDriveEventKind.ENV_NOT_READY, "2"),
        (12, RemoteDriveEventKind.ENV_NOT_READY, "12"),
    ],
)
async def test_an_ack_result_maps_to_its_fault_and_ends_the_session(
    result: int, kind: RemoteDriveEventKind, detail: str | None
) -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)

    await rig.ack(0, result=result, app_send_ts_ms=rig.clock.now_ms())

    assert [(e.kind, e.detail) for e in rig.events] == [(kind, detail)]
    assert _speeds(rig)[-1][1:] == (0, 0), "a forced stop goes out first"
    assert rig.sink.kinds[-1] == "exit"
    assert rig.session.phase is RemoteDrivePhase.IDLE


async def test_a_bluetooth_preempt_names_the_masked_account() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)

    await rig.ack(0, result=9, preempt_account=123456789)

    assert [(e.kind, e.detail) for e in rig.events] == [(RemoteDriveEventKind.BLE_PREEMPT, "12****789")]
    assert _speeds(rig)[-1][1:] == (0, 0)
    assert rig.session.phase is RemoteDrivePhase.IDLE


async def test_a_bluetooth_preempt_without_an_account_has_no_detail() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)

    await rig.ack(0, result=9)

    assert [(e.kind, e.detail) for e in rig.events] == [(RemoteDriveEventKind.BLE_PREEMPT, None)]


@pytest.mark.parametrize("result", [3, 5])
async def test_a_soft_ack_result_keeps_driving(result: int) -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)

    await rig.ack(0, result=result, app_send_ts_ms=rig.clock.now_ms())
    await rig.clock.advance(0.15)

    assert rig.events == []
    assert _speeds(rig)[-1] == (1, 100, 0)


async def test_nearing_the_fence_stops_the_mower_and_pauses_input() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)

    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms(), fence_exceed_distance=5.0, localization_valid=True)
    await rig.session.drive(200, 0)
    await rig.clock.advance(1)

    assert rig.kinds == [RemoteDriveEventKind.APPROACH_FENCE]
    # Index 0 is the frame the fence ack answered.
    assert _speeds(rig)[1:] == [(1, 0, 0)], "a forced stop, and the paused input is dropped"
    assert rig.session.phase is RemoteDrivePhase.ACTIVE


async def test_acknowledging_the_fence_warning_resumes_input() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)
    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms(), fence_exceed_distance=6.0, localization_valid=True)
    await rig.clock.advance(1.5)

    rig.session.acknowledge_fence_warning()
    # The fence stop awaits no ack, so nothing is in flight and this goes out at once.
    await rig.session.drive(200, 0)

    assert _speeds(rig)[-1][1:] == (200, 0)


async def test_a_fence_distance_without_localisation_is_ignored() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)

    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms(), fence_exceed_distance=9.0, localization_valid=False)
    await rig.clock.advance(0.15)

    assert rig.events == []
    assert _speeds(rig)[-1] == (1, 100, 0)


async def test_high_measured_delay_warns_once_at_the_threshold_less_500_ms() -> None:
    rig = await make_active_rig(grant=make_grant(latencyThreshold=1500))
    await rig.session.drive(100, 0)

    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms(), measured_delay_ms=999)
    await rig.clock.advance(0.15)
    assert rig.events == []
    await rig.ack(1, app_send_ts_ms=rig.clock.now_ms(), measured_delay_ms=1000)
    await rig.clock.advance(0.15)
    await rig.ack(2, app_send_ts_ms=rig.clock.now_ms(), measured_delay_ms=4000)

    assert [(e.kind, e.detail) for e in rig.events] == [(RemoteDriveEventKind.LATENCY_HIGH, "1000")]
    assert rig.session.phase is RemoteDrivePhase.ACTIVE


async def test_no_latency_threshold_means_no_latency_warning() -> None:
    rig = await make_active_rig(grant=make_grant(latencyThreshold=None))
    await rig.session.drive(100, 0)

    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms(), measured_delay_ms=60_000)

    assert rig.events == []


async def test_new_input_supersedes_a_hold_repeat_that_has_not_gone_out() -> None:
    """A slow ack queues the held speed for "now"; input landing first must replace it, not trail it."""
    rig = await make_active_rig()
    await rig.session.drive(100, 0)
    await rig.clock.advance(0.2)
    await rig.handle.broker.on_message(make_session_ack(0, app_send_ts_ms=FAKE_CLOCK_START_MS))

    await rig.session.drive(0, 0)
    await rig.ack(1, app_send_ts_ms=rig.clock.now_ms())
    await rig.clock.advance(1)

    assert _speeds(rig) == [(0, 100, 0), (1, 0, 0)]


async def test_input_inside_the_interval_with_nothing_in_flight_waits_until_it_ends() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)
    await rig.clock.advance(0.2)
    await rig.ack(0, app_send_ts_ms=FAKE_CLOCK_START_MS)
    await rig.ack(1, app_send_ts_ms=rig.clock.now_ms())
    await rig.clock.advance(0.01)

    await rig.session.drive(250, 0)
    await rig.clock.advance(0.139)
    assert _speeds(rig) == [(0, 100, 0), (1, 100, 0)], "150 ms have not passed since the last send"
    await rig.clock.advance(0.001)

    assert _speeds(rig) == [(0, 100, 0), (1, 100, 0), (2, 250, 0)]


async def test_a_fence_distance_just_under_five_metres_keeps_driving() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)

    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms(), fence_exceed_distance=4.9, localization_valid=True)
    await rig.clock.advance(0.15)

    assert rig.events == []
    assert _speeds(rig) == [(0, 100, 0), (1, 100, 0)]


async def test_moving_back_from_the_fence_re_arms_the_warning() -> None:
    rig = await make_active_rig()
    await rig.session.drive(100, 0)
    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms(), fence_exceed_distance=6.0, localization_valid=True)
    rig.session.acknowledge_fence_warning()
    await rig.clock.advance(0.2)
    await rig.session.drive(100, 0)
    await rig.ack(
        rig.sink.ctrl[-1].ctrl_seq,
        app_send_ts_ms=rig.clock.now_ms(),
        fence_exceed_distance=1.0,
        localization_valid=True,
    )
    await rig.clock.advance(0.15)

    await rig.ack(
        rig.sink.ctrl[-1].ctrl_seq,
        app_send_ts_ms=rig.clock.now_ms(),
        fence_exceed_distance=6.0,
        localization_valid=True,
    )

    assert rig.kinds == [RemoteDriveEventKind.APPROACH_FENCE, RemoteDriveEventKind.APPROACH_FENCE]


async def test_a_timeout_resend_carries_input_queued_since_the_lost_frame() -> None:
    rig = await make_active_rig()
    rig.sink.failures = [TimeoutError()]
    await rig.session.drive(100, 0)

    await rig.session.drive(200, 0)
    await rig.clock.advance(0)

    assert _speeds(rig) == [(0, 100, 0), (0, 200, 0)]


@pytest.mark.regression
async def test_input_after_an_early_fence_acknowledgement_survives_the_deferred_stop() -> None:
    """The fence stop goes out a clock turn after the ack that triggers it.

    If the host acknowledged the warning and drove inside that turn, the deferred stop used
    to clear the queue on its way out, and the new input was silently lost.
    """
    rig = await make_active_rig()
    await rig.session.drive(300, 0)
    await rig.handle.broker.on_message(
        make_session_ack(0, app_send_ts_ms=rig.clock.now_ms(), fence_exceed_distance=6.0, localization_valid=True)
    )

    rig.session.acknowledge_fence_warning()
    await rig.session.drive(200, 0)
    await rig.clock.advance(0.15)

    assert _speeds(rig) == [(0, 300, 0), (1, 0, 0), (2, 200, 0)]


async def test_input_while_paused_before_the_fence_stop_goes_out_is_dropped() -> None:
    rig = await make_active_rig()
    await rig.session.drive(300, 0)
    await rig.handle.broker.on_message(
        make_session_ack(0, app_send_ts_ms=rig.clock.now_ms(), fence_exceed_distance=6.0, localization_valid=True)
    )

    await rig.session.drive(200, 0)
    await rig.clock.advance(1)

    assert _speeds(rig) == [(0, 300, 0), (1, 0, 0)]
    assert rig.kinds == [RemoteDriveEventKind.APPROACH_FENCE]


async def test_the_hold_repeat_queued_by_a_fence_ack_never_goes_out() -> None:
    """The fence ack also queues a hold-repeat of the old speed; acknowledging must not release it."""
    rig = await make_active_rig()
    await rig.session.drive(300, 0)
    await rig.ack(0, app_send_ts_ms=rig.clock.now_ms(), fence_exceed_distance=6.0, localization_valid=True)

    rig.session.acknowledge_fence_warning()
    await rig.clock.advance(0.5)

    assert _speeds(rig) == [(0, 300, 0), (1, 0, 0)]
