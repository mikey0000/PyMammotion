"""Tests that stale Aliyun thing-event envelopes are dropped by AliyunMQTTTransport.

Issue #130: `params.time` (Unix ms) reflects cloud-side generation time and
survives buffering.  Messages older than _STALE_EVENT_THRESHOLD_MS relative to
the current wall clock are dropped in the transport layer so that buffered
telemetry from connectivity gaps never reaches DeviceHandle.
"""
from __future__ import annotations

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport, _STALE_EVENT_THRESHOLD_MS


@pytest.fixture
def transport():
    """AliyunMQTTTransport with a mocked cloud gateway."""
    config = AliyunMQTTConfig(
        host="test.iot-as-mqtt.cn-shanghai.aliyuncs.com",
        client_id_base="testpk&testdn",
        username="testdn&testpk",
        device_name="testdn",
        product_key="testpk",
        device_secret="testsecret",
        iot_token="testtoken",
    )
    gateway = MagicMock()
    t = AliyunMQTTTransport(config, gateway)
    t.on_device_event = AsyncMock()
    t.on_device_properties = AsyncMock()
    return t


def _make_event_envelope(envelope_time_ms: int, identifier: str = "device_protobuf_msg_event") -> bytes:
    """Build a raw JSON thing/events envelope with the given params.time."""
    sample_bytes = b'\x08\xf4\x01\x10\x01\x18\x07(\x010\x01R\x08\xba\x02\x05\x12\x03\x08\x05\x10K'
    encoded = base64.b64encode(sample_bytes).decode("ascii")

    payload = {
        "method": "thing.events",
        "id": "test-event-id",
        "version": "1.0",
        "params": {
            "identifier": identifier,
            "type": "info",
            "time": envelope_time_ms,
            "iotId": "test_iot_id",
            "productKey": "testpk",
            "deviceName": "testdn",
            "gmtCreate": 1714000000000,
            "groupIdList": [],
            "groupId": "",
            "categoryKey": "LawnMower",
            "batchId": "",
            "checkLevel": 0,
            "namespace": "",
            "tenantId": "",
            "name": "",
            "thingType": "DEVICE",
            "tenantInstanceId": "",
            "value": {
                "content": encoded,
            },
        },
    }
    return json.dumps(payload).encode()


@pytest.mark.asyncio
async def test_fresh_event_forwarded(transport: AliyunMQTTTransport):
    """Events with params.time within the threshold are forwarded."""
    now_ms = int(time.time() * 1000)
    raw = _make_event_envelope(now_ms - 5_000)  # 5 seconds old

    await transport._dispatch_aliyun_event("/sys/testpk/testdn/app/down/thing/events", raw)

    transport.on_device_event.assert_called_once()


@pytest.mark.asyncio
async def test_stale_event_dropped(transport: AliyunMQTTTransport):
    """Events older than the threshold are silently dropped."""
    now_ms = int(time.time() * 1000)
    raw = _make_event_envelope(now_ms - _STALE_EVENT_THRESHOLD_MS - 10_000)  # well past threshold

    await transport._dispatch_aliyun_event("/sys/testpk/testdn/app/down/thing/events", raw)

    transport.on_device_event.assert_not_called()


@pytest.mark.asyncio
async def test_event_without_time_forwarded(transport: AliyunMQTTTransport):
    """Events with params.time=0 (missing) are not dropped."""
    raw = _make_event_envelope(0)

    await transport._dispatch_aliyun_event("/sys/testpk/testdn/app/down/thing/events", raw)

    transport.on_device_event.assert_called_once()


@pytest.mark.asyncio
async def test_stale_properties_dropped(transport: AliyunMQTTTransport):
    """Stale thing/properties messages are also dropped."""
    now_ms = int(time.time() * 1000)
    payload = {
        "method": "thing.properties",
        "id": "test-props-id",
        "version": "1.0",
        "params": {
            "iotId": "test_iot_id",
            "time": now_ms - _STALE_EVENT_THRESHOLD_MS - 30_000,
            "items": {},
        },
    }
    raw = json.dumps(payload).encode()

    await transport._dispatch_aliyun_event("/sys/testpk/testdn/app/down/thing/properties", raw)

    transport.on_device_properties.assert_not_called()


@pytest.mark.asyncio
async def test_event_at_threshold_boundary_forwarded(transport: AliyunMQTTTransport):
    """Events exactly at the threshold age are forwarded (not strictly greater)."""
    now_ms = int(time.time() * 1000)
    # Subtract threshold minus a small margin to stay within bounds
    raw = _make_event_envelope(now_ms - _STALE_EVENT_THRESHOLD_MS + 1_000)

    await transport._dispatch_aliyun_event("/sys/testpk/testdn/app/down/thing/events", raw)

    transport.on_device_event.assert_called_once()
