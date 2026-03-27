"""AccountSession and AccountRegistry — replaces the Mammotion god-object."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymammotion.auth.token_manager import TokenManager
    from pymammotion.mqtt.pool import MQTTConnectionPool


@dataclass
class AccountSession:
    """All per-account state: credentials, MQTT pool, and BLE manager.

    One AccountSession per logged-in account. Multiple accounts are supported.
    The ``ble_manager`` attribute is intentionally omitted here to avoid circular
    import issues; callers may attach a BLETransportManager at runtime as needed.
    """

    account_id: str
    token_manager: TokenManager
    mqtt_pool: MQTTConnectionPool
    device_ids: set[str] = field(default_factory=set)


class AccountRegistry:
    """Maps account_id to AccountSession. Thread/coroutine-safe via asyncio.Lock."""

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._sessions: dict[str, AccountSession] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def register(self, session: AccountSession) -> None:
        """Add or replace a session in the registry.

        Args:
            session: The :class:`AccountSession` to register.

        """
        async with self._lock:
            self._sessions[session.account_id] = session

    async def unregister(self, account_id: str) -> None:
        """Remove a session from the registry by account ID.

        If *account_id* is not present, this is a no-op.

        Args:
            account_id: The account to remove.

        """
        async with self._lock:
            self._sessions.pop(account_id, None)

    def get(self, account_id: str) -> AccountSession | None:
        """Return the session for *account_id*, or ``None`` if not registered.

        This method does **not** acquire the lock because reads from a dict are
        thread-safe in CPython and the method is not async.  Callers that need
        strong consistency while modifying the registry should use
        ``async with registry._lock``.

        Args:
            account_id: The account identifier to look up.

        Returns:
            The matching :class:`AccountSession` or ``None``.

        """
        return self._sessions.get(account_id)

    @property
    def sessions(self) -> dict[str, AccountSession]:
        """Return a shallow copy of the current sessions mapping."""
        return dict(self._sessions)
