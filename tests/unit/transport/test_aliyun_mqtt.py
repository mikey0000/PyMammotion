"""Tests for AliyunMQTTTransport."""
from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport
from pymammotion.transport.base import ReLoginRequiredError, TransportError, TransportType


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
def cloud_gateway() -> MagicMock:
    gw = MagicMock()
    gw.send_cloud_command = AsyncMock()
    return gw


@pytest.fixture
def transport(config: AliyunMQTTConfig, cloud_gateway: MagicMock) -> AliyunMQTTTransport:
    return AliyunMQTTTransport(config, cloud_gateway)


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
async def test_connect_sets_is_connected(config: AliyunMQTTConfig, cloud_gateway: MagicMock) -> None:
    """connect() should set is_connected to True once the MQTT loop is running."""
    transport = AliyunMQTTTransport(config, cloud_gateway)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)
        assert transport.is_connected is True
        await transport.disconnect()


@pytest.mark.asyncio
async def test_disconnect_sets_is_connected_false(config: AliyunMQTTConfig, cloud_gateway: MagicMock) -> None:
    """disconnect() should leave is_connected as False."""
    transport = AliyunMQTTTransport(config, cloud_gateway)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)
        await transport.disconnect()
        assert transport.is_connected is False


@pytest.mark.asyncio
async def test_connect_idempotent(config: AliyunMQTTConfig, cloud_gateway: MagicMock) -> None:
    """Calling connect() twice should not create a second task."""
    transport = AliyunMQTTTransport(config, cloud_gateway)
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


# ---------------------------------------------------------------------------
# send()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_raises_when_no_iot_id(transport: AliyunMQTTTransport) -> None:
    """send() with an empty iot_id should raise TransportError."""
    with pytest.raises(TransportError, match="iot_id"):
        await transport.send(b"hello")


@pytest.mark.asyncio
async def test_send_calls_cloud_gateway(config: AliyunMQTTConfig) -> None:
    """send() with a valid iot_id delegates to cloud_gateway.send_cloud_command."""
    cloud_gateway = MagicMock()
    cloud_gateway.send_cloud_command = AsyncMock()
    transport = AliyunMQTTTransport(config, cloud_gateway)

    await transport.send(b"\x01\x02", iot_id="abc123")

    cloud_gateway.send_cloud_command.assert_awaited_once_with("abc123", b"\x01\x02")


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
async def test_on_message_called_with_unwrapped_bytes(config: AliyunMQTTConfig, cloud_gateway: MagicMock) -> None:
    """on_message should receive the decoded protobuf bytes, not the JSON envelope.

    The Aliyun thing.events envelope shape (params.value.content) arrives on topics
    such as _thing/event/notify and thing/model/down_raw, which go through
    _unwrap_envelope → on_message.  The /thing/events topic routes to on_device_event
    instead and is tested separately.
    """
    received: list[bytes] = []

    async def _handler(data: bytes) -> None:
        received.append(data)

    transport = AliyunMQTTTransport(config, cloud_gateway)
    transport.on_message = _handler

    proto_bytes = b"\x08\x01\x12\x03foo"
    envelope = _make_thing_events_envelope(proto_bytes)
    fake_client = _FakeMQTTClient(
        messages=[_FakeMessage("/sys/pk/dn/app/down/_thing/event/notify", envelope)]
    )

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
async def test_on_message_called_mammotion_direct_shape(config: AliyunMQTTConfig, cloud_gateway: MagicMock) -> None:
    """on_message should also unwrap the Mammotion direct-MQTT params.content shape."""
    received: list[bytes] = []

    async def _handler(data: bytes) -> None:
        received.append(data)

    transport = AliyunMQTTTransport(config, cloud_gateway)
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
# Non-protobuf messages without content are silently dropped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_content_message_does_not_call_on_message(config: AliyunMQTTConfig, cloud_gateway: MagicMock) -> None:
    """Messages with no base64 content field (e.g. bind_reply) must not call on_message."""
    received: list[bytes] = []

    async def _handler(data: bytes) -> None:
        received.append(data)

    transport = AliyunMQTTTransport(config, cloud_gateway)
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
# thing/status messages are routed to on_device_status, not on_message
# ---------------------------------------------------------------------------


