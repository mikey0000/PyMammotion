"""AliyunMQTTTransport when another session holds the account lock (bind_reply 2152).

The broker answers ``bind_reply`` 2152 ("distributed lock failed") while the
Mammotion app holds the account's exclusive session.  That is transport-scoped
and not an auth failure: the HTTP login is healthy and re-login cannot release
the lock.  The transport must stay recoverable and retry on a fixed slow timer
until the lock is released.

The retry sleep is intercepted by matching ``ACCOUNT_IN_USE_RETRY_SEC`` exactly;
every other ``asyncio.sleep`` (the event loop's, ``wait_until``'s) passes through.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
import logging
from unittest.mock import AsyncMock, patch

import aiomqtt
import pytest

from pymammotion.transport.aliyun_mqtt import AliyunMQTTTransport
from pymammotion.transport.base import TransportAvailability
from pymammotion.transport.cloud import ACCOUNT_IN_USE_RETRY_SEC, MQTT_RECONNECT_MIN_SEC
from tests._helpers import wait_until
from tests.unit.transport._fakes import FakeMessage, FakeMQTTClient
from tests.unit.transport._helpers import make_aliyun_transport, make_bind_reply

_TIMEOUT = 2.0


class _RetryGate:
    """Replaces ``asyncio.sleep``: parks each lock-retry sleep until released, records every delay."""

    def __init__(self) -> None:
        self.delays: list[float] = []
        #: Lock-retry sleeps entered so far.
        self.parks = 0
        self._releases: asyncio.Queue[None] = asyncio.Queue()
        self._real_sleep = asyncio.sleep

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        if delay != ACCOUNT_IN_USE_RETRY_SEC:
            await self._real_sleep(0)
            return
        self.parks += 1
        await self._releases.get()

    async def wait_parked(self, count: int) -> None:
        await wait_until(lambda: self.parks >= count, timeout=_TIMEOUT, message=f"lock retry #{count} never slept")

    def release(self) -> None:
        self._releases.put_nowait(None)


@pytest.fixture
def gate() -> _RetryGate:
    return _RetryGate()


@asynccontextmanager
async def _driving(
    transport: AliyunMQTTTransport, gate: _RetryGate, clients: list[FakeMQTTClient]
) -> AsyncIterator[None]:
    """Run *transport*'s receive loop against *clients* in order, the lock-retry sleep held by *gate*.

    Disconnects on exit, so a failed assertion does not leave the parked loop task behind.
    """
    with patch.object(asyncio, "sleep", gate.sleep), patch.object(aiomqtt, "Client", side_effect=clients):
        await transport.connect()
        try:
            yield
        finally:
            await transport.disconnect()


@pytest.mark.regression
async def test_bind_reply_2152_leaves_the_transport_recoverable(gate: _RetryGate) -> None:
    """A held account lock is not an auth failure and must not end the transport.

    The loop raised AccountInUseError (a ReLoginRequiredError) through
    _handle_fatal_auth_error: the transport was marked auth-failed, connect() refused
    forever, and on_fatal_auth_error told the client to fail the account's mowers —
    although the login was healthy and the lock is released when the app signs out.
    """
    transport = make_aliyun_transport()
    transport.on_fatal_auth_error = AsyncMock()
    transport.on_auth_failure = AsyncMock(return_value=True)
    clients = [FakeMQTTClient(messages=[make_bind_reply(2152)]), FakeMQTTClient()]

    async with _driving(transport, gate, clients):
        await gate.wait_parked(1)

        assert transport.account_in_use is True
        assert transport.availability is TransportAvailability.DISCONNECTED
        assert transport.is_usable is False, "a lock-held transport must not be picked for sends"
        assert transport.is_unrecoverable_auth_failure is False
        transport.on_fatal_auth_error.assert_not_awaited()
        transport.on_auth_failure.assert_not_awaited()
        assert transport._task is not None and not transport._task.done(), "the receive loop must keep retrying"


async def test_bind_reply_2152_retries_on_the_fixed_lock_delay_not_the_backoff(gate: _RetryGate) -> None:
    transport = make_aliyun_transport()
    clients = [FakeMQTTClient(messages=[make_bind_reply(2152)]) for _ in range(3)] + [FakeMQTTClient()]

    async with _driving(transport, gate, clients):
        for n in range(1, 4):
            await gate.wait_parked(n)
            gate.release()
        await wait_until(lambda: clients[-1].publish.await_count == 1, message="no bind after the third retry")

    transport_waits = [d for d in gate.delays if d >= MQTT_RECONNECT_MIN_SEC]
    assert transport_waits == [ACCOUNT_IN_USE_RETRY_SEC] * 3, "each 2152 waits the fixed delay, never the backoff"


async def test_account_in_use_change_fires_once_per_transition(gate: _RetryGate) -> None:
    transport = make_aliyun_transport()
    changes: list[bool] = []

    async def _on_change(held: bool) -> None:
        changes.append(held)

    transport.on_account_in_use_changed = _on_change
    released = FakeMQTTClient(messages=[make_bind_reply(200)])
    clients = [FakeMQTTClient(messages=[make_bind_reply(2152)]), FakeMQTTClient(messages=[make_bind_reply(2152)]), released]

    async with _driving(transport, gate, clients):
        for n in range(1, 3):
            await gate.wait_parked(n)
            gate.release()
        await asyncio.wait_for(released.drained.wait(), _TIMEOUT)

        assert changes == [True, False], "two 2152s are one episode; the accepted bind ends it"
        assert transport.account_in_use is False
        assert transport.is_usable is True
        assert transport.is_connected is True


async def test_account_in_use_warns_once_per_episode(gate: _RetryGate, caplog: pytest.LogCaptureFixture) -> None:
    """The warning is the user-visible log line; one per 5-minute retry would flood the log."""
    transport = make_aliyun_transport()
    clients = [FakeMQTTClient(messages=[make_bind_reply(2152)]) for _ in range(3)] + [FakeMQTTClient()]

    with caplog.at_level(logging.WARNING, logger="pymammotion.transport.aliyun_mqtt"):
        async with _driving(transport, gate, clients):
            for n in range(1, 4):
                await gate.wait_parked(n)
                gate.release()
            await wait_until(lambda: clients[-1].publish.await_count == 1, message="no bind after the third retry")

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "another session" in r.getMessage()]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors == [], "a 2152 on every retry must not log an error each time"


class _DroppingMQTTClient(FakeMQTTClient):
    """A session the broker drops after delivering *messages* — the receive loop reconnects."""

    @property
    def messages(self) -> AsyncIterator[FakeMessage]:
        async def _then_drop() -> AsyncIterator[FakeMessage]:
            for message in self._messages_list:
                yield message
            raise aiomqtt.MqttError("connection lost")

        return _then_drop()


def _first_episode() -> tuple[list[FakeMQTTClient], set[int], int]:
    return [FakeMQTTClient(messages=[make_bind_reply(2152)]), FakeMQTTClient()], set(), 1


def _lock_retry() -> tuple[list[FakeMQTTClient], set[int], int]:
    return [FakeMQTTClient(messages=[make_bind_reply(2152)]) for _ in range(2)] + [FakeMQTTClient()], set(), 2


def _after_an_accepted_session() -> tuple[list[FakeMQTTClient], set[int], int]:
    clients = [_DroppingMQTTClient(messages=[make_bind_reply(200)]), FakeMQTTClient(messages=[make_bind_reply(2152)])]
    return [*clients, FakeMQTTClient()], {id(clients[0])}, 1


@pytest.mark.regression
@pytest.mark.parametrize(
    "scenario",
    [_first_episode, _lock_retry, _after_an_accepted_session],
    ids=["first-episode", "lock-retry", "after-an-accepted-session"],
)
async def test_connected_is_announced_only_on_a_session_whose_bind_was_accepted(
    gate: _RetryGate, scenario: Callable[[], tuple[list[FakeMQTTClient], set[int], int]]
) -> None:
    """A TCP handshake is not a usable session; announcing CONNECTED would flash the mowers usable.

    CONNECTED was announced at the handshake whenever the lock was not already known
    held, so the first 2152 of an episode — at startup, or on a reconnect after an
    accepted session — flashed the mowers available and usable before the bind came back refused.
    """
    transport = make_aliyun_transport()
    clients, accepted, parks = scenario()
    announced_on: list[object] = []

    async def _listener(state: TransportAvailability) -> None:
        if state is TransportAvailability.CONNECTED:
            announced_on.append(transport._client)

    transport.add_availability_listener(_listener)

    async with _driving(transport, gate, clients):
        for n in range(1, parks):
            await gate.wait_parked(n)
            gate.release()
        await gate.wait_parked(parks)

    assert clients[-2].publish.await_count == 1, "the refused session must have reached the bind"
    assert all(id(client) in accepted for client in announced_on), "CONNECTED announced before an accepted bind"
    assert len(announced_on) == len(accepted)


async def test_bind_reply_2043_never_announces_the_refused_session_connected() -> None:
    transport = make_aliyun_transport()
    transport.on_auth_failure = AsyncMock(return_value=True)
    seen: list[TransportAvailability] = []

    async def _listener(state: TransportAvailability) -> None:
        seen.append(state)

    transport.add_availability_listener(_listener)
    accepted = FakeMQTTClient(messages=[make_bind_reply(200)])
    clients = [FakeMQTTClient(messages=[make_bind_reply(2043)]), accepted]

    with patch.object(aiomqtt, "Client", side_effect=clients), patch.object(asyncio, "sleep", AsyncMock()):
        await transport.connect()
        try:
            await asyncio.wait_for(accepted.drained.wait(), _TIMEOUT)
        finally:
            await transport.disconnect()

    transport.on_auth_failure.assert_awaited_once()
    assert seen.count(TransportAvailability.CONNECTED) == 1, seen
    assert seen.index(TransportAvailability.CONNECTED) > seen.index(TransportAvailability.DISCONNECTED), seen


async def test_a_failing_account_in_use_callback_does_not_stop_the_retry(gate: _RetryGate) -> None:
    transport = make_aliyun_transport()
    transport.on_account_in_use_changed = AsyncMock(side_effect=RuntimeError("host bug"))
    clients = [FakeMQTTClient(messages=[make_bind_reply(2152)]), FakeMQTTClient()]

    async with _driving(transport, gate, clients):
        await gate.wait_parked(1)

        transport.on_account_in_use_changed.assert_awaited_once_with(True)
        assert transport.account_in_use is True


async def test_bind_reply_2152_after_an_accepted_bind_takes_the_session_down(gate: _RetryGate) -> None:
    """The app can take the lock mid-session; the live session must stop counting as usable."""
    transport = make_aliyun_transport()
    clients = [FakeMQTTClient(messages=[make_bind_reply(200), make_bind_reply(2152)]), FakeMQTTClient()]

    async with _driving(transport, gate, clients):
        await gate.wait_parked(1)

        assert transport.account_in_use is True
        assert transport.availability is TransportAvailability.DISCONNECTED
        assert transport.is_usable is False


async def test_disconnect_while_the_lock_is_held_tells_the_host_it_is_released(gate: _RetryGate) -> None:
    """A torn-down transport sends no further transitions, so the held state must end with it.

    Otherwise the host's account-in-use notice outlives the transport, and a later
    connect() starts out believing the lock is held.
    """
    transport = make_aliyun_transport()
    changes: list[bool] = []

    async def _on_change(held: bool) -> None:
        changes.append(held)

    transport.on_account_in_use_changed = _on_change
    clients = [FakeMQTTClient(messages=[make_bind_reply(2152)]), FakeMQTTClient()]

    async with _driving(transport, gate, clients):
        await gate.wait_parked(1)

    assert changes == [True, False]
    assert transport.account_in_use is False


async def test_disconnect_without_a_held_lock_reports_no_transition() -> None:
    transport = make_aliyun_transport()
    transport.on_account_in_use_changed = AsyncMock()

    await transport.disconnect()

    transport.on_account_in_use_changed.assert_not_awaited()


async def test_each_repeat_2152_logs_one_debug_line(gate: _RetryGate, caplog: pytest.LogCaptureFixture) -> None:
    """The retry cadence is visible in field logs while the WARNING stays once per episode."""
    transport = make_aliyun_transport()
    clients = [FakeMQTTClient(messages=[make_bind_reply(2152)]) for _ in range(3)] + [FakeMQTTClient()]

    with caplog.at_level(logging.DEBUG, logger="pymammotion.transport.aliyun_mqtt"):
        async with _driving(transport, gate, clients):
            for n in range(1, 4):
                await gate.wait_parked(n)
                gate.release()
            await wait_until(lambda: clients[-1].publish.await_count == 1, message="no bind after the third retry")

    repeats = [r for r in caplog.records if r.levelno == logging.DEBUG and "still held" in r.getMessage()]
    assert len(repeats) == 2, [r.getMessage() for r in repeats]


async def test_disconnect_survives_a_failing_account_in_use_callback(gate: _RetryGate) -> None:
    transport = make_aliyun_transport()
    clients = [FakeMQTTClient(messages=[make_bind_reply(2152)]), FakeMQTTClient()]

    async with _driving(transport, gate, clients):
        await gate.wait_parked(1)
        transport.on_account_in_use_changed = AsyncMock(side_effect=RuntimeError("host bug"))

    transport.on_account_in_use_changed.assert_awaited_once_with(False)
    assert transport.account_in_use is False
