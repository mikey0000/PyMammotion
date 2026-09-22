"""MammotionClient.refresh_login routes by the transports the account actually has.

Regression: ``refresh_login`` used to refresh Aliyun unconditionally, so every
Mammotion-direct account got ``ReLoginRequiredError("No Aliyun cloud gateway
configured")`` from the host's generic recovery call.  It must refresh exactly
the chains the account is wired for, never a password login.

(The old first half of this file tested a hand-written copy of
``_on_aliyun_auth_failure`` with a ``_full_relogin`` escalation tier that was
deliberately removed from production — the real handler gives up
transport-scoped and never re-logins; see
tests/unit/transport/test_aliyun_mqtt.py for the real-code coverage.)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pymammotion.account.registry import AccountSession
from pymammotion.client import MammotionClient
from tests._helpers import make_bare_client
from pymammotion.transport.base import ReLoginRequiredError


def _relogin_session() -> tuple[MammotionClient, AccountSession, MagicMock, MagicMock]:
    """Build a client + AccountSession wired with spied http and token_manager."""

    http = MagicMock()
    http.login_v2 = AsyncMock(return_value=MagicMock(code=0))
    http.logout = AsyncMock()
    http.refresh_token_v2 = AsyncMock()

    tm = MagicMock()
    tm.refresh_aliyun_credentials = AsyncMock()
    tm.refresh_mqtt_credentials = AsyncMock()
    tm.connect_iot = AsyncMock()
    tm.refresh_http = AsyncMock()

    session = AccountSession(account_id="a@b.com", email="a@b.com", password="pw")
    session.mammotion_http = http
    session.token_manager = tm
    return make_bare_client(session), session, http, tm


async def test_refresh_login_routes_to_aliyun_only_for_aliyun_accounts() -> None:
    """An Aliyun-only account refreshes the IoT session and nothing else."""
    client, session, http, tm = _relogin_session()
    session.cloud_client = MagicMock()  # has Aliyun
    session.mammotion_transport = None  # no Mammotion MQTT

    await client.refresh_login("a@b.com")

    tm.refresh_aliyun_credentials.assert_awaited_once()
    tm.refresh_mqtt_credentials.assert_not_awaited()
    http.login_v2.assert_not_awaited()


async def test_refresh_login_routes_to_mqtt_only_for_mammotion_accounts() -> None:
    """A post-2025 account must NOT be sent down the Aliyun path."""
    client, session, http, tm = _relogin_session()
    session.cloud_client = None  # no Aliyun
    session.mammotion_transport = MagicMock()  # has Mammotion MQTT

    await client.refresh_login("a@b.com")

    tm.refresh_mqtt_credentials.assert_awaited_once()
    tm.refresh_aliyun_credentials.assert_not_awaited()
    http.login_v2.assert_not_awaited()


async def test_refresh_login_refreshes_both_for_hybrid_accounts() -> None:
    """A hybrid account refreshes both chains, still without any password login."""
    client, session, http, tm = _relogin_session()
    session.cloud_client = MagicMock()
    session.mammotion_transport = MagicMock()

    await client.refresh_login("a@b.com")

    tm.refresh_aliyun_credentials.assert_awaited_once()
    tm.refresh_mqtt_credentials.assert_awaited_once()
    http.login_v2.assert_not_awaited()


async def test_refresh_login_one_transport_failing_does_not_skip_the_other() -> None:
    """A hybrid account whose Aliyun chain is dead must still refresh Mammotion MQTT."""
    client, session, http, tm = _relogin_session()
    session.cloud_client = MagicMock()
    session.mammotion_transport = MagicMock()
    tm.refresh_aliyun_credentials = AsyncMock(side_effect=ReLoginRequiredError("a@b.com", "aliyun dead"))

    await client.refresh_login("a@b.com")  # must not raise — one chain succeeded

    tm.refresh_mqtt_credentials.assert_awaited_once()


async def test_refresh_login_unknown_account_is_a_noop_not_default_session(caplog) -> None:
    """A named-but-unregistered account must not fall back to refreshing another account."""
    client, session, http, tm = _relogin_session()
    session.cloud_client = MagicMock()

    await client.refresh_login("nobody@example.com")

    tm.refresh_aliyun_credentials.assert_not_awaited()
    tm.refresh_mqtt_credentials.assert_not_awaited()
    assert "not registered" in caplog.text


async def test_refresh_transport_credentials_unknown_account_is_a_noop() -> None:
    """Same guard on the transport-scoped entry point."""
    from pymammotion.transport.base import TransportType

    client, session, http, tm = _relogin_session()
    session.mammotion_transport = MagicMock()

    await client.refresh_transport_credentials(TransportType.CLOUD_MAMMOTION, account="nobody@example.com")

    tm.refresh_mqtt_credentials.assert_not_awaited()
    tm.refresh_aliyun_credentials.assert_not_awaited()
