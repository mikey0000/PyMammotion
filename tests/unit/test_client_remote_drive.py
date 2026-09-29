"""``MammotionClient``'s remote-drive entry points: session lookup, the HTTP token source and the cloud send.

The session logic itself is covered in ``tests/unit/device/test_remote_drive*.py``; here the
subject is the wiring — which handle and whose login a call uses, that frames go out cloud-only
on the user path, and that a refused frame is not logged away as delivered.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import partial
from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock, create_autospec

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.auth.token_manager import TokenManager
from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle
from pymammotion.device.remote_drive import (
    RemoteDriveError,
    RemoteDriveEvent,
    RemoteDriveEventKind,
    RemoteDrivePhase,
    RemoteDriveSession,
)
from pymammotion.proto import DrvSessionCtrlAck, LubaMsg, MctlDriver
from pymammotion.transport.base import (
    NoTransportAvailableError,
    SessionExpiredError,
    TransportRateLimitedError,
    TransportType,
)
from tests._helpers import (
    block_forever,
    let_others_run,
    make_account_session,
    make_bare_client,
    make_mock_mowing_device,
    make_mock_transport,
    wait_until,
)
from tests.unit._helpers import make_http_posting
from tests.unit.device._drive_helpers import make_grant
from tests.unit.device._fakes import FakeDriveClock, ScriptedTokens

NAME = "Luba-VS6ABCDE"
IOT_ID = "iot-drive"
_GRANT = {"code": 0, "msg": "ok", "data": {"deviceResult": 0, "token": "ctl-1", "expireIn": 600, "timeoutExit": 10}}
#: Stands in for the 1 s invoke timeout: any suspension outlasts it, so no real time has to pass.
#: Valid only while the stubbed ``send_user`` returns without suspending, as ``AsyncMock`` does.
_EXPIRED_AT_ONCE = 0.0


def _handle(*, cloud: bool = True, device_id: str = "dev1") -> DeviceHandle:
    kind = TransportType.CLOUD_ALIYUN if cloud else TransportType.BLE
    transport = make_mock_transport(kind, send_user=AsyncMock())
    return DeviceHandle(
        device_id=device_id,
        device_name=NAME,
        initial_device=make_mock_mowing_device(),
        iot_id=IOT_ID,
        mqtt_transport=transport if cloud else None,
        ble_transport=None if cloud else transport,
    )


@pytest.fixture
async def handles() -> AsyncIterator[list[DeviceHandle]]:
    """Handles whose sessions are stopped at teardown, even after a failed assertion, so no keep-alive leaks."""
    tracked: list[DeviceHandle] = []
    yield tracked
    for handle in tracked:
        if handle.remote_drive is not None:
            await handle.remote_drive.stop()


def _account(account_id: str, body: dict | None = None) -> tuple[AccountSession, object]:
    http, http_session = make_http_posting(HTTPStatus.OK.value, _GRANT if body is None else body)
    token_manager = create_autospec(TokenManager, instance=True)
    return make_account_session(account_id, http=http, token_manager=token_manager), http_session


async def _client_with(
    handle: DeviceHandle, handles: list[DeviceHandle], account_id: str = "acct", *, body: dict | None = None
) -> tuple[MammotionClient, object]:
    session, http_session = _account(account_id, body)
    client = make_bare_client(session)
    await client.device_registry.register(handle, account_id)
    handles.append(handle)
    return client, http_session


def _ack(ctrl_seq: int, **fields: object) -> LubaMsg:
    return LubaMsg(driver=MctlDriver(toapp_session_ctrl_ack=DrvSessionCtrlAck(ctrl_seq=ctrl_seq, **fields)))


def _speeds(transport: object) -> list[tuple[int, int]]:
    frames = [m.driver.todev_session_ctrl_req for m in _sent(transport)]
    return [(f.set_linear_speed, f.set_angular_speed) for f in frames if f is not None]


def _sent(transport: object) -> list[LubaMsg]:
    return [LubaMsg().parse(call.args[0]) for call in transport.send_user.await_args_list]  # type: ignore[attr-defined]


async def test_an_unregistered_device_is_a_key_error() -> None:
    client = make_bare_client()

    with pytest.raises(KeyError):
        await client.start_remote_drive("Luba-NOPE")


async def test_the_session_belongs_to_the_named_accounts_handle(handles: list[DeviceHandle]) -> None:
    first, second = _handle(device_id="dev1"), _handle(device_id="dev1")
    client, _ = await _client_with(first, handles, "a")
    await client.device_registry.register(second, "b")

    session = client.remote_drive_session(NAME, account_id="b")

    assert session is second.remote_drive
    assert first.remote_drive is None


async def test_starting_asks_the_accounts_login_for_a_token_and_sends_the_keep_alive_over_the_cloud(
    handles: list[DeviceHandle],
) -> None:
    handle = _handle()
    client, http_session = await _client_with(handle, handles)

    assert await client.start_remote_drive(NAME) is True

    assert http_session.post.await_args.kwargs["json"] == {"deviceId": IOT_ID}
    frame = _sent(handle.get_transport(TransportType.CLOUD_ALIYUN))[0].driver.todev_session_ctrl_req
    assert (frame.ctrl_seq, frame.token) == (0, "ctl-1")


async def test_a_device_without_a_cloud_transport_refuses(handles: list[DeviceHandle]) -> None:
    handle = _handle(cloud=False)
    client, http_session = await _client_with(handle, handles)

    with pytest.raises(NoTransportAvailableError):
        await client.start_remote_drive(NAME)

    http_session.post.assert_not_awaited()


async def test_an_expired_transport_session_is_refreshed_once_and_the_frame_resent(handles: list[DeviceHandle]) -> None:
    handle = _handle()
    client, _ = await _client_with(handle, handles)
    transport = handle.get_transport(TransportType.CLOUD_ALIYUN)
    transport.send_user.side_effect = [SessionExpiredError(TransportType.CLOUD_ALIYUN, "x"), None]  # type: ignore[union-attr]
    token_manager = client.account_registry.get("acct").token_manager  # type: ignore[union-attr]

    await client.start_remote_drive(NAME)

    token_manager.refresh_aliyun_credentials.assert_awaited_once()
    assert len(_sent(handle.get_transport(TransportType.CLOUD_ALIYUN))) == 2
    assert client.remote_drive_session(NAME).phase is RemoteDrivePhase.SAFETY_NOTICE


def _session_over(client: MammotionClient, handle: DeviceHandle, clock: FakeDriveClock) -> RemoteDriveSession:
    """A session sending through the client's real cloud send, with an invoke timeout that has already passed."""
    return RemoteDriveSession(
        handle,
        tokens=ScriptedTokens(requests=[make_grant()]),
        send=partial(client._send_remote_drive_frame, handle),
        clock=clock,
        invoke_timeout=_EXPIRED_AT_ONCE,
    )


