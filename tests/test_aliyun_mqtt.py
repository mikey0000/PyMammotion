"""Unit tests for AliyunMQTT (aiomqtt-based implementation)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import ssl
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import betterproto2
import pytest

from pymammotion.data.mqtt.event import DeviceProtobufMsgEventParams, ThingEventMessage
from pymammotion.mqtt.aliyun_mqtt import (
    AliyunMQTT,
    _MQTT_KEEPALIVE,
    _MQTT_MAX_INFLIGHT,
    _MQTT_MAX_QUEUED,
    _MQTT_PORT,
    _MQTT_RECONNECT_MAX_SEC,
    _MQTT_RECONNECT_MIN_SEC,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_cloud_client(iot_token: str = "test-iot-token") -> MagicMock:
    cloud_client = MagicMock()
    cloud_client.session_by_authcode_response.data.iotToken = iot_token
    return cloud_client


def _make_aliyun_mqtt(
    *,
    region_id: str = "eu-central-1",
    product_key: str = "testProductKey",
    device_name: str = "testDevice",
    device_secret: str = "testSecret",
    iot_token: str = "test-iot-token",
    client_id: str | None = "myClient",
    cloud_client: MagicMock | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> AliyunMQTT:
    """Create an AliyunMQTT instance for testing.

    Pass ``loop`` in synchronous tests (where there is no running event loop).
    Omit ``loop`` in async tests — the running loop is used directly.
    """
    if cloud_client is None:
        cloud_client = _make_cloud_client(iot_token)

    def _create() -> AliyunMQTT:
        return AliyunMQTT(
            region_id=region_id,
            product_key=product_key,
            device_name=device_name,
            device_secret=device_secret,
            iot_token=iot_token,
            cloud_client=cloud_client,
            client_id=client_id,
        )

    if loop is not None:
        with patch("pymammotion.mqtt.aliyun_mqtt.asyncio.get_running_loop", return_value=loop):
            return _create()
    return _create()


# ---------------------------------------------------------------------------
# Credential format tests
# ---------------------------------------------------------------------------


class TestCredentials:
    def test_client_id_format(self, event_loop: asyncio.AbstractEventLoop) -> None:
        """Custom client_id is the base; full string includes securemode options and timestamp."""
        fixed_ts = 1700000000
        with patch("pymammotion.mqtt.aliyun_mqtt.time.time", return_value=fixed_ts):
            obj = _make_aliyun_mqtt(client_id="myClient", loop=event_loop)
            client_id, _ = obj._build_credentials()
        assert client_id == f"myClient|securemode=2,signmethod=hmacsha1,ext=1,_ss=1,timestamp={fixed_ts}|"

    def test_client_id_default(self, event_loop: asyncio.AbstractEventLoop) -> None:
        """Default client_id base is '{product_key}&{device_name}'."""
        obj = _make_aliyun_mqtt(client_id=None, device_name="dev123", product_key="pk", loop=event_loop)
        assert obj._client_id_base == "pk&dev123"

    def test_username_format(self, event_loop: asyncio.AbstractEventLoop) -> None:
        """Username must be '{device_name}&{product_key}'."""
        obj = _make_aliyun_mqtt(device_name="dev", product_key="pk", loop=event_loop)
        assert obj._mqtt_username == "dev&pk"

    def test_password_hmac_sha1(self, event_loop: asyncio.AbstractEventLoop) -> None:
        """Password is HMAC-SHA1 of 'clientId{base}deviceName{dn}productKey{pk}timestamp{ts}'."""
        client_id_base = "myClient"
        device_name = "dev"
        product_key = "pk"
        device_secret = "secret"
        fixed_ts = 1700000000
        sign_content = (
            f"clientId{client_id_base}deviceName{device_name}productKey{product_key}timestamp{fixed_ts}"
        )
        expected = hmac.new(
            device_secret.encode("utf-8"), sign_content.encode("utf-8"), hashlib.sha1
        ).hexdigest()

        with patch("pymammotion.mqtt.aliyun_mqtt.time.time", return_value=fixed_ts):
            obj = _make_aliyun_mqtt(
                client_id=client_id_base,
                device_name=device_name,
                product_key=product_key,
                device_secret=device_secret,
                loop=event_loop,
            )
            _, password = obj._build_credentials()
        assert password == expected

    def test_mqtt_host_format(self, event_loop: asyncio.AbstractEventLoop) -> None:
        """Endpoint must be '{product_key}.iot-as-mqtt.{region_id}.aliyuncs.com'."""
        obj = _make_aliyun_mqtt(product_key="pk", region_id="cn-shanghai", loop=event_loop)
        assert obj._mqtt_host == "pk.iot-as-mqtt.cn-shanghai.aliyuncs.com"


# ---------------------------------------------------------------------------
# TLS configuration tests
# ---------------------------------------------------------------------------


class TestTLSConfiguration:
    def test_tls_context_created_with_ca_data(self, event_loop: asyncio.AbstractEventLoop) -> None:
        """TLS context must be created using Aliyun's embedded CA bundle."""
        with (
            patch("pymammotion.mqtt.aliyun_mqtt.asyncio.get_running_loop", return_value=event_loop),
            patch("pymammotion.mqtt.aliyun_mqtt.ssl.create_default_context") as mock_ctx_fn,
        ):
            mock_ctx = MagicMock()
            mock_ctx_fn.return_value = mock_ctx
            obj = AliyunMQTT(
                region_id="eu-central-1",
                product_key="pk",
                device_name="dn",
                device_secret="sec",
                iot_token="tok",
                cloud_client=_make_cloud_client(),
            )

        mock_ctx_fn.assert_called_once()
        pos_args, kw_args = mock_ctx_fn.call_args
        assert pos_args[0] == ssl.Purpose.SERVER_AUTH
        assert "-----BEGIN CERTIFICATE-----" in kw_args["cadata"]
        assert obj._tls_context is mock_ctx


