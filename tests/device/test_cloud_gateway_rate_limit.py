"""Tests for CloudIOTGateway rate-limiting circuit breaker.

Verifies that when send_cloud_command receives an HTTP 429 response:

1. TooManyRequestsException is raised immediately.
2. All subsequent calls are rejected (without touching the network) until the
   backoff window expires (starting at 60 s).
3. The backoff doubles on each consecutive 429 (60 s → 120 s → 240 s …).
4. A successful response resets both the window and the backoff counter.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.exceptions import TooManyRequestsException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
