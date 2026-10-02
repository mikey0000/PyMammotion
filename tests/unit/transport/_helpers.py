"""Builders for the transport unit tests.

Plain functions, matching ``tests/unit/_helpers.py``; hand-written fakes live in
``_fakes.py`` next to this file.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport
from tests.unit._helpers import make_aliyun_cloud_gateway
from tests.unit.transport._fakes import FakeMessage


def make_aliyun_config() -> AliyunMQTTConfig:
    """An AliyunMQTTConfig for product key ``pk`` / device ``dn``; the bind_reply topic is ``/sys/pk/dn/...``."""
    return AliyunMQTTConfig(
        host="pk.iot-as-mqtt.cn-shanghai.aliyuncs.com",
        client_id_base="pk&dn",
        username="dn&pk",
        device_name="dn",
        product_key="pk",
        device_secret="secret",
        iot_token="tok",
    )


def make_aliyun_transport(gateway: MagicMock | None = None) -> AliyunMQTTTransport:
    """A real AliyunMQTTTransport over :func:`make_aliyun_config`."""
    return AliyunMQTTTransport(make_aliyun_config(), gateway if gateway is not None else make_aliyun_cloud_gateway())


def make_bind_reply(code: int) -> FakeMessage:
    """An Aliyun ``account/bind_reply`` frame for :func:`make_aliyun_config`'s topic; 200 accepts the bind."""
    payload = {"code": code, "id": "msgid1", "message": "ok" if code == 200 else "check iotToken failed"}
    return FakeMessage("/sys/pk/dn/app/down/account/bind_reply", json.dumps(payload).encode())