def _make_thing_status_payload(iot_id: str, status: int) -> bytes:
    """Build a thing/status JSON payload (StatusType: 1=online, 3=offline)."""
    return json.dumps({
        "method": "thing.status",
        "id": "99",
        "version": "1.0",
        "params": {
            "iotId": iot_id,
            "status": {"value": status, "time": 1700000000000},
            "groupIdList": [],
            "netType": "NET_WIFI",
            "activeTime": 0,
            "ip": "1.2.3.4",
            "aliyunCommodityCode": "iothub_senior",
            "categoryKey": "LawnMower",
            "nodeType": "DEVICE",
            "productKey": "pk",
            "statusLast": status,
            "deviceName": "dn",
            "namespace": "ns",
            "tenantId": "t1",
            "thingType": "DEVICE",
            "tenantInstanceId": "ti1",
            "categoryId": 1,
        },
    }).encode()


@pytest.mark.asyncio
async def test_thing_status_online_routes_to_on_device_status(
    config: AliyunMQTTConfig, cloud_gateway: MagicMock
) -> None:
    """thing/status with value=1 must call on_device_status('iot123', ThingStatusMessage)."""
    from pymammotion.data.mqtt.status import StatusType, ThingStatusMessage

    calls: list[tuple[str, ThingStatusMessage]] = []

    async def _status_handler(iot_id: str, msg: ThingStatusMessage) -> None:
        calls.append((iot_id, msg))

    transport = AliyunMQTTTransport(config, cloud_gateway)
    transport.on_device_status = _status_handler
    transport.on_message = AsyncMock()  # must NOT be called

    payload = _make_thing_status_payload("iot123", 1)
    fake_client = _FakeMQTTClient(
        messages=[_FakeMessage("/sys/pk/dn/app/down/thing/status", payload)]
    )

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.1)
        assert len(calls) == 1
        iot_id, msg = calls[0]
        assert iot_id == "iot123"
        assert isinstance(msg, ThingStatusMessage)
        assert msg.params.status.value is StatusType.CONNECTED
        transport.on_message.assert_not_awaited()
        await transport.disconnect()


@pytest.mark.asyncio
async def test_thing_status_offline_routes_to_on_device_status(
    config: AliyunMQTTConfig, cloud_gateway: MagicMock
) -> None:
    """thing/status with value=3 must call on_device_status('iot123', ThingStatusMessage)."""
    from pymammotion.data.mqtt.status import StatusType, ThingStatusMessage

    calls: list[tuple[str, ThingStatusMessage]] = []

    async def _status_handler(iot_id: str, msg: ThingStatusMessage) -> None:
        calls.append((iot_id, msg))

    transport = AliyunMQTTTransport(config, cloud_gateway)
    transport.on_device_status = _status_handler

    payload = _make_thing_status_payload("iot123", 3)
    fake_client = _FakeMQTTClient(
        messages=[_FakeMessage("/sys/pk/dn/app/down/thing/status", payload)]
    )

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.1)
        assert len(calls) == 1
        iot_id, msg = calls[0]
        assert iot_id == "iot123"
        assert isinstance(msg, ThingStatusMessage)
        assert msg.params.status.value is StatusType.DISCONNECTED
        await transport.disconnect()


# ---------------------------------------------------------------------------
# Auth error (rc=4/5) raises AuthError and stops reconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_error_raises_and_stops_reconnect(config: AliyunMQTTConfig, cloud_gateway: MagicMock) -> None:
    """rc=4/5 from the broker should raise ReLoginRequiredError and stop the connection loop."""
    transport = AliyunMQTTTransport(config, cloud_gateway)

    with patch("aiomqtt.Client", return_value=_AuthFailMQTTClient()):
        with pytest.raises(ReLoginRequiredError):
            await transport.connect()
            if transport._task is not None:
                await transport._task

    assert transport._stop_event.is_set()


# ---------------------------------------------------------------------------
# Network errors (OSError / DNS / ENETUNREACHABLE) — retry with backoff, no auth count
# ---------------------------------------------------------------------------


class _NetworkErrorClient:
    """Client whose __aenter__ raises a bare OSError (e.g. DNS failure or ENETUNREACHABLE)."""

    def __init__(self, exc: OSError) -> None:
        self._exc = exc

    async def __aenter__(self) -> "_NetworkErrorClient":
        raise self._exc

    async def __aexit__(self, *args: object) -> None:
        pass


