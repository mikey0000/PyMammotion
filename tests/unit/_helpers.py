"""Mock factories used only by the unit tier.

Plain functions, not fixtures — matching tests/unit/transport/_fakes.py and
tests/unit/messaging/_helpers.py.  Builders the integration tier also needs live
in tests/_helpers.py; keep one superset builder per concept, so the per-file
variants can't drift apart (the exact failure mode _fakes.py's docstring warns
about).
"""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager
import struct
import time
import zlib
from unittest.mock import AsyncMock, MagicMock

from pymammotion.account.registry import AccountSession
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.auth.token_manager import TokenManager
from pymammotion.client import MammotionClient
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import JWTTokenInfo
from pymammotion.transport.aliyun_mqtt import AliyunMQTTTransport
from tests._helpers import make_bare_client


def make_http_posting(
    status: int,
    body: dict,
    content_type: str = "application/json",
) -> tuple[MammotionHTTP, MagicMock]:
    """A MammotionHTTP whose ``_client_session`` requests return a canned response.

    Returns the session too, so callers can assert on url/json/headers.  The
    far-future ``expires_in`` keeps ``refresh_token_decorator`` from rotating.
    """
    http = MammotionHTTP()
    http.login_info = MagicMock(access_token="tok")  # type: ignore[assignment]
    http.expires_in = time.time() + 3600
    http.jwt_info = JWTTokenInfo(iot="https://iot.example", robot="https://robot.example")
    resp = MagicMock(status=status, headers={"Content-Type": content_type})
    resp.json = AsyncMock(return_value=body)
    session = MagicMock()
    # Every verb device-server uses (the product list is a GET, the error-code
    # endpoints are POSTs, map backups add PUT and DELETE); an unmocked one returns
    # a non-awaitable MagicMock.
    session.post = AsyncMock(return_value=resp)
    session.get = AsyncMock(return_value=resp)
    session.put = AsyncMock(return_value=resp)
    session.delete = AsyncMock(return_value=resp)

    @asynccontextmanager
    async def _fake_session() -> object:  # type: ignore[misc]
        yield session

    http._client_session = _fake_session  # type: ignore[method-assign]
    return http, session


def _agora_string(value: str) -> bytes:
    raw = value.encode()
    return struct.pack("<H", len(raw)) + raw


def make_agora_token(
    *,
    app_id: str = "app",
    channel: str = "chan",
    uid: str = "42",
    issued_at: int = 1_700_000_000,
    leading_services: tuple[bytes, ...] = (),
) -> str:
    """Pack an AccessToken2 the way Agora's builder does (little-endian, length-prefixed strings).

    ``leading_services`` are pre-packed service blocks placed before the RTC one; use
    ``agora_service`` to build them.
    """
    rtc = agora_service(1, {1: 3600, 2: 3600}, channel, uid)
    services = struct.pack("<H", len(leading_services) + 1) + b"".join(leading_services) + rtc
    content = _agora_string("sig-bytes") + _agora_string(app_id) + struct.pack("<III", issued_at, 3600, 12345) + services
    return "007" + base64.b64encode(zlib.compress(content)).decode()


def agora_service(service_type: int, privileges: dict[int, int], *strings: str) -> bytes:
    """One AccessToken2 service block: type, privilege map, then the service's own strings."""
    block = struct.pack("<H", service_type) + struct.pack("<H", len(privileges))
    for key, value in privileges.items():
        block += struct.pack("<H", key) + struct.pack("<I", value)
    return block + b"".join(_agora_string(text) for text in strings)


def make_aliyun_cloud_gateway(iot_token: str = "initial-tok") -> MagicMock:
    """A CloudIOTGateway with the login responses ``_setup_aliyun_transport`` reads and a succeeding cloud send."""
    gateway = MagicMock(spec=CloudIOTGateway)
    gateway.send_cloud_command = AsyncMock()
    gateway.client_id = "client-id-base"
    gateway.aep_response.data.productKey = "pk"
    gateway.aep_response.data.deviceName = "dn"
    gateway.aep_response.data.deviceSecret = "secret"
    gateway.region_response.data.regionId = "cn-shanghai"
    gateway.session_by_authcode_response.data.iotToken = iot_token
    return gateway


def make_aliyun_session(
    iot_token: str = "initial-tok", account_id: str = "test@example.com"
) -> tuple[MammotionClient, AccountSession, AliyunMQTTTransport]:
    """Return ``(client, session, transport)`` with the transport wired by the client's own ``_setup_aliyun_transport``."""
    session = AccountSession(account_id=account_id, email=account_id, password="secret")
    session.mammotion_http = AsyncMock(spec=MammotionHTTP)
    session.token_manager = AsyncMock(spec=TokenManager)
    client = make_bare_client(session)
    transport = client._setup_aliyun_transport(make_aliyun_cloud_gateway(iot_token), session)
    session.aliyun_transport = transport
    return client, session, transport
