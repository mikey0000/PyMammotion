"""Tests for the serialized, cooldown-protected OAuth refresh path in MammotionHTTP.

Covers the fixes for the oauth2/token hammering reported by Mammotion:
- ensure_token_valid() serializes concurrent refreshes (no stampede) and arms a
  failure cooldown so a persistently failing refresh cannot fire on every call.
- refresh_token_v2()/login_v2() raise ConnectionError on 408/429/5xx or non-JSON
  bodies so a server outage backs off instead of escalating to password logins.
- refresh_login() falls back to login_v2 ONLY on an explicit refresh-token
  rejection, never on a transient server failure.
- Successful oauth2/token exchanges fire on_login_refreshed so rotations get
  persisted.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import time
from unittest.mock import AsyncMock, MagicMock

from aiohttp import ClientError, ContentTypeError
import jwt as pyjwt
import pytest

from pymammotion.http.http import _REFRESH_FAILURE_COOLDOWN, MammotionHTTP


def _jwt(expires_in: float = 3600.0) -> str:
    """Return an unsigned-verifiable JWT with the given relative expiry."""
    return pyjwt.encode({"exp": int(time.time() + expires_in), "iot": "", "robot": ""}, "x", algorithm="HS256")


def _login_payload(access_token: str | None = None) -> dict:
    """A full, decodable oauth2/token success body."""
    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "access_token": access_token or _jwt(),
            "token_type": "bearer",
            "refresh_token": "new-ref",
            "expires_in": 3600,
            "authorization_code": "authcode",
            "userInformation": {
                "areaCode": "US",
                "domainAbbreviation": "US",
                "userId": "1",
                "userAccount": "42",
                "authType": "0",
            },
        },
    }


def _make_http(status: int = 200, json_data: dict | None = None, json_exc: Exception | None = None) -> MammotionHTTP:
    """Build a MammotionHTTP whose _client_session posts return a canned response."""
    http = MammotionHTTP(account="a@b.c", password="pw")
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data, side_effect=json_exc)
    mock_session = MagicMock()
    mock_session.post = AsyncMock(return_value=resp)

    @asynccontextmanager
    async def _fake_session() -> object:  # type: ignore[misc]
        yield mock_session

    http._client_session = _fake_session  # type: ignore[method-assign]
    return http


# ---------------------------------------------------------------------------
# ensure_token_valid — serialization + cooldown
# ---------------------------------------------------------------------------


async def test_ensure_token_valid_skips_when_token_fresh() -> None:
    http = MammotionHTTP()
    http.expires_in = time.time() + 3600
    http._refresh_login_locked = AsyncMock()  # type: ignore[method-assign]

    await http.ensure_token_valid()

    http._refresh_login_locked.assert_not_awaited()


async def test_concurrent_callers_produce_exactly_one_refresh() -> None:
    """The documented stampede: N near-expiry callers must NOT each fire a refresh."""
    http = MammotionHTTP()
    http.expires_in = 0.0  # stale

    async def _refresh() -> MagicMock:
        await asyncio.sleep(0)  # let the other callers pile up on the lock
        http.expires_in = time.time() + 3600
        return MagicMock(code=0)

    http._refresh_login_locked = AsyncMock(side_effect=_refresh)  # type: ignore[method-assign]

    await asyncio.gather(*(http.ensure_token_valid(caller=f"c{i}") for i in range(5)))

    assert http._refresh_login_locked.await_count == 1


async def test_decorator_routes_through_ensure_token_valid() -> None:
    @MammotionHTTP.refresh_token_decorator
    async def _probe(self: MammotionHTTP) -> str:
        return "ok"

    http = MammotionHTTP()
    http.ensure_token_valid = AsyncMock()  # type: ignore[method-assign]

    assert await _probe(http) == "ok"
    http.ensure_token_valid.assert_awaited_once()


async def test_rejected_refresh_arms_cooldown() -> None:
    """A refresh rejected by the server must not be retried on the very next call."""
    http = MammotionHTTP()
    http.expires_in = 0.0
    http._refresh_login_locked = AsyncMock(return_value=MagicMock(code=401))  # type: ignore[method-assign]

    await http.ensure_token_valid()
    await http.ensure_token_valid()  # within cooldown — must not refresh again

    assert http._refresh_login_locked.await_count == 1
    assert http._refresh_failed_at is not None


async def test_transient_refresh_error_arms_cooldown_without_raising() -> None:
    http = MammotionHTTP()
    http.expires_in = 0.0
    http._refresh_login_locked = AsyncMock(side_effect=ClientError("boom"))  # type: ignore[method-assign]

    await http.ensure_token_valid()  # must not raise

    assert http._refresh_failed_at is not None
    await http.ensure_token_valid()
    assert http._refresh_login_locked.await_count == 1


async def test_cooldown_expiry_allows_retry() -> None:
    http = MammotionHTTP()
    http.expires_in = 0.0
    http._refresh_login_locked = AsyncMock(return_value=MagicMock(code=401))  # type: ignore[method-assign]

    await http.ensure_token_valid()
    http._refresh_failed_at = time.monotonic() - (_REFRESH_FAILURE_COOLDOWN + 1.0)
    await http.ensure_token_valid()

    assert http._refresh_login_locked.await_count == 2


async def test_successful_refresh_clears_cooldown() -> None:
    http = MammotionHTTP()
    http.expires_in = 0.0
    http._refresh_failed_at = time.monotonic() - (_REFRESH_FAILURE_COOLDOWN + 1.0)

    async def _refresh() -> MagicMock:
        http.expires_in = time.time() + 3600
        return MagicMock(code=0)

    http._refresh_login_locked = AsyncMock(side_effect=_refresh)  # type: ignore[method-assign]

    await http.ensure_token_valid()

    assert http._refresh_failed_at is None


# ---------------------------------------------------------------------------
# refresh_login — fallback policy
# ---------------------------------------------------------------------------


async def test_refresh_login_does_not_password_login_on_server_outage() -> None:
    """A 5xx from oauth2/token must propagate as ConnectionError, never trigger login_v2."""
    http = MammotionHTTP(account="a@b.c", password="pw")
    http.login_info = MagicMock(refresh_token="ref")  # type: ignore[assignment]
    http._refresh_token_v2_locked = AsyncMock(side_effect=ConnectionError("HTTP 503"))  # type: ignore[method-assign]
    http.login_v2 = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(ConnectionError):
        await http.refresh_login()

    http.login_v2.assert_not_awaited()


async def test_refresh_login_falls_back_on_explicit_rejection() -> None:
    """An explicit refresh-token rejection (JSON code != 0) still falls back to login_v2."""
    http = MammotionHTTP(account="a@b.c", password="pw")
    http.login_info = MagicMock(refresh_token="ref")  # type: ignore[assignment]
    http._refresh_token_v2_locked = AsyncMock(return_value=MagicMock(code=2401))  # type: ignore[method-assign]
    sentinel = MagicMock(code=0)
    http.login_v2 = AsyncMock(return_value=sentinel)  # type: ignore[method-assign]

    result = await http.refresh_login()

    assert result is sentinel
    http.login_v2.assert_awaited_once_with("a@b.c", "pw")


# ---------------------------------------------------------------------------
# refresh_token_v2 / login_v2 — transient server failures raise ConnectionError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503])
async def test_refresh_token_v2_raises_connection_error_on_server_failure(status: int) -> None:
    http = _make_http(status=status)
    http.login_info = MagicMock(refresh_token="ref")  # type: ignore[assignment]

    with pytest.raises(ConnectionError):
        await http.refresh_token_v2()


async def test_refresh_token_v2_raises_connection_error_on_non_json_body() -> None:
    http = _make_http(status=200, json_exc=ContentTypeError(MagicMock(), ()))
    http.login_info = MagicMock(refresh_token="ref")  # type: ignore[assignment]

    with pytest.raises(ConnectionError):
        await http.refresh_token_v2()


@pytest.mark.parametrize("status", [429, 503])
async def test_login_v2_raises_connection_error_on_server_failure(status: int) -> None:
    http = _make_http(status=status)

    with pytest.raises(ConnectionError):
        await http.login_v2("a@b.c", "pw")


# ---------------------------------------------------------------------------
# on_login_refreshed — rotations are observable (so TokenManager can persist them)
# ---------------------------------------------------------------------------


async def test_refresh_token_v2_success_fires_on_login_refreshed() -> None:
    http = _make_http(status=200, json_data=_login_payload())
    http.login_info = MagicMock(refresh_token="ref", access_token="old-tok")  # type: ignore[assignment]
    http.on_login_refreshed = AsyncMock()

    result = await http.refresh_token_v2()

    assert result.code == 0
    http.on_login_refreshed.assert_awaited_once()


async def test_login_v2_success_fires_on_login_refreshed() -> None:
    http = _make_http(status=200, json_data=_login_payload())
    http.on_login_refreshed = AsyncMock()

    result = await http.login_v2("a@b.c", "pw")

    assert result.code == 0
    http.on_login_refreshed.assert_awaited_once()


async def test_listener_failure_does_not_break_refresh() -> None:
    http = _make_http(status=200, json_data=_login_payload())
    http.login_info = MagicMock(refresh_token="ref", access_token="old-tok")  # type: ignore[assignment]
    http.on_login_refreshed = AsyncMock(side_effect=RuntimeError("persist failed"))

    result = await http.refresh_token_v2()

    assert result.code == 0  # the refresh itself must still succeed
