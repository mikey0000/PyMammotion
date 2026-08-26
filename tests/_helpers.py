"""Shared helpers used across unit and integration tests.

Plain functions rather than fixtures, matching the tests/unit/transport/_fakes.py
and tests/unit/messaging/_helpers.py precedent: call sites stay terse and the
helpers stay greppable.
"""

from __future__ import annotations

from typing import Any

import jwt as pyjwt

from pymammotion.account.registry import AccountRegistry, AccountSession
from pymammotion.client import MammotionClient

#: Signing key for test JWTs.  The library decodes with verify_signature=False,
#: so the key is irrelevant — it just has to satisfy pyjwt's minimum length.
JWT_TEST_KEY = "x" * 32


def encode_jwt(claims: dict[str, Any] | None = None, **extra: Any) -> str:
    """Encode a test JWT with the given claims (dict and/or keywords)."""
    payload = dict(claims or {})
    payload.update(extra)
    return pyjwt.encode(payload, JWT_TEST_KEY, algorithm="HS256")


def make_bare_client(session: AccountSession | None = None) -> MammotionClient:
    """A MammotionClient with only the account registry initialised.

    For tests that exercise one client method in isolation: ``__new__`` skips
    the constructor's transports/registries/loops, and *session* (if given) is
    registered directly — ``AccountRegistry.register`` is async and its lock is
    never contended here.
    """
    client = MammotionClient.__new__(MammotionClient)
    client._account_registry = AccountRegistry()
    client._watcher_subscriptions = {}
    if session is not None:
        client._account_registry._sessions[session.account_id] = session
    return client