@pytest.mark.asyncio
async def test_oserror_retries_without_auth_failure(config: AliyunMQTTConfig, cloud_gateway: MagicMock) -> None:
    """OSError (e.g. ENETUNREACHABLE) must retry with backoff and never call on_auth_failure."""
    transport = AliyunMQTTTransport(config, cloud_gateway)
    transport.on_auth_failure = AsyncMock(return_value=True)

    connect_attempts = 0

    def _client_factory(**_kwargs: object) -> object:
        nonlocal connect_attempts
        connect_attempts += 1
        if connect_attempts < 3:
            return _NetworkErrorClient(OSError(101, "Network is unreachable"))
        return _FakeMQTTClient(messages=[])  # succeeds on 3rd attempt

    # Zero-out backoff so retries happen immediately; real asyncio.sleep(0) yields the event loop.
    with patch("pymammotion.transport.aliyun_mqtt._MQTT_RECONNECT_MIN_SEC", 0), \
         patch("pymammotion.transport.aliyun_mqtt._MQTT_RECONNECT_MAX_SEC", 0), \
         patch("aiomqtt.Client", side_effect=_client_factory):
        await transport.connect()
        # Use a small real sleep — `asyncio.sleep(0)` does not pump executor
        # callbacks, and `get_ssl_context` now properly awaits a thread offload.
        for _ in range(200):
            if connect_attempts >= 3:
                break
            await asyncio.sleep(0.005)
        await transport.disconnect()

    assert connect_attempts >= 3
    transport.on_auth_failure.assert_not_awaited()


@pytest.mark.asyncio
async def test_dns_error_retries_without_auth_failure(config: AliyunMQTTConfig, cloud_gateway: MagicMock) -> None:
    """socket.gaierror (DNS failure) must retry and not trigger on_auth_failure."""
    import socket

    transport = AliyunMQTTTransport(config, cloud_gateway)
    transport.on_auth_failure = AsyncMock(return_value=True)

    connect_attempts = 0

    def _client_factory(**_kwargs: object) -> object:
        nonlocal connect_attempts
        connect_attempts += 1
        if connect_attempts < 2:
            return _NetworkErrorClient(socket.gaierror(-2, "Name or service not known"))
        return _FakeMQTTClient(messages=[])

    with patch("pymammotion.transport.aliyun_mqtt._MQTT_RECONNECT_MIN_SEC", 0), \
         patch("pymammotion.transport.aliyun_mqtt._MQTT_RECONNECT_MAX_SEC", 0), \
         patch("aiomqtt.Client", side_effect=_client_factory):
        await transport.connect()
        for _ in range(200):
            if connect_attempts >= 2:
                break
            await asyncio.sleep(0.005)
        await transport.disconnect()

    assert connect_attempts >= 2
    transport.on_auth_failure.assert_not_awaited()


# ---------------------------------------------------------------------------
# AliyunMQTTConfig.from_aliyun_credentials factory
# ---------------------------------------------------------------------------


def test_from_aliyun_credentials_builds_correct_config() -> None:
    """from_aliyun_credentials should derive host and username correctly."""
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


# ---------------------------------------------------------------------------
# update_iot_token
# ---------------------------------------------------------------------------


def test_update_iot_token_stores_new_value(config: AliyunMQTTConfig, cloud_gateway: MagicMock) -> None:
    """update_iot_token() must replace _iot_token; the frozen config is unchanged."""
    transport = AliyunMQTTTransport(config, cloud_gateway)
    assert transport._iot_token == "tok"

    transport.update_iot_token("new-token")

    assert transport._iot_token == "new-token"
    assert transport._config.iot_token == "tok"  # frozen config is not mutated


# ---------------------------------------------------------------------------
# Helpers for bind_reply tests
# ---------------------------------------------------------------------------


def _bind_reply_msg(code: int) -> _FakeMessage:
    topic = "/sys/pk/dn/app/down/account/bind_reply"
    payload = json.dumps({"code": code, "id": "msgid1", "message": "check iotToken failed" if code != 200 else "ok"}).encode()
    return _FakeMessage(topic, payload)


# ---------------------------------------------------------------------------
# bind_reply 2043 — SessionExpiredError cascade (transport level)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bind_reply_2043_no_callback_raises_relogin_required(
    config: AliyunMQTTConfig, cloud_gateway: MagicMock
) -> None:
    """bind_reply 2043 with no on_auth_failure → ReLoginRequiredError propagates out of _run()."""
    transport = AliyunMQTTTransport(config, cloud_gateway)
    fake_client = _FakeMQTTClient(messages=[_bind_reply_msg(2043)])

    with patch("aiomqtt.Client", return_value=fake_client):
        with pytest.raises(ReLoginRequiredError):
            await transport._run()

    assert transport._stop_event.is_set()


