"""How CloudIOTGateway.check_or_refresh_session classifies a refused refresh.

Only a rejected IoT refresh token means the session must be rebuilt; a server fault
is transient and any other refusal is a verdict that a rebuild would not change.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import orjson
import pytest

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.exceptions import CloudSetupError
from pymammotion.transport.base import SessionExpiredError
from tests.unit.aliyun._helpers import make_region, make_session


async def _refresh_answering(code: int) -> None:
    gateway = CloudIOTGateway(
        mammotion_http=MagicMock(), session_by_authcode_response=make_session(), region_response=make_region()
    )
    mock_response = MagicMock()
    mock_response.body = orjson.dumps({"code": code, "message": "refused", "id": "req"})
    mock_client = MagicMock()
    mock_client.async_do_request = AsyncMock(return_value=mock_response)
    with patch("pymammotion.aliyun.cloud_gateway.Client", return_value=mock_client):
        await gateway.check_or_refresh_session(force=True)


@pytest.mark.parametrize("code", [2401, 2460])
async def test_check_or_refresh_session_treats_a_rejected_refresh_token_as_an_expired_session(code: int) -> None:
    with pytest.raises(SessionExpiredError):
        await _refresh_answering(code)


@pytest.mark.regression
@pytest.mark.parametrize(("code", "expected"), [(503, ConnectionError), (2064, CloudSetupError)])
async def test_check_or_refresh_session_does_not_read_every_failure_as_an_expired_session(
    code: int, expected: type[Exception]
) -> None:
    """Every non-200 meant "session expired", so a server fault cost a full rebuild with a fresh authorization code."""
    with pytest.raises(expected) as excinfo:
        await _refresh_answering(code)

    assert not isinstance(excinfo.value, SessionExpiredError)
