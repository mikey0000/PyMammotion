"""Regression test for C1: bare ``except:`` in ``MammotionClient._full_relogin``.

The original implementation wrapped the inner ``logout()`` call in a bare
``except:`` block which silently swallowed ``KeyboardInterrupt``,
``SystemExit`` and ``GeneratorExit`` — preventing graceful shutdown when the
user (or supervisor) attempted to terminate the process during a re-login.

This test patches ``logout()`` to raise ``KeyboardInterrupt`` and asserts the
signal propagates out of ``_full_relogin``.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.client import MammotionClient


async def test_full_relogin_propagates_keyboard_interrupt() -> None:
    """``KeyboardInterrupt`` raised inside ``logout()`` must propagate out of ``_full_relogin``."""
    client = MammotionClient()
    session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    mock_http = MagicMock()
    mock_http.logout = AsyncMock(side_effect=KeyboardInterrupt)
    # ``login_v2`` should never be reached, but stub it so an accidental call is observable.
    mock_http.login_v2 = AsyncMock(return_value=MagicMock(code=0))
    session.mammotion_http = mock_http

    with pytest.raises(KeyboardInterrupt):
        await client._full_relogin(session)

    # Ensure we did not silently fall through to the login attempt.
    mock_http.login_v2.assert_not_awaited()