@pytest.mark.asyncio
async def test_bind_reply_2043_callback_returns_false_raises_relogin_required(
    config: AliyunMQTTConfig, cloud_gateway: MagicMock
) -> None:
    """bind_reply 2043 → on_auth_failure returns False → ReLoginRequiredError propagates."""
    transport = AliyunMQTTTransport(config, cloud_gateway)
    transport.on_auth_failure = AsyncMock(return_value=False)

    fake_client = _FakeMQTTClient(messages=[_bind_reply_msg(2043)])
    with patch("aiomqtt.Client", return_value=fake_client):
        with pytest.raises(ReLoginRequiredError):
            await transport._run()

    transport.on_auth_failure.assert_awaited_once()
    assert transport._stop_event.is_set()


@pytest.mark.asyncio
async def test_bind_reply_2043_callback_raises_nonfatal_exception_raises_relogin_required(
    config: AliyunMQTTConfig, cloud_gateway: MagicMock
) -> None:
    """Non-ReLoginRequiredError from on_auth_failure is swallowed; ReLoginRequiredError propagates."""
    transport = AliyunMQTTTransport(config, cloud_gateway)
    transport.on_auth_failure = AsyncMock(side_effect=RuntimeError("refresh exploded"))

    fake_client = _FakeMQTTClient(messages=[_bind_reply_msg(2043)])
    with patch("aiomqtt.Client", return_value=fake_client):
        with pytest.raises(ReLoginRequiredError):
            await transport._run()

    transport.on_auth_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_bind_reply_2043_callback_returns_true_reconnects(
    config: AliyunMQTTConfig, cloud_gateway: MagicMock
) -> None:
    """bind_reply 2043 → on_auth_failure returns True → loop continues and reconnects."""
    transport = AliyunMQTTTransport(config, cloud_gateway)

    auth_failure_calls: list[int] = []

    async def _refresh() -> bool:
        auth_failure_calls.append(1)
        transport.update_iot_token("refreshed-token")
        return True

    transport.on_auth_failure = _refresh

    # First connect: sends 2043; second: blocks with no messages (cancelled by disconnect)
    clients = [
        _FakeMQTTClient(messages=[_bind_reply_msg(2043)]),
        _FakeMQTTClient(messages=[]),
    ]

    with patch("aiomqtt.Client", side_effect=clients):
        await transport.connect()
        await asyncio.sleep(0.1)
        assert transport.is_connected
        assert transport._iot_token == "refreshed-token"
        assert len(auth_failure_calls) == 1
        await transport.disconnect()


@pytest.mark.asyncio
async def test_bind_reply_2043_new_token_sent_on_reconnect(
    config: AliyunMQTTConfig, cloud_gateway: MagicMock
) -> None:
    """After a successful on_auth_failure refresh, the new iot_token is published in the bind message."""
    transport = AliyunMQTTTransport(config, cloud_gateway)

    async def _refresh() -> bool:
        transport.update_iot_token("brand-new-token")
        return True

    transport.on_auth_failure = _refresh

    second_client = _FakeMQTTClient(messages=[])
    clients = [
        _FakeMQTTClient(messages=[_bind_reply_msg(2043)]),
        second_client,
    ]

    with patch("aiomqtt.Client", side_effect=clients):
        await transport.connect()
        await asyncio.sleep(0.1)
        await transport.disconnect()

    # The second client's publish should have been called with the new token
    assert second_client.publish.await_count >= 1
    _, bind_kwargs = second_client.publish.call_args
    published_body = json.loads(bind_kwargs.get("payload") or second_client.publish.call_args.args[1])
    assert published_body["params"]["iotToken"] == "brand-new-token"


@pytest.mark.asyncio
async def test_bind_reply_200_no_auth_failure(
    config: AliyunMQTTConfig, cloud_gateway: MagicMock
) -> None:
    """bind_reply 200 (success) must not trigger on_auth_failure."""
    transport = AliyunMQTTTransport(config, cloud_gateway)
    transport.on_auth_failure = AsyncMock(return_value=True)

    fake_client = _FakeMQTTClient(messages=[_bind_reply_msg(200)])

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)
        await transport.disconnect()

    transport.on_auth_failure.assert_not_awaited()


