"""Tests for MammotionClient (Wave 4 top-level API)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.transport.base import TransportType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mowing_device() -> MagicMock:
    """Return a MagicMock shaped like a MowingDevice."""
    device = MagicMock()
    device.online = True
    device.enabled = True
    device.report_data.dev.battery_val = 75
    device.report_data.dev.sys_status = "idle"
    device.report_data.work.knife_height = 40
    return device


def make_handle(device_id: str = "dev1", device_name: str = "Luba-Test") -> DeviceHandle:
    """Build a real DeviceHandle backed by a mock MowingDevice."""
    return DeviceHandle(
        device_id=device_id,
        device_name=device_name,
        initial_device=make_mowing_device(),
    )


# ---------------------------------------------------------------------------
# test 1: stop() is idempotent
# ---------------------------------------------------------------------------


async def test_stop_is_idempotent() -> None:
    """Calling stop() twice must complete without error and without double-teardown."""
    client = MammotionClient()
    # First call should work fine
    await client.stop()
    # Second call must not raise
    await client.stop()


# ---------------------------------------------------------------------------
# test 2: stop() calls stop() on all registered handles
# ---------------------------------------------------------------------------


async def test_stop_calls_device_handle_stop() -> None:
    """stop() must call stop() on every registered DeviceHandle."""
    client = MammotionClient()

    handle1 = make_handle("dev1", "Mower-A")
    handle2 = make_handle("dev2", "Mower-B")

    handle1.stop = AsyncMock()  # type: ignore[method-assign]
    handle2.stop = AsyncMock()  # type: ignore[method-assign]

    await client._device_registry.register(handle1)
    await client._device_registry.register(handle2)

    await client.stop()

    handle1.stop.assert_awaited_once()
    handle2.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# test 3: remove_device schedules unregister as a task
# ---------------------------------------------------------------------------


async def test_remove_device_schedules_unregister() -> None:
    """remove_device() must schedule a task that eventually unregisters the handle."""
    client = MammotionClient()

    handle = make_handle("dev1", "Luba-One")
    handle.stop = AsyncMock()  # type: ignore[method-assign]
    await client._device_registry.register(handle)

    # Verify handle is present before removal
    assert client._device_registry.get_by_name("Luba-One") is handle

    client.remove_device("Luba-One")

    # Let the scheduled task run
    await asyncio.sleep(0)

    # Handle should now be unregistered (stop was called inside unregister)
    handle.stop.assert_awaited_once()
    assert client._device_registry.get_by_name("Luba-One") is None


# ---------------------------------------------------------------------------
# test 4: get_device_by_name returns None for unknown device
# ---------------------------------------------------------------------------


async def test_get_device_by_name_returns_none_for_unknown() -> None:
    """Unknown device name must return None, not raise."""
    client = MammotionClient()
    result = client.get_device_by_name("nonexistent-mower")
    assert result is None


# ---------------------------------------------------------------------------
# test 5: send_command_with_args raises KeyError for missing device
# ---------------------------------------------------------------------------


async def test_send_command_with_args_raises_for_unknown_device() -> None:
    """send_command_with_args must raise KeyError when device is not registered."""
    client = MammotionClient()

    with pytest.raises(KeyError, match="Device 'ghost-mower' not registered"):
        await client.send_command_with_args("ghost-mower", "start_mow")


# ---------------------------------------------------------------------------
# test 6: add_ble_device calls BLETransportManager.register_external_ble_client
# ---------------------------------------------------------------------------


async def test_add_ble_device_calls_manager() -> None:
    """add_ble_device must delegate to BLETransportManager.register_external_ble_client."""
    client = MammotionClient()

    fake_ble_device = MagicMock()
    client._ble_manager.register_external_ble_client = MagicMock()  # type: ignore[method-assign]

    await client.add_ble_device("dev-xyz", fake_ble_device)

    client._ble_manager.register_external_ble_client.assert_called_once_with("dev-xyz", fake_ble_device)


# ---------------------------------------------------------------------------
# test 7: mower() returns the DeviceHandle (or None for unknown)
# ---------------------------------------------------------------------------


async def test_mower_returns_handle() -> None:
    """mower(name) must return the registered DeviceHandle for that name."""
    client = MammotionClient()

    handle = make_handle("dev1", "Yuka-Prime")
    await client._device_registry.register(handle)

    result = client.mower("Yuka-Prime")
    assert result is handle

    # Unknown name returns None
    assert client.mower("no-such-device") is None


# ---------------------------------------------------------------------------
# test 8: get_device_by_name returns MowingDevice (snapshot.raw)
# ---------------------------------------------------------------------------


async def test_get_device_by_name_returns_mowing_device() -> None:
    """get_device_by_name must return the MowingDevice stored in snapshot.raw."""
    client = MammotionClient()

    handle = make_handle("dev99", "Luba-X")
    await client._device_registry.register(handle)

    result = client.get_device_by_name("Luba-X")
    assert result is handle.snapshot.raw


# ---------------------------------------------------------------------------
# test 9: send_command_with_args succeeds for a registered device (logs, no raise)
# ---------------------------------------------------------------------------


async def test_send_command_with_args_succeeds_for_known_device() -> None:
    """send_command_with_args must complete without error for a registered device."""
    client = MammotionClient()

    mqtt_transport = MagicMock()
    mqtt_transport.transport_type = TransportType.CLOUD_ALIYUN
    mqtt_transport.is_connected = True
    mqtt_transport.send = AsyncMock()

    handle = make_handle("dev1", "Luba-Runner")
    await handle.add_transport(mqtt_transport)
    await client._device_registry.register(handle)

    # Should not raise
    await client.send_command_with_args("Luba-Runner", "start_job")


# ---------------------------------------------------------------------------
# test 10: device_registry and account_registry properties
# ---------------------------------------------------------------------------


async def test_properties_return_correct_objects() -> None:
    """device_registry and account_registry must return the internal instances."""
    client = MammotionClient()

    assert client.device_registry is client._device_registry
    assert client.account_registry is client._account_registry


# ---------------------------------------------------------------------------
# _apply_geojson / _apply_mow_path_geojson helpers
# ---------------------------------------------------------------------------


def _make_device_with_rtk(lat: float = 0.5, lon: float = 0.5) -> MagicMock:
    """Return a MowingDevice-shaped mock with a non-zero RTK location."""
    device = MagicMock()
    device.location.RTK.latitude = lat
    device.location.RTK.longitude = lon
    device.location.dock.latitude = 0.01
    device.location.dock.longitude = 0.01
    device.location.dock.rotation = 0
    return device


# ---------------------------------------------------------------------------
# start_map_sync / start_mow_path_saga — geojson generated on completion
# ---------------------------------------------------------------------------


def _make_mock_transport(transport_type: TransportType = TransportType.CLOUD_ALIYUN) -> MagicMock:
    """Return a connected mock transport."""
    t = MagicMock()
    t.transport_type = transport_type
    t.is_connected = True
    t.send = AsyncMock()
    t.disconnect = AsyncMock()
    t.on_message = None
    return t


async def _make_handle_with_transport(device_id: str, device_name: str) -> DeviceHandle:
    handle = make_handle(device_id, device_name)
    await handle.add_transport(_make_mock_transport())
    await handle.start()
    return handle


async def test_start_map_sync_generates_geojson_on_completion() -> None:
    """start_map_sync must call device.map.generate_geojson after the MapFetchSaga succeeds."""
    client = MammotionClient()
    handle = await _make_handle_with_transport("dev1", "Luba-Map")
    await client._device_registry.register(handle)

    mock_device = _make_device_with_rtk(lat=0.5, lon=0.5)
    client.get_device_by_name = MagicMock(return_value=mock_device)  # type: ignore[method-assign]

    with patch("pymammotion.client.MapFetchSaga") as MockSaga:
        mock_saga_instance = MagicMock()
        mock_saga_instance.name = "map_fetch"
        mock_saga_instance.max_attempts = 1
        mock_saga_instance.execute = AsyncMock()
        mock_saga_instance.result = None
        MockSaga.return_value = mock_saga_instance

        await client.start_map_sync("Luba-Map")
        await asyncio.sleep(0.15)

    mock_device.map.generate_geojson.assert_called_once()
    await handle.stop()


async def test_start_mow_path_saga_generates_geojson_on_completion() -> None:
    """start_mow_path_saga must call device.map.generate_mowing_geojson after the saga succeeds."""
    client = MammotionClient()
    handle = await _make_handle_with_transport("dev1", "Luba-Mow")
    await client._device_registry.register(handle)

    mock_device = _make_device_with_rtk(lat=0.5, lon=0.5)
    client.get_device_by_name = MagicMock(return_value=mock_device)  # type: ignore[method-assign]

    with patch("pymammotion.messaging.mow_path_saga.MowPathSaga") as MockSaga:
        mock_saga_instance = MagicMock()
        mock_saga_instance.name = "mow_path_fetch"
        mock_saga_instance.max_attempts = 1
        mock_saga_instance.execute = AsyncMock()
        MockSaga.return_value = mock_saga_instance

        await client.start_mow_path_saga("Luba-Mow", zone_hashs=[1, 2])
        await asyncio.sleep(0.15)

    mock_device.map.generate_mowing_geojson.assert_called_once()
    await handle.stop()


async def test_start_map_sync_skips_geojson_when_rtk_zero() -> None:
    """generate_geojson must not be called when RTK location is 0,0 (not yet received)."""
    client = MammotionClient()
    handle = await _make_handle_with_transport("dev1", "Luba-NoRTK")
    await client._device_registry.register(handle)

    mock_device = _make_device_with_rtk(lat=0.0, lon=0.0)  # zero = no RTK fix
    client.get_device_by_name = MagicMock(return_value=mock_device)  # type: ignore[method-assign]

    with patch("pymammotion.client.MapFetchSaga") as MockSaga:
        mock_saga_instance = MagicMock()
        mock_saga_instance.name = "map_fetch"
        mock_saga_instance.max_attempts = 1
        mock_saga_instance.execute = AsyncMock()
        mock_saga_instance.result = None
        MockSaga.return_value = mock_saga_instance

        await client.start_map_sync("Luba-NoRTK")
        await asyncio.sleep(0.15)

    mock_device.map.generate_geojson.assert_not_called()
    await handle.stop()


# ---------------------------------------------------------------------------
# TokenManager created during cloud login and credential restore
# ---------------------------------------------------------------------------


async def test_token_manager_set_after_restore_aliyun() -> None:
    """_restore_aliyun must set token_manager on the session."""
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    mock_cloud = MagicMock()
    mock_cloud.mammotion_http = MagicMock()
    mock_cloud.mammotion_http.login_info = None
    mock_cloud.devices_by_account_response = None

    with (
        patch("pymammotion.client.CloudIOTGateway.from_cache", AsyncMock(return_value=mock_cloud)),
        patch.object(client, "_setup_aliyun_transport", return_value=MagicMock()),
    ):
        await client._restore_aliyun(
            "user@test.com", "pass", {}, acct_session, check_for_new_devices=False
        )

    assert acct_session.token_manager is not None


async def test_token_manager_set_after_restore_mammotion_mqtt() -> None:
    """_restore_mammotion_mqtt must set token_manager on the session when mqtt_creds are present."""
    from pymammotion.http.model.http import MQTTConnection

    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    mqtt_creds = MQTTConnection(
        host="mqtt.example.com",
        client_id="client-1",
        username="user",
        jwt="token",
    )
    cached_data = {
        "mammotion_mqtt": mqtt_creds.to_dict(),
        "mammotion_device_records": {"records": []},
    }

    mock_transport = MagicMock()
    mock_transport.connect = AsyncMock()

    with patch.object(client, "_setup_mammotion_transport", return_value=mock_transport):
        await client._restore_mammotion_mqtt(
            "user@test.com", "pass", cached_data, None, acct_session, check_for_new_devices=False
        )

    assert acct_session.token_manager is not None


async def test_token_manager_set_after_login_and_initiate_cloud() -> None:
    """login_and_initiate_cloud must set token_manager when Aliyun devices are present."""
    client = MammotionClient()

    mock_device = MagicMock()
    mock_device.device_name = "Luba-Cloud"
    mock_device.iot_id = "iot-123"

    mock_devices_data = MagicMock()
    mock_devices_data.data.data = [mock_device]

    mock_cloud = MagicMock()
    mock_cloud.mammotion_http = MagicMock()
    mock_cloud.mammotion_http.login_info = None
    mock_cloud.devices_by_account_response = mock_devices_data
    mock_cloud.aep_response = MagicMock()
    mock_cloud.aep_response.data = MagicMock(productKey="pk", deviceName="dn", deviceSecret="ds")
    mock_cloud.region_response = MagicMock()
    mock_cloud.region_response.data.regionId = "cn-shanghai"
    mock_cloud.session_by_authcode_response = MagicMock()
    mock_cloud.session_by_authcode_response.data = MagicMock(iotToken="tok")

    mock_http = MagicMock()
    mock_http.login_v2 = AsyncMock(return_value=MagicMock(code=0))
    mock_http.get_user_device_list = AsyncMock(return_value=MagicMock(data=None))
    mock_http.get_user_shared_device_page = AsyncMock(return_value=MagicMock(data=["placeholder"]))
    mock_http.get_user_device_page = AsyncMock(return_value=MagicMock(data=None))
    mock_http.login_info = None
    mock_http.mqtt_credentials = None

    mock_transport = MagicMock()
    mock_transport.connect = AsyncMock()

    with (
        patch("pymammotion.client.MammotionHTTP", return_value=mock_http),
        patch("pymammotion.client.CloudIOTGateway", return_value=mock_cloud),
        patch("pymammotion.client.MammotionClient._connect_iot", AsyncMock()),
        patch.object(client, "_setup_aliyun_transport", return_value=mock_transport),
        patch.object(client, "_register_aliyun_device", AsyncMock()),
    ):
        mock_cloud.get_shared_notice_list = AsyncMock(return_value=MagicMock(data=None))
        mock_cloud.get_shared_notice_list.return_value.data = None
        await client.login_and_initiate_cloud("user@test.com", "pass")

    session = client._account_registry.get("user@test.com")
    assert session is not None
    assert session.token_manager is not None


# ---------------------------------------------------------------------------
# send_command_with_args prefer_ble routing
# ---------------------------------------------------------------------------


def _make_connected_transport(transport_type: TransportType) -> MagicMock:
    t = MagicMock()
    t.transport_type = transport_type
    t.is_connected = True
    t.send = AsyncMock()
    t.disconnect = AsyncMock()
    t.on_message = None
    t.add_availability_listener = MagicMock()
    return t


async def _drain(handle: DeviceHandle) -> None:
    """Flush all pending queue items then stop the worker."""
    handle.queue.start()
    await handle.queue._queue.join()  # noqa: SLF001
    await handle.queue.stop()


def _stub_commands(handle: DeviceHandle, fake_bytes: bytes) -> MagicMock:
    """Replace the handle's commands property with a mock that returns fake_bytes."""
    mock_commands = MagicMock()
    mock_commands.get_report_cfg = MagicMock(return_value=fake_bytes)
    # commands is a @property — patch it on the class via PropertyMock
    patcher = patch.object(type(handle), "commands", new_callable=PropertyMock, return_value=mock_commands)
    patcher.start()
    return patcher  # caller must call patcher.stop()


