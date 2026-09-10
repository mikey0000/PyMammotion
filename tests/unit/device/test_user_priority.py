"""``Priority.USER`` — the direct send path for commands a person is waiting on.

A user-initiated command must not wait behind a saga, must not be TTL-dropped, and
must not be starved by the quota that exists to pace *polling*.  It must still pick
its transport the same way a queued command does, still be classified by the same
error buckets, and still stop dead at a cloud-imposed 429.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.aliyun.exceptions import DeviceOfflineException, GatewayTimeoutException, TooManyRequestsException
from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.mqtt.status import Params, Status, StatusType, ThingStatusMessage
from pymammotion.messaging.command_queue import Priority
from pymammotion.transport.ble import BLETransport
from pymammotion.transport.base import (
    NoTransportAvailableError,
    ReLoginRequiredError,
    TransportRateLimitedError,
    TransportType,
)
from tests._helpers import let_others_run, wait_until, make_mock_handle, make_mock_transport


async def _client_with(handle: object) -> MammotionClient:
    client = MammotionClient()
    await client._device_registry.register(handle)  # type: ignore[arg-type]  # noqa: SLF001
    return client


def _quota_exhausted(transport: MagicMock) -> None:
    """Shape the mock like a transport whose own budget is spent but has no 429 ban."""
    transport.is_cloud_banned = False
    transport.is_quota_exhausted = True
    transport.is_rate_limited = True
    transport.is_send_blocked = MagicMock(side_effect=lambda _fw, *, user_initiated=False: not user_initiated)


def _cloud_banned(transport: MagicMock) -> None:
    """Shape the mock like a transport the cloud has 429'd — blocked for everyone."""
    transport.is_cloud_banned = True
    transport.is_quota_exhausted = False
    transport.is_rate_limited = True
    transport.is_send_blocked = MagicMock(return_value=True)


async def test_user_command_sends_while_the_self_imposed_quota_is_exhausted() -> None:
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    _quota_exhausted(mqtt)
    mqtt.send_user = AsyncMock()
    handle = make_mock_handle(device_name="Luba-U1")
    await handle.add_transport(mqtt)
    client = await _client_with(handle)

    await client.send_command_with_args("Luba-U1", "start_job", priority=Priority.USER)

    mqtt.send_user.assert_awaited_once()
    mqtt.send.assert_not_awaited()
    await handle.stop()


async def test_a_queued_command_is_still_blocked_by_the_same_quota() -> None:
    """The exemption is opt-in per call site; nothing changes for the default path."""
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    _quota_exhausted(mqtt)
    handle = make_mock_handle(device_name="Luba-U2")
    await handle.add_transport(mqtt)

    with pytest.raises(TransportRateLimitedError):
        await handle.send_raw(b"\x01")

    mqtt.send.assert_not_awaited()
    await handle.stop()


async def test_a_cloud_ban_still_stops_a_user_command() -> None:
    """A 429 is the server saying stop; pushing through risks a longer ban."""
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    _cloud_banned(mqtt)
    mqtt.send_user = AsyncMock()
    handle = make_mock_handle(device_name="Luba-U3")
    await handle.add_transport(mqtt)

    with pytest.raises(TransportRateLimitedError):
        await handle.send_raw(b"\x01", user_initiated=True)

    mqtt.send_user.assert_not_awaited()
    await handle.stop()


async def test_ble_takes_the_plain_send_verb() -> None:
    """BLE has no quota, so there is nothing for the user path to exempt it from."""
    ble = make_mock_transport(TransportType.BLE)
    handle = make_mock_handle(device_name="Luba-U4", prefer_ble=True)
    await handle.add_transport(ble)

    await handle.send_raw(b"\x01", user_initiated=True)

    ble.send.assert_awaited_once()
    assert not hasattr(BLETransport, "send_user"), "send_user is a CloudTransport verb; BLE must not gain one"
    await handle.stop()


