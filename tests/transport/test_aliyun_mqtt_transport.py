"""Tests for AliyunMQTTTransport."""
from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import AsyncMock, patch

import pytest

from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport
from pymammotion.transport.base import AuthError, TransportError, TransportType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> AliyunMQTTConfig:
    return AliyunMQTTConfig(
        host="pk.iot-as-mqtt.cn-shanghai.aliyuncs.com",
        client_id_base="pk&dn",
        username="dn&pk",
        device_name="dn",
        product_key="pk",
        device_secret="secret",
        iot_token="tok",
    )


@pytest.fixture
def transport(config: AliyunMQTTConfig) -> AliyunMQTTTransport:
    return AliyunMQTTTransport(config)


# ---------------------------------------------------------------------------
# Minimal fake aiomqtt helpers
# ---------------------------------------------------------------------------


class _FakeMessage:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


class _FakeAsyncMessages:
    """Async iterator that yields given messages then blocks until cancelled."""

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


class _AuthFailMQTTClient:
    """Client whose __aenter__ raises MqttCodeError with rc=5."""

    async def __aenter__(self) -> "_AuthFailMQTTClient":
        import aiomqtt

        raise aiomqtt.MqttCodeError(5)

    async def __aexit__(self, *args: object) -> None:
        pass


# ---------------------------------------------------------------------------
# transport_type
# ---------------------------------------------------------------------------


def test_transport_type(transport: AliyunMQTTTransport) -> None:
    assert transport.transport_type is TransportType.CLOUD_ALIYUN


# ---------------------------------------------------------------------------
# is_connected initial state
# ---------------------------------------------------------------------------


def test_is_connected_initially_false(transport: AliyunMQTTTransport) -> None:
    assert transport.is_connected is False


# ---------------------------------------------------------------------------
# Connect / disconnect lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_sets_is_connected(config: AliyunMQTTConfig) -> None:
    """connect() should set is_connected to True once the MQTT loop is running."""
    transport = AliyunMQTTTransport(config)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)
        assert transport.is_connected is True
        await transport.disconnect()


@pytest.mark.asyncio
async def test_disconnect_sets_is_connected_false(config: AliyunMQTTConfig) -> None:
    """disconnect() should leave is_connected as False."""
    transport = AliyunMQTTTransport(config)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)
        await transport.disconnect()
        assert transport.is_connected is False


@pytest.mark.asyncio
async def test_connect_idempotent(config: AliyunMQTTConfig) -> None:
    """Calling connect() twice should not create a second task."""
    transport = AliyunMQTTTransport(config)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)
        first_task = transport._task
        await transport.connect()  # should be ignored
        assert transport._task is first_task
        await transport.disconnect()


# ---------------------------------------------------------------------------
# Topic management
# ---------------------------------------------------------------------------


def test_add_subscribe_topic(transport: AliyunMQTTTransport) -> None:
    transport.add_subscribe_topic("/sys/pk/dn/app/down/thing/events")
    assert "/sys/pk/dn/app/down/thing/events" in transport._subscribe_topics


def test_add_subscribe_topic_no_duplicates(transport: AliyunMQTTTransport) -> None:
    topic = "/sys/pk/dn/app/down/thing/events"
    transport.add_subscribe_topic(topic)
    transport.add_subscribe_topic(topic)
    assert transport._subscribe_topics.count(topic) == 1


def test_set_publish_topic(transport: AliyunMQTTTransport) -> None:
    transport.set_publish_topic("/sys/pk/dn/app/up/thing/thing/event/post")
    assert transport._publish_topic == "/sys/pk/dn/app/up/thing/thing/event/post"


# ---------------------------------------------------------------------------
# send() enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_raises_when_not_connected(transport: AliyunMQTTTransport) -> None:
    with pytest.raises(TransportError, match="not connected"):
        await transport.send(b"hello")


@pytest.mark.asyncio
async def test_send_raises_when_no_publish_topic(config: AliyunMQTTConfig) -> None:
    """send() should raise TransportError when no publish topic is set."""
    transport = AliyunMQTTTransport(config)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)
        with pytest.raises(TransportError, match="No publish topic"):
            await transport.send(b"hello")
        await transport.disconnect()


@pytest.mark.asyncio
async def test_send_calls_publish_on_correct_topic(config: AliyunMQTTConfig) -> None:
    """send() should call client.publish only on the configured publish topic."""
    transport = AliyunMQTTTransport(config)
    pub_topic = "/sys/pk/dn/app/up/thing/event/post"
    transport.set_publish_topic(pub_topic)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)

        payload = b"\x01\x02\x03"
        await transport.send(payload)

        # publish should have been called at least once for the bind message,
        # then once for our payload on pub_topic
        calls = [call for call in fake_client.publish.await_args_list if call.args[0] == pub_topic]
        assert len(calls) == 1
        assert calls[0].args[1] == payload

        await transport.disconnect()


# ---------------------------------------------------------------------------
# Envelope unwrapping: params.value.content (Aliyun thing.events shape)
# ---------------------------------------------------------------------------