@pytest.mark.regression
async def test_a_refresh_slower_than_the_invoke_timeout_completes_and_the_frame_is_resent(
    handles: list[DeviceHandle],
) -> None:
    """The invoke timeout wrapped the auth retry as well as the send.

    A credential refresh slower than 1 s was cancelled mid-flight, after the server may
    already have rotated the refresh token, and the frame counted as an invoke timeout.
    """
    handle = _handle()
    client, _ = await _client_with(handle, handles)
    transport = handle.get_transport(TransportType.CLOUD_ALIYUN)
    transport.send_user.side_effect = [SessionExpiredError(TransportType.CLOUD_ALIYUN, "x"), None]  # type: ignore[union-attr]
    token_manager = client.account_registry.get("acct").token_manager  # type: ignore[union-attr]
    refreshed: list[bool] = []

    async def _slow_refresh() -> None:
        await let_others_run()  # suspends past the invoke timeout
        refreshed.append(True)

    token_manager.refresh_aliyun_credentials.side_effect = _slow_refresh
    clock = FakeDriveClock()
    session = _session_over(client, handle, clock)
    events: list[RemoteDriveEvent] = []

    async def _record(event: RemoteDriveEvent) -> None:
        events.append(event)

    session.subscribe(_record)

    assert await session.start() is True
    await clock.advance(0)  # runs the resend an invoke timeout would have queued

    assert refreshed == [True], "the refresh ran to completion"
    assert len(_sent(transport)) == 2, "the expired send and its one retry"
    assert session._timeouts == 0, "the refresh did not count as an invoke timeout"
    assert events == []
    assert session.phase is RemoteDrivePhase.SAFETY_NOTICE
    await session.stop()