# ---------------------------------------------------------------------------
# connect_async / disconnect tests
# ---------------------------------------------------------------------------


class TestConnectDisconnect:
    def test_connect_async_schedules_task(self, event_loop: asyncio.AbstractEventLoop) -> None:
        """connect_async() schedules _start_task on the event loop."""
        obj = _make_aliyun_mqtt(loop=event_loop)
        with patch.object(obj.loop, "call_soon_threadsafe") as mock_cst:
            obj.connect_async()
        mock_cst.assert_called_once_with(obj._start_task)
        assert not obj._disconnect_requested

    def test_connect_async_clears_disconnect_flag(self, event_loop: asyncio.AbstractEventLoop) -> None:
        obj = _make_aliyun_mqtt(loop=event_loop)
        obj._disconnect_requested = True
        with patch.object(obj.loop, "call_soon_threadsafe"):
            obj.connect_async()
        assert not obj._disconnect_requested

    def test_connect_async_ignored_when_already_connected(self, event_loop: asyncio.AbstractEventLoop) -> None:
        """connect_async() must not schedule a new task when is_connected is True."""
        obj = _make_aliyun_mqtt(loop=event_loop)
        obj.is_connected = True
        with patch.object(obj.loop, "call_soon_threadsafe") as mock_cst:
            obj.connect_async()
        mock_cst.assert_not_called()

    def test_disconnect_sets_flag_and_cancels_task(self, event_loop: asyncio.AbstractEventLoop) -> None:
        obj = _make_aliyun_mqtt(loop=event_loop)
        mock_task = MagicMock()
        obj._task = mock_task
        with patch.object(obj.loop, "call_soon_threadsafe") as mock_cst:
            obj.disconnect()
        assert obj._disconnect_requested
        mock_cst.assert_called_once_with(mock_task.cancel)

    def test_disconnect_without_task_is_safe(self, event_loop: asyncio.AbstractEventLoop) -> None:
        obj = _make_aliyun_mqtt(loop=event_loop)
        obj._task = None
        obj.disconnect()  # must not raise
        assert obj._disconnect_requested


# ---------------------------------------------------------------------------
# _start_task tests
# ---------------------------------------------------------------------------


