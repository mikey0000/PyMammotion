"""Tests for AccountRegistry and AccountSession."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from pymammotion.account.registry import AccountRegistry, AccountSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(account_id: str = "user@example.com") -> AccountSession:
    token_manager = MagicMock()
    return AccountSession(
        account_id=account_id,
        token_manager=token_manager,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_and_get() -> None:
    """register() stores a session; get() retrieves it by account_id."""
    registry = AccountRegistry()
    session = _make_session("alice@example.com")

    await registry.register(session)

    result = registry.get("alice@example.com")
    assert result is session


@pytest.mark.asyncio
async def test_unregister_removes_session() -> None:
    """unregister() removes the session; get() returns None afterwards."""
    registry = AccountRegistry()
    session = _make_session("bob@example.com")

    await registry.register(session)
    assert registry.get("bob@example.com") is session

    await registry.unregister("bob@example.com")
    assert registry.get("bob@example.com") is None


@pytest.mark.asyncio
async def test_concurrent_register_safe() -> None:
    """Two concurrent register() calls both store their sessions safely."""
    registry = AccountRegistry()

    session_a = _make_session("a@example.com")
    session_b = _make_session("b@example.com")

    await asyncio.gather(
        registry.register(session_a),
        registry.register(session_b),
    )

    assert registry.get("a@example.com") is session_a
    assert registry.get("b@example.com") is session_b
    assert len(registry.sessions) == 2
