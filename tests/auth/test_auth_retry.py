"""Tests for MammotionClient._send_with_auth_retry credential refresh cascade."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.client import MammotionClient
from pymammotion.transport.base import (
    AuthError,
    LoginFailedError,
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
        tm.force_refresh = AsyncMock()
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
    session.token_manager.force_refresh.assert_not_awaited()


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
    session.token_manager.force_refresh.assert_not_awaited()


async def test_mammotion_session_expired_targeted_refresh_succeeds() -> None:
    """SessionExpiredError(CLOUD_MAMMOTION) → refresh_mqtt_credentials → retry succeeds."""
    client, session = _make_client()
    send_fn = AsyncMock(side_effect=[SessionExpiredError(TransportType.CLOUD_MAMMOTION), None])

    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2
    session.token_manager.refresh_mqtt_credentials.assert_awaited_once()
    session.token_manager.refresh_aliyun_credentials.assert_not_awaited()
    session.token_manager.force_refresh.assert_not_awaited()


# ---------------------------------------------------------------------------
# SessionExpiredError — targeted refresh fails, force_refresh succeeds
# ---------------------------------------------------------------------------


async def test_targeted_refresh_fails_force_refresh_succeeds() -> None:
    """Targeted refresh doesn't fix it → force_refresh → third attempt succeeds."""
    client, session = _make_client()
    send_fn = AsyncMock(
        side_effect=[
            SessionExpiredError(TransportType.CLOUD_ALIYUN),
            SessionExpiredError(TransportType.CLOUD_ALIYUN),
            None,
        ]
    )

    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 3
    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()
    session.token_manager.force_refresh.assert_awaited_once()


async def test_targeted_refresh_fails_with_auth_error_then_force_refresh() -> None:
    """Retry after targeted refresh raises AuthError → falls back to force_refresh."""
    client, session = _make_client()
    send_fn = AsyncMock(
        side_effect=[
            SessionExpiredError(TransportType.CLOUD_MAMMOTION),
            AuthError("still broken"),
            None,
        ]
    )

    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 3
    session.token_manager.refresh_mqtt_credentials.assert_awaited_once()
    session.token_manager.force_refresh.assert_awaited_once()


# ---------------------------------------------------------------------------
# SessionExpiredError — all retries fail → propagate
# ---------------------------------------------------------------------------


async def test_all_retries_fail_propagates_exception() -> None:
    """When all three attempts fail, the final exception propagates."""
    client, session = _make_client()
    final_error = SessionExpiredError(TransportType.CLOUD_ALIYUN, "still dead")
    send_fn = AsyncMock(
        side_effect=[
            SessionExpiredError(TransportType.CLOUD_ALIYUN),
            SessionExpiredError(TransportType.CLOUD_ALIYUN),
            final_error,
        ]
    )

    with pytest.raises(SessionExpiredError, match="still dead"):
        await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 3


# ---------------------------------------------------------------------------
# Plain AuthError — goes straight to force_refresh
# ---------------------------------------------------------------------------


async def test_auth_error_force_refresh_succeeds() -> None:
    """Plain AuthError (e.g. from mqtt.py) → force_refresh → retry succeeds."""
    client, session = _make_client()
    send_fn = AsyncMock(side_effect=[AuthError("mqtt rejected"), None])

    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2
    session.token_manager.force_refresh.assert_awaited_once()
    session.token_manager.refresh_aliyun_credentials.assert_not_awaited()
    session.token_manager.refresh_mqtt_credentials.assert_not_awaited()


async def test_auth_error_force_refresh_fails_propagates() -> None:
    """Plain AuthError → force_refresh → retry also fails → propagates."""
    client, session = _make_client()
    send_fn = AsyncMock(side_effect=[AuthError("first"), AuthError("second")])

    with pytest.raises(AuthError, match="second"):
        await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2
    session.token_manager.force_refresh.assert_awaited_once()


# ---------------------------------------------------------------------------
# ReLoginRequiredError triggers _full_relogin
# ---------------------------------------------------------------------------


async def test_relogin_required_from_force_refresh_triggers_full_relogin() -> None:
    """force_refresh raises ReLoginRequiredError → _full_relogin is attempted."""
    client, session = _make_client()
    session.token_manager.force_refresh = AsyncMock(
        side_effect=[ReLoginRequiredError("user@example.com", "refresh token expired"), None]
    )
    login_resp = MagicMock()
    login_resp.code = 0
    session.mammotion_http.login_v2 = AsyncMock(return_value=login_resp)
    send_fn = AsyncMock(side_effect=[AuthError("expired"), None])

    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2
    session.mammotion_http.login_v2.assert_awaited_once()
    assert session.token_manager.force_refresh.await_count == 2


async def test_full_relogin_fails_raises_login_failed_error() -> None:
    """If _full_relogin also fails, LoginFailedError propagates to the caller."""
    client, session = _make_client()
    session.token_manager.force_refresh = AsyncMock(
        side_effect=ReLoginRequiredError("user@example.com", "refresh token expired")
    )
    login_resp = MagicMock()
    login_resp.code = 500
    login_resp.msg = "server error"
    session.mammotion_http.login_v2 = AsyncMock(return_value=login_resp)
    send_fn = AsyncMock(side_effect=AuthError("expired"))

    with pytest.raises(LoginFailedError, match="server error"):
        await client._send_with_auth_retry(send_fn, session)

    send_fn.assert_awaited_once()


async def test_relogin_required_from_targeted_refresh_triggers_full_relogin() -> None:
    """Targeted refresh raises ReLoginRequiredError → _full_relogin is attempted."""
    client, session = _make_client()
    session.token_manager.refresh_aliyun_credentials = AsyncMock(
        side_effect=ReLoginRequiredError("user@example.com", "session gone")
    )
    login_resp = MagicMock()
    login_resp.code = 0
    session.mammotion_http.login_v2 = AsyncMock(return_value=login_resp)
    send_fn = AsyncMock(side_effect=[SessionExpiredError(TransportType.CLOUD_ALIYUN), None])

    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2
    session.mammotion_http.login_v2.assert_awaited_once()


# ---------------------------------------------------------------------------
# No token manager — retry without refresh
# ---------------------------------------------------------------------------


async def test_no_token_manager_session_expired_retries_without_refresh() -> None:
    """Without a token manager, send is retried but no refresh is called."""
    client, session = _make_client(has_token_manager=False)
    send_fn = AsyncMock(side_effect=[SessionExpiredError(TransportType.CLOUD_ALIYUN), None])

    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2


async def test_no_token_manager_auth_error_retries_without_refresh() -> None:
    """Without a token manager, AuthError path retries without refresh."""
    client, session = _make_client(has_token_manager=False)
    send_fn = AsyncMock(side_effect=[AuthError("no creds"), None])

    await client._send_with_auth_retry(send_fn, session)

    assert send_fn.await_count == 2


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
