"""Shared aiomqtt fakes for the transport tests.

``AliyunMQTTTransport`` and ``MQTTTransport`` speak different protocols but drive
the same ``aiomqtt.Client`` surface, so their tests need the same handful of
stand-ins.  Those had been copy-pasted into both suites, which is worse than
duplication in production code: a fake that drifts silently weakens every test
built on it, and there is no type checker or failing test to notice.

They had already drifted — ``test_mammotion_mqtt``'s copy of
``FakeAsyncMessages`` was documented as yielding "one message" when it yields all
of them.

Plain classes rather than pytest fixtures, matching the
``tests/unit/messaging/_helpers.py`` precedent, so call sites stay terse and
tests can construct variants inline.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock


class FakeMessage:
    """Stand-in for an aiomqtt message — just a topic and a payload."""

    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


class FakeAsyncMessages:
    """Async iterator yielding the given messages, then blocking until cancelled.

    The block matters: a real ``client.messages`` never completes, so returning
    ``StopAsyncIteration`` after the seeded messages would let the transport's
    receive loop exit and mask bugs that only show up while it is still running.
    """

    def __init__(self, messages: list[FakeMessage]) -> None:
        self._messages = iter(messages)

    def __aiter__(self) -> FakeAsyncMessages:
        return self

    async def __anext__(self) -> FakeMessage:
        try:
            return next(self._messages)
        except StopIteration:
            await asyncio.sleep(3600)
            raise StopAsyncIteration from None


class FakeMQTTClient:
    """Minimal stand-in for ``aiomqtt.Client`` that connects cleanly."""

    def __init__(self, messages: list[FakeMessage] | None = None) -> None:
        self._messages_list: list[FakeMessage] = messages or []
        self.publish = AsyncMock()
        self.subscribe = AsyncMock()

    @property
    def messages(self) -> FakeAsyncMessages:
        return FakeAsyncMessages(self._messages_list)

    async def __aenter__(self) -> FakeMQTTClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class AuthFailMQTTClient:
    """Client whose ``__aenter__`` raises ``MqttCodeError`` — broker rejected auth.

    *rc* defaults to 5 ("Not Authorized", MQTT 3.1.1).  The transports also treat
    4 ("Bad User Name or Password") and their MQTT 5.0 equivalents 134/135 as auth
    failures, so pass those to cover the other branches.
    """

    def __init__(self, rc: int = 5) -> None:
        self._rc = rc

    async def __aenter__(self) -> AuthFailMQTTClient:
        import aiomqtt

        raise aiomqtt.MqttCodeError(self._rc)

    async def __aexit__(self, *args: object) -> None:
        pass


class NetworkErrorClient:
    """Client whose ``__aenter__`` raises a bare ``OSError``.

    Covers DNS failure (``socket.gaierror``) and ENETUNREACHABLE — conditions the
    transports must retry with backoff rather than treat as auth failures.
    """

    def __init__(self, exc: OSError) -> None:
        self._exc = exc

    async def __aenter__(self) -> NetworkErrorClient:
        raise self._exc

    async def __aexit__(self, *args: object) -> None:
        pass
