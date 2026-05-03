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
# (BLE polling-loop autoload-suppress fixture lives in tests/conftest.py.)


def make_mowing_device() -> MagicMock:
    """Return a MagicMock shaped like a MowingDevice.

    Explicit ``charge_state = 0`` because ``int(MagicMock())`` returns 1, which
    would push :meth:`DeviceHandle._device_mode` into ``DOCKED_CHARGING`` and
    surprise tests that don't otherwise care about charge state.
    """
    device = MagicMock()
    device.online = True
    device.enabled = True
    device.report_data.dev.battery_val = 75
    device.report_data.dev.charge_state = 0
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

    with (
        patch.object(client, "_setup_mammotion_transport", return_value=mock_transport),
        patch("pymammotion.http.http.MammotionHTTP.login_v2", new_callable=AsyncMock) as mock_login,
    ):
        mock_login.return_value = MagicMock(code=0, data=MagicMock())
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
    t.is_rate_limited = False
    t.is_usable = True  # default: ready to attempt sends; tests flip to False to exercise gates
    t.send = AsyncMock()
    t.send_heartbeat = AsyncMock()
    t.disconnect = AsyncMock()
    t.on_message = None
    t.add_availability_listener = MagicMock()
    t.last_received_monotonic = 0.0
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
    await handle.stop()


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
    await handle.stop()


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
# set_scheduled_updates: transport lifecycle
# ---------------------------------------------------------------------------


async def test_set_scheduled_updates_false_disconnects_all_transports() -> None:
    """set_scheduled_updates(enabled=False) must disconnect all transport types."""
    client = MammotionClient()
    handle = make_handle("dev1", "Luba-Sched")
    handle.connect_transport = AsyncMock()  # type: ignore[method-assign]
    handle.disconnect_transport = AsyncMock()  # type: ignore[method-assign]
    await client._device_registry.register(handle)

    await client.set_scheduled_updates("Luba-Sched", enabled=False)

    disconnected = [call.args[0] for call in handle.disconnect_transport.await_args_list]
    assert TransportType.CLOUD_ALIYUN in disconnected
    assert TransportType.CLOUD_MAMMOTION in disconnected
    assert TransportType.BLE in disconnected
    handle.connect_transport.assert_not_awaited()


async def test_set_scheduled_updates_true_connects_all_transports() -> None:
    """set_scheduled_updates(enabled=True) must reconnect all transport types."""
    client = MammotionClient()
    handle = make_handle("dev1", "Luba-Sched2")
    handle.connect_transport = AsyncMock()  # type: ignore[method-assign]
    handle.disconnect_transport = AsyncMock()  # type: ignore[method-assign]
    await client._device_registry.register(handle)

    await client.set_scheduled_updates("Luba-Sched2", enabled=True)

    connected = [call.args[0] for call in handle.connect_transport.await_args_list]
    assert TransportType.CLOUD_ALIYUN in connected
    assert TransportType.CLOUD_MAMMOTION in connected
    assert TransportType.BLE in connected
    handle.disconnect_transport.assert_not_awaited()


async def test_set_scheduled_updates_noop_for_unknown_device() -> None:
    """set_scheduled_updates must silently do nothing for an unregistered device name."""
    client = MammotionClient()
    await client.set_scheduled_updates("ghost-device", enabled=False)
    await client.set_scheduled_updates("ghost-device", enabled=True)


# ---------------------------------------------------------------------------
# User-command stamping: send_command_* stamps handle._last_user_command_monotonic
# ---------------------------------------------------------------------------


async def test_send_command_with_args_stamps_user_command_on_handle() -> None:
    """send_command_with_args must call handle.record_user_command() (updates _last_user_command_monotonic)."""
    import time

    client = MammotionClient()
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    handle = make_handle("dev1", "Luba-TS")
    await handle.add_transport(mqtt)
    await client._device_registry.register(handle)

    # Force an old timestamp so we can verify it changes.
    handle._last_user_command_monotonic = 0.0  # noqa: SLF001

    before = time.monotonic()
    await client.send_command_with_args("Luba-TS", "start_job")
    after = time.monotonic()

    assert before <= handle._last_user_command_monotonic <= after  # noqa: SLF001


