"""Tests for the serialized, refresh-token-only OAuth path in MammotionHTTP.

Covers the oauth2/token hammering fixes reported by Mammotion, and the stronger
policy that replaced them: MammotionHTTP never mints a session from a stored
password on its own.

- ensure_token_valid() serializes concurrent refreshes (no stampede).
- A *rejected* refresh token is terminal: ReLoginRequiredError propagates to the
  host so it can prompt for re-authentication.  It is NOT retried on a timer and
  it never falls back to login_v2.
- A *transient* server failure (408/429/5xx, non-JSON body, connection error)
  raises its own exception type so callers back off.  It must never be
  reclassified as an auth failure, and never escalate to a password login.
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

from pymammotion.http.http import MammotionHTTP
from pymammotion.transport.base import ReLoginRequiredError


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


def _logged_in(http: MammotionHTTP) -> MammotionHTTP:
    """Give *http* a login session so ensure_token_valid has something to refresh."""
    http.login_info = MagicMock(refresh_token="ref", access_token="old-tok")  # type: ignore[assignment]
    return http


# ---------------------------------------------------------------------------
# ensure_token_valid — serialization
# ---------------------------------------------------------------------------


async def test_ensure_token_valid_skips_when_token_fresh() -> None:
    http = _logged_in(MammotionHTTP())
    http.expires_in = time.time() + 3600
    http._refresh_token_v2_locked = AsyncMock()  # type: ignore[method-assign]

    await http.ensure_token_valid()

    http._refresh_token_v2_locked.assert_not_awaited()


async def test_concurrent_callers_produce_exactly_one_refresh() -> None:
    """The documented stampede: N near-expiry callers must NOT each fire a refresh."""
    http = _logged_in(MammotionHTTP())
    http.expires_in = 0.0  # stale

    async def _refresh() -> MagicMock:
        await asyncio.sleep(0)  # let the other callers pile up on the lock
        http.expires_in = time.time() + 3600
        return MagicMock(code=0)

    http._refresh_token_v2_locked = AsyncMock(side_effect=_refresh)  # type: ignore[method-assign]

    await asyncio.gather(*(http.ensure_token_valid(caller=f"c{i}") for i in range(5)))

    assert http._refresh_token_v2_locked.await_count == 1


async def test_decorator_routes_through_ensure_token_valid() -> None:
    @MammotionHTTP.refresh_token_decorator
    async def _probe(self: MammotionHTTP) -> str:
        return "ok"

    http = MammotionHTTP()
    http.ensure_token_valid = AsyncMock()  # type: ignore[method-assign]

    assert await _probe(http) == "ok"
    http.ensure_token_valid.assert_awaited_once()


# ---------------------------------------------------------------------------
# ensure_token_valid — a rejected refresh token is terminal
# ---------------------------------------------------------------------------


async def test_rejected_refresh_raises_relogin_required() -> None:
    """A rejected refresh token must surface so the host can prompt for re-auth."""
    http = _logged_in(MammotionHTTP())
    http.expires_in = 0.0
    http._refresh_token_v2_locked = AsyncMock(return_value=MagicMock(code=2401))  # type: ignore[method-assign]

    with pytest.raises(ReLoginRequiredError):
        await http.ensure_token_valid()


async def test_rejected_refresh_never_falls_back_to_login_v2() -> None:
    """The core policy: no decorated call may turn into a password grant."""
    http = _logged_in(MammotionHTTP())
    http.expires_in = 0.0
    http._refresh_token_v2_locked = AsyncMock(return_value=MagicMock(code=2401))  # type: ignore[method-assign]
    http.login_v2 = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(ReLoginRequiredError):
        await http.ensure_token_valid()

    http.login_v2.assert_not_awaited()


async def test_no_login_session_raises_relogin_required() -> None:
    """Nothing to refresh means re-auth, not a silent password login."""
    http = MammotionHTTP(account="a@b.c", password="pw")
    http.expires_in = 0.0
    http.login_v2 = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(ReLoginRequiredError):
        await http.ensure_token_valid()

    http.login_v2.assert_not_awaited()


async def test_decorated_endpoint_surfaces_relogin_required() -> None:
    """The terminal signal must reach the endpoint's caller, not be swallowed."""

    @MammotionHTTP.refresh_token_decorator
    async def _probe(self: MammotionHTTP) -> str:
        return "should not run"

    http = _logged_in(MammotionHTTP())
    http.expires_in = 0.0
    http._refresh_token_v2_locked = AsyncMock(return_value=MagicMock(code=2401))  # type: ignore[method-assign]

    with pytest.raises(ReLoginRequiredError):
        await _probe(http)


# ---------------------------------------------------------------------------
# ensure_token_valid — transient failures are NOT auth failures
# ---------------------------------------------------------------------------


async def test_transient_refresh_error_propagates_as_itself() -> None:
    """A network blip must stay a network error so the caller backs off."""
    http = _logged_in(MammotionHTTP())
    http.expires_in = 0.0
    http._refresh_token_v2_locked = AsyncMock(side_effect=ClientError("boom"))  # type: ignore[method-assign]

    with pytest.raises(ClientError):
        await http.ensure_token_valid()


async def test_transient_refresh_error_does_not_trigger_login_v2() -> None:
    """A server outage must never escalate into a password login."""
    http = _logged_in(MammotionHTTP())
    http.expires_in = 0.0
    http._refresh_token_v2_locked = AsyncMock(side_effect=ConnectionError("HTTP 503"))  # type: ignore[method-assign]
    http.login_v2 = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(ConnectionError):
        await http.ensure_token_valid()

    http.login_v2.assert_not_awaited()


async def test_transient_refresh_error_is_not_relogin_required() -> None:
    """Explicitly: ClientError must not be reclassified as an auth failure."""
    http = _logged_in(MammotionHTTP())
    http.expires_in = 0.0
    http._refresh_token_v2_locked = AsyncMock(side_effect=ClientError("boom"))  # type: ignore[method-assign]

    with pytest.raises(ClientError) as excinfo:
        await http.ensure_token_valid()

    assert not isinstance(excinfo.value, ReLoginRequiredError)


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


# ---------------------------------------------------------------------------
# No automatic password login anywhere in MammotionHTTP
# ---------------------------------------------------------------------------


def test_no_refresh_helper_can_reach_login_v2() -> None:
    """Structural guard: only the explicit login entry points call login_v2.

    ``login_v2`` remains the way a caller logs in — but no refresh/renew helper
    may invoke it, because that would bypass the host's re-auth prompt and fire a
    password grant per queued request during an outage.

    Checked against the AST rather than the source text so that prose explaining
    the policy does not count as a violation of it.
    """
    import ast
    import inspect
    import textwrap

    def _calls(func: object) -> set[str]:
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))  # type: ignore[arg-type]
        return {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }

    for name in ("ensure_token_valid", "refresh_token_v2", "_refresh_token_v2_locked", "fetch_authorization_token"):
        assert "login_v2" not in _calls(getattr(MammotionHTTP, name)), f"{name} must not call login_v2"
        assert "login" not in _calls(getattr(MammotionHTTP, name)), f"{name} must not call login"


def test_handle_expiry_is_gone() -> None:
    """handle_expiry re-logged in from a stored password on any 401 — it must stay removed."""
    assert not hasattr(MammotionHTTP, "handle_expiry")
    assert not hasattr(MammotionHTTP, "refresh_login")
