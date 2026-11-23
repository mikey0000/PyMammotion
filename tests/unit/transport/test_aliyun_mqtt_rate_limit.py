"""AliyunMQTTTransport when its credential refresh is throttled.

A ``RateLimitedError`` is neither a refusal nor a network blip: the transport backs off
and reconnects on its usual backoff, and is never given up over it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from pymammotion.http.model.http import RateLimitedError
from pymammotion.transport.aliyun_mqtt import AliyunMQTTTransport
from tests._helpers import wait_until
from tests.unit._helpers import make_aliyun_cloud_gateway
from tests.unit.transport._fakes import FakeMQTTClient
from tests.unit.transport._helpers import make_aliyun_config, make_bind_reply


@pytest.mark.regression
async def test_bind_reply_2043_callback_raising_a_rate_limit_backs_off_and_reconnects() -> None:
    """A throttled credential refresh was read as a refusal and gave the Aliyun transport up for good."""
    transport = AliyunMQTTTransport(make_aliyun_config(), make_aliyun_cloud_gateway())
    transport.on_auth_failure = AsyncMock(side_effect=RateLimitedError("oauth2/token", 3600.0))
    clients = [
        FakeMQTTClient(messages=[make_bind_reply(2043)]),
        FakeMQTTClient(messages=[make_bind_reply(200)]),
    ]

    with (
        patch("pymammotion.transport.aliyun_mqtt.MQTT_RECONNECT_MIN_SEC", 0),
        patch("aiomqtt.Client", side_effect=clients),
    ):
        await transport.connect()
        await wait_until(lambda: transport.is_connected, message="the transport never reconnected after the throttle")
        await transport.disconnect()

    transport.on_auth_failure.assert_awaited_once()
    assert transport.is_usable