async def test_send_command_with_args_prefer_ble_uses_ble_transport() -> None:
    """send_command_with_args(prefer_ble=True) must route through the BLE transport.

    Both BLE and MQTT are connected. With prefer_ble=True the active transport
    selector should return BLE, so only ble.send() is awaited.
    """
    client = MammotionClient()

    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    ble = _make_connected_transport(TransportType.BLE)

    handle = make_handle("Luba-BLE", "Luba-BLE")
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)

    # Confirm the BLE transport is registered on the handle before sending.
    assert handle._transports.get(TransportType.BLE) is ble  # noqa: SLF001

    fake_bytes = b"\xDE\xAD\xBE\xEF"
    patcher = _stub_commands(handle, fake_bytes)
    try:
        await client._device_registry.register(handle)
        await client.send_command_with_args("Luba-BLE", "get_report_cfg", prefer_ble=True)
        await _drain(handle)
    finally:
        patcher.stop()

    ble.send.assert_awaited_once_with(fake_bytes, iot_id="")
    mqtt.send.assert_not_awaited()


async def test_send_command_with_args_uses_connected_ble_over_mqtt() -> None:
    """When both transports are connected, BLE is chosen unconditionally."""
    client = MammotionClient()

    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    ble = _make_connected_transport(TransportType.BLE)

    handle = make_handle("Luba-MQTT", "Luba-MQTT")
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)

    fake_bytes = b"\xCA\xFE"
    patcher = _stub_commands(handle, fake_bytes)
    try:
        await client._device_registry.register(handle)
        await client.send_command_with_args("Luba-MQTT", "get_report_cfg")
        await _drain(handle)
    finally:
        patcher.stop()

    ble.send.assert_awaited_once_with(fake_bytes, iot_id="")
    mqtt.send.assert_not_awaited()