async def test_send_command_and_wait_stamps_user_command_on_handle() -> None:
    """send_command_and_wait must call handle.record_user_command() before waiting for response."""
    import time

    client = MammotionClient()
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    handle = make_handle("dev1", "Luba-TS2")
    await handle.add_transport(mqtt)
    await client._device_registry.register(handle)

    handle._last_user_command_monotonic = 0.0  # noqa: SLF001

    with pytest.raises(Exception):  # noqa: BLE001
        await client.send_command_and_wait("Luba-TS2", "start_job", "some_field", send_timeout=0.01)

    assert time.monotonic() - handle._last_user_command_monotonic < 5.0  # noqa: SLF001


async def test_internal_subscription_does_not_stamp_user_command() -> None:
    """Internal subscription sends must NOT update _last_user_command_monotonic.

    If _send_one_shot_report stamped the timestamp, the poll loop would
    never enter long-idle mode.
    """
    handle = make_handle("dev1", "Luba-NoStamp")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    await handle.add_transport(mqtt)

    handle._last_user_command_monotonic = 0.0  # noqa: SLF001

    await handle._send_one_shot_report()  # noqa: SLF001

    assert handle._last_user_command_monotonic == 0.0  # noqa: SLF001


async def test_send_command_with_args_record_cmd_false_does_not_stamp() -> None:
    """send_command_with_args with _record_cmd=False must not update the user-command timestamp."""
    client = MammotionClient()
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    handle = make_handle("dev1", "Luba-NR")
    await handle.add_transport(mqtt)
    await client._device_registry.register(handle)

    sentinel = 0.0
    handle._last_user_command_monotonic = sentinel  # noqa: SLF001

    await client.send_command_with_args("Luba-NR", "start_job", _record_cmd=False)

    assert handle._last_user_command_monotonic == sentinel  # noqa: SLF001


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


# ---------------------------------------------------------------------------
# handle._poll_interval() — poll interval selection tests
# ---------------------------------------------------------------------------

from pymammotion.device.handle import (  # noqa: E402
    _BLE_POLL_INTERVAL,
    _KEEP_ALIVE_BLE_INTERVAL,
    _MQTT_POLL_INTERVAL,
    _RATE_LIMITED_BACKOFF,
    _DeviceMode,
)


def _make_handle_for_poll(transport_type: TransportType | None) -> DeviceHandle:
    handle = make_handle("dev1", "Luba-Poll")
    handle.snapshot.raw.report_data.dev.sys_status = 0
    handle.snapshot.raw.report_data.dev.battery_val = 0
    handle.snapshot.raw.report_data.dev.charge_state = 0
    if transport_type is not None:
        t = _make_connected_transport(transport_type)
        handle._transports[transport_type] = t  # noqa: SLF001
    return handle


async def test_poll_interval_mowing_returns_fifteen_minutes() -> None:
    from pymammotion.utility.constant import WorkMode

    handle = _make_handle_for_poll(TransportType.CLOUD_ALIYUN)
    handle.snapshot.raw.report_data.dev.sys_status = WorkMode.MODE_WORKING.value
    assert handle._poll_interval() == _MQTT_POLL_INTERVAL[_DeviceMode.ACTIVE]  # noqa: SLF001
    assert handle._device_mode() is _DeviceMode.ACTIVE  # noqa: SLF001


async def test_poll_interval_returning_returns_fifteen_minutes() -> None:
    from pymammotion.utility.constant import WorkMode

    handle = _make_handle_for_poll(TransportType.CLOUD_ALIYUN)
    handle.snapshot.raw.report_data.dev.sys_status = WorkMode.MODE_RETURNING.value
    assert handle._poll_interval() == _MQTT_POLL_INTERVAL[_DeviceMode.ACTIVE]  # noqa: SLF001


async def test_poll_interval_idle_returns_fifteen_minutes() -> None:
    """sys_status=0 with no charge → IDLE (paused/lost) → 15 min for MQTT."""
    handle = _make_handle_for_poll(TransportType.CLOUD_ALIYUN)
    handle.snapshot.raw.report_data.dev.sys_status = 0
    assert handle._device_mode() is _DeviceMode.IDLE  # noqa: SLF001
    assert handle._poll_interval() == _MQTT_POLL_INTERVAL[_DeviceMode.IDLE]  # noqa: SLF001


async def test_poll_interval_docked_charging_returns_thirty_minutes() -> None:
    handle = _make_handle_for_poll(TransportType.CLOUD_ALIYUN)
    handle.snapshot.raw.report_data.dev.sys_status = 0
    handle.snapshot.raw.report_data.dev.battery_val = 80
    handle.snapshot.raw.report_data.dev.charge_state = 1
    assert handle._device_mode() is _DeviceMode.DOCKED_CHARGING  # noqa: SLF001
    assert handle._poll_interval() == _MQTT_POLL_INTERVAL[_DeviceMode.DOCKED_CHARGING]  # noqa: SLF001


