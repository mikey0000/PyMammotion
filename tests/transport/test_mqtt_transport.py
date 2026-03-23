"""Tests for MQTTTransport."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.transport.base import TransportType
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig


@pytest.fixture
def config() -> MQTTTransportConfig:
    return MQTTTransportConfig(
        host="mqtt.example.com",
        port=1883,
        client_id="test-client",
        username="user",
        password="jwt-token",
    )


@pytest.fixture
def transport(config: MQTTTransportConfig) -> MQTTTransport:
    return MQTTTransport(config)


# ---------------------------------------------------------------------------
# transport_type
# ---------------------------------------------------------------------------


def test_transport_type(transport: MQTTTransport) -> None:
    assert transport.transport_type is TransportType.CLOUD_MAMMOTION


# ---------------------------------------------------------------------------
# is_connected initial state
# ---------------------------------------------------------------------------


def test_is_connected_initially_false(transport: MQTTTransport) -> None:
    assert transport.is_connected is False


# ---------------------------------------------------------------------------
# connect() / disconnect() — mock the aiomqtt.Client context manager
# ---------------------------------------------------------------------------


class _FakeMessage:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


class _FakeAsyncMessages:
    """Async iterator that yields one message then blocks until cancelled."""

    def __init__(self, messages: list[_FakeMessage]) -> None:
        self._messages = iter(messages)

    def __aiter__(self) -> "_FakeAsyncMessages":
        return self

    async def __anext__(self) -> _FakeMessage:
        try:
            return next(self._messages)
        except StopIteration:
            # Block forever so the loop task stays alive during the test
            await asyncio.sleep(3600)
            raise StopAsyncIteration


class _FakeMQTTClient:
    """Minimal stand-in for aiomqtt.Client."""

    def __init__(self, messages: list[_FakeMessage] | None = None) -> None:
        self._messages_list: list[_FakeMessage] = messages or []
        self.publish = AsyncMock()
        self.subscribe = AsyncMock()

    @property
    def messages(self) -> _FakeAsyncMessages:
        return _FakeAsyncMessages(self._messages_list)

    async def __aenter__(self) -> "_FakeMQTTClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


@pytest.mark.asyncio
async def test_connect_sets_is_connected(config: MQTTTransportConfig) -> None:
    """connect() should set is_connected to True once the MQTT loop starts."""
    transport = MQTTTransport(config)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        # Give the loop task a moment to enter the async-with block
        await asyncio.sleep(0.05)
        assert transport.is_connected is True
        await transport.disconnect()


@pytest.mark.asyncio
async def test_disconnect_sets_is_connected_false(config: MQTTTransportConfig) -> None:
    """disconnect() should set is_connected to False."""
    transport = MQTTTransport(config)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)
        await transport.disconnect()
        assert transport.is_connected is False


# ---------------------------------------------------------------------------
# send() calls client.publish
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_calls_publish(config: MQTTTransportConfig) -> None:
    """send() should call client.publish with the correct topic and payload."""
    transport = MQTTTransport(config)
    topic = "/sys/pk/dn/thing/event/+/post"
    transport.add_topic(topic)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)

        payload = b"\x01\x02\x03"
        await transport.send(payload)

        fake_client.publish.assert_awaited_once_with(topic, payload)
        await transport.disconnect()


# ---------------------------------------------------------------------------
# on_message callback is invoked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_message_callback_called(config: MQTTTransportConfig) -> None:
    """on_message should be called with the raw bytes of an incoming message."""
    received: list[bytes] = []

    async def _handler(data: bytes) -> None:
        received.append(data)

    transport = MQTTTransport(config)
    transport.on_message = _handler

    incoming = [_FakeMessage("some/topic", b"hello")]
    fake_client = _FakeMQTTClient(messages=incoming)

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        # Allow the loop task to process the message and then block
        await asyncio.sleep(0.1)

        assert received == [b"hello"]
        await transport.disconnect()
