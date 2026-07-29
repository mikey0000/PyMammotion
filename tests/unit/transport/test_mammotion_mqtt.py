"""Tests for MQTTTransport."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.data.mqtt.properties import ThingPropertiesMessage
from pymammotion.transport.base import TransportError, TransportType
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig
from tests.unit.transport._fakes import (
    FakeMessage as _FakeMessage,
    FakeMQTTClient as _FakeMQTTClient,
    NetworkErrorClient as _NetworkErrorClient,
)


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
    http.mqtt_invoke = AsyncMock(return_value=MagicMock(code=0))
    return http


@pytest.fixture
def transport(config: MQTTTransportConfig, mammotion_http: MagicMock) -> MQTTTransport:
    return MQTTTransport(config, mammotion_http, AsyncMock())


# ---------------------------------------------------------------------------
# transport_type
# ---------------------------------------------------------------------------


def test_transport_type(transport: MQTTTransport) -> None:
    assert transport.transport_type is TransportType.CLOUD_MAMMOTION


# ---------------------------------------------------------------------------
# is_connected initial state
# ---------------------------------------------------------------------------


def test_is_connected_initially_false(transport: MQTTTransport) -> None:
    assert transport.is_connected is False


# ---------------------------------------------------------------------------
# update_credentials — full credential rotation
# ---------------------------------------------------------------------------


def test_update_credentials_rotates_client_id_username_and_jwt(transport: MQTTTransport) -> None:
    """A re-login can mint a new client_id/username bound to the new JWT, so all
    of host/client_id/username/password must be applied together — swapping only
    the password leaves a stale client_id/username the broker rejects.
    """
    from pymammotion.auth.token_manager import MQTTCredentials

    transport.update_credentials(
        MQTTCredentials(
            host="mqtts://broker.new.example:8883",
            client_id="rotated-client",
            username="rotated-user",
            jwt="rotated-jwt",
            expires_at=0.0,
        )
    )
    cfg = transport._config
    assert cfg.client_id == "rotated-client"
    assert cfg.username == "rotated-user"
    assert cfg.password == "rotated-jwt"
    assert cfg.host == "broker.new.example"
    assert cfg.port == 8883
    assert cfg.use_ssl is True
    assert transport._tls_context is not None


def test_update_credentials_plain_host_defaults_to_plaintext_port(transport: MQTTTransport) -> None:
    """A bare hostname (no scheme) must default to the plaintext MQTT port."""
    from pymammotion.auth.token_manager import MQTTCredentials

    transport.update_credentials(
        MQTTCredentials(host="plain.broker", client_id="c", username="u", jwt="j", expires_at=0.0)
    )
    cfg = transport._config
    assert cfg.host == "plain.broker"
    assert cfg.port == 1883
    assert cfg.use_ssl is False


@pytest.mark.asyncio
async def test_refresh_credentials_applies_full_rotated_set(
    config: MQTTTransportConfig, mammotion_http: MagicMock
) -> None:
    """_refresh_credentials must apply the full rotated set (not just the JWT)."""
    from pymammotion.auth.token_manager import MQTTCredentials

    async def _refresher(force: bool) -> MQTTCredentials:  # noqa: ARG001
        return MQTTCredentials(host="newhost", client_id="newcid", username="newuser", jwt="newjwt", expires_at=0.0)

    transport = MQTTTransport(config, mammotion_http, AsyncMock(), creds_refresher=_refresher)
    await transport._refresh_credentials(force=True)
    cfg = transport._config
    assert (cfg.client_id, cfg.username, cfg.password) == ("newcid", "newuser", "newjwt")


# ---------------------------------------------------------------------------
# connect() / disconnect() — mock the aiomqtt.Client context manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_sets_is_connected(config: MQTTTransportConfig, mammotion_http: MagicMock) -> None:
    """connect() should set is_connected to True once the MQTT loop starts."""
    transport = MQTTTransport(config, mammotion_http, AsyncMock())
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)
        assert transport.is_connected is True
        await transport.disconnect()


@pytest.mark.asyncio
async def test_disconnect_sets_is_connected_false(config: MQTTTransportConfig, mammotion_http: MagicMock) -> None:
    """disconnect() should set is_connected to False."""
    transport = MQTTTransport(config, mammotion_http, AsyncMock())
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.05)
        await transport.disconnect()
        assert transport.is_connected is False


@pytest.mark.asyncio
async def test_run_preconnect_refresh_rotates_full_credentials(
    config: MQTTTransportConfig, mammotion_http: MagicMock
) -> None:
    """The pre-connect refresh in _run must hand the *full* rotated credential
    set to aiomqtt.Client — not just the password — so a re-login that rotated
    client_id/username connects with matching identifiers (the bug that left the
    broker rejecting every reconnect as "Not Authorized").
    """
    from pymammotion.auth.token_manager import MQTTCredentials

    async def _refresher(force: bool) -> MQTTCredentials:  # noqa: ARG001
        return MQTTCredentials(
            host="mqtt.example.com",
            client_id="rotated-client",
            username="rotated-user",
            jwt="rotated-jwt",
            expires_at=0.0,
        )

    transport = MQTTTransport(config, mammotion_http, AsyncMock(), creds_refresher=_refresher)
    fake_client = _FakeMQTTClient()

    with patch("aiomqtt.Client", return_value=fake_client) as mock_client:
        await transport.connect()
        await asyncio.sleep(0.05)
        await transport.disconnect()

    kwargs = mock_client.call_args.kwargs
    assert kwargs["identifier"] == "rotated-client"
    assert kwargs["username"] == "rotated-user"
    assert kwargs["password"] == "rotated-jwt"


# ---------------------------------------------------------------------------
# send() calls the HTTP invoke API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_calls_mqtt_invoke(config: MQTTTransportConfig) -> None:
    """send() should forward the payload via mammotion_http.mqtt_invoke."""
    import base64

    http = MagicMock()
    http.mqtt_invoke = AsyncMock(return_value=MagicMock(code=0))
    transport = MQTTTransport(config, http, AsyncMock())

    payload = b"\x01\x02\x03"
    await transport.send(payload, iot_id="dev123")

    http.mqtt_invoke.assert_awaited_once()
    call_args = http.mqtt_invoke.call_args
    # First arg is base64-encoded payload
    assert call_args.args[0] == base64.b64encode(payload).decode()
    # Third arg is the iot_id
    assert call_args.args[2] == "dev123"


@pytest.mark.asyncio
async def test_send_raises_when_no_iot_id(config: MQTTTransportConfig, mammotion_http: MagicMock) -> None:
    """send() with an empty iot_id should raise TransportError."""
    transport = MQTTTransport(config, mammotion_http, AsyncMock())
    with pytest.raises(TransportError, match="iot_id"):
        await transport.send(b"hello")


# ---------------------------------------------------------------------------
# on_message callback is invoked for non-status messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_message_callback_called(config: MQTTTransportConfig, mammotion_http: MagicMock) -> None:
    """on_message should be called with the raw bytes of an incoming non-status message."""
    received: list[bytes] = []

    async def _handler(data: bytes) -> None:
        received.append(data)

    transport = MQTTTransport(config, mammotion_http, AsyncMock())
    transport.on_message = _handler

    incoming = [_FakeMessage("some/topic", b"hello")]
    fake_client = _FakeMQTTClient(messages=incoming)

    with patch("aiomqtt.Client", return_value=fake_client):
        await transport.connect()
        await asyncio.sleep(0.1)
        assert received == [b"hello"]
        await transport.disconnect()


# ---------------------------------------------------------------------------
# Network errors (OSError / DNS) — retry with backoff, no auth count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oserror_retries_without_counting_as_auth_failure(
    config: MQTTTransportConfig, mammotion_http: MagicMock
) -> None:
    """OSError (e.g. ENETUNREACHABLE) must retry with backoff and never call on_fatal_auth_error."""
    transport = MQTTTransport(config, mammotion_http, AsyncMock())
    transport.on_fatal_auth_error = AsyncMock()

    connect_attempts = 0

    def _client_factory(**_kwargs: object) -> object:
        nonlocal connect_attempts
        connect_attempts += 1
        if connect_attempts < 3:
            return _NetworkErrorClient(OSError(101, "Network is unreachable"))
        return _FakeMQTTClient()  # succeeds on 3rd attempt

    # Zero-out backoff so retries happen immediately; real asyncio.sleep(0) yields the event loop.
    with (
        patch("pymammotion.transport.mqtt.MQTT_RECONNECT_MIN_SEC", 0),
        patch("pymammotion.transport.mqtt.MQTT_RECONNECT_MAX_SEC_MAMMOTION", 0),
        patch("aiomqtt.Client", side_effect=_client_factory),
    ):
        await transport.connect()
        for _ in range(100):
            if connect_attempts >= 3:
                break
            await asyncio.sleep(0)
        await transport.disconnect()

    assert connect_attempts >= 3
    transport.on_fatal_auth_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_dns_error_retries_without_counting_as_auth_failure(
    config: MQTTTransportConfig, mammotion_http: MagicMock
) -> None:
    """socket.gaierror (DNS failure) must retry and not trigger on_fatal_auth_error."""
    import socket

    transport = MQTTTransport(config, mammotion_http, AsyncMock())
    transport.on_fatal_auth_error = AsyncMock()

    connect_attempts = 0

    def _client_factory(**_kwargs: object) -> object:
        nonlocal connect_attempts
        connect_attempts += 1
        if connect_attempts < 2:
            return _NetworkErrorClient(socket.gaierror(-2, "Name or service not known"))
        return _FakeMQTTClient()

    with (
        patch("pymammotion.transport.mqtt.MQTT_RECONNECT_MIN_SEC", 0),
        patch("pymammotion.transport.mqtt.MQTT_RECONNECT_MAX_SEC_MAMMOTION", 0),
        patch("aiomqtt.Client", side_effect=_client_factory),
    ):
        await transport.connect()
        for _ in range(100):
            if connect_attempts >= 2:
                break
            await asyncio.sleep(0)
        await transport.disconnect()

    assert connect_attempts >= 2
    transport.on_fatal_auth_error.assert_not_awaited()


# ===========================================================================
# send() without a token manager must raise TransportError (not a stripped assert)
# ===========================================================================


async def test_send_without_token_manager_raises_transport_error() -> None:
    """_token_manager None + invoke 401 → TransportError (H2 regression; survives python -O)."""
    from unittest.mock import AsyncMock, MagicMock

    from pymammotion.http.model.http import UnauthorizedExceptionError
    from pymammotion.transport.base import TransportError
    from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig

    cfg = MQTTTransportConfig(host="mqtt.example.com", port=1883, client_id="c", username="u", password="jwt")
    http = MagicMock()
    http.mqtt_invoke = AsyncMock(side_effect=UnauthorizedExceptionError("token expired"))
    transport = MQTTTransport(cfg, http, AsyncMock())
    transport._token_manager = None  # type: ignore[assignment]  # noqa: SLF001

    with pytest.raises(TransportError) as exc_info:
        await transport.send(b"payload", iot_id="iot-123")
    assert not isinstance(exc_info.value, AssertionError)
    assert "token manager" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Cloud error-code classification
#
# The code sets live in pymammotion.aliyun.exceptions so both cloud send paths
# share one table; these tests pin the behaviour the table drives here.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", [6205, 6221, 50103, 50104])
async def test_send_raises_device_offline_for_every_offline_code(
    config: MQTTTransportConfig, mammotion_http: MagicMock, code: int
) -> None:
    """Every known "device not reachable" code must surface as DeviceOfflineException.

    6221 (APK BindCode.DEVICE_OFFLINE) was previously unhandled and fell through
    to a generic TransportError, which the queue treats as an unexpected failure
    rather than an expected offline device.
    """
    from pymammotion.aliyun.exceptions import DeviceOfflineException

    mammotion_http.mqtt_invoke = AsyncMock(return_value=MagicMock(code=code))
    transport = MQTTTransport(config, mammotion_http, AsyncMock())

    with pytest.raises(DeviceOfflineException):
        await transport.send(b"\x00", iot_id="iot-1")


async def test_send_raises_gateway_timeout_for_20056(
    config: MQTTTransportConfig, mammotion_http: MagicMock
) -> None:
    from pymammotion.aliyun.exceptions import GatewayTimeoutException

    mammotion_http.mqtt_invoke = AsyncMock(return_value=MagicMock(code=20056))
    transport = MQTTTransport(config, mammotion_http, AsyncMock())

    with pytest.raises(GatewayTimeoutException):
        await transport.send(b"\x00", iot_id="iot-1")


async def test_send_raises_transport_error_for_unknown_code(
    config: MQTTTransportConfig, mammotion_http: MagicMock
) -> None:
    """An unclassified failure must not be mistaken for an offline device."""
    mammotion_http.mqtt_invoke = AsyncMock(return_value=MagicMock(code=99999))
    transport = MQTTTransport(config, mammotion_http, AsyncMock())

    with pytest.raises(TransportError):
        await transport.send(b"\x00", iot_id="iot-1")


# ---------------------------------------------------------------------------
# Dispatch must not swallow what the downstream callback raises
#
# The parse and the callback used to sit inside one broad `except Exception`, so
# anything a handler raised — SessionExpiredError, AuthError — was logged at DEBUG
# and dropped.  `_run` already has the exception taxonomy (auth handling, backoff,
# a catch-all); the dispatch helper must not second-guess it.
# ---------------------------------------------------------------------------


async def test_status_dispatch_propagates_callback_exceptions(
    config: MQTTTransportConfig, mammotion_http: MagicMock
) -> None:
    """An auth error raised by the status handler must reach _run, not be buried."""
    from pymammotion.transport.base import SessionExpiredError

    transport = MQTTTransport(config, mammotion_http, AsyncMock())
    transport.on_device_status = AsyncMock(
        side_effect=SessionExpiredError(TransportType.CLOUD_MAMMOTION, "token expired")
    )

    raw = json.dumps(
        {
            "action": "online",
            "productKey": "pk",
            "deviceName": "Yuka-X",
            "iotId": "iot-1",
            "gmtCreate": 1779395099943,
        }
    ).encode()
    with pytest.raises(SessionExpiredError):
        await transport._dispatch_device_status("/x/thing/status", raw)


async def test_status_dispatch_still_swallows_malformed_payloads(
    config: MQTTTransportConfig, mammotion_http: MagicMock
) -> None:
    """A bad payload is noise — it must not escape and tear down the connection."""
    transport = MQTTTransport(config, mammotion_http, AsyncMock())
    transport.on_device_status = AsyncMock()

    await transport._dispatch_device_status("/x/thing/status", b"{not json")
    await transport._dispatch_device_status("/x/thing/status", json.dumps({"unexpected": 1}).encode())
    transport.on_device_status.assert_not_awaited()


async def test_properties_dispatch_propagates_callback_exceptions(
    config: MQTTTransportConfig, mammotion_http: MagicMock
) -> None:
    from pymammotion.transport.base import SessionExpiredError

    transport = MQTTTransport(config, mammotion_http, AsyncMock())
    transport.on_device_properties = AsyncMock(
        side_effect=SessionExpiredError(TransportType.CLOUD_MAMMOTION, "token expired")
    )
    # ThingPropertiesMessage.Params requires a dozen aliased Aliyun fields; building
    # one by hand would test mashumaro, not the dispatch.  Stub the parse so the test
    # isolates what it is actually about — a successfully-parsed message whose
    # callback raises.
    parsed = MagicMock()
    parsed.params.iot_id = "iot-1"
    with patch.object(ThingPropertiesMessage, "from_json", return_value=parsed), pytest.raises(SessionExpiredError):
        await transport._dispatch_device_properties("/x/thing/properties", b"{}")