async def test_poll_interval_docked_full_returns_sixty_minutes() -> None:
    handle = _make_handle_for_poll(TransportType.CLOUD_ALIYUN)
    handle.snapshot.raw.report_data.dev.sys_status = 0
    handle.snapshot.raw.report_data.dev.battery_val = 100
    handle.snapshot.raw.report_data.dev.charge_state = 1
    assert handle._device_mode() is _DeviceMode.DOCKED_FULL  # noqa: SLF001
    assert handle._poll_interval() == _MQTT_POLL_INTERVAL[_DeviceMode.DOCKED_FULL]  # noqa: SLF001


async def test_ble_poll_interval_table_values() -> None:
    """ACTIVE → continuous stream (None); other modes → numeric count=1 cadences."""
    assert _BLE_POLL_INTERVAL[_DeviceMode.ACTIVE] is None
    assert _BLE_POLL_INTERVAL[_DeviceMode.DOCKED_CHARGING] == 5 * 60.0
    assert _BLE_POLL_INTERVAL[_DeviceMode.DOCKED_FULL] == 30 * 60.0
    assert _BLE_POLL_INTERVAL[_DeviceMode.IDLE] == 15 * 60.0


# ---------------------------------------------------------------------------
# Offline / loop-exit behaviour
# ---------------------------------------------------------------------------


async def test_poll_loop_sends_after_silence() -> None:
    """After the interval elapses without incoming data, the loop sends a one-shot poll."""
    handle = make_handle("dev1", "Luba-Poll")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    await handle.add_transport(mqtt)

    one_shot_mock = AsyncMock()

    async def _send_and_stop() -> None:
        handle._stopping = True  # noqa: SLF001
        await one_shot_mock()

    with (
        patch.object(handle, "_sleep_or_rearm", AsyncMock(return_value=False)),
        patch.object(handle, "_send_one_shot_report", AsyncMock(side_effect=_send_and_stop)),
    ):
        await asyncio.wait_for(handle._mqtt_activity_loop(), timeout=2.0)

    one_shot_mock.assert_awaited_once()


async def test_poll_loop_rate_limited_no_ble_backs_off() -> None:
    """When MQTT is rate-limited and no BLE is connected, the loop backs off."""
    handle = make_handle("dev1", "Luba-RL3")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    mqtt.is_rate_limited = True
    await handle.add_transport(mqtt)

    sleep_seconds: list[float] = []

    async def _record_sleep(s: float) -> bool:
        sleep_seconds.append(s)
        handle._stopping = True  # noqa: SLF001
        return False

    one_shot_mock = AsyncMock()

    with (
        patch.object(handle, "_sleep_or_rearm", AsyncMock(side_effect=_record_sleep)),
        patch.object(handle, "_send_one_shot_report", one_shot_mock),
    ):
        await asyncio.wait_for(handle._mqtt_activity_loop(), timeout=2.0)

    one_shot_mock.assert_not_awaited()
    assert any(s >= _RATE_LIMITED_BACKOFF for s in sleep_seconds)


async def test_poll_loop_rate_limited_with_ble_still_polls() -> None:
    """MQTT rate-limited but BLE is connected — MQTT poll loop still falls through to BLE.

    The BLE polling loop is suppressed for this test (we patch its starter) so we
    isolate the MQTT loop's behaviour: the rate-limit backoff path must NOT trigger
    when a BLE transport is registered, and the loop must call _send_one_shot_report.
    """
    handle = make_handle("dev1", "Luba-RLBLE")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    mqtt.is_rate_limited = True
    ble = _make_connected_transport(TransportType.BLE)
    # Suppress the auto-start of BLE keepalive + polling loops so they don't race
    # with the MQTT loop under test (the polling loop would set _ble_stream_active
    # and force MQTT to defer).
    with (
        patch.object(handle, "_start_ble_loop"),
        patch.object(handle, "_start_ble_polling_loop"),
    ):
        await handle.add_transport(mqtt)
        await handle.add_transport(ble)

    one_shot_mock = AsyncMock()

    async def _send_and_stop() -> None:
        handle._stopping = True  # noqa: SLF001
        await one_shot_mock()

    with (
        patch.object(handle, "_sleep_or_rearm", AsyncMock(return_value=False)),
        patch.object(handle, "_send_one_shot_report", AsyncMock(side_effect=_send_and_stop)),
    ):
        await asyncio.wait_for(handle._mqtt_activity_loop(), timeout=2.0)
        await handle.stop()

    one_shot_mock.assert_awaited_once()