async def test_a_running_saga_does_not_delay_a_user_command() -> None:
    """The queue processor is sequential; the direct path is the only real preemption."""
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    mqtt.send_user = AsyncMock()
    handle = make_mock_handle(device_name="Luba-U5")
    await handle.add_transport(mqtt)
    client = await _client_with(handle)

    handle.queue.start()
    handle.queue._exclusive_active.clear()  # a saga holds the slot  # noqa: SLF001
    try:
        await asyncio.wait_for(
            client.send_command_with_args("Luba-U5", "start_job", priority=Priority.USER),
            timeout=1.0,
        )
    finally:
        handle.queue._exclusive_active.set()  # noqa: SLF001

    mqtt.send_user.assert_awaited_once()
    assert handle.queue._queue.empty(), "a direct command must never touch the queue"  # noqa: SLF001
    await handle.stop()


async def test_no_usable_transport_raises_instead_of_returning_silently() -> None:
    """A person pressed a button — silently doing nothing is the one unactionable outcome."""
    handle = make_mock_handle(device_name="Luba-U6")
    client = await _client_with(handle)

    with pytest.raises(NoTransportAvailableError):
        await client.send_command_with_args("Luba-U6", "start_job", priority=Priority.USER)

    await handle.stop()


async def test_a_queued_command_keeps_the_silent_return() -> None:
    handle = make_mock_handle(device_name="Luba-U7")
    client = await _client_with(handle)

    await client.send_command_with_args("Luba-U7", "start_job")  # must not raise

    await handle.stop()


async def test_a_gateway_timeout_is_retried_then_propagates() -> None:
    """Same retry the queue applies, but the caller learns it ultimately failed."""
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    mqtt.send_user = AsyncMock(side_effect=GatewayTimeoutException("timeout", "iot-1"))
    handle = make_mock_handle(device_name="Luba-U8")
    await handle.add_transport(mqtt)
    client = await _client_with(handle)

    with pytest.raises(GatewayTimeoutException):
        await client.send_command_with_args("Luba-U8", "start_job", priority=Priority.USER)

    assert mqtt.send_user.await_count == 3
    await handle.stop()


async def test_an_auth_error_escalates_and_propagates() -> None:
    """on_critical_error still fires — the host must get its reauth prompt either way."""
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    mqtt.send_user = AsyncMock(side_effect=ReLoginRequiredError("acct", "rejected"))
    handle = make_mock_handle(device_name="Luba-U9")
    await handle.add_transport(mqtt)
    escalated: list[Exception] = []
    handle.queue.on_critical_error = lambda exc: _collect(escalated, exc)
    client = await _client_with(handle)

    with pytest.raises(ReLoginRequiredError):
        await client.send_command_with_args("Luba-U9", "start_job", priority=Priority.USER)

    assert len(escalated) == 1
    await handle.stop()


async def test_send_command_and_wait_marks_the_send_user_initiated() -> None:
    """This entry point never used the queue; the quota exemption is all that changes."""
    handle = make_mock_handle(device_name="Luba-U10")
    handle.send_raw = AsyncMock()  # type: ignore[method-assign]
    async def _run_send(send_fn, **_kw):  # noqa: ANN001, ANN003, ANN202
        await send_fn()

    handle.broker.send_and_wait = AsyncMock(side_effect=_run_send)  # type: ignore[method-assign]
    client = await _client_with(handle)

    await client.send_command_and_wait("Luba-U10", "start_job", "toapp_dev_info", priority=Priority.USER)

    assert handle.send_raw.await_args.kwargs["user_initiated"] is True
    await handle.stop()


async def _collect(sink: list[Exception], exc: Exception) -> None:
    sink.append(exc)


