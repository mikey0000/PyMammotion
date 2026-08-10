"""Tests for auth give-up behaviour — no transport ever re-logins.

A cloud transport refreshes its credentials once and, if the broker still
rejects, gives up.  "Give up" marks that account's transport unrecoverable
(gating exactly its mowers via ``active_transport``/``is_usable``) and fires each
affected device's error bus, so the host can mark just those mowers unavailable.

The global ``on_unrecoverable_auth_error`` callback — which hosts map to "prompt
the user to re-authenticate" — fires only when the account's HTTP login is itself
dead.  A transport-scoped failure must leave the login, the cached credentials,
and the account's other transport intact.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.auth.token_manager import MQTTCredentials
from pymammotion.client import MammotionClient
from pymammotion.http.model.http import MQTTConnection
from pymammotion.transport.base import ReLoginRequiredError, TransportType
from pymammotion.transport.mqtt import MQTTTransport


def _make_session() -> AccountSession:
    """Build an AccountSession with the minimum mocks for `_setup_mammotion_transport`."""
    session = AccountSession(account_id="acc", email="user@test.com", password="pw")
    session.mammotion_http = MagicMock()
    session.mammotion_http.logout = AsyncMock()
    session.mammotion_http.login_v2 = AsyncMock(return_value=MagicMock(code=0))
    tm = MagicMock()
    tm.account_id = "acc"
    tm.reauth_required = None  # the account's HTTP login is healthy unless a test says otherwise
    tm.refresh_aliyun_credentials = AsyncMock()  # Aliyun targeted refresh
    tm.connect_iot = AsyncMock()  # Aliyun-triggered re-login re-establishes via the full IoT flow
    _creds = MQTTCredentials(
        host="tcp://mqtt.example:1883", client_id="cid", username="u", jwt="fresh-jwt", expires_at=0.0
    )
    tm.refresh_mqtt_credentials = AsyncMock(return_value=_creds)
    tm.get_mammotion_mqtt_credentials = AsyncMock(return_value=_creds)
    session.token_manager = tm
    return session


def _make_mqtt_creds() -> MQTTConnection:
    return MQTTConnection(host="tcp://mqtt.example:1883", jwt="initial-jwt", client_id="cid", username="u")


def _make_device(*, has_transport: TransportType | None) -> MagicMock:
    """A mock DeviceHandle that reports a transport for *has_transport* only."""
    handle = MagicMock()
    handle.notify_critical_error = AsyncMock()
    handle.get_transport = MagicMock(side_effect=lambda tt: MagicMock() if tt == has_transport else None)
    return handle


# ---------------------------------------------------------------------------
# Mammotion MQTT: give up (no re-login)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mammotion_fatal_auth_gives_up_without_relogin() -> None:
    """On fatal auth the handler must NOT re-login: it marks the transport
    unrecoverable and fires the enriched callback.  No login_v2, no logout.
    """
    client = MammotionClient()
    client.on_unrecoverable_auth_error = AsyncMock()
    session = _make_session()

    session.token_manager.reauth_required = "refresh token rejected"  # account login is dead too
    transport = client._setup_mammotion_transport(
        _make_mqtt_creds(), session.mammotion_http, session, session.token_manager
    )
    handler = transport.on_fatal_auth_error
    assert handler is not None

    trigger = ReLoginRequiredError("acc", "broker still rejecting after full refresh")
    await handler(trigger)

    session.mammotion_http.login_v2.assert_not_awaited()
    session.mammotion_http.logout.assert_not_awaited()
    assert transport.is_unrecoverable_auth_failure
    assert not transport.is_usable
    client.on_unrecoverable_auth_error.assert_awaited_once_with("acc", TransportType.CLOUD_MAMMOTION, trigger)


@pytest.mark.asyncio
async def test_give_up_marks_transport_so_connect_refuses() -> None:
    """After giving up, connect() must refuse to spawn a new _run task."""
    client = MammotionClient()
    session = _make_session()

    transport = client._setup_mammotion_transport(
        _make_mqtt_creds(), session.mammotion_http, session, session.token_manager
    )
    handler = transport.on_fatal_auth_error
    assert handler is not None
    assert not transport.is_unrecoverable_auth_failure

    await handler(ReLoginRequiredError("acc", "rejected"))

    assert transport.is_unrecoverable_auth_failure
    assert not transport.is_usable
    await transport.connect()
    assert transport._task is None or transport._task.done()


@pytest.mark.asyncio
async def test_give_up_signals_only_mowers_on_that_transport() -> None:
    """The per-device error bus must fire only for the account's mowers that use the
    failed transport — not other devices, not other accounts.
    """
    client = MammotionClient()
    client.on_unrecoverable_auth_error = AsyncMock()
    session = _make_session()
    session.token_manager.reauth_required = "refresh token rejected"  # account login is dead too
    session.device_ids = {"on_mammotion", "ble_only"}

    on_mammotion = _make_device(has_transport=TransportType.CLOUD_MAMMOTION)
    ble_only = _make_device(has_transport=TransportType.BLE)
    client._device_registry.get = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda did: {"on_mammotion": on_mammotion, "ble_only": ble_only}.get(did)
    )

    transport = client._setup_mammotion_transport(
        _make_mqtt_creds(), session.mammotion_http, session, session.token_manager
    )
    trigger = ReLoginRequiredError("acc", "rejected")
    await transport.on_fatal_auth_error(trigger)

    on_mammotion.notify_critical_error.assert_awaited_once_with(trigger)
    ble_only.notify_critical_error.assert_not_awaited()
    client.on_unrecoverable_auth_error.assert_awaited_once_with("acc", TransportType.CLOUD_MAMMOTION, trigger)


# ---------------------------------------------------------------------------
# A dead transport must not cost the account its login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transport_give_up_does_not_prompt_reauth_when_login_healthy() -> None:
    """The regression this whole design exists for.

    One cloud transport dying used to tear down the entire config entry — the
    host's ``on_unrecoverable_auth_error`` handler signs the user out and asks
    them to reconfigure.  While the HTTP login and refresh token are still valid
    that is pure collateral damage: the account's *other* transport and every
    HTTP-backed feature were working fine.
    """
    client = MammotionClient()
    client.on_unrecoverable_auth_error = AsyncMock()
    session = _make_session()
    session.token_manager.reauth_required = None  # login still valid

    transport = client._setup_mammotion_transport(
        _make_mqtt_creds(), session.mammotion_http, session, session.token_manager
    )
    await transport.on_fatal_auth_error(ReLoginRequiredError("acc", "broker rejected"))

    # The transport is given up...
    assert transport.is_unrecoverable_auth_failure
    # ...but the account keeps its session and the user is not asked to reconfigure.
    client.on_unrecoverable_auth_error.assert_not_awaited()
    session.mammotion_http.logout.assert_not_awaited()
    session.mammotion_http.login_v2.assert_not_awaited()


@pytest.mark.asyncio
async def test_transport_give_up_still_signals_affected_devices() -> None:
    """Scoped, not silent: the transport's own mowers are still marked unavailable."""
    client = MammotionClient()
    client.on_unrecoverable_auth_error = AsyncMock()
    session = _make_session()
    session.token_manager.reauth_required = None
    session.device_ids = {"on_mammotion"}
    on_mammotion = _make_device(has_transport=TransportType.CLOUD_MAMMOTION)
    client._device_registry.get = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda did: {"on_mammotion": on_mammotion}.get(did)
    )

    transport = client._setup_mammotion_transport(
        _make_mqtt_creds(), session.mammotion_http, session, session.token_manager
    )
    trigger = ReLoginRequiredError("acc", "broker rejected")
    await transport.on_fatal_auth_error(trigger)

    on_mammotion.notify_critical_error.assert_awaited_once_with(trigger)
    client.on_unrecoverable_auth_error.assert_not_awaited()