async def test_poll_loop_defers_while_ble_stream_active() -> None:
    """When BLE polling loop has the continuous stream active, MQTT loop must defer."""
    handle = make_handle("dev1", "Luba-Defer")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    with patch.object(handle, "_start_ble_polling_loop"):
        await handle.add_transport(mqtt)

    handle._ble_stream_active = True  # noqa: SLF001 — simulate stream feeding

    one_shot_mock = AsyncMock()
    sleep_calls: list[float] = []

    async def _record_and_stop(seconds: float) -> bool:
        sleep_calls.append(seconds)
        handle._stopping = True  # noqa: SLF001
        return False

    with (
        patch.object(handle, "_sleep_or_rearm", AsyncMock(side_effect=_record_and_stop)),
        patch.object(handle, "_send_one_shot_report", one_shot_mock),
    ):
        await asyncio.wait_for(handle._mqtt_activity_loop(), timeout=2.0)

    one_shot_mock.assert_not_awaited()
    assert sleep_calls, "MQTT loop should have entered _sleep_or_rearm"


async def test_poll_loop_skips_during_saga() -> None:
    """While a saga is active the loop defers the poll."""
    handle = make_handle("dev1", "Luba-Saga")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    await handle.add_transport(mqtt)

    one_shot_mock = AsyncMock()
    sleep_count = 0

    async def _counting_sleep(s: float) -> bool:
        nonlocal sleep_count
        sleep_count += 1
        handle._stopping = True  # noqa: SLF001
        return False

    from pymammotion.messaging.command_queue import DeviceCommandQueue

    with (
        patch.object(handle, "_sleep_or_rearm", AsyncMock(side_effect=_counting_sleep)),
        patch.object(handle, "_send_one_shot_report", one_shot_mock),
        patch.object(type(handle.queue), "is_saga_active", new_callable=lambda: property(lambda _: True)),
    ):
        await asyncio.wait_for(handle._mqtt_activity_loop(), timeout=2.0)

    one_shot_mock.assert_not_awaited()
    assert sleep_count >= 1


async def test_update_availability_restarts_loop_on_reconnect() -> None:
    """update_availability must restart the activity loop when transitioning to CONNECTED."""
    from pymammotion.transport.base import TransportAvailability

    handle = make_handle("dev1", "Luba-Rec")
    handle.restart_keep_alive = AsyncMock()  # type: ignore[method-assign]

    # Start from disconnected.
    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.DISCONNECTED)
    from pymammotion.state.device_state import DeviceConnectionState
    assert handle.availability.connection_state != DeviceConnectionState.CONNECTED

    # Transition to connected → loop should restart.
    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED)
    await asyncio.sleep(0)  # let the created task execute

    handle.restart_keep_alive.assert_awaited_once()


# ---------------------------------------------------------------------------
# send_raw sets _rate_limited on TooManyRequestsException
# ---------------------------------------------------------------------------


async def test_send_raw_sets_rate_limited_on_too_many_requests() -> None:
    """send_raw must call transport.set_rate_limited() when the transport raises TooManyRequestsException."""
    from pymammotion.aliyun.exceptions import TooManyRequestsException

    handle = make_handle("dev1", "Luba-RL")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    mqtt.send = AsyncMock(side_effect=TooManyRequestsException("rate limited", "iot-id"))
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    await handle.send_raw(b"\x00")
    mqtt.set_rate_limited.assert_called_once()


# ---------------------------------------------------------------------------
# BLE-connect failure → MQTT fallback (regression: ESPHome proxy out of slots)
# ---------------------------------------------------------------------------


async def test_send_raw_ble_connect_failure_falls_back_to_mqtt() -> None:
    """When BLE.connect() raises BLEUnavailableError but MQTT is registered,
    send_raw must route the payload through MQTT instead of dropping it.

    Reproduces the production symptom (HA log 2026-05-02): ESPHome BLE proxy
    out of connection slots → ``BLEUnavailableError`` → request silently lost.
    """
    from pymammotion.transport.base import BLEUnavailableError

    handle = make_handle("dev1", "Luba-FB-MQTT")
    handle._prefer_ble = True  # noqa: SLF001 — force BLE-first path

    ble = _make_connected_transport(TransportType.BLE)
    ble.is_connected = False
    ble.connect = AsyncMock(side_effect=BLEUnavailableError("proxy out of slots"))

    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)

    handle._transports[TransportType.BLE] = ble  # noqa: SLF001
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    await handle.send_raw(b"\xAB\xCD", prefer_ble=True)

    # Must have attempted BLE reconnect (and failed), then sent via MQTT.
    ble.connect.assert_awaited_once()
    mqtt.send.assert_awaited_once_with(b"\xAB\xCD", iot_id="")
    ble.send.assert_not_awaited()