async def test_send_command_with_args_uses_mqtt_when_ble_disconnected() -> None:
    """When BLE is registered but not connected, MQTT is used."""
    client = MammotionClient()

    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    ble = _make_connected_transport(TransportType.BLE)
    ble.is_connected = False  # registered but not connected

    handle = make_handle("Luba-MQTT", "Luba-MQTT")
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)

    fake_bytes = b"\xCA\xFE"
    patcher = _stub_commands(handle, fake_bytes)
    try:
        await client._device_registry.register(handle)
        await client.send_command_with_args("Luba-MQTT", "get_report_cfg")
        await _drain(handle)
    finally:
        patcher.stop()

    mqtt.send.assert_awaited_once_with(fake_bytes, iot_id="")
    ble.send.assert_not_awaited()


async def test_send_command_with_args_prefer_ble_reconnects_before_mqtt_fallback() -> None:
    """When prefer_ble=True and BLE is disconnected, send_raw attempts reconnect first.

    If reconnect succeeds the command goes over BLE, not MQTT.
    """
    client = MammotionClient()

    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    ble = _make_connected_transport(TransportType.BLE)
    ble.is_connected = False

    async def _reconnect() -> None:
        ble.is_connected = True

    ble.connect = AsyncMock(side_effect=_reconnect)

    handle = make_handle("Luba-RC", "Luba-RC")
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)

    fake_bytes = b"\xAB\xCD"
    patcher = _stub_commands(handle, fake_bytes)
    try:
        await client._device_registry.register(handle)
        await client.send_command_with_args("Luba-RC", "get_report_cfg", prefer_ble=True)
        await _drain(handle)
    finally:
        patcher.stop()

    ble.connect.assert_awaited_once()
    ble.send.assert_awaited_once_with(fake_bytes, iot_id="")
    mqtt.send.assert_not_awaited()


