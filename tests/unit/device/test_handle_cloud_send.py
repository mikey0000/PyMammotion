"""``DeviceHandle.send_cloud`` — the cloud-only send path the remote-drive session uses.

The app sends session frames through ``sendOrderMsg_DriverIotOnly`` (2.3.20.30): IoT only,
never Bluetooth, and with no fallback.  So this path picks the cloud transport even when a
BLE link is up, refuses outright when BLE is all there is, and on a user-initiated send waives
only the advisory ``mqtt_reported_offline`` flag — exactly as ``active_transport`` does.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pymammotion.aliyun.exceptions import DeviceOfflineException, TooManyRequestsException
from pymammotion.transport.base import NoTransportAvailableError, SessionExpiredError, TransportType
from tests._helpers import make_mock_handle, make_mock_transport


async def test_a_cloud_send_goes_over_the_cloud_even_while_ble_is_connected() -> None:
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN, send_user=AsyncMock())
    ble = make_mock_transport(TransportType.BLE)
    handle = make_mock_handle(mqtt_transport=mqtt, ble_transport=ble)

    await handle.send_cloud(b"\x01", user_initiated=True)

    mqtt.send_user.assert_awaited_once_with(b"\x01", iot_id=handle.iot_id, firmware_version=handle.firmware_version)
    ble.send.assert_not_awaited()


async def test_a_cloud_send_ignores_a_preference_for_ble() -> None:
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN, send_user=AsyncMock())
    ble = make_mock_transport(TransportType.BLE)
    handle = make_mock_handle(prefer_ble=True, mqtt_transport=mqtt, ble_transport=ble)

    await handle.send_cloud(b"\x01", user_initiated=True)

    mqtt.send_user.assert_awaited_once()
    ble.send.assert_not_awaited()


@pytest.mark.parametrize("prefer_ble", [False, True])
async def test_a_cloud_send_refuses_when_only_ble_is_registered(prefer_ble: bool) -> None:
    ble = make_mock_transport(TransportType.BLE)
    handle = make_mock_handle(prefer_ble=prefer_ble, ble_transport=ble)

    with pytest.raises(NoTransportAvailableError):
        await handle.send_cloud(b"\x01", user_initiated=True)

    ble.send.assert_not_awaited()


async def test_a_user_cloud_send_waives_the_offline_flag() -> None:
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN, send_user=AsyncMock())
    handle = make_mock_handle(mqtt_transport=mqtt)
    handle.update_availability(TransportType.CLOUD_ALIYUN, handle.availability.mqtt, mqtt_reported_offline=True)

    await handle.send_cloud(b"\x01", user_initiated=True)

    mqtt.send_user.assert_awaited_once()


async def test_a_background_cloud_send_honours_the_offline_flag() -> None:
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    handle = make_mock_handle(mqtt_transport=mqtt)
    handle.update_availability(TransportType.CLOUD_ALIYUN, handle.availability.mqtt, mqtt_reported_offline=True)

    with pytest.raises(NoTransportAvailableError):
        await handle.send_cloud(b"\x01")

    mqtt.send.assert_not_awaited()


async def test_a_cloud_send_refuses_a_transport_that_lost_its_auth() -> None:
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN, usable=False, send_user=AsyncMock())
    handle = make_mock_handle(mqtt_transport=mqtt)

    with pytest.raises(NoTransportAvailableError):
        await handle.send_cloud(b"\x01", user_initiated=True)

    mqtt.send_user.assert_not_awaited()


async def test_an_offline_rejection_rearms_the_flag_and_does_not_fall_back_to_ble() -> None:
    mqtt = make_mock_transport(
        TransportType.CLOUD_ALIYUN, send_user=AsyncMock(side_effect=DeviceOfflineException(6205, "x"))
    )
    ble = make_mock_transport(TransportType.BLE)
    handle = make_mock_handle(mqtt_transport=mqtt, ble_transport=ble)

    with pytest.raises(DeviceOfflineException):
        await handle.send_cloud(b"\x01", user_initiated=True)

    assert handle.availability.mqtt_reported_offline is True
    ble.send.assert_not_awaited()


async def test_an_auth_failure_propagates_unchanged() -> None:
    """``_send_with_auth_retry`` recovers a ``SessionExpiredError`` by type, so it must arrive as itself."""
    expired = SessionExpiredError(TransportType.CLOUD_ALIYUN, "x")
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN, send_user=AsyncMock(side_effect=expired))
    handle = make_mock_handle(mqtt_transport=mqtt)

    with pytest.raises(SessionExpiredError) as caught:
        await handle.send_cloud(b"\x01", user_initiated=True)

    assert caught.value is expired


async def test_a_429_arms_the_ban_and_propagates() -> None:
    mqtt = make_mock_transport(
        TransportType.CLOUD_ALIYUN, send_user=AsyncMock(side_effect=TooManyRequestsException("x", "y"))
    )
    handle = make_mock_handle(mqtt_transport=mqtt)

    with pytest.raises(TooManyRequestsException):
        await handle.send_cloud(b"\x01", user_initiated=True)

    mqtt.set_rate_limited.assert_called_once()
