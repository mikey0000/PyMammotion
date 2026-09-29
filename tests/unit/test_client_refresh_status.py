"""``MammotionClient.refresh_status`` — the user-initiated one-shot report request.

A person pressing "refresh status" is waiting on the answer, so the call takes the
direct send path (``Priority.USER`` semantics): no age check, no debounce, no queue,
and the cloud's advisory offline flag does not refuse it.  ``ensure_fresh_state`` is
the background counterpart and keeps every one of those gates.

The handle is a real ``DeviceHandle``; the cloud transport's ``send_user`` stands in
for the device by feeding a ``toapp_report_data`` frame back through
``on_raw_message``, which is what ends the RPT_START verification window.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest

from pymammotion.aliyun.exceptions import DeviceOfflineException
from pymammotion.auth.token_manager import TokenManager
from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowingDevice
from pymammotion.device.handle import DeviceHandle
from pymammotion.proto import LubaMsg, MctlSys, ReportInfoCfg, ReportInfoData, RptAct
from pymammotion.transport.base import NoTransportAvailableError, SessionExpiredError, TransportType
from tests._helpers import make_account_session, make_bare_client, make_mock_handle, make_mock_transport

_SEND_TIMEOUT = 1.0
_REPORT_FRAME = bytes(LubaMsg(sys=MctlSys(toapp_report_data=ReportInfoData())))


async def _registered(handle: DeviceHandle) -> MammotionClient:
    client = make_bare_client()
    await client._device_registry.register(handle)  # noqa: SLF001
    return client


def _device_answers(handle: DeviceHandle) -> AsyncMock:
    """A send verb whose device replies with a report frame, as a real one would."""

    async def _send_user(*_args: object, **_kwargs: object) -> None:
        await handle.on_raw_message(_REPORT_FRAME)

    return AsyncMock(side_effect=_send_user)


def _report_cfg(payload: bytes) -> ReportInfoCfg:
    cfg = LubaMsg().parse(payload).sys.todev_report_cfg
    assert cfg is not None, "the payload is not a request_iot_sys report config"
    return cfg


async def _cloud_handle(name: str, *, reported_offline: bool) -> tuple[DeviceHandle, MagicMock]:
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    handle = make_mock_handle(device_name=name, device=MowingDevice())
    await handle.add_transport(mqtt)
    handle.update_availability(TransportType.CLOUD_ALIYUN, mqtt.availability, mqtt_reported_offline=reported_offline)
    mqtt.send_user = _device_answers(handle)
    return handle, mqtt


@pytest.mark.regression
async def test_refresh_status_reaches_the_cloud_when_the_device_was_reported_offline() -> None:
    """The button went through ``ensure_fresh_state`` → a BACKGROUND queued one-shot.

    That path honours ``mqtt_reported_offline``, so pressing "refresh status" on a mower
    the cloud had last called offline sent nothing at all — the one press that could
    have shown the mower was back was the one the gate refused.
    """
    handle, mqtt = await _cloud_handle("Luba-R1", reported_offline=True)
    client = await _registered(handle)

    await asyncio.wait_for(client.refresh_status("Luba-R1"), _SEND_TIMEOUT)

    mqtt.send_user.assert_awaited_once()
    cfg = _report_cfg(mqtt.send_user.await_args.args[0])
    assert (cfg.act, cfg.count) == (RptAct.RPT_START, 1), "expected a one-shot count=1 RPT_START"
    await handle.stop()


@pytest.mark.regression
async def test_refresh_status_sends_although_a_report_just_arrived() -> None:
    """A press within 120 s of the last report was a no-op.

    ``ensure_fresh_state`` skipped when the last report was younger than ``max_age_s``,
    and behind it ``request_report_snapshot`` debounced for 15 s; either one turned a
    deliberate press into silence.
    """
    handle, mqtt = await _cloud_handle("Luba-R2", reported_offline=False)
    await handle.on_raw_message(_REPORT_FRAME)
    client = await _registered(handle)

    await asyncio.wait_for(client.refresh_status("Luba-R2"), _SEND_TIMEOUT)

    mqtt.send_user.assert_awaited_once()
    await handle.stop()


@pytest.mark.regression
async def test_refresh_status_is_not_held_behind_a_running_saga() -> None:
    """The queued one-shot was enqueued with ``skip_if_saga_active``, so a map sync dropped it."""
    handle, mqtt = await _cloud_handle("Luba-R3", reported_offline=False)
    client = await _registered(handle)
    handle.queue.start()
    handle.queue._exclusive_active.clear()  # a saga holds the slot  # noqa: SLF001
    try:
        await asyncio.wait_for(client.refresh_status("Luba-R3"), _SEND_TIMEOUT)
    finally:
        handle.queue._exclusive_active.set()  # noqa: SLF001

    mqtt.send_user.assert_awaited_once()
    assert handle.queue._queue.empty(), "a direct send must never touch the queue"  # noqa: SLF001
    await handle.stop()


@pytest.mark.regression
async def test_refresh_status_raises_when_the_cloud_rejects_the_device_as_offline() -> None:
    """The queue swallowed the rejection, so the press reported success for a refused send."""
    handle, mqtt = await _cloud_handle("Luba-R4", reported_offline=True)
    mqtt.send_user = AsyncMock(side_effect=DeviceOfflineException(6205, "iot-1"))
    client = await _registered(handle)

    with pytest.raises(DeviceOfflineException):
        await asyncio.wait_for(client.refresh_status("Luba-R4"), _SEND_TIMEOUT)

    mqtt.send_user.assert_awaited_once()
    await handle.stop()


@pytest.mark.regression
async def test_refresh_status_raises_when_no_transport_is_registered() -> None:
    """With nothing to send over, the queued path returned silently and the press looked successful."""
    handle = make_mock_handle(device_name="Luba-R5", device=MowingDevice())
    client = await _registered(handle)

    with pytest.raises(NoTransportAvailableError):
        await asyncio.wait_for(client.refresh_status("Luba-R5"), _SEND_TIMEOUT)

    await handle.stop()


async def test_refresh_status_refuses_a_terminally_failed_transport() -> None:
    """Only the offline flag is waived for a person; a dead cloud session refuses everyone."""
    handle, mqtt = await _cloud_handle("Luba-R6", reported_offline=True)
    mqtt.is_usable = False
    client = await _registered(handle)

    with pytest.raises(NoTransportAvailableError):
        await asyncio.wait_for(client.refresh_status("Luba-R6"), _SEND_TIMEOUT)

    mqtt.send_user.assert_not_awaited()
    await handle.stop()


async def test_refresh_status_goes_over_a_connected_ble_link() -> None:
    """BLE still wins transport selection; the cloud's offline flag says nothing about it."""
    handle, mqtt = await _cloud_handle("Luba-R7", reported_offline=True)
    ble = make_mock_transport(TransportType.BLE)
    ble.send = _device_answers(handle)
    await handle.add_transport(ble)
    client = await _registered(handle)

    await asyncio.wait_for(client.refresh_status("Luba-R7"), _SEND_TIMEOUT)

    ble.send.assert_awaited_once()
    mqtt.send_user.assert_not_awaited()
    await handle.stop()