async def test_a_cloud_429_propagates_after_arming_the_ban() -> None:
    """``send_raw`` used to swallow this, which the direct path cannot tolerate.

    ``execute_command(reraise=True)`` exists so the host learns a command did not
    land; a swallowed 429 reports success for a send the cloud rejected outright,
    and leaves HA's ``api_limit_exceeded`` handler unreachable.
    """
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    mqtt.send_user = AsyncMock(side_effect=TooManyRequestsException("429", "iot-1"))
    handle = make_mock_handle(device_name="Luba-U11")
    await handle.add_transport(mqtt)
    client = await _client_with(handle)

    with pytest.raises(TooManyRequestsException):
        await client.send_command_with_args("Luba-U11", "start_job", priority=Priority.USER)

    mqtt.set_rate_limited.assert_called_once()
    await handle.stop()


async def test_a_cloud_429_on_the_queued_path_is_still_absorbed_by_the_queue() -> None:
    """Propagating from send_raw must not start crashing the queue processor."""
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    mqtt.send = AsyncMock(side_effect=TooManyRequestsException("429", "iot-1"))
    handle = make_mock_handle(device_name="Luba-U12")
    await handle.add_transport(mqtt)
    client = await _client_with(handle)

    handle.queue.start()
    await client.send_command_with_args("Luba-U12", "start_job")  # must not raise
    await wait_until(lambda: mqtt.set_rate_limited.called, message="the queue never absorbed the 429")

    assert mqtt.set_rate_limited.called
    assert handle.queue._task is not None and not handle.queue._task.done()  # noqa: SLF001
    await handle.stop()


# The offline gate is uniform: Priority.USER raises, it does not send anyway.
#
# A user command skips the has_usable_transport *pre-check* so the host gets an
# exception instead of silence — that is the only difference.  It must not reach
# the transport: the cloud may queue the payload and deliver it when the mower
# returns, and a start_job landing hours later unattended is a safety problem.


def _status(value: StatusType) -> ThingStatusMessage:
    """A minimal thing/status push, the shape the cloud sends on an online/offline edge."""
    return ThingStatusMessage(params=Params(iot_id="iot-1", status=Status(time=0, value=value)))


def _cloud_says_offline(handle: object, mqtt: MagicMock) -> None:
    """Cloud reported the device offline; the transport itself is perfectly healthy."""
    handle.update_availability(  # type: ignore[attr-defined]
        TransportType.CLOUD_ALIYUN, mqtt.availability, mqtt_reported_offline=True
    )


async def test_a_user_command_reaches_the_cloud_despite_a_reported_offline_flag() -> None:
    """The flag is advisory for a person: spend one bounded round trip and find out.

    The gate exists to stop *background* traffic pestering a device the cloud says is
    away.  It is wrong for a command someone is waiting on, for a reason specific to how
    a send actually works: this is not a publish into a broker queue that the mower
    drains later.  ``CloudIOTGateway.send_cloud_command`` is a synchronous HTTPS POST to
    ``/thing/service/invoke`` (``MQTTTransport._invoke`` likewise, via ``mqtt_invoke``),
    and an offline device is *rejected* with a ``DEVICE_OFFLINE_CODES`` code — see
    ``test_a_device_that_goes_offline_mid_send_re_arms_the_flag``.  Nothing is left
    queued to act on the mower unattended, so there is no delayed-``start_job`` hazard
    to protect against here.

    What the flag can be is stale: MQTT carries the *replies*, so its state is a poor
    proxy for whether a command can be delivered, and it is only ever as fresh as the
    last thing the cloud chose to push.  Refusing on it turns a possibly-wrong cloud
    opinion into a hard failure for someone standing next to a mower they can see is on.
    """
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    mqtt.send_user = AsyncMock()
    handle = make_mock_handle(device_name="Luba-O1")
    await handle.add_transport(mqtt)
    _cloud_says_offline(handle, mqtt)
    client = await _client_with(handle)

    assert handle.has_usable_transport is False, "background work must still see this as unsendable"

    await client.send_command_with_args("Luba-O1", "start_job", priority=Priority.USER)

    mqtt.send_user.assert_awaited_once()
    await handle.stop()