async def test_a_send_that_hangs_is_cut_at_the_invoke_timeout_without_a_refresh(handles: list[DeviceHandle]) -> None:
    handle = _handle()
    client, _ = await _client_with(handle, handles)
    transport = handle.get_transport(TransportType.CLOUD_ALIYUN)
    token_manager = client.account_registry.get("acct").token_manager  # type: ignore[union-attr]
    attempts: list[int] = []

    async def _first_hangs(*_args: Any, **_kwargs: Any) -> None:
        attempts.append(len(attempts))
        if len(attempts) == 1:
            await block_forever()

    transport.send_user.side_effect = _first_hangs  # type: ignore[union-attr]
    clock = FakeDriveClock()
    session = _session_over(client, handle, clock)

    assert await session.start() is True
    await clock.advance(0)

    assert attempts == [0, 1], "the hung keep-alive was cut and resent"
    assert token_manager.method_calls == []
    await session.stop()


async def test_a_refused_frame_ends_the_session_instead_of_being_logged_as_sent(handles: list[DeviceHandle]) -> None:
    """``_send_with_auth_retry`` logs and drops transport errors by default; a drive frame must not."""
    handle = _handle()
    client, _ = await _client_with(handle, handles)
    refusal = TransportRateLimitedError("banned")
    handle.get_transport(TransportType.CLOUD_ALIYUN).send_user.side_effect = refusal  # type: ignore[union-attr]
    events: list[RemoteDriveEvent] = []

    async def _record(event: RemoteDriveEvent) -> None:
        events.append(event)

    client.subscribe_remote_drive(NAME, _record)
    await client.start_remote_drive(NAME)
    await wait_until(lambda: events)

    assert [(e.kind, e.error) for e in events] == [(RemoteDriveEventKind.SEND_FAILED, refusal)]


async def test_stopping_the_handle_releases_a_running_session(handles: list[DeviceHandle]) -> None:
    handle = _handle()
    client, _ = await _client_with(handle, handles)
    await client.start_remote_drive(NAME)
    transport = handle.get_transport(TransportType.CLOUD_ALIYUN)

    await handle.stop()

    exits = [m.driver.todev_session_exit_nfty for m in _sent(transport)]
    assert [e.token for e in exits if e is not None] == ["ctl-1"]
    assert client.remote_drive_session(NAME).phase is RemoteDrivePhase.IDLE


async def test_stopping_without_a_session_does_nothing(handles: list[DeviceHandle]) -> None:
    handle = _handle()
    client, _ = await _client_with(handle, handles)

    await client.stop_remote_drive(NAME)

    assert _sent(handle.get_transport(TransportType.CLOUD_ALIYUN)) == []


async def test_require_video_is_forwarded_and_video_ready_lets_a_retry_start(handles: list[DeviceHandle]) -> None:
    handle = _handle()
    client, http_session = await _client_with(handle, handles)
    transport = handle.get_transport(TransportType.CLOUD_ALIYUN)

    with pytest.raises(RemoteDriveError):
        await client.start_remote_drive(NAME, require_video=True)
    http_session.post.assert_not_awaited()
    assert _sent(transport) == []

    await client.set_remote_drive_video_ready(NAME, ready=True)
    assert await client.start_remote_drive(NAME, require_video=True) is True


async def test_confirming_and_driving_through_the_client_reaches_the_mower(handles: list[DeviceHandle]) -> None:
    handle = _handle()
    client, _ = await _client_with(handle, handles)
    await client.start_remote_drive(NAME)

    await client.confirm_remote_drive(NAME)
    await client.remote_drive(NAME, 300, 20)

    assert client.remote_drive_session(NAME).phase is RemoteDrivePhase.ACTIVE
    assert _speeds(handle.get_transport(TransportType.CLOUD_ALIYUN)) == [(0, 0), (300, 20)]


async def _two_accounts(handles: list[DeviceHandle]) -> tuple[MammotionClient, DeviceHandle, DeviceHandle]:
    """One device visible to accounts ``a`` and ``b``, each with its own login and handle."""
    first, second = _handle(device_id="dev1"), _handle(device_id="dev1")
    client, _ = await _client_with(first, handles, "a")
    session_b, _ = _account("b")
    await client.account_registry.register(session_b)
    await client.device_registry.register(second, "b")
    handles.append(second)
    return client, first, second


