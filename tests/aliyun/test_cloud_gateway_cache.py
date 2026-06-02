"""Round-trip tests for CloudIOTGateway.to_cache / from_cache and session refresh.

These lock in the fix for the silent 401 on the first cloud call after a restore:
``token_issued_at`` was never persisted, so a restored gateway treated an expired
``iotToken`` as freshly issued, skipped ``check_or_refresh_session``'s refresh, and
the first cloud call (e.g. ``list_binding_by_account``) returned 401/460.
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import orjson

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.model.regions_response import RegionResponse, RegionResponseData
from pymammotion.aliyun.model.session_by_authcode_response import (
    SessionByAuthCodeResponse,
    SessionOauthToken,
)


def _session(issued_in_past: int = 0, iot_token_expire: int = 86_400) -> SessionByAuthCodeResponse:
    """Build a session response.  token_issued_at is intentionally left None (as the
    server returns it) — the gateway tracks the real issued-at in memory."""
    return SessionByAuthCodeResponse(
        code=200,
        data=SessionOauthToken(
            identityId="identity-1",
            refreshTokenExpire=2_592_000,
            iotToken="iot-token",
            iotTokenExpire=iot_token_expire,
            refreshToken="refresh-token",
        ),
    )


def _region() -> RegionResponse:
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


def test_to_cache_stamps_token_issued_at() -> None:
    """to_cache() must copy the in-memory issued-at into the serializable session."""
    gateway = CloudIOTGateway(mammotion_http=MagicMock(), session_by_authcode_response=_session())
    issued = int(time.time()) - 100_000
    gateway._iot_token_issued_at = issued  # noqa: SLF001

    raw = gateway.to_cache()

    assert raw["session_data"].token_issued_at == issued


def test_cache_round_trip_preserves_token_issued_at() -> None:
    """A to_cache() → JSON → reconstruct round-trip must restore the true issued-at.

    Regression: without the stamp, the reconstructed gateway seeds
    ``_iot_token_issued_at`` to "now", masking an expired token.
    """
    issued = int(time.time()) - 100_000  # well in the past

    saver = CloudIOTGateway(mammotion_http=MagicMock(), session_by_authcode_response=_session())
    saver._iot_token_issued_at = issued  # noqa: SLF001
    raw = saver.to_cache()

    # mimic persistence: session model → JSON dict → model
    restored_session = SessionByAuthCodeResponse.from_dict(orjson.loads(raw["session_data"].to_json()))
    restored = CloudIOTGateway(mammotion_http=MagicMock(), session_by_authcode_response=restored_session)

    assert restored._iot_token_issued_at == issued  # noqa: SLF001 — NOT int(time.time())


async def test_check_or_refresh_session_refreshes_expired_cached_token() -> None:
    """A restored gateway whose iotToken has expired must hit the refresh endpoint."""
    # Issued long ago with a 1-day lifetime → expired now (and within the 1h skew window).
    session = _session(iot_token_expire=86_400)
    gateway = CloudIOTGateway(
        mammotion_http=MagicMock(),
        session_by_authcode_response=session,
        region_response=_region(),
    )
    gateway._iot_token_issued_at = int(time.time()) - 100_000  # noqa: SLF001 — expired

    fresh_session = {
        "code": 200,
        "data": {
            "identityId": "identity-1",
            "refreshTokenExpire": 2_592_000,
            "iotToken": "new-iot-token",
            "iotTokenExpire": 86_400,
            "refreshToken": "new-refresh-token",
        },
    }
    mock_response = MagicMock()
    mock_response.body = orjson.dumps(fresh_session)
    mock_client = MagicMock()
    mock_client.async_do_request = AsyncMock(return_value=mock_response)

    with patch("pymammotion.aliyun.cloud_gateway.Client", return_value=mock_client):
        await gateway.check_or_refresh_session()

    mock_client.async_do_request.assert_awaited_once()
    assert gateway._session_by_authcode_response.data.iotToken == "new-iot-token"  # noqa: SLF001


def test_none_token_issued_at_seeds_epoch_not_now() -> None:
    """A session with an unknown (None) issued-at must seed the epoch, forcing a refresh.

    Belt-and-suspenders for caches written before issued-at was persisted: those
    restore with token_issued_at=None and must not be trusted as freshly issued.
    """
    gateway = CloudIOTGateway(mammotion_http=MagicMock(), session_by_authcode_response=_session())
    assert gateway._session_by_authcode_response.token_issued_at is None  # noqa: SLF001
    assert gateway._iot_token_issued_at == 0  # noqa: SLF001 — NOT int(time.time())


async def test_restore_with_none_issued_at_triggers_refresh() -> None:
    """A restored gateway with an unknown issued-at must hit the refresh endpoint."""
    gateway = CloudIOTGateway(
        mammotion_http=MagicMock(),
        session_by_authcode_response=_session(),  # token_issued_at is None
        region_response=_region(),
    )

    fresh_session = {
        "code": 200,
        "data": {
            "identityId": "identity-1",
            "refreshTokenExpire": 2_592_000,
            "iotToken": "new-iot-token",
            "iotTokenExpire": 86_400,
            "refreshToken": "new-refresh-token",
        },
    }
    mock_response = MagicMock()
    mock_response.body = orjson.dumps(fresh_session)
    mock_client = MagicMock()
    mock_client.async_do_request = AsyncMock(return_value=mock_response)

    with patch("pymammotion.aliyun.cloud_gateway.Client", return_value=mock_client):
        await gateway.check_or_refresh_session()

    mock_client.async_do_request.assert_awaited_once()
    assert gateway._session_by_authcode_response.data.iotToken == "new-iot-token"  # noqa: SLF001


async def test_check_or_refresh_session_skips_when_token_fresh() -> None:
    """A genuinely fresh token must NOT trigger a network refresh."""
    gateway = CloudIOTGateway(
        mammotion_http=MagicMock(),
        session_by_authcode_response=_session(iot_token_expire=86_400),
        region_response=_region(),
    )
    gateway._iot_token_issued_at = int(time.time())  # noqa: SLF001 — just issued

    with patch("pymammotion.aliyun.cloud_gateway.Client") as mock_client_cls:
        await gateway.check_or_refresh_session()

    mock_client_cls.assert_not_called()