class TestStartTask:
    def test_creates_task_when_none(self, event_loop: asyncio.AbstractEventLoop) -> None:
        obj = _make_aliyun_mqtt(loop=event_loop)
        with patch.object(obj.loop, "create_task") as mock_ct:
            obj._start_task()
        mock_ct.assert_called_once()

    def test_does_not_create_task_when_running(self, event_loop: asyncio.AbstractEventLoop) -> None:
        obj = _make_aliyun_mqtt(loop=event_loop)
        mock_task = MagicMock()
        mock_task.done.return_value = False
        obj._task = mock_task
        with patch.object(obj.loop, "create_task") as mock_ct:
            obj._start_task()
        mock_ct.assert_not_called()

    def test_creates_new_task_when_previous_done(self, event_loop: asyncio.AbstractEventLoop) -> None:
        obj = _make_aliyun_mqtt(loop=event_loop)
        mock_task = MagicMock()
        mock_task.done.return_value = True
        obj._task = mock_task
        with patch.object(obj.loop, "create_task") as mock_ct:
            obj._start_task()
        mock_ct.assert_called_once()


# ---------------------------------------------------------------------------
# _run() integration tests (mocked aiomqtt.Client)
# ---------------------------------------------------------------------------


def _make_async_iter(items: list[Any]) -> AsyncMock:
    """Return an async context that yields items one by one."""

    async def _ait() -> Any:
        for item in items:
            yield item

    mock = MagicMock()
    mock.__aiter__ = lambda self: _ait()
    return mock


class TestRunLoop:
    async def _run_once(
        self,
        obj: AliyunMQTT,
        messages: list[Any] | None = None,
        connect_raises: Exception | None = None,
    ) -> MagicMock:
        """Run _run() through exactly one connection cycle.

        The cycle completes when:
        - the messages async iterator is exhausted (normal path), or
        - the mock Client raises on entry (error path).
        Either way, the sleep mock sets _disconnect_requested=True so the
        while loop exits after the first iteration.
        """
        if messages is None:
            messages = []

        mock_client = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client.publish = AsyncMock()
        mock_client.messages = _make_async_iter(messages)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        if connect_raises is not None:
            mock_client.__aenter__.side_effect = connect_raises

        async def _stop_after_sleep(*_args: Any, **_kwargs: Any) -> None:
            obj._disconnect_requested = True

        with (
            patch("pymammotion.mqtt.aliyun_mqtt.aiomqtt.Client", return_value=mock_client),
            patch("pymammotion.mqtt.aliyun_mqtt.asyncio.sleep", side_effect=_stop_after_sleep),
        ):
            obj._disconnect_requested = False
            await obj._run()

        return mock_client

    async def test_subscribes_to_all_topics(self) -> None:
        obj = _make_aliyun_mqtt(product_key="pk", device_name="dn")
        mock_client = await self._run_once(obj)
        subscribed = [c.args[0] for c in mock_client.subscribe.call_args_list]
        assert subscribed == obj._subscription_topics()

    async def test_publishes_bind_request(self) -> None:
        cloud = _make_cloud_client(iot_token="tok123")
        obj = _make_aliyun_mqtt(product_key="pk", device_name="dn", cloud_client=cloud)
        mock_client = await self._run_once(obj)
        publish_call = mock_client.publish.call_args
        assert publish_call is not None
        topic = publish_call.args[0]
        payload = json.loads(publish_call.args[1])
        assert topic == "/sys/pk/dn/app/up/account/bind"
        assert payload["params"]["iotToken"] == "tok123"

    async def test_fires_on_connected_and_on_ready(self) -> None:
        obj = _make_aliyun_mqtt()
        connected = AsyncMock()
        ready = AsyncMock()
        obj.on_connected = connected
        obj.on_ready = ready
        await self._run_once(obj)
        connected.assert_awaited_once()
        ready.assert_awaited_once()

    async def test_sets_and_clears_is_connected(self) -> None:
        obj = _make_aliyun_mqtt()
        assert not obj.is_connected
        await self._run_once(obj)
        assert not obj.is_connected

    async def test_fires_on_disconnected_after_connection(self) -> None:
        obj = _make_aliyun_mqtt()
        disconnected = AsyncMock()
        obj.on_disconnected = disconnected
        await self._run_once(obj)
        disconnected.assert_awaited_once()

    async def test_mqtt_error_does_not_fire_on_disconnected_if_never_connected(self) -> None:
        import aiomqtt as _aiomqtt

        obj = _make_aliyun_mqtt()
        disconnected = AsyncMock()
        obj.on_disconnected = disconnected
        await self._run_once(obj, connect_raises=_aiomqtt.MqttError("refused"))
        disconnected.assert_not_awaited()


