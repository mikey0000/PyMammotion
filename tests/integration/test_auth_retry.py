"""Tests for MammotionClient._send_with_auth_retry: one targeted refresh, one retry, then propagate."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.client import MammotionClient
from pymammotion.transport.base import (
    AuthError,
    ReLoginRequiredError,
    SessionExpiredError,
    TransportType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(*, has_token_manager: bool = True) -> AccountSession:
    """Return an AccountSession with mocked token manager and HTTP client."""
    session = AccountSession(
        account_id="test@example.com",
        email="test@example.com",
        password="password123",
    )
    session.mammotion_http = MagicMock()
    if has_token_manager:
        tm = AsyncMock()
        tm.refresh_aliyun_credentials = AsyncMock()
        tm.refresh_mqtt_credentials = AsyncMock()
        session.token_manager = tm
    return session


def _make_client(*, has_token_manager: bool = True) -> tuple[MammotionClient, AccountSession]:
    """Return a (client, session) with the session registered in the account registry."""
    client = MammotionClient.__new__(MammotionClient)
    from pymammotion.account.registry import AccountRegistry

    client._account_registry = AccountRegistry()
    session = _make_session(has_token_manager=has_token_manager)
    # Bypass the async lock — directly insert into the internal dict
    client._account_registry._sessions[session.account_id] = session
    return client, session


# ---------------------------------------------------------------------------
# Happy path — no error
# ---------------------------------------------------------------------------


async def test_send_succeeds_no_retry() -> None:
    """When send_fn succeeds on the first call, no refresh is attempted."""
    client, session = _make_client()
    send_fn = AsyncMock()

    await client._send_with_auth_retry(send_fn, session)

    send_fn.assert_awaited_once()
    session.token_manager.refresh_aliyun_credentials.assert_not_awaited()
    session.token_manager.refresh_mqtt_credentials.assert_not_awaited()


# ---------------------------------------------------------------------------
# SessionExpiredError — targeted refresh succeeds
# ---------------------------------------------------------------------------


async def test_aliyun_session_expired_targeted_refresh_succeeds() -> None:
    """SessionExpiredError(CLOUD_ALIYUN) → refresh_aliyun_credentials → retry succeeds."""
    client, session = _make_client()
    send_fn = AsyncMock(side_effect=[SessionExpiredError(TransportType.CLOUD_ALIYUN), None])

    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2
    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()


async def test_mammotion_session_expired_targeted_refresh_succeeds() -> None:
    """SessionExpiredError(CLOUD_MAMMOTION) → refresh_mqtt_credentials → retry succeeds."""
    client, session = _make_client()
    send_fn = AsyncMock(side_effect=[SessionExpiredError(TransportType.CLOUD_MAMMOTION), None])

    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2
    session.token_manager.refresh_mqtt_credentials.assert_awaited_once()
    session.token_manager.refresh_aliyun_credentials.assert_not_awaited()


# ---------------------------------------------------------------------------
# Targeted refresh is the ONLY recovery — no escalation ladder
# ---------------------------------------------------------------------------


async def test_targeted_refresh_fails_propagates_without_escalating() -> None:
    """One targeted refresh, one retry, then the error propagates.

    The old cascade retried up to four times, escalating to an account-wide
    refresh and then a password re-login.  Each rung fired more auth traffic for a
    credential that had already been rejected once.
    """
    client, session = _make_client()
    final_error = SessionExpiredError(TransportType.CLOUD_ALIYUN, "still dead")
    send_fn = AsyncMock(side_effect=[SessionExpiredError(TransportType.CLOUD_ALIYUN), final_error])

    with pytest.raises(SessionExpiredError, match="still dead"):
        await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2
    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()


async def test_plain_auth_error_propagates_without_refresh() -> None:
    """A transport-agnostic AuthError has no transport to target, so it propagates.

    The transports already run their own scoped recovery (MQTTTransport refreshes
    the invoke token; the Aliyun transport refreshes its IoT session).  Retrying
    here as well just duplicated that work with an account-wide refresh.
    """
    client, session = _make_client()
    send_fn = AsyncMock(side_effect=AuthError("mqtt rejected"))

    with pytest.raises(AuthError, match="mqtt rejected"):
        await client._send_with_auth_retry(send_fn, session)

    send_fn.assert_awaited_once()
    session.token_manager.refresh_aliyun_credentials.assert_not_awaited()
    session.token_manager.refresh_mqtt_credentials.assert_not_awaited()


async def test_relogin_required_reaches_the_host() -> None:
    """ReLoginRequiredError must propagate so the host can prompt for re-auth."""
    client, session = _make_client()
    session.mammotion_http.login_v2 = AsyncMock()
    send_fn = AsyncMock(side_effect=ReLoginRequiredError("user@example.com", "refresh token expired"))

    with pytest.raises(ReLoginRequiredError):
        await client._send_with_auth_retry(send_fn, session)

    session.mammotion_http.login_v2.assert_not_awaited()


async def test_relogin_required_from_targeted_refresh_reaches_the_host() -> None:
    """A refresh that reports "re-auth required" must not be answered with a password."""
    client, session = _make_client()
    session.token_manager.refresh_aliyun_credentials = AsyncMock(
        side_effect=ReLoginRequiredError("user@example.com", "session gone")
    )
    session.mammotion_http.login_v2 = AsyncMock()
    send_fn = AsyncMock(side_effect=SessionExpiredError(TransportType.CLOUD_ALIYUN))

    with pytest.raises(ReLoginRequiredError):
        await client._send_with_auth_retry(send_fn, session)

    session.mammotion_http.login_v2.assert_not_awaited()


@pytest.mark.parametrize(
    "error",
    [
        SessionExpiredError(TransportType.CLOUD_ALIYUN, "expired"),
        SessionExpiredError(TransportType.CLOUD_MAMMOTION, "expired"),
        AuthError("rejected"),
        ReLoginRequiredError("user@example.com", "dead"),
    ],
    ids=["aliyun-expired", "mammotion-expired", "auth-error", "relogin-required"],
)
async def test_no_send_failure_ever_triggers_a_password_login(error: Exception) -> None:
    """The core invariant, swept across every auth failure the send path can raise."""
    client, session = _make_client()
    session.mammotion_http.login_v2 = AsyncMock()
    session.mammotion_http.logout = AsyncMock()
    send_fn = AsyncMock(side_effect=error)

    with pytest.raises(Exception):  # noqa: B017 - the type varies; the assertion below is the point
        await client._send_with_auth_retry(send_fn, session)

    session.mammotion_http.login_v2.assert_not_awaited()
    session.mammotion_http.logout.assert_not_awaited()


# ---------------------------------------------------------------------------
# No token manager — retry without refresh
# ---------------------------------------------------------------------------


async def test_no_token_manager_session_expired_retries_without_refresh() -> None:
    """Without a token manager, send is retried but no refresh is called."""
    client, session = _make_client(has_token_manager=False)
    send_fn = AsyncMock(side_effect=[SessionExpiredError(TransportType.CLOUD_ALIYUN), None])

    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2


async def test_no_token_manager_auth_error_propagates() -> None:
    """Without a token manager there is nothing to refresh — the error propagates."""
    client, session = _make_client(has_token_manager=False)
    send_fn = AsyncMock(side_effect=AuthError("no creds"))

    with pytest.raises(AuthError):
        await client._send_with_auth_retry(send_fn, session)

    send_fn.assert_awaited_once()


# ---------------------------------------------------------------------------
# CheckSessionException backward compat
# ---------------------------------------------------------------------------


async def test_check_session_exception_caught_as_session_expired() -> None:
    """CheckSessionException (backward-compat subclass) is handled as SessionExpiredError."""
    from pymammotion.aliyun.exceptions import CheckSessionException

    client, session = _make_client()
    send_fn = AsyncMock(side_effect=[CheckSessionException("legacy error"), None])

    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2
    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()


# ---------------------------------------------------------------------------
# _refresh_for_transport dispatches correctly
# ---------------------------------------------------------------------------


async def test_refresh_for_transport_aliyun() -> None:
    """_refresh_for_transport(CLOUD_ALIYUN) calls refresh_aliyun_credentials."""
    client, session = _make_client()
    await client._refresh_for_transport(TransportType.CLOUD_ALIYUN, session)
    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()
    session.token_manager.refresh_mqtt_credentials.assert_not_awaited()


async def test_refresh_for_transport_mammotion() -> None:
    """_refresh_for_transport(CLOUD_MAMMOTION) calls refresh_mqtt_credentials."""
    client, session = _make_client()
    await client._refresh_for_transport(TransportType.CLOUD_MAMMOTION, session)
    session.token_manager.refresh_mqtt_credentials.assert_awaited_once()
    session.token_manager.refresh_aliyun_credentials.assert_not_awaited()


async def test_refresh_for_transport_ble_is_noop() -> None:
    """_refresh_for_transport(BLE) does nothing — BLE has no token to refresh."""
    client, session = _make_client()
    await client._refresh_for_transport(TransportType.BLE, session)
    session.token_manager.refresh_aliyun_credentials.assert_not_awaited()
    session.token_manager.refresh_mqtt_credentials.assert_not_awaited()