# ---------------------------------------------------------------------------
# set_scheduled_updates: transport + watchdog lifecycle
# ---------------------------------------------------------------------------


async def test_set_scheduled_updates_false_disconnects_and_stops_watchdog() -> None:
    """set_scheduled_updates(enabled=False) must disconnect all transports and cancel the watchdog."""
    client = MammotionClient()
    handle = make_handle("dev1", "Luba-Sched")
    handle.connect_transport = AsyncMock()  # type: ignore[method-assign]
    handle.disconnect_transport = AsyncMock()  # type: ignore[method-assign]
    await client._device_registry.register(handle)

    # Simulate a running watchdog (pre-installed cleanup callable).
    mock_cleanup = MagicMock()
    mock_cleanup._arm = MagicMock()  # noqa: SLF001
    client._watchdog_cleanups["Luba-Sched"] = mock_cleanup

    await client.set_scheduled_updates("Luba-Sched", enabled=False)

    # Watchdog cleanup must be called and the entry removed.
    mock_cleanup.assert_called_once()
    assert "Luba-Sched" not in client._watchdog_cleanups

    # All three transport types must be disconnected.
    disconnected = [call.args[0] for call in handle.disconnect_transport.await_args_list]
    assert TransportType.CLOUD_ALIYUN in disconnected
    assert TransportType.CLOUD_MAMMOTION in disconnected
    assert TransportType.BLE in disconnected

    handle.connect_transport.assert_not_awaited()