# ---------------------------------------------------------------------------
# _dispatch() tests
# ---------------------------------------------------------------------------


class TestDispatch:
    async def test_routes_message_with_iot_id(self) -> None:
        obj = _make_aliyun_mqtt()
        callback = AsyncMock()
        obj.on_message = callback
        payload = json.dumps({"params": {"iotId": "dev-abc", "value": "x"}}).encode()
        await obj._dispatch("/sys/pk/dn/app/down/thing/events", payload)
        callback.assert_awaited_once()
        topic, raw, iot_id = callback.call_args.args
        assert topic == "/sys/pk/dn/app/down/thing/events"
        assert iot_id == "dev-abc"
        assert isinstance(raw, bytes)

    async def test_ignores_message_without_iot_id(self) -> None:
        obj = _make_aliyun_mqtt()
        callback = AsyncMock()
        obj.on_message = callback
        payload = json.dumps({"params": {"status": "online"}}).encode()
        await obj._dispatch("/sys/pk/dn/app/down/thing/status", payload)
        callback.assert_not_awaited()

    async def test_ignores_non_json_payload(self) -> None:
        obj = _make_aliyun_mqtt()
        obj.on_message = AsyncMock()
        await obj._dispatch("/sys/pk/dn/app/down/thing/events", b"not-json")
        obj.on_message.assert_not_awaited()

    async def test_accepts_str_payload(self) -> None:
        obj = _make_aliyun_mqtt()
        callback = AsyncMock()
        obj.on_message = callback
        payload = json.dumps({"params": {"iotId": "dev-1"}})
        await obj._dispatch("/sys/pk/dn/app/down/thing/events", payload)
        callback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Subscription topic list tests
# ---------------------------------------------------------------------------


class TestSubscriptionTopics:
    def test_returns_nine_topics(self, event_loop: asyncio.AbstractEventLoop) -> None:
        obj = _make_aliyun_mqtt(loop=event_loop)
        assert len(obj._subscription_topics()) == 9

    def test_topics_scoped_to_product_and_device(self, event_loop: asyncio.AbstractEventLoop) -> None:
        obj = _make_aliyun_mqtt(product_key="mypk", device_name="mydn", loop=event_loop)
        for topic in obj._subscription_topics():
            assert topic.startswith("/sys/mypk/mydn/"), topic

    def test_required_topics_present(self, event_loop: asyncio.AbstractEventLoop) -> None:
        obj = _make_aliyun_mqtt(product_key="pk", device_name="dn", loop=event_loop)
        topics = obj._subscription_topics()
        base = "/sys/pk/dn"
        for suffix in [
            "/app/down/account/bind_reply",
            "/app/down/thing/events",
            "/app/down/thing/status",
            "/app/down/thing/properties",
            "/app/down/thing/model/down_raw",
        ]:
            assert f"{base}{suffix}" in topics


# ---------------------------------------------------------------------------
# send_cloud_command test
# ---------------------------------------------------------------------------


class TestSendCloudCommand:
    async def test_delegates_to_cloud_client(self) -> None:
        cloud = _make_cloud_client()
        cloud.send_cloud_command = AsyncMock(return_value="ok")
        obj = _make_aliyun_mqtt(cloud_client=cloud)

        result = await obj.send_cloud_command("iot-id-1", b"\x01\x02")

        cloud.send_cloud_command.assert_awaited_once_with("iot-id-1", b"\x01\x02")
        assert result == "ok"


# ---------------------------------------------------------------------------
# ThingEventMessage parsing — Aliyun thing/events payload
# ---------------------------------------------------------------------------

