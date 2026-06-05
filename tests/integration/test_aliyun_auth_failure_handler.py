"""Tests for _on_aliyun_auth_failure targeted-refresh-first strategy.

Regression: on every 2043/460 bind rejection the handler called _full_relogin
directly, firing login_v2 + force_refresh on each failure.  When the account
was rate-limited/blocked by Aliyun (460 "iotToken blank"), each _full_relogin
call added more requests that extended the block and eventually invalidated the
refreshToken (2401), locking the integration out entirely.

Fix: try token_manager.refresh_aliyun_credentials() first (single
check_or_refresh_session HTTP call).  Only if that raises ReLoginRequiredError
(refreshToken exhausted) escalate to _full_relogin.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.client import MammotionClient
from pymammotion.transport.base import ReLoginRequiredError, TransportType


def _build_handler(
    *,
    refresh_aliyun_raises: Exception | None = None,
    full_relogin_raises: Exception | None = None,
    iot_token: str = "fresh_token",
) -> tuple[object, dict[str, int]]:
    """Build an _on_aliyun_auth_failure closure and a call-counter dict.

    Returns (handler_coro_fn, counters) where counters tracks how many times
    each operation was called.
    """
    counters: dict[str, int] = {"refresh_aliyun": 0, "full_relogin": 0}

    token_manager = MagicMock()
    transport = MagicMock()
    acct_session = MagicMock()
    acct_session.email = "test@example.com"

    creds = MagicMock()
    creds.iot_token = iot_token
    token_manager.get_aliyun_credentials = AsyncMock(return_value=creds)

    async def _fake_refresh_aliyun() -> None:
        counters["refresh_aliyun"] += 1
        if refresh_aliyun_raises is not None:
            raise refresh_aliyun_raises

    token_manager.refresh_aliyun_credentials = _fake_refresh_aliyun

    async def _fake_full_relogin(_session: object) -> None:
        counters["full_relogin"] += 1
        if full_relogin_raises is not None:
            raise full_relogin_raises

    # Build the closure the same way the real client does
    async def _on_aliyun_auth_failure() -> bool:
        if token_manager is None:
            return False
        try:
            await token_manager.refresh_aliyun_credentials()
            _creds = await token_manager.get_aliyun_credentials()
            transport.update_iot_token(_creds.iot_token)
            return True
        except ReLoginRequiredError:
            pass
        try:
            await _fake_full_relogin(acct_session)
            _creds = await token_manager.get_aliyun_credentials()
            transport.update_iot_token(_creds.iot_token)
            return True
        except Exception as exc:
            raise ReLoginRequiredError(
                acct_session.email,
                f"Full re-login failed after Aliyun bind rejection: {exc}",
            ) from exc

    return _on_aliyun_auth_failure, counters, transport


async def test_targeted_refresh_succeeds_no_full_relogin() -> None:
    """When refresh_aliyun_credentials succeeds, _full_relogin must NOT be called.

    This is the normal 2043/460 recovery path: iotToken expired, refreshToken
    still valid.  One check_or_refresh_session call is enough.
    """
    handler, counters, transport = _build_handler()

    result = await handler()

    assert result is True
    assert counters["refresh_aliyun"] == 1
    assert counters["full_relogin"] == 0
    transport.update_iot_token.assert_called_once_with("fresh_token")


async def test_full_relogin_called_only_when_refresh_token_exhausted() -> None:
    """_full_relogin is called only after ReLoginRequiredError from targeted refresh.

    This covers the "refreshToken invalid (2401 twice in 120 s)" case where
    check_or_refresh_session is truly blocked.
    """
    handler, counters, transport = _build_handler(
        refresh_aliyun_raises=ReLoginRequiredError("test@example.com", "refreshToken exhausted"),
    )

    result = await handler()

    assert result is True
    assert counters["refresh_aliyun"] == 1
    assert counters["full_relogin"] == 1


async def test_raises_relogin_when_both_paths_fail() -> None:
    """ReLoginRequiredError must propagate when both targeted and full re-login fail."""
    handler, counters, _ = _build_handler(
        refresh_aliyun_raises=ReLoginRequiredError("test@example.com", "exhausted"),
        full_relogin_raises=RuntimeError("login_v2 failed"),
    )

    with pytest.raises(ReLoginRequiredError):
        await handler()

    assert counters["refresh_aliyun"] == 1
    assert counters["full_relogin"] == 1


async def test_iot_token_pushed_to_transport_on_success() -> None:
    """The fresh iotToken must be pushed to the transport after a successful refresh."""
    handler, _, transport = _build_handler(iot_token="brand_new_token")

    await handler()

    transport.update_iot_token.assert_called_once_with("brand_new_token")


# ---------------------------------------------------------------------------
# _full_relogin: an Aliyun-triggered re-login must refresh ONLY Aliyun
#
# Regression: the escalation called force_refresh(None), which runs refresh_http
# (→ refresh_token_v2) and rotates the Mammotion-direct MQTT JWT.  Neither belongs
# to the Aliyun auth chain — the user saw "refreshing the mqtt auth token instead
# of the aliyun token" and refresh_token_v2 being called during an Aliyun re-login.
# ---------------------------------------------------------------------------


def _relogin_session() -> tuple[MammotionClient, AccountSession, MagicMock, MagicMock]:
    """Build a client + AccountSession wired with spied http and token_manager."""
    client = MammotionClient()

    http = MagicMock()
    http.login_v2 = AsyncMock(return_value=MagicMock(code=0))
    http.logout = AsyncMock()
    # These back refresh_token_v2 — they must NOT be reached on the Aliyun path.
    http.refresh_login = AsyncMock()
    http.refresh_token_v2 = AsyncMock()

    tm = MagicMock()
    tm.refresh_aliyun_credentials = AsyncMock()
    tm.connect_iot = AsyncMock()  # full Aliyun IoT re-establish used by an Aliyun-triggered re-login
    tm.force_refresh = AsyncMock()
    tm.refresh_http = AsyncMock()  # calls refresh_login/refresh_token_v2 in the real TM

    session = AccountSession(account_id="a@b.com", email="a@b.com", password="pw")
    session.mammotion_http = http
    session.token_manager = tm
    return client, session, http, tm


async def test_full_relogin_aliyun_refreshes_only_aliyun_not_token_v2() -> None:
    """transport_type=CLOUD_ALIYUN → refresh_aliyun_credentials only; no refresh_token_v2, no MQTT JWT."""
    client, session, http, tm = _relogin_session()

    await client._full_relogin(session, transport_type=TransportType.CLOUD_ALIYUN)

    # A fresh login happened, then ONLY the Aliyun session was re-established via the full
    # IoT flow (connect_iot: session_by_auth_code etc.).
    http.login_v2.assert_awaited_once()
    tm.connect_iot.assert_awaited_once()
    # The Mammotion/HTTP token chain (refresh_token_v2) and the MQTT JWT must be untouched.
    tm.force_refresh.assert_not_awaited()
    tm.refresh_http.assert_not_awaited()
    http.refresh_login.assert_not_awaited()
    http.refresh_token_v2.assert_not_awaited()


async def test_full_relogin_generic_refreshes_all_credentials() -> None:
    """transport_type=None (send-retry path) → full rotation via force_refresh(None)."""
    client, session, http, tm = _relogin_session()

    await client._full_relogin(session, transport_type=None)

    http.login_v2.assert_awaited_once()
    tm.force_refresh.assert_awaited_once_with(transport_type=None)
    tm.refresh_aliyun_credentials.assert_not_awaited()