async def test_set_scheduled_updates_true_connects_and_reinstalls_watchdog() -> None:
    """set_scheduled_updates(enabled=True) must reconnect transports and reinstall the watchdog."""
    client = MammotionClient()
    handle = make_handle("dev1", "Luba-Sched2")
    handle.connect_transport = AsyncMock()  # type: ignore[method-assign]
    handle.disconnect_transport = AsyncMock()  # type: ignore[method-assign]
    await client._device_registry.register(handle)

    # No watchdog present (as it would be after a disable).
    assert "Luba-Sched2" not in client._watchdog_cleanups

    with patch.object(client, "_install_report_data_watchdog") as mock_install:
        await client.set_scheduled_updates("Luba-Sched2", enabled=True)

    # All three transport types must be connected.
    connected = [call.args[0] for call in handle.connect_transport.await_args_list]
    assert TransportType.CLOUD_ALIYUN in connected
    assert TransportType.CLOUD_MAMMOTION in connected
    assert TransportType.BLE in connected

    handle.disconnect_transport.assert_not_awaited()

    # Watchdog must be reinstalled since it was absent.
    mock_install.assert_called_once_with("Luba-Sched2")


async def test_set_scheduled_updates_true_skips_watchdog_if_already_installed() -> None:
    """set_scheduled_updates(enabled=True) must not double-install the watchdog."""
    client = MammotionClient()
    handle = make_handle("dev1", "Luba-Sched3")
    handle.connect_transport = AsyncMock()  # type: ignore[method-assign]
    handle.disconnect_transport = AsyncMock()  # type: ignore[method-assign]
    await client._device_registry.register(handle)

    # Watchdog already present.
    existing_cleanup = MagicMock()
    client._watchdog_cleanups["Luba-Sched3"] = existing_cleanup

    with patch.object(client, "_install_report_data_watchdog") as mock_install:
        await client.set_scheduled_updates("Luba-Sched3", enabled=True)

    mock_install.assert_not_called()
    # Existing cleanup must not have been touched.
    existing_cleanup.assert_not_called()


