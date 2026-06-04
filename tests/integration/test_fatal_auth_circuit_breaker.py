"""Tests for auth give-up + account-wide re-login behaviour.

Mammotion direct-MQTT (``CLOUD_MAMMOTION``) never re-logins: the transport
refreshes credentials in full once and, if the broker still rejects, gives up.
"Give up" marks that account's Mammotion transport unrecoverable (gating exactly
its mowers via ``active_transport``/``is_usable``) and signals them — fires each
affected device's error bus and the enriched ``on_unrecoverable_auth_error``
callback ``(account_id, transport_type, exc)`` — so the host can prompt re-auth
for just those mowers.

Also covers the account-wide re-login (Aliyun / send-retry path): a full
``login_v2`` tears down all of the account's in-use MQTT connections and restarts
them with fresh credentials.
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
    tm.force_refresh = AsyncMock()
    _creds = MQTTCredentials(
        host="tcp://mqtt.example:1883", client_id="cid", username="u", jwt="fresh-jwt", expires_at=0.0
    )
    tm.refresh_mqtt_credentials_strict = AsyncMock(return_value=_creds)
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
    """On Mammotion fatal auth the handler must NOT re-login: it marks the transport
    unrecoverable and fires the enriched callback. No login_v2 / _full_relogin.
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

        trigger = ReLoginRequiredError("acc", "broker still rejecting after full refresh")
        await handler(trigger)

        mock_relogin.assert_not_awaited()
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
# Account-wide re-login: tear down + restart in-use MQTT transports
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_relogin_refreshes_all_credentials() -> None:
    """A full re-login rotates every token the account holds — force_refresh(None)."""
    client = MammotionClient()
    session = _make_session()

    await client._full_relogin(session)

    session.mammotion_http.login_v2.assert_awaited_once()
    session.token_manager.force_refresh.assert_awaited_once_with(transport_type=None)


@pytest.mark.asyncio
async def test_full_relogin_cycles_other_in_use_mqtt_transports() -> None:
    """Re-login tears down the account's in-use MQTT transports (except the triggering
    one) before login_v2 and restarts them with fresh creds afterward.
    """
    client = MammotionClient()
    session = _make_session()

    mammotion = MagicMock(spec=MQTTTransport)
    mammotion.is_connected = True
    mammotion.is_unrecoverable_auth_failure = False
    mammotion.disconnect = AsyncMock()
    mammotion.connect = AsyncMock()
    mammotion.update_credentials = MagicMock()
    mammotion.clear_auth_failed = MagicMock()
    session.mammotion_transport = mammotion

    # Triggering transport (CLOUD_ALIYUN) is excluded from teardown.
    await client._full_relogin(session, transport_type=TransportType.CLOUD_ALIYUN)

    mammotion.disconnect.assert_awaited_once()
    session.mammotion_http.login_v2.assert_awaited_once()
    mammotion.update_credentials.assert_called_once()
    mammotion.connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_full_relogin_excludes_triggering_transport_from_teardown() -> None:
    """The triggering transport must not be torn down (it self-recovers via its caller)."""
    client = MammotionClient()
    session = _make_session()

    mammotion = MagicMock(spec=MQTTTransport)
    mammotion.is_connected = True
    mammotion.is_unrecoverable_auth_failure = False
    mammotion.disconnect = AsyncMock()
    mammotion.connect = AsyncMock()
    session.mammotion_transport = mammotion

    await client._full_relogin(session, transport_type=TransportType.CLOUD_MAMMOTION)

    mammotion.disconnect.assert_not_awaited()
    mammotion.connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_full_relogin_skips_given_up_transports() -> None:
    """A transport already marked unrecoverable is not 'in use' — don't revive it."""
    client = MammotionClient()
    session = _make_session()

    mammotion = MagicMock(spec=MQTTTransport)
    mammotion.is_connected = True
    mammotion.is_unrecoverable_auth_failure = True  # already gave up
    mammotion.disconnect = AsyncMock()
    mammotion.connect = AsyncMock()
    session.mammotion_transport = mammotion

    await client._full_relogin(session)

    mammotion.disconnect.assert_not_awaited()
    mammotion.connect.assert_not_awaited()
