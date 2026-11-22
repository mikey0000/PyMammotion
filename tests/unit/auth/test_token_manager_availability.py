"""The transport-scoped availability edges TokenManager reports to its client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.auth.token_manager import TokenManager
from pymammotion.transport.base import ReLoginRequiredError, TransportType
from tests._helpers import let_others_run
from tests.unit.auth._helpers import encode_jwt, make_aliyun_gateway, make_http_mock


async def test_a_transport_given_up_twice_is_reported_once() -> None:
    tm = TokenManager("user@example.com", make_http_mock())
    changed = AsyncMock()
    tm.on_transport_availability_changed = changed

    tm.mark_transport_unavailable(TransportType.CLOUD_MAMMOTION, "first")
    tm.mark_transport_unavailable(TransportType.CLOUD_MAMMOTION, "second")
    await let_others_run()

    changed.assert_awaited_once_with(TransportType.CLOUD_MAMMOTION, "first")
    assert tm.unavailable_transports == {TransportType.CLOUD_MAMMOTION: "first"}


async def test_a_successful_retry_clears_the_give_up_and_reports_the_recovery() -> None:
    http = make_http_mock(mqtt_jwt=encode_jwt(exp=9_999_999_999), login_info=MagicMock())
    tm = TokenManager("user@example.com", http)
    tm.mark_transport_unavailable(TransportType.CLOUD_MAMMOTION, "gone")
    changed = AsyncMock()
    tm.on_transport_availability_changed = changed

    await tm.retry_mqtt_credentials()
    await let_others_run()

    changed.assert_awaited_once_with(TransportType.CLOUD_MAMMOTION, None)
    assert tm.unavailable_transports == {}


async def test_a_failed_retry_keeps_the_give_up_and_reports_nothing() -> None:
    http = make_http_mock(refresh_code=0, login_info=MagicMock())
    http.get_mqtt_credentials.return_value = MagicMock(data=None)
    tm = TokenManager("user@example.com", http)
    tm.mark_transport_unavailable(TransportType.CLOUD_MAMMOTION, "gone")
    changed = AsyncMock()
    tm.on_transport_availability_changed = changed

    with pytest.raises(ReLoginRequiredError):
        await tm.retry_mqtt_credentials()
    await let_others_run()

    changed.assert_not_awaited()
    assert tm.unavailable_transports == {TransportType.CLOUD_MAMMOTION: "gone"}


async def test_a_given_up_aliyun_session_is_reported_and_a_successful_reestablish_clears_it() -> None:
    http = make_http_mock(login_info=MagicMock())
    tm = TokenManager("user@example.com", http)
    tm.mark_transport_unavailable(TransportType.CLOUD_ALIYUN, "refused")
    changed = AsyncMock()
    tm.on_transport_availability_changed = changed
    gateway = make_aliyun_gateway(region_response=MagicMock())

    assert await tm.reestablish_aliyun(gateway) is gateway
    await let_others_run()

    changed.assert_awaited_once_with(TransportType.CLOUD_ALIYUN, None)
    assert tm.unavailable_transports == {}