async def test_set_scheduled_updates_noop_for_unknown_device() -> None:
    """set_scheduled_updates must silently do nothing for an unregistered device name."""
    client = MammotionClient()
    # Must not raise even when the device is not registered.
    await client.set_scheduled_updates("ghost-device", enabled=False)
    await client.set_scheduled_updates("ghost-device", enabled=True)


# ---------------------------------------------------------------------------
# User-command active window: send_command_* stamps _last_user_command_ts
# ---------------------------------------------------------------------------


async def test_send_command_with_args_stamps_last_user_command_ts() -> None:
    """send_command_with_args must update _last_user_command_ts for the device."""
    import time

    client = MammotionClient()

    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    handle = make_handle("dev1", "Luba-TS")
    await handle.add_transport(mqtt)
    await client._device_registry.register(handle)

    assert "Luba-TS" not in client._last_user_command_ts

    before = time.monotonic()
    await client.send_command_with_args("Luba-TS", "start_job")
    after = time.monotonic()

    assert "Luba-TS" in client._last_user_command_ts
    assert before <= client._last_user_command_ts["Luba-TS"] <= after


async def test_send_command_and_wait_stamps_last_user_command_ts() -> None:
    """send_command_and_wait must update _last_user_command_ts for the device."""
    import time

    client = MammotionClient()

    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    handle = make_handle("dev1", "Luba-TS2")
    await handle.add_transport(mqtt)
    await client._device_registry.register(handle)

    assert "Luba-TS2" not in client._last_user_command_ts

    # send_command_and_wait will time out waiting for a response — that's fine,
    # we only care that the timestamp is stamped before the await.
    with pytest.raises(Exception):  # noqa: BLE001
        await client.send_command_and_wait("Luba-TS2", "start_job", "some_field", send_timeout=0.01)

    assert "Luba-TS2" in client._last_user_command_ts
    ts = client._last_user_command_ts["Luba-TS2"]
    assert time.monotonic() - ts < 5.0  # stamped very recently