# ---------------------------------------------------------------------------
# Client _on_aliyun_auth_failure callback (integration)
# ---------------------------------------------------------------------------


def _make_mock_cloud_client(iot_token: str = "initial-tok") -> MagicMock:
    """Build a minimal mock CloudIOTGateway sufficient for _setup_aliyun_transport."""
    gw = MagicMock()
    gw.client_id = "client-id-base"
    gw.aep_response.data.productKey = "pk"
    gw.aep_response.data.deviceName = "dn"
    gw.aep_response.data.deviceSecret = "secret"
    gw.region_response.data.regionId = "cn-shanghai"
    gw.session_by_authcode_response.data.iotToken = iot_token
    return gw


def _make_aliyun_session(iot_token: str = "initial-tok") -> tuple:
    """Return (MammotionClient, AccountSession, AliyunMQTTTransport) wired via _setup_aliyun_transport."""
    from pymammotion.account.registry import AccountRegistry, AccountSession
    from pymammotion.client import MammotionClient

    session = AccountSession(
        account_id="test@example.com",
        email="test@example.com",
        password="secret",
    )
    session.mammotion_http = AsyncMock()
    session.token_manager = AsyncMock()

    client = MammotionClient.__new__(MammotionClient)
    client._account_registry = AccountRegistry()
    client._account_registry._sessions[session.account_id] = session

    cloud_client = _make_mock_cloud_client(iot_token)
    transport = client._setup_aliyun_transport(cloud_client, session)
    session.aliyun_transport = transport
    return client, session, transport


@pytest.mark.asyncio
async def test_on_aliyun_auth_failure_targeted_refresh_succeeds_no_full_relogin() -> None:
    """Happy path: targeted refresh succeeds → token pushed → True, login_v2 NOT called.

    When the iotToken simply expired (2043/460) but the refreshToken is still valid,
    check_or_refresh_session is sufficient.  _full_relogin (login_v2) must NOT fire
    because that would hammer the API unnecessarily and risk triggering an account block.
    """
    client, session, transport = _make_aliyun_session("old-tok")

    new_creds = MagicMock()
    new_creds.iot_token = "fresh-tok"

    session.token_manager.refresh_aliyun_credentials = AsyncMock()  # succeeds
    session.token_manager.get_aliyun_credentials = AsyncMock(return_value=new_creds)
    session.mammotion_http.login_v2 = AsyncMock()

    result = await transport.on_auth_failure()

    assert result is True
    assert transport._iot_token == "fresh-tok"
    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()
    session.mammotion_http.login_v2.assert_not_awaited()
    session.token_manager.get_aliyun_credentials.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_aliyun_auth_failure_full_relogin_after_exhausted_refresh_token() -> None:
    """When refreshToken is exhausted, escalate to _full_relogin → token updated → True."""
    client, session, transport = _make_aliyun_session("old-tok")

    new_creds = MagicMock()
    new_creds.iot_token = "post-relogin-tok"

    session.token_manager.refresh_aliyun_credentials = AsyncMock(
        side_effect=ReLoginRequiredError("test@example.com", "refreshToken exhausted")
    )
    login_resp = MagicMock()
    login_resp.code = 0
    session.mammotion_http.login_v2 = AsyncMock(return_value=login_resp)
    session.token_manager.force_refresh = AsyncMock()
    session.token_manager.get_aliyun_credentials = AsyncMock(return_value=new_creds)

    result = await transport.on_auth_failure()

    assert result is True
    assert transport._iot_token == "post-relogin-tok"
    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()
    session.mammotion_http.login_v2.assert_awaited_once()
    session.token_manager.get_aliyun_credentials.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_aliyun_auth_failure_both_paths_fail_raises_relogin_required() -> None:
    """targeted refresh + _full_relogin both fail → ReLoginRequiredError raised."""
    client, session, transport = _make_aliyun_session("old-tok")

    session.token_manager.refresh_aliyun_credentials = AsyncMock(
        side_effect=ReLoginRequiredError("test@example.com", "exhausted")
    )
    login_resp = MagicMock()
    login_resp.code = 401
    login_resp.msg = "invalid credentials"
    session.mammotion_http.login_v2 = AsyncMock(return_value=login_resp)

    with pytest.raises(ReLoginRequiredError):
        await transport.on_auth_failure()

    assert transport._iot_token == "old-tok"  # not updated
    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()
    session.mammotion_http.login_v2.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_aliyun_auth_failure_calls_targeted_refresh_before_full_relogin() -> None:
    """on_auth_failure must call refresh_aliyun_credentials first.

    The targeted refresh (check_or_refresh_session) is the lightweight path that
    works whenever the iotToken expired but the refreshToken is still valid.
    Skipping it and going straight to _full_relogin (login_v2) fires unnecessary
    API calls that can trigger an account block on Aliyun.
    """
    client, session, transport = _make_aliyun_session("old-tok")

    new_creds = MagicMock()
    new_creds.iot_token = "renewed-tok"
    session.token_manager.refresh_aliyun_credentials = AsyncMock()  # succeeds
    session.token_manager.get_aliyun_credentials = AsyncMock(return_value=new_creds)
    session.mammotion_http.login_v2 = AsyncMock()

    await transport.on_auth_failure()

    # Targeted refresh is called; _full_relogin (login_v2) is NOT called.
    session.token_manager.refresh_aliyun_credentials.assert_awaited_once()
    session.mammotion_http.login_v2.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_aliyun_auth_failure_no_token_manager_returns_false() -> None:
    """When token_manager is None (edge case), on_auth_failure returns False immediately."""
    client, session, transport = _make_aliyun_session()
    session.token_manager = None

    # Re-wire with no token manager
    _client2, session2, transport2 = _make_aliyun_session()
    session2.token_manager = None
    cloud_client = _make_mock_cloud_client()
    transport2 = client._setup_aliyun_transport(cloud_client, session2)

    result = await transport2.on_auth_failure()

    assert result is False


