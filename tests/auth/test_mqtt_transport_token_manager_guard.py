"""Regression test for H2: MQTTTransport.send() must raise TransportError, not
AssertionError/AttributeError, when ``_token_manager`` is ``None`` and the
HTTP invoke returns 401.

The original code used ``assert self._token_manager is not None`` which:
  * is stripped by ``python -O`` (turning the failure into ``AttributeError``)
  * gives callers an opaque error type that is not a ``TransportError``

The fix replaces the assert with an explicit ``TransportError`` raise, so
this test guards against regressions in either ``-O`` or normal mode.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.http.model.http import UnauthorizedException
from pymammotion.transport.base import TransportError
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig


@pytest.fixture
def config() -> MQTTTransportConfig:
    return MQTTTransportConfig(
        host="mqtt.example.com",
        port=1883,
        client_id="test-client",
        username="user",
        password="jwt-token",
    )


@pytest.fixture
def mammotion_http() -> MagicMock:
    http = MagicMock()
    # First call to mqtt_invoke raises Unauthorized -> exercises the assert path
    http.mqtt_invoke = AsyncMock(side_effect=UnauthorizedException("token expired"))
    return http


@pytest.mark.asyncio
async def test_send_without_token_manager_raises_transport_error(
    config: MQTTTransportConfig, mammotion_http: MagicMock
) -> None:
    """When _token_manager is None and the invoke returns 401, send() must
    raise ``TransportError`` (not ``AssertionError`` or ``AttributeError``).
    """
    transport = MQTTTransport(config, mammotion_http, AsyncMock())
    # Simulate a misconfiguration where the token manager is unset at runtime
    transport._token_manager = None  # type: ignore[assignment]

    with pytest.raises(TransportError) as exc_info:
        await transport.send(b"payload", iot_id="iot-123")

    # Ensure we got a real TransportError (not a stripped-assert AttributeError
    # which would propagate as a different exception class).
    assert not isinstance(exc_info.value, AssertionError)
    assert "token manager" in str(exc_info.value).lower()
