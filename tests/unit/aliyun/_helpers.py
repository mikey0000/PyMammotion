"""Shared builders for the Aliyun gateway tests.

The gateway is always built via the REAL constructor so tests exercise the
production seeding (``_iot_token_issued_at`` from ``session.token_issued_at``,
epoch fallback, refresh lock, rate-limit state) instead of hand-maintained
``__new__`` field lists that rot as the constructor evolves.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.model.regions_response import RegionResponse, RegionResponseData
from pymammotion.aliyun.model.session_by_authcode_response import (
    SessionByAuthCodeResponse,
    SessionOauthToken,
)

__all__ = ["make_gateway", "make_region", "make_session"]


def make_session(
    iot_token: str = "iot-token",
    iot_token_expire: int = 86_400,
    *,
    refresh_token: str = "refresh-token",
    refresh_token_expire: int = 2_592_000,
) -> SessionByAuthCodeResponse:
    """Build a session response.  token_issued_at is intentionally left None (as the
    server returns it) — the gateway tracks the real issued-at in memory."""
    return SessionByAuthCodeResponse(
        code=200,
        data=SessionOauthToken(
            identityId="identity-1",
            refreshTokenExpire=refresh_token_expire,
            iotToken=iot_token,
            iotTokenExpire=iot_token_expire,
            refreshToken=refresh_token,
        ),
    )


def make_region() -> RegionResponse:
    return RegionResponse(
        code=200,
        data=RegionResponseData(
            shortRegionId="EU",
            oaApiGatewayEndpoint="oa.example.com",
            regionId="EU",
            mqttEndpoint="mqtt.example.com:1883",
            pushChannelEndpoint="push.example.com",
            regionEnglishName="Europe",
            apiGatewayEndpoint="api.example.com",
        ),
    )


def make_gateway(
    session: SessionByAuthCodeResponse | None = None,
    *,
    age: int = 0,
    region: RegionResponse | None = None,
) -> CloudIOTGateway:
    """A real-constructor gateway carrying *session*, issued *age* seconds ago.

    ``_iot_token_issued_at`` is the one private poke: the constructor seeds it
    from ``session.token_issued_at`` (None → epoch), never from "now", so tests
    that need a token of a known age must stamp it after construction.
    """
    gw = CloudIOTGateway(
        mammotion_http=MagicMock(),
        session_by_authcode_response=session if session is not None else make_session(),
        region_response=region if region is not None else make_region(),
    )
    gw._iot_token_issued_at = int(time.time()) - age  # noqa: SLF001
    return gw