async def test_refresh_status_leaves_a_live_ble_stream_alone() -> None:
    """The stream is already delivering fresher data, and a count=1 RPT_START would fight it."""
    handle, mqtt = await _cloud_handle("Luba-R8", reported_offline=False)
    ble = make_mock_transport(TransportType.BLE)
    await handle.add_transport(ble)
    handle.ble_stream_active = True
    client = await _registered(handle)

    await asyncio.wait_for(client.refresh_status("Luba-R8"), _SEND_TIMEOUT)

    ble.send.assert_not_awaited()
    mqtt.send_user.assert_not_awaited()
    await handle.stop()


async def test_refresh_status_wakes_the_poll_loop() -> None:
    """A press is user activity, so the poll loop re-evaluates its cadence now, as for any command."""
    handle, _mqtt = await _cloud_handle("Luba-R11", reported_offline=False)
    client = await _registered(handle)
    handle._rearm_event.clear()  # noqa: SLF001

    await asyncio.wait_for(client.refresh_status("Luba-R11"), _SEND_TIMEOUT)

    assert handle._rearm_event.is_set(), "refresh_status did not record a user command"  # noqa: SLF001
    await handle.stop()


async def test_refresh_status_refreshes_an_expired_session_once_and_resends() -> None:
    """The send goes through the client's auth retry, not a bare ``send_raw``."""
    token_manager = create_autospec(TokenManager, instance=True)
    session = make_account_session("acct-a", token_manager=token_manager)
    client = make_bare_client(session)
    handle, mqtt = await _cloud_handle("Luba-R12", reported_offline=False)
    await client._device_registry.register(handle, account_id="acct-a")  # noqa: SLF001
    answers = mqtt.send_user
    expired = iter([SessionExpiredError(TransportType.CLOUD_ALIYUN)])

    async def _expired_then_answers(*args: object, **kwargs: object) -> None:
        if (exc := next(expired, None)) is not None:
            raise exc
        await answers(*args, **kwargs)

    mqtt.send_user = AsyncMock(side_effect=_expired_then_answers)

    await asyncio.wait_for(client.refresh_status("Luba-R12"), _SEND_TIMEOUT)

    assert mqtt.send_user.await_count == 2, "expected the expired send plus one resend"
    token_manager.refresh_aliyun_credentials.assert_awaited_once()
    await handle.stop()


