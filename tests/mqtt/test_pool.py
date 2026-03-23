"""Tests for MQTTConnectionPool."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.auth.token_manager import MQTTCredentials
from pymammotion.http.model.http import DeviceInfo, DeviceRecord
from pymammotion.mqtt.pool import MQTTConnectionPool
from pymammotion.transport.base import Transport, TransportType

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transport() -> MagicMock:
    """Return a mock Transport with async connect/disconnect."""
    transport = MagicMock(spec=Transport)
    transport.connect = AsyncMock()
    transport.disconnect = AsyncMock()
    return transport


def _make_creds(host: str = "mqtt.example.com") -> MQTTCredentials:
    return MQTTCredentials(
        host=host,
        client_id="client-1",
        username="user-1",
        jwt="jwt-token",
        expires_at=9999999999.0,
    )


def _make_pool(
    transport_factory: object | None = None,
) -> tuple[MQTTConnectionPool, MagicMock]:
    """Create a pool with a mock TokenManager and optional factory."""
    token_manager = MagicMock()
    token_manager.get_mammotion_mqtt_credentials = AsyncMock(return_value=_make_creds())

    if transport_factory is None:
        default_transport = _make_transport()
        factory = MagicMock(return_value=default_transport)
    else:
        factory = transport_factory  # type: ignore[assignment]

    pool = MQTTConnectionPool(
        account_id="test@example.com",
        token_manager=token_manager,
        transport_factory=factory,
    )
    return pool, factory


def _make_device_info(iot_id: str) -> DeviceInfo:
    info = DeviceInfo()
    info.iot_id = iot_id
    return info


def _make_device_record(iot_id: str) -> DeviceRecord:
    return DeviceRecord(
        identity_id="identity-1",
        iot_id=iot_id,
        product_key="pk-1",
        device_name="device-name",
        owned=1,
        status=1,
        bind_time=0,
        create_time="2024-01-01",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aliyun_host_format() -> None:
    """register_aliyun_devices builds the correct Aliyun host string."""
    pool, factory = _make_pool()
    devices = [_make_device_info("dev-1")]

    await pool.register_aliyun_devices(devices, product_key="my-pk", region_id="eu-central-1")

    # The factory should have been called with the formatted host
    call_args = factory.call_args
    host_arg: str = call_args[0][0]
    assert host_arg == "my-pk.iot-as-mqtt.eu-central-1.aliyuncs.com"


@pytest.mark.asyncio
async def test_mammotion_host_from_credentials() -> None:
    """register_mammotion_devices uses mqtt_creds.host."""
    pool, factory = _make_pool()
    creds = _make_creds(host="special.mqtt.mammotion.com")
    records = [_make_device_record("dev-mammotion-1")]

    await pool.register_mammotion_devices(records, mqtt_creds=creds)

    call_args = factory.call_args
    host_arg: str = call_args[0][0]
    assert host_arg == "special.mqtt.mammotion.com"


@pytest.mark.asyncio
async def test_shared_transport_per_key() -> None:
    """Two devices registered under the same key share the same Transport."""
    call_count = 0
    transports: list[MagicMock] = []

    def factory(host: str, creds: MQTTCredentials) -> MagicMock:
        nonlocal call_count
        call_count += 1
        t = _make_transport()
        transports.append(t)
        return t

    pool, _ = _make_pool(transport_factory=factory)

    creds = _make_creds()
    records_1 = [_make_device_record("dev-A")]
    records_2 = [_make_device_record("dev-B")]

    transport_1 = await pool.register_mammotion_devices(records_1, mqtt_creds=creds)
    transport_2 = await pool.register_mammotion_devices(records_2, mqtt_creds=creds)

    assert transport_1 is transport_2, "Both devices must share the same Transport"
    assert call_count == 1, "Transport factory must be called only once per key"


@pytest.mark.asyncio
async def test_get_transport_by_device_id() -> None:
    """get_transport returns the correct Transport for a registered device ID."""
    pool, factory = _make_pool()
    creds = _make_creds()
    records = [_make_device_record("dev-lookup")]

    returned = await pool.register_mammotion_devices(records, mqtt_creds=creds)
    found = pool.get_transport("dev-lookup")

    assert found is returned


@pytest.mark.asyncio
async def test_connect_all_calls_transport_connect() -> None:
    """connect_all calls transport.connect() for each pool entry."""
    aliyun_transport = _make_transport()
    mammotion_transport = _make_transport()
    call_order: list[str] = []

    def factory(host: str, creds: MQTTCredentials) -> MagicMock:
        if "aliyuncs.com" in host:
            aliyun_transport.connect.side_effect = lambda: call_order.append("aliyun") or None
            return aliyun_transport
        mammotion_transport.connect.side_effect = lambda: call_order.append("mammotion") or None
        return mammotion_transport

    pool, _ = _make_pool(transport_factory=factory)

    aliyun_devices = [_make_device_info("dev-a")]
    mammotion_records = [_make_device_record("dev-m")]
    mammotion_creds = _make_creds(host="mqtt.mammotion.com")

    await pool.register_aliyun_devices(aliyun_devices, product_key="pk", region_id="eu-central-1")
    await pool.register_mammotion_devices(mammotion_records, mqtt_creds=mammotion_creds)

    # Make connect() coroutine-compatible for the real call
    aliyun_transport.connect = AsyncMock()
    mammotion_transport.connect = AsyncMock()

    await pool.connect_all()

    aliyun_transport.connect.assert_awaited_once()
    mammotion_transport.connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_connection_key() -> None:
    """get_connection_key returns the correct Literal for a registered device."""
    pool, _ = _make_pool()
    creds = _make_creds()
    records = [_make_device_record("dev-key-test")]

    await pool.register_mammotion_devices(records, mqtt_creds=creds)

    key = pool.get_connection_key("dev-key-test")
    assert key == "mammotion"

    missing = pool.get_connection_key("nonexistent-device")
    assert missing is None
