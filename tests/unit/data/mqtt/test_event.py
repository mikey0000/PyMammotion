"""Thing-event payload models: the parsed device times they expose."""

from __future__ import annotations

from datetime import UTC, datetime

from pymammotion.data.mqtt.event import DeviceNotificationEventCode


def test_notification_local_time_parses_the_milliseconds_the_cloud_sends() -> None:
    event = DeviceNotificationEventCode.from_json('{"localTime":1725159492000,"code":"1002"}')
    assert event.local_time == datetime(2024, 9, 1, 2, 58, 12, tzinfo=UTC)


def test_notification_local_time_is_none_when_the_device_sends_zero() -> None:
    assert DeviceNotificationEventCode(localTime=0, code="1002").local_time is None
