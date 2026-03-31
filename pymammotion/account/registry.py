"""AccountSession and AccountRegistry — per-account state management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
    from pymammotion.auth.token_manager import TokenManager
    from pymammotion.http.http import MammotionHTTP
    from pymammotion.transport.aliyun_mqtt import AliyunMQTTTransport
    from pymammotion.transport.mqtt import MQTTTransport

# Account ID used for BLE-only devices that have no cloud account.
BLE_ONLY_ACCOUNT = "__ble__"


@dataclass
class AccountSession:
    """All per-account state: credentials, transports, and device ownership.

    One AccountSession per logged-in account.  BLE-only devices get a shared
    session with ``account_id = BLE_ONLY_ACCOUNT`` and all cloud fields left
    as ``None``.
    """

    account_id: str
    email: str = ""
    password: str = ""
    user_account: int = 0
    token_manager: TokenManager | None = None
    mammotion_http: MammotionHTTP | None = None
    cloud_client: CloudIOTGateway | None = None
    aliyun_transport: AliyunMQTTTransport | None = None
    mammotion_transport: MQTTTransport | None = None
    device_ids: set[str] = field(default_factory=set)


class AccountRegistry:
    """Maps account_id to AccountSession. Thread/coroutine-safe via asyncio.Lock."""

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._sessions: dict[str, AccountSession] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def register(self, session: AccountSession) -> None:
        """Add or replace a session in the registry."""
        async with self._lock:
            self._sessions[session.account_id] = session

    async def unregister(self, account_id: str) -> None:
        """Remove a session from the registry by account ID (no-op if absent)."""
        async with self._lock:
            self._sessions.pop(account_id, None)

    def get(self, account_id: str) -> AccountSession | None:
        """Return the session for *account_id*, or ``None``."""
        return self._sessions.get(account_id)

    def find_by_device(self, device_name: str) -> AccountSession | None:
        """Return the session that owns *device_name*, or ``None``."""
        for session in self._sessions.values():
            if device_name in session.device_ids:
                return session
        return None

    @property
    def all_sessions(self) -> list[AccountSession]:
        """Return all registered sessions."""
        return list(self._sessions.values())

    @property
    def sessions(self) -> dict[str, AccountSession]:
        """Return a shallow copy of the current sessions mapping."""
        return dict(self._sessions)