async def test_an_online_status_push_clears_the_flag_without_us_sending() -> None:
    """An "online" push clears the flag with no outbound traffic from us.

    Scope, deliberately narrow: this proves the *mechanism*, which is enough to refute
    "the flag clears only when an inbound frame arrives".  It does **not** prove the
    cloud reliably emits that push for a mower that has come back — that is field
    behaviour and nothing in this repo can test it.  So it is evidence against one
    specific claim, not a guarantee the flag can never stick.

    The gate does not rest on this either way; the reason it stays uniform is the
    queued-delivery hazard on the test above.
    """
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    # A real device model: on_status_message runs dataclasses.replace on it.
    handle = make_mock_handle(device_name="Luba-O1b", device=MowingDevice())
    await handle.add_transport(mqtt)
    _cloud_says_offline(handle, mqtt)
    assert handle.has_usable_transport is False

    await handle.on_status_message(_status(StatusType.CONNECTED))

    assert handle.availability.mqtt_reported_offline is False
    assert handle.has_usable_transport is True
    mqtt.send.assert_not_awaited()
    await handle.stop()


async def test_a_queued_command_still_respects_the_offline_flag() -> None:
    """Background traffic can afford to wait the flag out, and the cloud drops it anyway."""
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    handle = make_mock_handle(device_name="Luba-O2")
    await handle.add_transport(mqtt)
    _cloud_says_offline(handle, mqtt)
    client = await _client_with(handle)

    handle.queue.start()
    await client.send_command_with_args("Luba-O2", "start_job")
    # Wait for the queue to drain, so "never sent" means processed-and-skipped, not not-yet-run.
    await wait_until(lambda: handle.queue._queue.empty(), message="the queued command was never processed")  # noqa: SLF001
    await let_others_run()

    mqtt.send.assert_not_awaited()
    await handle.stop()


async def test_a_dead_transport_refuses_a_user_command_too() -> None:
    """Terminal auth failure and a reported-offline device both refuse everyone."""
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    mqtt.is_usable = False
    mqtt.send_user = AsyncMock()
    handle = make_mock_handle(device_name="Luba-O3")
    await handle.add_transport(mqtt)
    _cloud_says_offline(handle, mqtt)
    client = await _client_with(handle)

    with pytest.raises(NoTransportAvailableError):
        await client.send_command_with_args("Luba-O3", "start_job", priority=Priority.USER)

    mqtt.send_user.assert_not_awaited()
    await handle.stop()


async def test_a_device_that_goes_offline_mid_send_re_arms_the_flag() -> None:
    """The flag was clear, so the send went out; the cloud's answer re-arms the gate.

    No BLE fallback is asserted here because that branch needs a *connected* BLE, and a
    connected BLE would have won transport selection outright (``active_transport`` rule
    1) so MQTT would never have been tried.  The fallback in ``send_raw`` only covers the
    narrow race where a background connect lands mid-send.
    """
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    mqtt.send_user = AsyncMock(side_effect=DeviceOfflineException(6221, "iot-1"))
    handle = make_mock_handle(device_name="Luba-O4")
    await handle.add_transport(mqtt)
    handle.update_availability(TransportType.CLOUD_ALIYUN, mqtt.availability, mqtt_reported_offline=False)

    with pytest.raises(DeviceOfflineException):
        await handle.send_raw(b"\x01", prefer_ble=False, user_initiated=True)

    mqtt.send_user.assert_awaited_once()
    assert handle.availability.mqtt_reported_offline is True, "the flag must go back up"
    await handle.stop()


async def test_a_connected_ble_wins_outright_so_the_flag_never_matters() -> None:
    """The offline flag is a cloud fact; it says nothing about the Bluetooth link."""
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    mqtt.send_user = AsyncMock()
    ble = make_mock_transport(TransportType.BLE)
    handle = make_mock_handle(device_name="Luba-O5")
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)
    _cloud_says_offline(handle, mqtt)

    await handle.send_raw(b"\x01", user_initiated=True)

    ble.send.assert_awaited_once()
    mqtt.send_user.assert_not_awaited()
    await handle.stop()