async def test_send_raw_ble_connect_failure_no_mqtt_propagates() -> None:
    """When BLE.connect() fails AND no MQTT is registered, send_raw must raise."""
    import pytest

    from pymammotion.transport.base import BLEUnavailableError

    handle = make_handle("dev1", "Luba-NoMQTT")
    handle._prefer_ble = True  # noqa: SLF001

    ble = _make_connected_transport(TransportType.BLE)
    ble.is_connected = False
    ble.connect = AsyncMock(side_effect=BLEUnavailableError("proxy out of slots"))
    handle._transports[TransportType.BLE] = ble  # noqa: SLF001

    with pytest.raises(BLEUnavailableError):
        await handle.send_raw(b"\xAB\xCD", prefer_ble=True)


async def test_send_raw_ble_connect_failure_mqtt_offline_propagates() -> None:
    """When BLE.connect() fails AND MQTT is reported offline, send_raw must raise."""
    import pytest

    from pymammotion.state.device_state import DeviceAvailability
    from pymammotion.transport.base import BLEUnavailableError

    handle = make_handle("dev1", "Luba-MQTTOff")
    handle._prefer_ble = True  # noqa: SLF001
    # Mark MQTT as cloud-reported-offline so it's registered but unusable.
    handle._availability = DeviceAvailability(  # noqa: SLF001
        ble=handle._availability.ble,  # noqa: SLF001
        mqtt=handle._availability.mqtt,  # noqa: SLF001
        mqtt_reported_offline=True,
    )

    ble = _make_connected_transport(TransportType.BLE)
    ble.is_connected = False
    ble.connect = AsyncMock(side_effect=BLEUnavailableError("proxy out of slots"))
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)

    handle._transports[TransportType.BLE] = ble  # noqa: SLF001
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    with pytest.raises(BLEUnavailableError):
        await handle.send_raw(b"\xAB\xCD", prefer_ble=True)
    mqtt.send.assert_not_awaited()


# ---------------------------------------------------------------------------
# is_usable gate — active_transport / send_raw must skip BLE when not usable
# ---------------------------------------------------------------------------


async def test_active_transport_skips_ble_when_not_usable() -> None:
    """Disconnected + not-usable BLE (in cooldown) must not be returned by active_transport."""
    handle = make_handle("dev1", "Luba-Cooldown")

    ble = _make_connected_transport(TransportType.BLE)
    ble.is_connected = False
    ble.is_usable = False  # simulate cooldown / no cached BLEDevice
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)

    handle._transports[TransportType.BLE] = ble  # noqa: SLF001
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    chosen = handle.active_transport(prefer_ble=True)
    assert chosen is mqtt  # BLE preferred but unusable → MQTT


async def test_send_raw_skips_ble_reconnect_when_not_usable() -> None:
    """When BLE is registered+disconnected but unusable, send_raw must NOT call ble.connect()."""
    handle = make_handle("dev1", "Luba-NoUsableBLE")
    handle._prefer_ble = True  # noqa: SLF001

    ble = _make_connected_transport(TransportType.BLE)
    ble.is_connected = False
    ble.is_usable = False  # cooldown / no device
    ble.connect = AsyncMock()  # would normally be invoked — assert it isn't
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)

    handle._transports[TransportType.BLE] = ble  # noqa: SLF001
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    await handle.send_raw(b"\xCA\xFE", prefer_ble=True)

    ble.connect.assert_not_awaited()  # <- the whole point of the gate
    mqtt.send.assert_awaited_once_with(b"\xCA\xFE", iot_id="")
    ble.send.assert_not_awaited()


# ---------------------------------------------------------------------------
# MammotionClient.update_ble_device / clear_ble_device
# ---------------------------------------------------------------------------