# ---------------------------------------------------------------------------
# End-to-end: bind_reply 2043 → full relogin failure → AuthError → HA must re-login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bind_reply_2043_relogin_failure_raises_relogin_required_end_to_end() -> None:
    """Full cascade: bind_reply 2043 → targeted refresh fails → _full_relogin fails →
    ReLoginRequiredError propagates out of _run().

    Targeted refresh is attempted first (lighter path).  When it raises
    ReLoginRequiredError, _full_relogin is called.  Both fail → error propagates.
    """
    client, session, transport = _make_aliyun_session("stale-tok")

    session.token_manager.refresh_aliyun_credentials = AsyncMock(
        side_effect=ReLoginRequiredError("test@example.com", "refreshToken exhausted")
    )
    login_resp = MagicMock()
    login_resp.code = 500
    login_resp.msg = "server error"
    session.mammotion_http.login_v2 = AsyncMock(return_value=login_resp)

    fake_client = _FakeMQTTClient(messages=[_bind_reply_msg(2043)])

    with patch("aiomqtt.Client", return_value=fake_client):
        with pytest.raises(ReLoginRequiredError):
            await transport._run()

    assert transport._stop_event.is_set()
    # Targeted refresh was called first
    session.token_manager.refresh_aliyun_credentials.assert_awaited()
    # login_v2 called twice: once from on_auth_failure, once from on_fatal_auth_error
    assert session.mammotion_http.login_v2.await_count == 2


@pytest.mark.asyncio
async def test_bind_reply_2043_relogin_success_fires_on_fatal_auth_and_reconnects() -> None:
    """bind_reply 2043 → targeted refresh fails → _full_relogin fails → on_fatal_auth_error fires."""
    client, session, transport = _make_aliyun_session("stale-tok")

    fatal_calls: list[ReLoginRequiredError] = []

    async def _on_fatal(exc: ReLoginRequiredError) -> None:
        fatal_calls.append(exc)

    transport.on_fatal_auth_error = _on_fatal

    # Targeted refresh exhausted, full re-login also fails
    session.token_manager.refresh_aliyun_credentials = AsyncMock(
        side_effect=ReLoginRequiredError("test@example.com", "exhausted")
    )
    login_resp_fail = MagicMock()
    login_resp_fail.code = 500
    login_resp_fail.msg = "server error"
    session.mammotion_http.login_v2 = AsyncMock(return_value=login_resp_fail)

    fake_client = _FakeMQTTClient(messages=[_bind_reply_msg(2043)])

    with patch("aiomqtt.Client", return_value=fake_client):
        with pytest.raises(ReLoginRequiredError):
            await transport._run()

    assert transport._stop_event.is_set()
    assert len(fatal_calls) == 1
    assert isinstance(fatal_calls[0], ReLoginRequiredError)
