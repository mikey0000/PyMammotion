"""Tests for the re-login circuit breaker on transport fatal-auth events.

When a transport's `on_fatal_auth_error` handler keeps producing credentials
that are still rejected (revoked refreshToken, server-side block, clock skew,
…) the recovery path would otherwise loop forever, spamming logs and hammering
the auth endpoints. The circuit breaker caps how many fatal-auth events the
handler will respond to within a sliding window; once tripped, it stops
scheduling reconnects and fires `on_unrecoverable_auth_error` so the host
application (e.g. Home Assistant) can prompt the user to re-authenticate.

Also covers the `_full_relogin` `transport_type` plumbing — a Mammotion MQTT
auth failure must not unnecessarily refresh the unrelated Aliyun IoT token.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.client import (
    _FATAL_AUTH_CIRCUIT_MAX,
    _FATAL_AUTH_CIRCUIT_WINDOW_SEC,
    MammotionClient,
)
from pymammotion.http.model.http import MQTTConnection
from pymammotion.transport.base import ReLoginRequiredError, TransportType


def _make_session() -> AccountSession:
    """Build an AccountSession with the minimum mocks for `_setup_mammotion_transport`."""
    session = AccountSession(account_id="acc", email="user@test.com", password="pw")
    session.mammotion_http = MagicMock()
    session.mammotion_http.logout = AsyncMock()
    session.mammotion_http.login_v2 = AsyncMock(return_value=MagicMock(code=0))
    tm = MagicMock()
    tm.account_id = "acc"
    tm.force_refresh = AsyncMock()
    tm.refresh_mqtt_credentials = AsyncMock(return_value=MagicMock(jwt="fresh-jwt"))
    session.token_manager = tm
    return session


def _make_mqtt_creds() -> MQTTConnection:
    return MQTTConnection(host="tcp://mqtt.example:1883", jwt="initial-jwt", client_id="cid", username="u")


@pytest.mark.asyncio
async def test_full_relogin_passes_transport_type_to_force_refresh() -> None:
    """_full_relogin(transport_type=X) must forward X to TokenManager.force_refresh.

    Otherwise a Mammotion MQTT auth failure ends up refreshing the unrelated
    Aliyun IoT token — the bug that triggered this work.
    """
    client = MammotionClient()
    session = _make_session()

    await client._full_relogin(session, transport_type=TransportType.CLOUD_MAMMOTION)

    session.token_manager.force_refresh.assert_awaited_once_with(
        transport_type=TransportType.CLOUD_MAMMOTION
    )


@pytest.mark.asyncio
async def test_full_relogin_default_transport_type_is_none() -> None:
    """Default call (no transport_type) preserves the old behavior of refreshing everything."""
    client = MammotionClient()
    session = _make_session()

    await client._full_relogin(session)

    session.token_manager.force_refresh.assert_awaited_once_with(transport_type=None)


@pytest.mark.asyncio
async def test_circuit_breaker_trips_after_max_fatal_auth_events() -> None:
    """After _FATAL_AUTH_CIRCUIT_MAX fatal-auth events in the window, the (N+1)th
    event must NOT trigger another re-login attempt and MUST fire
    on_unrecoverable_auth_error so HA can prompt the user.
    """
    client = MammotionClient()
    client.on_unrecoverable_auth_error = AsyncMock()
    session = _make_session()

    with patch.object(client, "_full_relogin", new=AsyncMock()) as mock_relogin:
        transport = client._setup_mammotion_transport(
            _make_mqtt_creds(), session.mammotion_http, session, session.token_manager
        )
        handler = transport.on_fatal_auth_error
        assert handler is not None

        # Fire MAX events — each one should drive a recovery attempt.
        for _ in range(_FATAL_AUTH_CIRCUIT_MAX):
            await handler(ReLoginRequiredError("acc", "broker rejected"))
        assert mock_relogin.await_count == _FATAL_AUTH_CIRCUIT_MAX
        client.on_unrecoverable_auth_error.assert_not_awaited()

        # The (MAX+1)th event trips the breaker: NO new relogin, breaker fires.
        trigger = ReLoginRequiredError("acc", "still rejected")
        await handler(trigger)
        assert mock_relogin.await_count == _FATAL_AUTH_CIRCUIT_MAX
        client.on_unrecoverable_auth_error.assert_awaited_once_with(trigger)


@pytest.mark.asyncio
async def test_circuit_breaker_marks_transport_unrecoverable() -> None:
    """When the breaker trips it must mark the transport so any subsequent
    connect() refuses — otherwise a queued call_soon(connect()) from an
    earlier non-tripped fatal_auth cycle resurrects the loop indefinitely.
    """
    client = MammotionClient()
    client.on_unrecoverable_auth_error = AsyncMock()
    session = _make_session()

    with patch.object(client, "_full_relogin", new=AsyncMock()):
        transport = client._setup_mammotion_transport(
            _make_mqtt_creds(), session.mammotion_http, session, session.token_manager
        )
        handler = transport.on_fatal_auth_error
        assert handler is not None
        assert not transport.is_unrecoverable_auth_failure

        # Trip the breaker.
        for _ in range(_FATAL_AUTH_CIRCUIT_MAX + 1):
            await handler(ReLoginRequiredError("acc", "rejected"))

        # Transport is now permanently unusable; connect() must refuse to
        # spawn a new _run task.
        assert transport.is_unrecoverable_auth_failure
        assert not transport.is_usable
        await transport.connect()
        assert transport._task is None or transport._task.done()


@pytest.mark.asyncio
async def test_circuit_breaker_window_evicts_old_events() -> None:
    """Events older than _FATAL_AUTH_CIRCUIT_WINDOW_SEC must drop off the counter
    so a slow trickle of failures (e.g. one bad token refresh per hour) doesn't
    permanently trip the breaker.
    """
    client = MammotionClient()
    client.on_unrecoverable_auth_error = AsyncMock()
    session = _make_session()

    with (
        patch.object(client, "_full_relogin", new=AsyncMock()) as mock_relogin,
        patch("pymammotion.client.time.monotonic") as mock_monotonic,
    ):
        transport = client._setup_mammotion_transport(
            _make_mqtt_creds(), session.mammotion_http, session, session.token_manager
        )
        handler = transport.on_fatal_auth_error

        # Burn MAX events at t=0.
        mock_monotonic.return_value = 0.0
        for _ in range(_FATAL_AUTH_CIRCUIT_MAX):
            await handler(ReLoginRequiredError("acc", "fail"))

        # Jump past the window so those events are evicted.
        mock_monotonic.return_value = _FATAL_AUTH_CIRCUIT_WINDOW_SEC + 1
        await handler(ReLoginRequiredError("acc", "later fail"))

        # That last event should be treated as a fresh attempt — relogin runs,
        # breaker is NOT tripped.
        assert mock_relogin.await_count == _FATAL_AUTH_CIRCUIT_MAX + 1
        client.on_unrecoverable_auth_error.assert_not_awaited()