async def test_update_ble_device_returns_true_on_first_set_false_on_same_address() -> None:
    """update_ble_device propagates the change-detection bool from BLETransport.set_ble_device."""
    from bleak import BLEDevice

    from pymammotion.transport.ble import BLETransport, BLETransportConfig

    client = MammotionClient()
    handle = make_handle("Luba-Update", "Luba-Update")
    await client._device_registry.register(handle)  # noqa: SLF001

    # Wire a real BLETransport (not a mock) so set_ble_device returns the proper bool.
    transport = BLETransport(BLETransportConfig(device_id="Luba-Update"))
    await handle.add_transport(transport)

    dev1 = MagicMock(spec=BLEDevice)
    dev1.address = "AA:BB:CC:DD:EE:FF"
    dev2 = MagicMock(spec=BLEDevice)
    dev2.address = "AA:BB:CC:DD:EE:FF"  # same address, different instance
    dev3 = MagicMock(spec=BLEDevice)
    dev3.address = "11:22:33:44:55:66"  # different address

    assert await client.update_ble_device("Luba-Update", dev1) is True
    assert await client.update_ble_device("Luba-Update", dev2) is False  # same address
    assert await client.update_ble_device("Luba-Update", dev3) is True   # different address

    await handle.stop()


async def test_clear_ble_device_resets_transport_state() -> None:
    """MammotionClient.clear_ble_device clears the cached BLEDevice on the transport."""
    from bleak import BLEDevice

    from pymammotion.transport.ble import BLETransport, BLETransportConfig

    client = MammotionClient()
    handle = make_handle("Luba-Clear", "Luba-Clear")
    await client._device_registry.register(handle)  # noqa: SLF001

    transport = BLETransport(BLETransportConfig(device_id="Luba-Clear"))
    dev = MagicMock(spec=BLEDevice)
    dev.address = "AA:BB:CC:DD:EE:FF"
    transport.set_ble_device(dev)
    await handle.add_transport(transport)

    assert transport.is_usable is True
    await client.clear_ble_device("Luba-Clear")
    assert transport.is_usable is False
    assert transport.ble_address is None

    await handle.stop()


async def test_clear_ble_device_no_handle_is_noop() -> None:
    """clear_ble_device on an unknown device id silently does nothing."""
    client = MammotionClient()
    await client.clear_ble_device("does-not-exist")  # must not raise


# ---------------------------------------------------------------------------
# add_ble_only_device — accepts ble_device or ble_address, requires one
# ---------------------------------------------------------------------------


async def test_add_ble_only_device_requires_ble_device_or_address() -> None:
    """Neither ble_device nor ble_address → ValueError."""
    from pymammotion.data.model.device import MowingDevice

    client = MammotionClient()
    with pytest.raises(ValueError, match="ble_device or ble_address"):
        await client.add_ble_only_device(
            device_id="x",
            device_name="x",
            initial_device=MowingDevice(name="x"),
        )


async def test_add_ble_only_device_with_address_enables_self_managed_scanning() -> None:
    """ble_address-only call defaults self_managed_scanning=True on the transport."""
    from pymammotion.data.model.device import MowingDevice
    from pymammotion.transport.ble import BLETransport

    client = MammotionClient()
    handle = await client.add_ble_only_device(
        device_id="luba-ble-1",
        device_name="luba-ble-1",
        initial_device=MowingDevice(name="luba-ble-1"),
        ble_address="AA:BB:CC:DD:EE:FF",
    )
    transport = handle.get_transport(TransportType.BLE)
    assert isinstance(transport, BLETransport)
    assert transport._config.self_managed_scanning is True  # noqa: SLF001
    assert transport._config.ble_address == "AA:BB:CC:DD:EE:FF"  # noqa: SLF001
    # No BLEDevice cached yet — connect() will trigger a scan.
    assert transport.ble_address is None


async def test_add_ble_only_device_with_ble_device_disables_self_managed_scanning() -> None:
    """ble_device-only call defaults self_managed_scanning=False (caller owns scanning)."""
    from bleak import BLEDevice

    from pymammotion.data.model.device import MowingDevice
    from pymammotion.transport.ble import BLETransport

    client = MammotionClient()
    fake_device = MagicMock(spec=BLEDevice)
    fake_device.address = "11:22:33:44:55:66"

    handle = await client.add_ble_only_device(
        device_id="luba-ble-2",
        device_name="luba-ble-2",
        initial_device=MowingDevice(name="luba-ble-2"),
        ble_device=fake_device,
    )
    transport = handle.get_transport(TransportType.BLE)
    assert isinstance(transport, BLETransport)
    assert transport._config.self_managed_scanning is False  # noqa: SLF001
    assert transport.ble_address == "11:22:33:44:55:66"