async def test_delegators_use_the_named_accounts_handle(handles: list[DeviceHandle]) -> None:
    client, first, second = await _two_accounts(handles)

    await client.start_remote_drive(NAME, account_id="b")
    await client.confirm_remote_drive(NAME, account_id="b")
    await client.remote_drive(NAME, 300, 0, account_id="b")
    await client.stop_remote_drive(NAME, account_id="b")

    assert _speeds(second.get_transport(TransportType.CLOUD_ALIYUN)) == [(0, 0), (300, 0), (0, 0)]
    assert _sent(first.get_transport(TransportType.CLOUD_ALIYUN)) == []


async def test_acknowledging_the_fence_through_the_client_resumes_input(handles: list[DeviceHandle]) -> None:
    handle = _handle()
    client, _ = await _client_with(handle, handles)
    transport = handle.get_transport(TransportType.CLOUD_ALIYUN)
    events: list[RemoteDriveEvent] = []

    async def _record(event: RemoteDriveEvent) -> None:
        events.append(event)

    client.subscribe_remote_drive(NAME, _record)
    await client.start_remote_drive(NAME)
    await client.confirm_remote_drive(NAME)
    await client.remote_drive(NAME, 300, 0)
    await handle.broker.on_message(_ack(0, fence_exceed_distance=6.0, localization_valid=True))
    await wait_until(lambda: events)
    await client.remote_drive(NAME, 200, 0)
    # Dropped rather than throttled is pinned on the fake clock in test_remote_drive_frames.py.
    assert _speeds(transport) == [(0, 0), (300, 0), (0, 0)], "paused input is not sent"

    client.acknowledge_remote_drive_fence(NAME)
    await client.remote_drive(NAME, 200, 0)

    await wait_until(lambda: _speeds(transport)[-1] == (200, 0))
    assert [e.kind for e in events] == [RemoteDriveEventKind.APPROACH_FENCE]


async def test_a_subscriber_registered_before_start_hears_a_refused_token(handles: list[DeviceHandle]) -> None:
    handle = _handle()
    body = {"code": 0, "msg": "ok", "data": {"deviceResult": 9, "preemptUser": "other@example.com"}}
    client, _ = await _client_with(handle, handles, body=body)
    events: list[RemoteDriveEvent] = []

    async def _record(event: RemoteDriveEvent) -> None:
        events.append(event)

    client.subscribe_remote_drive(NAME, _record)

    assert await client.start_remote_drive(NAME) is False
    assert [(e.kind, e.detail) for e in events] == [(RemoteDriveEventKind.OCCUPIED_BY_OTHER, "other@example.com")]
    assert _sent(handle.get_transport(TransportType.CLOUD_ALIYUN)) == []


async def test_acknowledging_the_fence_resumes_only_the_named_accounts_session(handles: list[DeviceHandle]) -> None:
    client, first, second = await _two_accounts(handles)
    transport = second.get_transport(TransportType.CLOUD_ALIYUN)
    await client.start_remote_drive(NAME, account_id="b")
    await client.confirm_remote_drive(NAME, account_id="b")
    await client.remote_drive(NAME, 300, 0, account_id="b")
    await second.broker.on_message(_ack(0, fence_exceed_distance=6.0, localization_valid=True))
    await wait_until(lambda: _speeds(transport) == [(0, 0), (300, 0), (0, 0)])
    assert client.remote_drive_session(NAME, account_id="b").fence_paused

    client.acknowledge_remote_drive_fence(NAME, account_id="b")
    await client.remote_drive(NAME, 200, 0, account_id="b")

    await wait_until(lambda: _speeds(transport)[-1] == (200, 0))
    assert _sent(first.get_transport(TransportType.CLOUD_ALIYUN)) == []


async def test_video_readiness_is_reported_per_account(handles: list[DeviceHandle]) -> None:
    client, _, _ = await _two_accounts(handles)

    await client.set_remote_drive_video_ready(NAME, ready=True, account_id="b")

    assert await client.start_remote_drive(NAME, account_id="b", require_video=True) is True
    with pytest.raises(RemoteDriveError):
        await client.start_remote_drive(NAME, account_id="a", require_video=True)
