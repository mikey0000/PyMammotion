"""Failure scoping when the Mammotion MQTT JWT cannot be renewed.

CLAUDE.md splits auth failures two ways.  An *account-scoped* failure (the HTTP
refresh token was rejected) kills every cloud path and must propagate.  A
*transport-scoped* one — the Mammotion MQTT JWT is unrenewable while the HTTP login
is still healthy — must give up only that transport: the login, the cached
credentials and any Aliyun transport have to survive.

``TokenManager.get_mammotion_mqtt_credentials`` signals both with the same
``ReLoginRequiredError``, so the terminal flags are what separate them.  Letting the
transport-scoped one escape ``_ensure_mammotion_transport`` aborted the whole
login/restore: the session was never registered and ``_start_token_refresh`` never
ran, so nothing renewed the credentials that were still perfectly good.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.transport.base import ReLoginRequiredError
from tests._helpers import make_bare_client


def _session() -> AccountSession:
    return AccountSession(account_id="a@example.com", email="a@example.com", password="pw")


def _client_with_token_manager(token_manager: MagicMock):
    client = make_bare_client()
    client._ensure_token_manager = AsyncMock(return_value=token_manager)  # type: ignore[method-assign]
    client._setup_mammotion_transport = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(connect=AsyncMock())
    )
    return client


async def test_transport_scoped_failure_returns_none_instead_of_raising() -> None:
    """mqtt_unavailable set, reauth_required clear → give up this transport only."""
    tm = MagicMock()
    tm.get_mammotion_mqtt_credentials = AsyncMock(
        side_effect=ReLoginRequiredError("a@example.com", "JWT endpoint returned no data")
    )
    tm.reauth_required = None
    tm.mqtt_unavailable = "JWT endpoint returned no data"
    client = _client_with_token_manager(tm)
    session = _session()

    result = await client._ensure_mammotion_transport("a@example.com", MagicMock(), session)

    assert result is None
    assert session.mammotion_transport is None


async def test_account_scoped_failure_still_propagates() -> None:
    """A rejected HTTP refresh token kills every cloud path — it must not be swallowed."""
    tm = MagicMock()
    tm.get_mammotion_mqtt_credentials = AsyncMock(
        side_effect=ReLoginRequiredError("a@example.com", "refresh token rejected")
    )
    tm.reauth_required = "refresh token rejected"
    tm.mqtt_unavailable = None
    client = _client_with_token_manager(tm)

    with pytest.raises(ReLoginRequiredError):
        await client._ensure_mammotion_transport("a@example.com", MagicMock(), _session())


async def test_success_builds_and_caches_the_transport() -> None:
    tm = MagicMock()
    tm.get_mammotion_mqtt_credentials = AsyncMock(return_value=MagicMock())
    tm.reauth_required = None
    tm.mqtt_unavailable = None
    client = _client_with_token_manager(tm)
    session = _session()

    transport = await client._ensure_mammotion_transport("a@example.com", MagicMock(), session)

    assert transport is not None
    assert session.mammotion_transport is transport
    transport.connect.assert_awaited_once()


async def test_an_already_built_transport_is_reused() -> None:
    tm = MagicMock()
    tm.get_mammotion_mqtt_credentials = AsyncMock()
    client = _client_with_token_manager(tm)
    session = _session()
    existing = MagicMock()
    session.mammotion_transport = existing

    assert await client._ensure_mammotion_transport("a@example.com", MagicMock(), session) is existing
    tm.get_mammotion_mqtt_credentials.assert_not_awaited()


async def test_bootstrap_skips_post_2025_devices_without_propagating() -> None:
    """The consequence: a transport-scoped failure must not abort login/restore.

    ``_bootstrap_mammotion_mqtt`` returns quietly, so its callers go on to register
    the session and start the refresh scheduler.
    """
    client = make_bare_client()
    client._ensure_mammotion_transport = AsyncMock(return_value=None)  # type: ignore[method-assign]
    # AsyncMock so every HTTP call on the way to the transport is awaitable; the
    # records only have to be non-empty to reach _ensure_mammotion_transport.
    http = AsyncMock()

    await client._bootstrap_mammotion_mqtt("a@example.com", http, _session(), {})  # must not raise

    client._ensure_mammotion_transport.assert_awaited_once()