async def test_refresh_status_sends_via_the_named_accounts_handle() -> None:
    """One mower bound to two accounts: *account_id* picks which handle sends."""
    client = make_bare_client()
    handle_a, mqtt_a = await _cloud_handle("Luba-R13", reported_offline=False)
    handle_b, mqtt_b = await _cloud_handle("Luba-R13", reported_offline=False)
    await client._device_registry.register(handle_a, account_id="acct-a")  # noqa: SLF001
    await client._device_registry.register(handle_b, account_id="acct-b")  # noqa: SLF001

    await asyncio.wait_for(client.refresh_status("Luba-R13", account_id="acct-b"), _SEND_TIMEOUT)

    mqtt_b.send_user.assert_awaited_once()
    mqtt_a.send_user.assert_not_awaited()
    await handle_a.stop()
    await handle_b.stop()


async def test_handle_refresh_status_defaults_to_a_user_initiated_send() -> None:
    """Called without the client's wrapper, the handle still waives the offline flag."""
    handle, mqtt = await _cloud_handle("Luba-R10", reported_offline=True)

    await asyncio.wait_for(handle.refresh_status(), _SEND_TIMEOUT)

    mqtt.send_user.assert_awaited_once()
    await handle.stop()


async def test_refresh_status_raises_for_an_unregistered_device() -> None:
    client = make_bare_client()

    with pytest.raises(KeyError):
        await client.refresh_status("Luba-missing")


async def test_ensure_fresh_state_still_skips_a_device_the_cloud_reported_offline() -> None:
    """The background call keeps the offline gate; only the user-initiated one waives it."""
    handle, mqtt = await _cloud_handle("Luba-R9", reported_offline=True)
    client = await _registered(handle)
    handle.queue.start()

    await client.ensure_fresh_state("Luba-R9")
    # The processor calls task_done() per item, so join() means processed-and-skipped, not not-yet-run.
    await asyncio.wait_for(handle.queue._queue.join(), _SEND_TIMEOUT)  # noqa: SLF001

    mqtt.send_user.assert_not_awaited()
    mqtt.send.assert_not_awaited()
    await handle.stop()
