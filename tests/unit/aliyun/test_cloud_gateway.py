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
import pytest

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.exceptions import TooManyRequestsException
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


# ===========================================================================
# Rate-limiting circuit breaker — send_cloud_command on HTTP 429
# ===========================================================================

_DUMMY_COMMAND = b"\x00\x01"
_DUMMY_IOT_ID = "test-iot-id"


def _make_gateway() -> CloudIOTGateway:
    """Return a CloudIOTGateway with all external dependencies mocked out."""
    http = MagicMock()

    # Minimal session data so token-expiry checks pass without network calls.
    session_data = MagicMock()
    session_data.iotTokenExpire = 999_999_999
    session_data.refreshTokenExpire = 999_999_999
    session_data.iotToken = "fake-iot-token"

    session_resp = MagicMock()
    session_resp.data = session_data

    region_data = MagicMock()
    region_data.apiGatewayEndpoint = "https://api.example.com"

    region_resp = MagicMock()
    region_resp.data = region_data

    gw = CloudIOTGateway.__new__(CloudIOTGateway)
    # Populate only the fields accessed by send_cloud_command.
    gw.mammotion_http = http
    gw._app_key = "app_key"
    gw._app_secret = "app_secret"
    gw.domain = "iot-api.cn-shanghai.aliyuncs.com"
    gw.message_delay = 1
    gw._rate_limited_until = 0.0
    gw._rate_limit_backoff = 60.0
    gw._session_by_authcode_response = session_resp
    gw._region_response = region_resp
    # Set issued_at to now so that (issued_at + expire=999_999_999) >> (now + 3600),
    # keeping the token-expiry branch False and avoiding network calls.
    gw._iot_token_issued_at = int(time.time())
    return gw


def _make_response(status_code: int, body: bytes = b'{"code":200}') -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.body = body
    resp.status_message = "Too Many Requests" if status_code == 429 else "OK"
    resp.headers = {}
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_429_raises_too_many_requests_exception() -> None:
    """A 429 response raises TooManyRequestsException immediately."""
    gw = _make_gateway()

    with patch("pymammotion.aliyun.cloud_gateway.Client") as MockClient:
        mock_client = MockClient.return_value
        mock_client.async_do_request = AsyncMock(return_value=_make_response(429))

        with pytest.raises(TooManyRequestsException):
            await gw.send_cloud_command(_DUMMY_IOT_ID, _DUMMY_COMMAND)


@pytest.mark.asyncio
async def test_429_arms_circuit_breaker_for_60_seconds() -> None:
    """After a 429 the circuit breaker blocks all sends for 60 s."""
    gw = _make_gateway()

    frozen_now = 1_000.0

    with patch("pymammotion.aliyun.cloud_gateway.Client") as MockClient:
        mock_client = MockClient.return_value
        mock_client.async_do_request = AsyncMock(return_value=_make_response(429))

        with patch("pymammotion.aliyun.cloud_gateway.time") as mock_time:
            mock_time.monotonic.return_value = frozen_now
            mock_time.time.return_value = 999_999  # keep token-expiry logic happy

            with pytest.raises(TooManyRequestsException):
                await gw.send_cloud_command(_DUMMY_IOT_ID, _DUMMY_COMMAND)

        # Circuit breaker should now block until frozen_now + 60
        assert gw._rate_limited_until == pytest.approx(frozen_now + 60.0)


@pytest.mark.asyncio
async def test_circuit_breaker_rejects_without_network_call() -> None:
    """While the window is active, no HTTP request is made."""
    gw = _make_gateway()
    # Arm the breaker manually — window expires far in the future.
    gw._rate_limited_until = time.monotonic() + 3_600.0

    with patch("pymammotion.aliyun.cloud_gateway.Client") as MockClient:
        mock_client = MockClient.return_value
        mock_client.async_do_request = AsyncMock()

        with pytest.raises(TooManyRequestsException):
            await gw.send_cloud_command(_DUMMY_IOT_ID, _DUMMY_COMMAND)

        mock_client.async_do_request.assert_not_called()