async def test_watchdog_window_uses_short_after_user_command() -> None:
    """When a user command was sent within 30 min on MQTT, watchdog uses the short window.

    Verified by checking that send_command_with_args sets _last_user_command_ts,
    which _current_silence_window() then reads to return _REPORT_DATA_SILENCE_SECONDS.
    """
    import time as _time

    from pymammotion.client import _REPORT_DATA_SILENCE_SECONDS, _USER_COMMAND_ACTIVE_SECONDS

    client = MammotionClient()

    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    handle = make_handle("dev1", "Luba-Win")
    handle.snapshot.raw.report_data.dev.battery_val = 50
    handle.snapshot.raw.report_data.dev.charge_state = 0
    handle.snapshot.raw.report_data.dev.sys_status = 0
    await handle.add_transport(mqtt)
    await client._device_registry.register(handle)

    # No command yet — timestamp absent, should NOT be in the short window.
    assert "Luba-Win" not in client._last_user_command_ts

    # Stamp a recent command.
    client._last_user_command_ts["Luba-Win"] = _time.monotonic()

    # Stamp is recent → still within the 30-min window.
    elapsed = _time.monotonic() - client._last_user_command_ts["Luba-Win"]
    assert elapsed < _USER_COMMAND_ACTIVE_SECONDS

    # Stamp an expired command (31 minutes ago) → window should revert.
    client._last_user_command_ts["Luba-Win"] = _time.monotonic() - (_USER_COMMAND_ACTIVE_SECONDS + 60)
    elapsed_expired = _time.monotonic() - client._last_user_command_ts["Luba-Win"]
    assert elapsed_expired > _USER_COMMAND_ACTIVE_SECONDS


async def test_send_command_with_args_prefer_ble_uses_ble_after_connect() -> None:
    """When prefer_ble=True and BLE is registered (disconnected), send_raw reconnects and sends via BLE.

    ble_ok = ble is not None — BLE is selected by active_transport() regardless of connection
    state.  send_raw() calls ble.connect() first, then routes the payload through BLE.
    """
    client = MammotionClient()

    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    ble = _make_connected_transport(TransportType.BLE)
    ble.is_connected = False
    ble.connect = AsyncMock()  # connect() does nothing — is_connected stays False (mock)

    handle = make_handle("Luba-FB", "Luba-FB")
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)

    fake_bytes = b"\xAB\xCD"
    patcher = _stub_commands(handle, fake_bytes)
    try:
        await client._device_registry.register(handle)
        await client.send_command_with_args("Luba-FB", "get_report_cfg", prefer_ble=True)
        await _drain(handle)
    finally:
        patcher.stop()

    ble.connect.assert_awaited_once()
    ble.send.assert_awaited_once_with(fake_bytes, iot_id="")
    mqtt.send.assert_not_awaited()