# Real payload captured from a live Yuka device on the Aliyun thing/events topic.
# params.value.content decodes to a LubaMsg containing toapp_all_hash_name.
_THING_EVENTS_PAYLOAD: dict[str, Any] = {
    "method": "thing.events",
    "id": "17742925978238386",
    "params": {
        "groupIdList": ["a103KFib2pj733DB"],
        "checkFailedData": {},
        "_tenantId": "90AB9606A6F24B4E8CFE9333B8B2F230",
        "groupId": "a103KFib2pj733DB",
        "batchId": "a4e3729642cf47feb9c068e3da271792",
        "productKey": "a1biqVGvxrE",
        "type": "info",
        "generateTime": 1774292597802,
        "deviceName": "Yuka-MNTXVHBE",
        "JMSXDeliveryCount": 1,
        "checkLevel": 0,
        "qos": 1,
        "requestId": "65110",
        "_categoryKey": "TmallGenie.LawnMower",
        "value": {
            "content": (
                "CPABEAEYByACKGIwAVqtAeoDqQEKGlVUcGJ3R0M3dnhkNERwTnZiRkdMMDAwMDAwEhsJ"
                "Z2vn+sZTOiUSEE5laWdoYm91cnMgZnJvbnQSHAlSC5tdTbBQRhIRQmVsb3cgY2xvdGhl"
                "c2xpbmUSDwm3RLI6QPU2RxIEUm9hZBIQCfxcvLRPwiZaEgVGZW5jZRIVCc36mPbms4Nz"
                "EgpGcm9udCB5YXJkEhYJbnjXy+zzq3YSC0Nsb3RoZXNsaW5l"
            )
        },
        "deviceType": "LawnMower",
        "identifier": "device_protobuf_msg_event",
        "categoryKey": "LawnMower",
        "gmtCreate": 1774292597802,
        "_traceId": "a9fef5d617742925977958244d0067",
        "iotId": "UTpbwGC7vxd4DpNvbFGL000000",
        "namespace": "TmallGenie",
        "tenantId": "90AB9606A6F24B4E8CFE9333B8B2F230",
        "name": "Protobuf\xe5\x8d\x8f\xe8\xae\xae\xe4\xbf\xa1\xe6\x81\xaf\xe4\xba\x8b\xe4\xbb\xb6",
        "thingType": "DEVICE",
        "time": 1774292597801,
        "tenantInstanceId": "iotx-oxssharez400",
    },
    "version": "1.0",
}


class TestThingEventMessage:
    def test_parses_as_protobuf_event(self) -> None:
        event = ThingEventMessage.from_dicts(_THING_EVENTS_PAYLOAD)
        assert isinstance(event.params, DeviceProtobufMsgEventParams)

    def test_extracts_iot_id(self) -> None:
        event = ThingEventMessage.from_dicts(_THING_EVENTS_PAYLOAD)
        assert isinstance(event.params, DeviceProtobufMsgEventParams)
        assert event.params.iot_id == "UTpbwGC7vxd4DpNvbFGL000000"

    def test_content_is_base64_string(self) -> None:
        event = ThingEventMessage.from_dicts(_THING_EVENTS_PAYLOAD)
        assert isinstance(event.params, DeviceProtobufMsgEventParams)
        content = event.params.value.content
        assert isinstance(content, str)
        # must be valid base64
        base64.b64decode(content)

    def test_content_decodes_to_luba_msg(self) -> None:
        from pymammotion.proto import LubaMsg

        event = ThingEventMessage.from_dicts(_THING_EVENTS_PAYLOAD)
        assert isinstance(event.params, DeviceProtobufMsgEventParams)
        luba_msg = LubaMsg().parse(base64.b64decode(event.params.value.content))
        assert luba_msg is not None

    def test_protobuf_contains_toapp_all_hash_name(self) -> None:
        from pymammotion.proto import LubaMsg

        event = ThingEventMessage.from_dicts(_THING_EVENTS_PAYLOAD)
        assert isinstance(event.params, DeviceProtobufMsgEventParams)
        luba_msg = LubaMsg().parse(base64.b64decode(event.params.value.content))

        sub_name, sub_val = betterproto2.which_one_of(luba_msg, "LubaSubMsg")
        assert sub_name == "nav", f"expected nav sub-message, got {sub_name!r}"
        leaf_name, _ = betterproto2.which_one_of(sub_val, "SubNavMsg")
        assert leaf_name == "toapp_all_hash_name", f"expected toapp_all_hash_name, got {leaf_name!r}"


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
