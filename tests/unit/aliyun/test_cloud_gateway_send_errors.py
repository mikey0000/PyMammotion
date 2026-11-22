"""How CloudIOTGateway.send_cloud_command classifies a refused invoke and a dead session.

The caller's recovery depends on the type: a session error earns a credential refresh,
a gateway timeout a retry, and anything else is reported as a failed request.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import orjson
import pytest

from pymammotion.aliyun.exceptions import AuthRefreshException, FailedRequestException, GatewayTimeoutException
from pymammotion.transport.base import SessionExpiredError, TransportType
from tests.unit.aliyun._helpers import make_gateway, make_session

_IOT_ID = "iot-1"
_COMMAND = b"\x00\x01"


def _invoke_answering(code: int) -> MagicMock:
    response = MagicMock(status_code=200, headers={})
    response.body = orjson.dumps({"code": code, "message": "refused"})
    client = MagicMock()
    client.async_do_request = AsyncMock(return_value=response)
    return client


@pytest.mark.parametrize("code", [29003, 460])
async def test_a_rejected_session_asks_for_an_aliyun_refresh(code: int) -> None:
    gateway = make_gateway(make_session(iot_token_expire=999_999_999))

    with (
        patch("pymammotion.aliyun.cloud_gateway.Client", return_value=_invoke_answering(code)),
        pytest.raises(SessionExpiredError) as excinfo,
    ):
        await gateway.send_cloud_command(_IOT_ID, _COMMAND)

    assert excinfo.value.transport_type is TransportType.CLOUD_ALIYUN


@pytest.mark.parametrize(("code", "expected"), [(20056, GatewayTimeoutException), (22000, FailedRequestException)])
async def test_a_refused_invoke_names_why_it_failed(code: int, expected: type[Exception]) -> None:
    gateway = make_gateway(make_session(iot_token_expire=999_999_999))

    with (
        patch("pymammotion.aliyun.cloud_gateway.Client", return_value=_invoke_answering(code)),
        pytest.raises(expected),
    ):
        await gateway.send_cloud_command(_IOT_ID, _COMMAND)


async def test_a_session_past_its_refresh_token_is_not_sent() -> None:
    """Neither the iotToken nor its refresh token can be renewed, so no invoke goes out."""
    gateway = make_gateway(make_session(iot_token_expire=60, refresh_token_expire=120))
    gateway._iot_token_issued_at = int(time.time()) - 3600  # noqa: SLF001
    client = _invoke_answering(200)

    with (
        patch("pymammotion.aliyun.cloud_gateway.Client", return_value=client),
        pytest.raises(AuthRefreshException),
    ):
        await gateway.send_cloud_command(_IOT_ID, _COMMAND)

    client.async_do_request.assert_not_awaited()
