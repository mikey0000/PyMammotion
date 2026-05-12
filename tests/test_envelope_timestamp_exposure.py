"""Tests that params.time from Aliyun thing-event envelope is accessible on DeviceHandle.

Issue #130: `params.time` (Unix ms) reliably reflects the cloud-side generation time and
survives buffering, unlike `LubaMsg.timestamp` which carries firmware-internal counters.
This test ensures subscribers can detect and handle delayed message delivery.
"""
from __future__ import annotations

import base64

import pytest

from pymammotion.data.model.device import MowingDevice
from pymammotion.data.mqtt.event import ThingEventMessage
from pymammotion.device.handle import DeviceHandle
from pymammotion.proto import LubaMsg, RptDevStatus, ReportInfoData, RptInfoType


@pytest.fixture
def handle():
    """DeviceHandle with no transports."""
    device = MowingDevice()
    device.device_name = "test_yuka"
    return DeviceHandle(
        device_id="test_device_id",
        device_name="test_yuka",
        initial_device=device,
        iot_id="test_iot_id",
    )


def _make_event_with_time(envelope_time_ms: int) -> ThingEventMessage:
    """Build a ThingEventMessage with a protobuf payload and params.time set."""
    # Use a minimal valid LubaMsg serialized payload (hard-coded known-good bytes)
    # This is a toapp_report_data message with dev.sys_status=5, battery_val=75
    sample_bytes = b'\x08\xf4\x01\x10\x01\x18\x07(\x010\x01R\x08\xba\x02\x05\x12\x03\x08\x05\x10K'
    encoded = base64.b64encode(sample_bytes).decode("ascii")

    payload = {
        "method": "thing.events",
        "id": "test-event-id",
        "version": "1.0",
        "params": {
            "identifier": "device_protobuf_msg_event",
            "type": "info",
            "time": envelope_time_ms,
            "iotId": "test_iot_id",
            "productKey": "test_product",
            "deviceName": "test_yuka",
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

    return ThingEventMessage.from_dicts(payload)


async def test_envelope_time_accessible_after_event(handle: DeviceHandle):
    """After on_device_event, handle.last_mqtt_envelope_time_ms holds params.time."""
    event = _make_event_with_time(envelope_time_ms=1714567890123)

    await handle.on_device_event(event)

    # The envelope timestamp should now be accessible
    assert handle.last_mqtt_envelope_time_ms == 1714567890123


async def test_envelope_time_zero_when_no_event_processed(handle: DeviceHandle):
    """Before any event is processed, last_mqtt_envelope_time_ms is 0."""
    assert handle.last_mqtt_envelope_time_ms == 0


async def test_envelope_time_updated_on_each_event(handle: DeviceHandle):
    """Successive events update the timestamp."""
    event1 = _make_event_with_time(envelope_time_ms=1000000000000)
    await handle.on_device_event(event1)
    assert handle.last_mqtt_envelope_time_ms == 1000000000000

    event2 = _make_event_with_time(envelope_time_ms=1000000005000)
    await handle.on_device_event(event2)
    assert handle.last_mqtt_envelope_time_ms == 1000000005000


async def test_envelope_time_with_zero_value(handle: DeviceHandle):
    """When params.time is 0, the attribute is set to 0."""
    # First set it to a non-zero value
    event1 = _make_event_with_time(envelope_time_ms=1000000000000)
    await handle.on_device_event(event1)
    assert handle.last_mqtt_envelope_time_ms == 1000000000000

    # Then send an event with time=0
    event2 = _make_event_with_time(envelope_time_ms=0)
    await handle.on_device_event(event2)

    # Should be updated to 0
    assert handle.last_mqtt_envelope_time_ms == 0
