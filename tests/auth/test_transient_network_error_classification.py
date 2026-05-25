"""Tests for the transient-network-error classifier and propagation.

Regression for the 2026-05-25 production incident: a DNS resolution failure
(``[Errno -3] Temporary failure in name resolution`` wrapped as
``aiohttp.ClientConnectorDNSError``) was being wrapped by
``token_manager.refresh_http``'s generic ``except Exception`` as a
``ReLoginRequiredError``.  The MQTT transport's fatal-auth handler then
kicked off a destructive full re-login, which itself failed with the same
DNS error.  Network outages must be treated as transient (back off + retry),
not as credential failures.
"""
from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.auth.token_manager import TokenManager
from pymammotion.transport.base import (
    AuthError,
    ReLoginRequiredError,
    is_transient_network_error,
)


# ---------------------------------------------------------------------------
# Classifier — the single source of truth
# ---------------------------------------------------------------------------


def test_classifier_recognises_dns_failure() -> None:
    """socket.gaierror (the underlying DNS failure) must be transient."""
    exc = socket.gaierror(-3, "Temporary failure in name resolution")
    assert is_transient_network_error(exc) is True


def test_classifier_recognises_connection_error() -> None:
    """Standard library ConnectionError must be transient."""
    assert is_transient_network_error(ConnectionError("Connection refused")) is True
    assert is_transient_network_error(ConnectionResetError("reset")) is True
    assert is_transient_network_error(ConnectionRefusedError("refused")) is True


def test_classifier_recognises_timeout() -> None:
    """asyncio / built-in TimeoutError must be transient."""
    assert is_transient_network_error(TimeoutError("read timeout")) is True
    assert is_transient_network_error(asyncio.TimeoutError()) is True


def test_classifier_recognises_oserror() -> None:
    """Bare OSError (e.g. EHOSTUNREACH) must be transient."""
    assert is_transient_network_error(OSError(101, "Network is unreachable")) is True


def test_classifier_recognises_aiohttp_dns_error_by_name() -> None:
    """aiohttp.ClientConnectorDNSError isn't imported here to avoid a hard dep —
    classification must work by class-name match so unit tests don't need aiohttp."""

    class ClientConnectorDNSError(Exception):
        pass

    assert is_transient_network_error(ClientConnectorDNSError("dns fail")) is True


def test_classifier_recognises_aiohttp_client_connector_error_by_name() -> None:
    class ClientConnectorError(Exception):
        pass

    assert is_transient_network_error(ClientConnectorError("connector fail")) is True


def test_classifier_walks_cause_chain() -> None:
    """aiohttp typically wraps OSError; the classifier must follow __cause__."""
    cause = socket.gaierror(-3, "dns")
    wrapper = RuntimeError("outer")
    wrapper.__cause__ = cause
    assert is_transient_network_error(wrapper) is True


def test_classifier_rejects_unrelated_exceptions() -> None:
    """Auth-class and unrelated exceptions must NOT be classified as transient."""
    assert is_transient_network_error(ValueError("bad data")) is False
    assert is_transient_network_error(KeyError("missing")) is False
    assert is_transient_network_error(ReLoginRequiredError("acc", "expired token")) is False
    assert is_transient_network_error(AuthError("forbidden")) is False


# ---------------------------------------------------------------------------
# token_manager.refresh_http — DNS failure must propagate, not become
# ReLoginRequiredError
# ---------------------------------------------------------------------------


@pytest.fixture
def token_manager() -> TokenManager:
    """Minimal TokenManager — only the HTTP client is exercised here."""
    http = MagicMock()
    http.refresh_login = AsyncMock()
    tm = TokenManager(account_id="user@test", mammotion_http=http)
    return tm


def test_refresh_http_propagates_dns_failure(token_manager: TokenManager) -> None:
    """A DNS failure raised by the underlying HTTP refresh must surface as
    the original exception type — NOT wrapped as ReLoginRequiredError.

    This is the exact bug from the 2026-05-25 incident: gaierror got wrapped,
    triggering a destructive full re-login on every network blip.
    """
    dns_err = socket.gaierror(-3, "Temporary failure in name resolution")
    token_manager._http.refresh_login.side_effect = dns_err

    with pytest.raises(socket.gaierror):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_http())


def test_refresh_http_propagates_aiohttp_connector_error(token_manager: TokenManager) -> None:
    """aiohttp.ClientConnectorDNSError isn't wrapped as ReLoginRequiredError."""

    class ClientConnectorDNSError(Exception):
        pass

    network_err = ClientConnectorDNSError("Cannot connect to host id.mammotion.com:443")
    token_manager._http.refresh_login.side_effect = network_err

    with pytest.raises(ClientConnectorDNSError):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_http())


def test_refresh_http_wraps_genuine_auth_error(token_manager: TokenManager) -> None:
    """A non-network exception (e.g. ValueError from bad response parsing)
    is still wrapped as ReLoginRequiredError — the classifier must only
    short-circuit for transient network errors."""
    token_manager._http.refresh_login.side_effect = ValueError("malformed response")

    with pytest.raises(ReLoginRequiredError):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_http())


def test_refresh_http_wraps_response_with_no_data(token_manager: TokenManager) -> None:
    """The explicit 'refresh_login returned no data' path still raises ReLoginRequiredError."""
    response = MagicMock()
    response.data = None
    token_manager._http.refresh_login.return_value = response

    with pytest.raises(ReLoginRequiredError):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_http())


# ---------------------------------------------------------------------------
# refresh_invoke_token — same classification rule applies
# ---------------------------------------------------------------------------


def test_refresh_invoke_token_propagates_dns_failure(token_manager: TokenManager) -> None:
    """refresh_invoke_token's generic-Exception path must let network errors through."""
    token_manager._http.refresh_authorization_token = AsyncMock(
        side_effect=socket.gaierror(-3, "dns")
    )

    with pytest.raises(socket.gaierror):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_invoke_token())


def test_refresh_invoke_token_wraps_non_network_error(token_manager: TokenManager) -> None:
    """Non-network exceptions still become AuthError."""
    token_manager._http.refresh_authorization_token = AsyncMock(side_effect=ValueError("bad"))

    with pytest.raises(AuthError):
        asyncio.new_event_loop().run_until_complete(token_manager.refresh_invoke_token())
