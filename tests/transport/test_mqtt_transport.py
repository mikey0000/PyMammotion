"""Tests for MQTTTransport."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.transport.base import TransportError, TransportType
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
def mammotion_http() -> MagicMock:
    http = MagicMock()
    http.mqtt_invoke = AsyncMock(return_value=MagicMock(code=0))
    return http


@pytest.fixture
def transport(config: MQTTTransportConfig, mammotion_http: MagicMock) -> MQTTTransport:
    return MQTTTransport(config, mammotion_http)


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
async def test_connect_sets_is_connected(config: MQTTTransportConfig, mammotion_http: MagicMock) -> None:
    """connect() should set is_connected to True once the MQTT loop starts."""
    transport = MQTTTransport(config, mammotion_http)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)
        assert transport.is_connected is True
        await transport.disconnect()


@pytest.mark.asyncio
async def test_disconnect_sets_is_connected_false(config: MQTTTransportConfig, mammotion_http: MagicMock) -> None:
    """disconnect() should set is_connected to False."""
    transport = MQTTTransport(config, mammotion_http)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)
        await transport.disconnect()
        assert transport.is_connected is False


# ---------------------------------------------------------------------------
# send() calls the HTTP invoke API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_calls_mqtt_invoke(config: MQTTTransportConfig) -> None:
    """send() should forward the payload via mammotion_http.mqtt_invoke."""
    import base64

    http = MagicMock()
    http.mqtt_invoke = AsyncMock(return_value=MagicMock(code=0))
    transport = MQTTTransport(config, http)

    payload = b"\x01\x02\x03"
    await transport.send(payload, iot_id="dev123")

    http.mqtt_invoke.assert_awaited_once()
    call_args = http.mqtt_invoke.call_args
    # First arg is base64-encoded payload
    assert call_args.args[0] == base64.b64encode(payload).decode()
    # Third arg is the iot_id
    assert call_args.args[2] == "dev123"


@pytest.mark.asyncio
async def test_send_raises_when_no_iot_id(config: MQTTTransportConfig, mammotion_http: MagicMock) -> None:
    """send() with an empty iot_id should raise TransportError."""
    transport = MQTTTransport(config, mammotion_http)
    with pytest.raises(TransportError, match="iot_id"):
        await transport.send(b"hello")


# ---------------------------------------------------------------------------
# on_message callback is invoked for non-status messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_message_callback_called(config: MQTTTransportConfig, mammotion_http: MagicMock) -> None:
    """on_message should be called with the raw bytes of an incoming non-status message."""
    received: list[bytes] = []

    async def _handler(data: bytes) -> None:
        received.append(data)

    transport = MQTTTransport(config, mammotion_http)
    transport.on_message = _handler

    incoming = [_FakeMessage("some/topic", b"hello")]
    fake_client = _FakeMQTTClient(messages=incoming)

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.1)
        assert received == [b"hello"]
        await transport.disconnect()