def _make_thing_events_envelope(proto_bytes: bytes) -> bytes:
    """Build a JSON envelope matching the Aliyun thing.events shape."""
    content = base64.b64encode(proto_bytes).decode()
    envelope = {
        "method": "thing.events",
        "id": "1",
        "version": "1.0",
        "params": {
            "identifier": "device_protobuf_msg_event",
            "iotId": "device123",
            "value": {"content": content},
        },
    }
    return json.dumps(envelope).encode()


@pytest.mark.asyncio
async def test_on_message_called_with_unwrapped_bytes(config: AliyunMQTTConfig) -> None:
    """on_message should receive the decoded protobuf bytes, not the JSON envelope."""
    received: list[bytes] = []

    async def _handler(data: bytes) -> None:
        received.append(data)

    transport = AliyunMQTTTransport(config)
    transport.on_message = _handler

    proto_bytes = b"\x08\x01\x12\x03foo"
    envelope = _make_thing_events_envelope(proto_bytes)
    fake_client = _FakeMQTTClient(messages=[_FakeMessage("/sys/pk/dn/app/down/thing/events", envelope)])

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.1)
        assert received == [proto_bytes]
        await transport.disconnect()


# ---------------------------------------------------------------------------
# Envelope unwrapping: params.content (Mammotion direct-MQTT shape)
# ---------------------------------------------------------------------------


def _make_mammotion_direct_envelope(proto_bytes: bytes) -> bytes:
    """Build a JSON envelope matching the Mammotion direct-MQTT shape."""
    content = base64.b64encode(proto_bytes).decode()
    envelope = {
        "id": "2",
        "version": "1.0",
        "params": {"content": content},
        "method": "thing.event.device_protobuf_msg_event.post",
    }
    return json.dumps(envelope).encode()


@pytest.mark.asyncio
async def test_on_message_called_mammotion_direct_shape(config: AliyunMQTTConfig) -> None:
    """on_message should also unwrap the Mammotion direct-MQTT params.content shape."""
    received: list[bytes] = []

    async def _handler(data: bytes) -> None:
        received.append(data)

    transport = AliyunMQTTTransport(config)
    transport.on_message = _handler

    proto_bytes = b"\xff\xfe\xfd"
    envelope = _make_mammotion_direct_envelope(proto_bytes)
    fake_client = _FakeMQTTClient(
        messages=[_FakeMessage("/sys/proto/pk/dn/thing/event/device_protobuf_msg_event/post", envelope)]
    )

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.1)
        assert received == [proto_bytes]
        await transport.disconnect()


# ---------------------------------------------------------------------------
# Non-protobuf messages (no content field) are silently dropped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_protobuf_message_is_silently_dropped(config: AliyunMQTTConfig) -> None:
    """Messages without a base64 content field should not call on_message."""
    received: list[bytes] = []

    async def _handler(data: bytes) -> None:
        received.append(data)

    transport = AliyunMQTTTransport(config)
    transport.on_message = _handler

    envelope = json.dumps({"code": 200, "message": "success"}).encode()
    fake_client = _FakeMQTTClient(
        messages=[_FakeMessage("/sys/pk/dn/app/down/account/bind_reply", envelope)]
    )

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.1)
        assert received == []
        await transport.disconnect()


# ---------------------------------------------------------------------------
# Auth error (rc=4/5) raises AuthError and stops reconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_error_raises_and_stops_reconnect(config: AliyunMQTTConfig) -> None:
    """rc=4/5 from the broker should raise AuthError and stop the connection loop."""
    transport = AliyunMQTTTransport(config)

    with patch("aiomqtt.Client", return_value=_AuthFailMQTTClient()):
        with pytest.raises(AuthError):
            await transport.connect()
            # Wait for the task to propagate the error
            if transport._task is not None:
                await transport._task

    # The stop event should have been set so no reconnect happens
    assert transport._stop_event.is_set()


# ---------------------------------------------------------------------------
# AliyunMQTTConfig.from_aliyun_credentials factory
# ---------------------------------------------------------------------------


def test_from_aliyun_credentials_builds_correct_config() -> None:
    """from_aliyun_credentials should derive host and username correctly."""
    from unittest.mock import MagicMock

    creds = MagicMock()
    creds.iot_token = "test-token"

    cfg = AliyunMQTTConfig.from_aliyun_credentials(
        region_id="cn-shanghai",
        product_key="myPK",
        device_name="myDN",
        device_secret="mySecret",
        credentials=creds,
    )

    assert cfg.host == "myPK.iot-as-mqtt.cn-shanghai.aliyuncs.com"
    assert cfg.username == "myDN&myPK"
    assert cfg.client_id_base == "myPK&myDN"
    assert cfg.device_name == "myDN"
    assert cfg.product_key == "myPK"
    assert cfg.device_secret == "mySecret"
    assert cfg.iot_token == "test-token"
    assert cfg.port == 8883


def test_from_aliyun_credentials_custom_client_id() -> None:
    """from_aliyun_credentials should respect a custom client_id_base."""
    from unittest.mock import MagicMock

    creds = MagicMock()
    creds.iot_token = "tok"

    cfg = AliyunMQTTConfig.from_aliyun_credentials(
        region_id="eu-central-1",
        product_key="pk",
        device_name="dn",
        device_secret="s",
        credentials=creds,
        client_id_base="custom-base",
    )

    assert cfg.client_id_base == "custom-base"