@pytest.mark.asyncio
async def test_backoff_doubles_on_successive_429s() -> None:
    """Each 429 doubles the backoff: 60 s → 120 s → 240 s."""
    gw = _make_gateway()

    call_count = 0
    base_now = 1_000.0

    with patch("pymammotion.aliyun.cloud_gateway.Client") as MockClient:
        mock_client = MockClient.return_value
        mock_client.async_do_request = AsyncMock(return_value=_make_response(429))

        for expected_backoff in (60.0, 120.0, 240.0):
            # Advance mock time past the previous window so the gate opens.
            current_now = base_now + call_count * 10_000  # well past any window
            call_count += 1

            with patch("pymammotion.aliyun.cloud_gateway.time") as mock_time:
                mock_time.monotonic.return_value = current_now
                mock_time.time.return_value = 999_999

                # Reset window to simulate the window having expired.
                gw._rate_limited_until = 0.0

                with pytest.raises(TooManyRequestsException):
                    await gw.send_cloud_command(_DUMMY_IOT_ID, _DUMMY_COMMAND)

            assert gw._rate_limited_until == pytest.approx(current_now + expected_backoff), (
                f"Expected backoff {expected_backoff} s, "
                f"got {gw._rate_limited_until - current_now} s"
            )


@pytest.mark.asyncio
async def test_success_resets_circuit_breaker() -> None:
    """A successful response resets both the window and the backoff counter."""
    gw = _make_gateway()
    # Simulate a previously-tripped breaker with elevated backoff.
    gw._rate_limited_until = 0.0  # window expired
    gw._rate_limit_backoff = 240.0

    success_body = b'{"code":200,"data":{"messageId":"msg-1"}}'

    with patch("pymammotion.aliyun.cloud_gateway.Client") as MockClient:
        mock_client = MockClient.return_value
        mock_client.async_do_request = AsyncMock(return_value=_make_response(200, success_body))

        with patch("pymammotion.aliyun.cloud_gateway.time") as mock_time:
            mock_time.monotonic.return_value = 1_000.0
            mock_time.time.return_value = 999_999

            await gw.send_cloud_command(_DUMMY_IOT_ID, _DUMMY_COMMAND)

    assert gw._rate_limited_until == 0.0, "window should be cleared"
    assert gw._rate_limit_backoff == 60.0, "backoff should reset to 60 s"


@pytest.mark.asyncio
async def test_window_expires_and_request_goes_through() -> None:
    """After the window expires the next call is forwarded to the network."""
    gw = _make_gateway()
    success_body = b'{"code":200,"data":{"messageId":"msg-ok"}}'

    with patch("pymammotion.aliyun.cloud_gateway.Client") as MockClient:
        mock_client = MockClient.return_value

        # First call → 429
        mock_client.async_do_request = AsyncMock(return_value=_make_response(429))
        frozen_now = 5_000.0
        with patch("pymammotion.aliyun.cloud_gateway.time") as mock_time:
            mock_time.monotonic.return_value = frozen_now
            mock_time.time.return_value = 999_999

            with pytest.raises(TooManyRequestsException):
                await gw.send_cloud_command(_DUMMY_IOT_ID, _DUMMY_COMMAND)

        # Window is now: frozen_now + 60 = 5060.
        assert gw._rate_limited_until == pytest.approx(5_060.0)

        # Second call before the window expires → rejected without network call.
        mock_client.async_do_request.reset_mock()
        with patch("pymammotion.aliyun.cloud_gateway.time") as mock_time:
            mock_time.monotonic.return_value = frozen_now + 30.0  # still within window
            mock_time.time.return_value = 999_999

            with pytest.raises(TooManyRequestsException):
                await gw.send_cloud_command(_DUMMY_IOT_ID, _DUMMY_COMMAND)

        mock_client.async_do_request.assert_not_called()

        # Third call after the window expires → goes through.
        mock_client.async_do_request = AsyncMock(return_value=_make_response(200, success_body))
        with patch("pymammotion.aliyun.cloud_gateway.time") as mock_time:
            mock_time.monotonic.return_value = frozen_now + 61.0  # past the window
            mock_time.time.return_value = 999_999

            msg_id = await gw.send_cloud_command(_DUMMY_IOT_ID, _DUMMY_COMMAND)

        assert msg_id  # a message ID was returned
        assert gw._rate_limited_until == 0.0  # breaker reset
        assert gw._rate_limit_backoff == 60.0
