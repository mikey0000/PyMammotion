"""Tests for MammotionClient (Wave 4 top-level API)."""
from __future__ import annotations

import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, PropertyMock, patch

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import (
    DeviceRecords,
    JWTTokenInfo,
    LoginResponseData,
    LoginResponseUserInformation,
    MQTTConnection,
    Response,
)
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


async def test_remove_device_unregisters_handle() -> None:
    """remove_device() must stop and remove the handle from the registry."""
    client = MammotionClient()

    handle = make_handle("dev1", "Luba-One")
    handle.stop = AsyncMock()  # type: ignore[method-assign]
    await client._device_registry.register(handle)

    assert client._device_registry.get_by_name("Luba-One") is handle

    await client.remove_device("Luba-One")

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
    mqtt_transport.last_send_monotonic = 0.0
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
    t.last_send_monotonic = 0.0
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

    with patch("pymammotion.client.MowPathSaga") as MockSaga:
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








def _access_token(iot: str, robot: str) -> str:
    """Mint an unsigned-verifiable access token carrying the iot/robot/exp claims.

    ``MammotionHTTP.response``'s setter decodes the access_token to seed
    ``jwt_info`` and ``expires_in``, so a populated http needs a real JWT.
    """
    import jwt as pyjwt

    return pyjwt.encode({"iot": iot, "robot": robot, "exp": 9999999999}, "x" * 32, algorithm="HS256")


def _populated_mammotion_http(account: str = "user@test.com") -> MammotionHTTP:
    """Return a MammotionHTTP populated as it would be after a successful login.

    Carries a login response, MQTT credentials, and JWT info so a ``to_cache`` →
    restore round-trip has something to preserve.  The explicit ``jwt_info``
    intentionally differs from the access_token's claims so a round-trip can prove
    the cached JWT (not the token-derived one) is what gets restored.
    """
    user_info = LoginResponseUserInformation(
        areaCode="44", domainAbbreviation="EU", userId="u1", userAccount="123", authType="email"
    )
    login_data = LoginResponseData(
        access_token=_access_token("token-iot.example.com", "token-robot.example.com"),
        token_type="bearer",
        refresh_token="rt",
        expires_in=3600,
        authorization_code="ac",
        userInformation=user_info,
    )
    http = MammotionHTTP(account, "pass")
    http.response = Response(code=0, msg="ok", data=login_data)
    http.login_info = login_data
    http.mqtt_credentials = MQTTConnection(
        host="mqtt.example.com", jwt="jwt-token", client_id="client-1", username="user"
    )
    http.jwt_info = JWTTokenInfo(iot="iot.example.com", robot="robot.example.com")
    return http










# ---------------------------------------------------------------------------
# _bootstrap_mammotion_mqtt — connect() and confirm_share call-count invariants
# ---------------------------------------------------------------------------


def _make_share_record(*, is_receiver: int = 1, status: int = -1, batch_id: str = "batch1", record_id: str = "1") -> MagicMock:
    """Return a MagicMock shaped like a ShareRecord."""
    r = MagicMock()
    r.is_receiver = is_receiver
    r.status = status
    r.batch_id = batch_id
    r.record_id = record_id
    return r


def _make_device_record(device_name: str = "Yuka-TEST", iot_id: str = "iot-yuka", product_key: str = "pk1") -> MagicMock:
    """Return a MagicMock shaped like a DeviceRecord."""
    r = MagicMock()
    r.device_name = device_name
    r.iot_id = iot_id
    r.product_key = product_key
    return r


def _make_mock_http(
    *,
    device_records: list[MagicMock] | None = None,
    share_records: list[MagicMock] | None = None,
    mqtt_creds: MagicMock | None = None,
) -> MagicMock:
    """Return a MagicMock shaped like MammotionHTTP with the given fixture data."""
    http = MagicMock()
    http.get_user_device_list = AsyncMock(return_value=MagicMock(data=[]))
    http.get_user_shared_device_page = AsyncMock(
        return_value=MagicMock(data=MagicMock(records=share_records or []))
    )
    # get_user_device_page both returns data AND updates http.device_records (side-effect)
    page_data = MagicMock()
    page_data.records = device_records or []
    page_resp = MagicMock()
    page_resp.data = page_data
    http.get_user_device_page = AsyncMock(return_value=page_resp)
    http.get_mqtt_credentials = AsyncMock()
    http.confirm_share = AsyncMock()
    http.mqtt_credentials = mqtt_creds or MagicMock()
    http.login_info = MagicMock()
    return http














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
    t.last_send_monotonic = 0.0
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

    ble.send.assert_awaited_once_with(fake_bytes, iot_id="", firmware_version=ANY)
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

    ble.send.assert_awaited_once_with(fake_bytes, iot_id="", firmware_version=ANY)
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

    mqtt.send.assert_awaited_once_with(fake_bytes, iot_id="", firmware_version=ANY)
    ble.send.assert_not_awaited()


async def test_send_command_with_args_prefer_ble_sends_over_mqtt_and_warms_ble() -> None:
    """When prefer_ble=True and BLE is disconnected, the command goes over the working MQTT now.

    BLE connection is a background task: the command is not blocked on it.  The command uses
    the connected MQTT immediately while BLE reconnects in the background for later sends.
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
        await asyncio.sleep(0)  # let the background BLE connect run
    finally:
        patcher.stop()

    # Command went over the working MQTT; BLE reconnect happened in the background.
    mqtt.send.assert_awaited_once_with(fake_bytes, iot_id="", firmware_version=ANY)
    ble.send.assert_not_awaited()
    ble.connect.assert_awaited_once()


# ---------------------------------------------------------------------------
# set_scheduled_updates: transport lifecycle
# ---------------------------------------------------------------------------


async def test_set_scheduled_updates_false_disconnects_all_transports() -> None:
    """set_scheduled_updates(enabled=False) must disconnect all transport types.

    Cloud transports are routed through ``handle.disconnect_transport``; BLE is
    disconnected directly on the transport (gated by ``is_usable``).
    """
    client = MammotionClient()
    handle = make_handle("dev1", "Luba-Sched")
    ble = _make_connected_transport(TransportType.BLE)
    ble.connect = AsyncMock()
    await handle.add_transport(ble)
    handle.connect_transport = AsyncMock()  # type: ignore[method-assign]
    handle.disconnect_transport = AsyncMock()  # type: ignore[method-assign]
    await client._device_registry.register(handle)

    await client.set_scheduled_updates("Luba-Sched", enabled=False)

    disconnected = [call.args[0] for call in handle.disconnect_transport.await_args_list]
    assert TransportType.CLOUD_ALIYUN in disconnected
    assert TransportType.CLOUD_MAMMOTION in disconnected
    ble.disconnect.assert_awaited_once()
    ble.connect.assert_not_awaited()
    handle.connect_transport.assert_not_awaited()


async def test_set_scheduled_updates_true_connects_all_transports() -> None:
    """set_scheduled_updates(enabled=True) must reconnect all transport types.

    Cloud transports are routed through ``handle.connect_transport``; BLE is
    connected directly on the transport (gated by ``is_usable``).
    """
    client = MammotionClient()
    handle = make_handle("dev1", "Luba-Sched2")
    ble = _make_connected_transport(TransportType.BLE)
    ble.connect = AsyncMock()
    await handle.add_transport(ble)
    handle.connect_transport = AsyncMock()  # type: ignore[method-assign]
    handle.disconnect_transport = AsyncMock()  # type: ignore[method-assign]
    await client._device_registry.register(handle)

    await client.set_scheduled_updates("Luba-Sched2", enabled=True)

    connected = [call.args[0] for call in handle.connect_transport.await_args_list]
    assert TransportType.CLOUD_ALIYUN in connected
    assert TransportType.CLOUD_MAMMOTION in connected
    ble.connect.assert_awaited_once()
    ble.disconnect.assert_not_awaited()
    handle.disconnect_transport.assert_not_awaited()


async def test_set_scheduled_updates_skips_ble_when_not_usable() -> None:
    """When BLE exists but ``is_usable`` is False (e.g. cooldown), it must be skipped."""
    client = MammotionClient()
    handle = make_handle("dev1", "Luba-Sched3")
    ble = _make_connected_transport(TransportType.BLE)
    ble.is_usable = False
    ble.connect = AsyncMock()
    await handle.add_transport(ble)
    await client._device_registry.register(handle)

    await client.set_scheduled_updates("Luba-Sched3", enabled=True)
    await client.set_scheduled_updates("Luba-Sched3", enabled=False)

    ble.connect.assert_not_awaited()
    ble.disconnect.assert_not_awaited()


async def test_set_scheduled_updates_noop_for_unknown_device() -> None:
    """set_scheduled_updates must silently do nothing for an unregistered device name."""
    client = MammotionClient()
    await client.set_scheduled_updates("ghost-device", enabled=False)
    await client.set_scheduled_updates("ghost-device", enabled=True)


# ---------------------------------------------------------------------------
# User-command recording: send_command_* wakes the poll loop via _rearm_event
# ---------------------------------------------------------------------------


async def test_send_command_with_args_stamps_user_command_on_handle() -> None:
    """send_command_with_args must call handle.record_user_command() (sets _rearm_event)."""
    client = MammotionClient()
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    handle = make_handle("dev1", "Luba-TS")
    await handle.add_transport(mqtt)
    await client._device_registry.register(handle)

    handle._rearm_event.clear()  # noqa: SLF001

    await client.send_command_with_args("Luba-TS", "start_job")

    assert handle._rearm_event.is_set()  # noqa: SLF001


async def test_send_command_and_wait_stamps_user_command_on_handle() -> None:
    """send_command_and_wait must call handle.record_user_command() before waiting for response."""
    client = MammotionClient()
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    handle = make_handle("dev1", "Luba-TS2")
    await handle.add_transport(mqtt)
    await client._device_registry.register(handle)

    handle._rearm_event.clear()  # noqa: SLF001

    with pytest.raises(Exception):  # noqa: BLE001
        await client.send_command_and_wait("Luba-TS2", "start_job", "some_field", send_timeout=0.01)

    assert handle._rearm_event.is_set()  # noqa: SLF001


async def test_internal_subscription_does_not_stamp_user_command() -> None:
    """Internal subscription sends must NOT call record_user_command (no _rearm_event set).

    If _send_one_shot_report woke the poll loop, it would never enter
    long-idle mode.
    """
    handle = make_handle("dev1", "Luba-NoStamp")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    await handle.add_transport(mqtt)

    handle._rearm_event.clear()  # noqa: SLF001

    await handle._send_one_shot_report()  # noqa: SLF001

    assert not handle._rearm_event.is_set()  # noqa: SLF001


async def test_send_command_with_args_record_cmd_false_does_not_stamp() -> None:
    """send_command_with_args with _record_cmd=False must not call record_user_command."""
    client = MammotionClient()
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    handle = make_handle("dev1", "Luba-NR")
    await handle.add_transport(mqtt)
    await client._device_registry.register(handle)

    handle._rearm_event.clear()  # noqa: SLF001

    await client.send_command_with_args("Luba-NR", "start_job", _record_cmd=False)

    assert not handle._rearm_event.is_set()  # noqa: SLF001


async def test_send_command_with_args_prefer_ble_uses_mqtt_while_ble_connect_pending() -> None:
    """prefer_ble=True with a BLE that stays disconnected: the command uses MQTT (the working link).

    The background BLE connect is attempted but does not complete here (mock stays disconnected),
    so active_transport keeps choosing MQTT.  The command is never blocked or dropped.
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
        await asyncio.sleep(0)  # let the background BLE connect run
    finally:
        patcher.stop()

    mqtt.send.assert_awaited_once_with(fake_bytes, iot_id="", firmware_version=ANY)
    ble.send.assert_not_awaited()
    ble.connect.assert_awaited_once()  # background warm-up attempted


# ---------------------------------------------------------------------------
# handle._poll_interval() — poll interval selection tests
# ---------------------------------------------------------------------------

from pymammotion.device.ble_loop import _BLE_POLL_INTERVAL, _KEEP_ALIVE_BLE_INTERVAL  # noqa: E402
from pymammotion.device.modes import _DeviceMode  # noqa: E402
from pymammotion.device.mqtt_loop import (  # noqa: E402
    _MQTT_POLL_INTERVAL,
    _RATE_LIMITED_BACKOFF,
    mqtt_activity_loop,
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
    assert handle.device_mode() is _DeviceMode.ACTIVE  # noqa: SLF001


async def test_poll_interval_returning_returns_fifteen_minutes() -> None:
    from pymammotion.utility.constant import WorkMode

    handle = _make_handle_for_poll(TransportType.CLOUD_ALIYUN)
    handle.snapshot.raw.report_data.dev.sys_status = WorkMode.MODE_RETURNING.value
    assert handle._poll_interval() == _MQTT_POLL_INTERVAL[_DeviceMode.ACTIVE]  # noqa: SLF001


async def test_poll_interval_idle_returns_fifteen_minutes() -> None:
    """sys_status=0 with no charge → IDLE (paused/lost) → 15 min for MQTT."""
    handle = _make_handle_for_poll(TransportType.CLOUD_ALIYUN)
    handle.snapshot.raw.report_data.dev.sys_status = 0
    assert handle.device_mode() is _DeviceMode.IDLE  # noqa: SLF001
    assert handle._poll_interval() == _MQTT_POLL_INTERVAL[_DeviceMode.IDLE]  # noqa: SLF001


async def test_poll_interval_docked_charging_returns_thirty_minutes() -> None:
    handle = _make_handle_for_poll(TransportType.CLOUD_ALIYUN)
    handle.snapshot.raw.report_data.dev.sys_status = 0
    handle.snapshot.raw.report_data.dev.battery_val = 80
    handle.snapshot.raw.report_data.dev.charge_state = 1
    assert handle.device_mode() is _DeviceMode.DOCKED_CHARGING  # noqa: SLF001
    assert handle._poll_interval() == _MQTT_POLL_INTERVAL[_DeviceMode.DOCKED_CHARGING]  # noqa: SLF001


async def test_poll_interval_docked_full_returns_sixty_minutes() -> None:
    handle = _make_handle_for_poll(TransportType.CLOUD_ALIYUN)
    handle.snapshot.raw.report_data.dev.sys_status = 0
    handle.snapshot.raw.report_data.dev.battery_val = 100
    handle.snapshot.raw.report_data.dev.charge_state = 1
    assert handle.device_mode() is _DeviceMode.DOCKED_FULL  # noqa: SLF001
    assert handle._poll_interval() == _MQTT_POLL_INTERVAL[_DeviceMode.DOCKED_FULL]  # noqa: SLF001


async def test_ble_poll_interval_table_values() -> None:
    """ACTIVE → continuous stream (None); other modes → numeric count=1 cadences."""
    assert _BLE_POLL_INTERVAL[_DeviceMode.ACTIVE] is None
    assert _BLE_POLL_INTERVAL[_DeviceMode.DOCKED_CHARGING] == 60.0
    assert _BLE_POLL_INTERVAL[_DeviceMode.DOCKED_FULL] == 5 * 60.0
    assert _BLE_POLL_INTERVAL[_DeviceMode.IDLE] == 5 * 60.0


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
        patch.object(handle, "sleep_or_rearm", AsyncMock(return_value=False)),
        patch.object(handle, "_send_one_shot_report", AsyncMock(side_effect=_send_and_stop)),
    ):
        await asyncio.wait_for(mqtt_activity_loop(handle), timeout=2.0)

    one_shot_mock.assert_awaited_once()


async def test_poll_loop_rate_limited_no_ble_backs_off() -> None:
    """When MQTT is rate-limited and no BLE is connected, the loop backs off."""
    handle = make_handle("dev1", "Luba-RL3")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    mqtt.is_rate_limited = True
    # The loop now backs off only until sends are available again; a full cloud ban still
    # caps at _RATE_LIMITED_BACKOFF.
    mqtt.seconds_until_send_available = MagicMock(return_value=_RATE_LIMITED_BACKOFF)
    await handle.add_transport(mqtt)

    sleep_seconds: list[float] = []

    async def _record_sleep(s: float) -> bool:
        sleep_seconds.append(s)
        handle._stopping = True  # noqa: SLF001
        return False

    one_shot_mock = AsyncMock()

    with (
        patch.object(handle, "sleep_or_rearm", AsyncMock(side_effect=_record_sleep)),
        patch.object(handle, "_send_one_shot_report", one_shot_mock),
    ):
        await asyncio.wait_for(mqtt_activity_loop(handle), timeout=2.0)

    one_shot_mock.assert_not_awaited()
    assert sleep_seconds == [_RATE_LIMITED_BACKOFF]


async def test_poll_loop_rate_limited_backoff_shortens_to_window_release() -> None:
    """The backoff resumes as soon as the rolling window will clear, not a flat 12 h."""
    handle = make_handle("dev1", "Luba-RL4")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    mqtt.is_rate_limited = True
    mqtt.seconds_until_send_available = MagicMock(return_value=300.0)  # window clears in 5 min
    await handle.add_transport(mqtt)

    sleep_seconds: list[float] = []

    async def _record_sleep(s: float) -> bool:
        sleep_seconds.append(s)
        handle._stopping = True  # noqa: SLF001
        return False

    with (
        patch.object(handle, "sleep_or_rearm", AsyncMock(side_effect=_record_sleep)),
        patch.object(handle, "_send_one_shot_report", AsyncMock()),
    ):
        await asyncio.wait_for(mqtt_activity_loop(handle), timeout=2.0)

    assert sleep_seconds == [300.0]  # not _RATE_LIMITED_BACKOFF


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
        patch.object(handle, "sleep_or_rearm", AsyncMock(return_value=False)),
        patch.object(handle, "_send_one_shot_report", AsyncMock(side_effect=_send_and_stop)),
    ):
        await asyncio.wait_for(mqtt_activity_loop(handle), timeout=2.0)
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
        patch.object(handle, "sleep_or_rearm", AsyncMock(side_effect=_record_and_stop)),
        patch.object(handle, "_send_one_shot_report", one_shot_mock),
    ):
        await asyncio.wait_for(mqtt_activity_loop(handle), timeout=2.0)

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
        patch.object(handle, "sleep_or_rearm", AsyncMock(side_effect=_counting_sleep)),
        patch.object(handle, "_send_one_shot_report", one_shot_mock),
        patch.object(type(handle.queue), "is_saga_active", new_callable=lambda: property(lambda _: True)),
    ):
        await asyncio.wait_for(mqtt_activity_loop(handle), timeout=2.0)

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
    """A failing background BLE connect must not drop the command: it goes over MQTT.

    Reproduces the production symptom (HA log 2026-05-02): ESPHome BLE proxy out of
    connection slots → ``BLEUnavailableError``.  The connect now runs in the background
    (its error is swallowed by attempt_ble_connection), and the command uses MQTT.
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
    await asyncio.sleep(0)  # let the background BLE connect run (and fail, swallowed)

    # Command sent via MQTT (the working link); BLE reconnect attempted in background.
    mqtt.send.assert_awaited_once_with(b"\xAB\xCD", iot_id="", firmware_version=ANY)
    ble.send.assert_not_awaited()
    ble.connect.assert_awaited_once()


async def test_send_raw_no_usable_transport_propagates() -> None:
    """BLE unusable (cooldown) and no MQTT → send_raw raises NoTransportAvailableError.

    With background connect, a failed connect no longer surfaces as BLEUnavailableError; the
    loud failure now comes from active_transport when nothing is usable to carry the command.
    """
    import pytest

    from pymammotion.transport.base import NoTransportAvailableError

    handle = make_handle("dev1", "Luba-NoMQTT")
    handle._prefer_ble = True  # noqa: SLF001

    ble = _make_connected_transport(TransportType.BLE)
    ble.is_connected = False
    ble.is_usable = False  # cooldown / no cached BLEDevice → not eligible to carry a send
    ble.connect = AsyncMock()
    handle._transports[TransportType.BLE] = ble  # noqa: SLF001

    with pytest.raises(NoTransportAvailableError):
        await handle.send_raw(b"\xAB\xCD", prefer_ble=True)

    ble.connect.assert_not_awaited()  # unusable BLE: no background connect attempted


async def test_send_raw_no_usable_transport_mqtt_offline_propagates() -> None:
    """BLE unusable (cooldown) AND MQTT reported offline → send_raw raises NoTransportAvailableError."""
    import pytest

    from pymammotion.state.device_state import DeviceAvailability
    from pymammotion.transport.base import NoTransportAvailableError

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
    ble.is_usable = False  # cooldown → not eligible to carry a send
    ble.connect = AsyncMock()
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)

    handle._transports[TransportType.BLE] = ble  # noqa: SLF001
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001

    with pytest.raises(NoTransportAvailableError):
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
    mqtt.send.assert_awaited_once_with(b"\xCA\xFE", iot_id="", firmware_version=ANY)
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


# ---------------------------------------------------------------------------
# MQTT loop respects offline state — never polls when no transport is usable
# ---------------------------------------------------------------------------


async def test_poll_loop_never_polls_when_device_reported_offline_and_no_ble() -> None:
    """When the cloud has reported the device offline AND no BLE is registered,
    the MQTT loop must never call _send_one_shot_report — it should only sleep.
    """
    from pymammotion.state.device_state import DeviceAvailability

    handle = make_handle("dev1", "Luba-Offline")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    await handle.add_transport(mqtt)

    # Cloud has marked the device offline.
    handle._availability = DeviceAvailability(  # noqa: SLF001
        ble=handle._availability.ble,  # noqa: SLF001
        mqtt=handle._availability.mqtt,  # noqa: SLF001
        mqtt_reported_offline=True,
    )

    one_shot_mock = AsyncMock()
    sleep_count = 0
    iteration_cap = 5  # bound the test in case the loop misbehaves

    async def _counting_sleep(seconds: float) -> bool:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= iteration_cap:
            handle._stopping = True  # noqa: SLF001
        return False

    with (
        patch.object(handle, "sleep_or_rearm", AsyncMock(side_effect=_counting_sleep)),
        patch.object(handle, "_send_one_shot_report", one_shot_mock),
    ):
        await asyncio.wait_for(mqtt_activity_loop(handle), timeout=2.0)

    # The loop must have looped — we forced 5 sleeps — and never sent a poll.
    assert sleep_count >= iteration_cap
    one_shot_mock.assert_not_awaited()


async def test_poll_loop_resumes_after_mqtt_offline_clears() -> None:
    """When mqtt_reported_offline starts True and is cleared, the next loop tick
    proceeds to _send_one_shot_report.  Validates that the offline gate is dynamic,
    not latched.
    """
    from pymammotion.state.device_state import DeviceAvailability

    handle = make_handle("dev1", "Luba-Recover")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    await handle.add_transport(mqtt)

    # Start offline.
    handle._availability = DeviceAvailability(  # noqa: SLF001
        ble=handle._availability.ble,  # noqa: SLF001
        mqtt=handle._availability.mqtt,  # noqa: SLF001
        mqtt_reported_offline=True,
    )

    sleep_count = 0

    async def _sleep_then_recover(seconds: float) -> bool:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count == 1:
            # Simulate the cloud pushing a thing/status that clears the offline flag.
            handle._availability = DeviceAvailability(  # noqa: SLF001
                ble=handle._availability.ble,  # noqa: SLF001
                mqtt=handle._availability.mqtt,  # noqa: SLF001
                mqtt_reported_offline=False,
            )
        return False

    one_shot_mock = AsyncMock()

    async def _send_and_stop() -> None:
        handle._stopping = True  # noqa: SLF001
        await one_shot_mock()

    with (
        patch.object(handle, "sleep_or_rearm", AsyncMock(side_effect=_sleep_then_recover)),
        patch.object(handle, "_send_one_shot_report", AsyncMock(side_effect=_send_and_stop)),
    ):
        await asyncio.wait_for(mqtt_activity_loop(handle), timeout=2.0)

    one_shot_mock.assert_awaited_once()


async def test_poll_loop_skips_when_ble_only_in_cooldown_and_no_mqtt() -> None:
    """Symmetric case: BLE-only device, BLE transport in cooldown / unusable,
    no MQTT registered — loop must not attempt to send.
    """
    handle = make_handle("dev1", "Luba-BLE-Cooldown")
    ble = _make_connected_transport(TransportType.BLE)
    ble.is_connected = False
    ble.is_usable = False  # simulating cooldown + no cached BLEDevice
    await handle.add_transport(ble)

    one_shot_mock = AsyncMock()
    sleep_count = 0
    iteration_cap = 4

    async def _counting_sleep(seconds: float) -> bool:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= iteration_cap:
            handle._stopping = True  # noqa: SLF001
        return False

    with (
        patch.object(handle, "sleep_or_rearm", AsyncMock(side_effect=_counting_sleep)),
        patch.object(handle, "_send_one_shot_report", one_shot_mock),
    ):
        await asyncio.wait_for(mqtt_activity_loop(handle), timeout=2.0)

    one_shot_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# Centralized offline handling — has_usable_transport + queue log demotion
# ---------------------------------------------------------------------------


async def test_has_usable_transport_false_when_offline_and_no_ble() -> None:
    """has_usable_transport mirrors active_transport: False when MQTT offline + no BLE."""
    from pymammotion.state.device_state import DeviceAvailability

    handle = make_handle("dev1", "Luba-NoTransport")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    await handle.add_transport(mqtt)
    handle._availability = DeviceAvailability(  # noqa: SLF001
        ble=handle._availability.ble,  # noqa: SLF001
        mqtt=handle._availability.mqtt,  # noqa: SLF001
        mqtt_reported_offline=True,
    )

    assert handle.has_usable_transport is False


async def test_has_usable_transport_true_when_mqtt_usable() -> None:
    """has_usable_transport is True with a registered + non-offline MQTT transport."""
    handle = make_handle("dev1", "Luba-Online")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    await handle.add_transport(mqtt)

    assert handle.has_usable_transport is True


async def test_has_usable_transport_true_when_ble_connected() -> None:
    """has_usable_transport is True when BLE is actively connected (Rule 1)."""
    handle = make_handle("dev1", "Luba-BLE-Up")
    ble = _make_connected_transport(TransportType.BLE)
    await handle.add_transport(ble)

    assert handle.has_usable_transport is True


async def test_has_usable_transport_false_when_ble_unusable_and_no_mqtt() -> None:
    """has_usable_transport False when only BLE is registered and it's in cooldown."""
    handle = make_handle("dev1", "Luba-Cooldown")
    ble = _make_connected_transport(TransportType.BLE)
    ble.is_connected = False
    ble.is_usable = False
    await handle.add_transport(ble)

    assert handle.has_usable_transport is False


async def test_send_command_with_args_skips_immediately_when_offline() -> None:
    """Offline + no usable transport → debug log, no enqueue retry, no hang."""
    from pymammotion.state.device_state import DeviceAvailability

    client = MammotionClient()
    handle = make_handle("luba-x", "luba-x")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    await handle.add_transport(mqtt)
    handle._availability = DeviceAvailability(  # noqa: SLF001
        ble=handle._availability.ble,  # noqa: SLF001
        mqtt=handle._availability.mqtt,  # noqa: SLF001
        mqtt_reported_offline=True,
    )
    await client._device_registry.register(handle)

    fake_bytes = b"\xCA\xFE"
    patcher = _stub_commands(handle, fake_bytes)
    sleep_calls: list[float] = []
    real_sleep = asyncio.sleep

    async def _spy_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        await real_sleep(0)  # don't actually delay

    try:
        with patch.object(asyncio, "sleep", new=_spy_sleep):
            await client.send_command_with_args("luba-x", "get_report_cfg")
            await _drain(handle)
    finally:
        patcher.stop()

    # No retry loop ⇒ no 2.0s sleeps fired by send_command_with_args.
    assert all(d != 2.0 for d in sleep_calls), f"unexpected retry sleep: {sleep_calls}"
    # And no actual send went out.
    mqtt.send.assert_not_awaited()


async def test_queue_logs_no_transport_at_debug_not_warning(caplog: pytest.LogCaptureFixture) -> None:
    """A queue work item raising NoTransportAvailableError must log at DEBUG, not WARNING."""
    import logging

    from pymammotion.transport.base import NoTransportAvailableError

    handle = make_handle("dev1", "Luba-Quiet")
    handle.queue.start()

    async def _raises() -> None:
        raise NoTransportAvailableError("test: no transport")

    caplog.set_level(logging.DEBUG, logger="pymammotion.messaging.command_queue")
    await handle.queue.enqueue(_raises)
    await handle.queue._queue.join()  # noqa: SLF001
    await handle.queue.stop()

    relevant = [r for r in caplog.records if "test: no transport" in r.getMessage()]
    assert relevant, "expected a log record mentioning the NoTransportAvailableError"
    assert all(r.levelno == logging.DEBUG for r in relevant), (
        f"expected DEBUG only, got: {[(r.levelname, r.getMessage()) for r in relevant]}"
    )


async def test_has_usable_transport_true_when_offline_with_ble_usable_but_disconnected() -> None:
    """MQTT offline + BLE registered with is_usable=True but not connected → True.

    The BLE transport hasn't established GATT yet (e.g. just woke up from
    cooldown, fresh BLEDevice cached) but it's eligible for a connect attempt.
    active_transport() returns it for the caller to (re)connect, so
    has_usable_transport must report True — otherwise send_command_with_args
    would skip the very command that should trigger the BLE reconnect.
    """
    from pymammotion.state.device_state import DeviceAvailability

    handle = make_handle("dev1", "Luba-Recovery")
    mqtt = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    ble = _make_connected_transport(TransportType.BLE)
    ble.is_connected = False     # GATT not up yet
    ble.is_usable = True         # has cached BLEDevice, not in cooldown
    await handle.add_transport(mqtt)
    await handle.add_transport(ble)
    handle._availability = DeviceAvailability(  # noqa: SLF001
        ble=handle._availability.ble,  # noqa: SLF001
        mqtt=handle._availability.mqtt,  # noqa: SLF001
        mqtt_reported_offline=True,
    )

    # Verify the property delegates to ble.is_usable via active_transport().
    assert ble.is_usable is True
    assert handle.has_usable_transport is True

    # Sanity: flipping ble.is_usable=False (cooldown) flips the property too.
    ble.is_usable = False
    assert handle.has_usable_transport is False


# ---------------------------------------------------------------------------
# Device unbound (Aliyun 29004) — migrate to Mammotion MQTT, else remove
# ---------------------------------------------------------------------------


async def test_device_unbound_migrates_to_mammotion() -> None:
    """When an unbound device now appears on Mammotion MQTT, attach that transport to the
    SAME handle (no new handle), remap the iot_id, and never disconnect the shared Aliyun.
    """
    client = MammotionClient()
    handle = make_handle("Luba-MIG", "Luba-MIG")
    handle.iot_id = "iot-old"
    await client._device_registry.register(handle)
    client._iot_id_to_device_id["iot-old"] = "Luba-MIG"

    record = _make_device_record(device_name="Luba-MIG", iot_id="iot-new", product_key="pkNEW")
    http = _make_mock_http(device_records=[record])
    http.get_user_device_list = AsyncMock(
        return_value=MagicMock(data=[MagicMock(device_name="Luba-MIG", iot_id="iot-new")])
    )
    session = AccountSession(account_id="user@test.com", email="user@test.com", password="pw")
    session.mammotion_http = http
    session.aliyun_transport = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    session.device_ids.add("Luba-MIG")
    await client._account_registry.register(session)

    mammotion_transport = _make_connected_transport(TransportType.CLOUD_MAMMOTION)
    mammotion_transport.add_topic = AsyncMock()
    mammotion_transport.register_device = MagicMock()

    with patch.object(client, "_ensure_mammotion_transport", AsyncMock(return_value=mammotion_transport)):
        await client._on_device_unbound(handle)

    # Same handle reused; Mammotion attached; iot_id remapped; shared Aliyun untouched.
    assert client._device_registry.get_by_name("Luba-MIG") is handle
    assert handle.get_transport(TransportType.CLOUD_MAMMOTION) is mammotion_transport
    assert handle.iot_id == "iot-new"
    assert client._iot_id_to_device_id.get("iot-new") == "Luba-MIG"
    assert "iot-old" not in client._iot_id_to_device_id
    mammotion_transport.register_device.assert_called_once()
    session.aliyun_transport.disconnect.assert_not_awaited()
    await handle.stop()


async def test_device_unbound_removed_when_on_no_cloud() -> None:
    """When the unbound device is on neither cloud, remove it entirely and fire on_device_removed.

    The account-shared Aliyun transport must NOT be disconnected (other devices use it).
    """
    client = MammotionClient()
    handle = make_handle("Luba-GONE", "Luba-GONE")
    handle.iot_id = "iot-gone"
    await client._device_registry.register(handle)
    client._iot_id_to_device_id["iot-gone"] = "Luba-GONE"

    http = _make_mock_http(device_records=[])  # not present on Mammotion either
    session = AccountSession(account_id="user@test.com", email="user@test.com", password="pw")
    session.mammotion_http = http
    session.aliyun_transport = _make_connected_transport(TransportType.CLOUD_ALIYUN)
    session.device_ids.add("Luba-GONE")
    await client._account_registry.register(session)

    removed = AsyncMock()
    client.on_device_removed = removed

    # Collapse the multi-minute migration retry backoff so the test runs instantly.
    with patch("pymammotion.client._UNBOUND_MIGRATION_DELAYS", (0.0, 0.0)):
        await client._on_device_unbound(handle)

    assert client._device_registry.get_by_name("Luba-GONE") is None
    assert "iot-gone" not in client._iot_id_to_device_id
    assert "Luba-GONE" not in session.device_ids
    removed.assert_awaited_once_with("Luba-GONE", "iot-gone")
    session.aliyun_transport.disconnect.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_stream_subscription: retry once when the token response carries no data
# ---------------------------------------------------------------------------


async def test_fetch_stream_subscription_retries_on_empty_data() -> None:
    """An empty data payload is logged and the token fetch is retried once."""
    client = MammotionClient()
    http = MagicMock()
    empty = MagicMock(data=None)
    good = MagicMock(data=MagicMock())
    http.get_stream_subscription = AsyncMock(side_effect=[empty, good])

    result = await client._fetch_stream_subscription(http, "iot-1", is_yuka=False)

    assert result is good
    assert http.get_stream_subscription.await_count == 2


async def test_fetch_stream_subscription_no_retry_when_data_present() -> None:
    """A populated response is returned immediately with no retry."""
    client = MammotionClient()
    http = MagicMock()
    good = MagicMock(data=MagicMock())
    http.get_stream_subscription = AsyncMock(return_value=good)

    result = await client._fetch_stream_subscription(http, "iot-1", is_yuka=True)

    assert result is good
    http.get_stream_subscription.assert_awaited_once()


async def test_fetch_stream_subscription_returns_empty_after_retry_exhausted() -> None:
    """If both attempts return no data, the (empty) second response is returned."""
    client = MammotionClient()
    http = MagicMock()
    http.get_stream_subscription = AsyncMock(side_effect=[None, MagicMock(data=None)])

    result = await client._fetch_stream_subscription(http, "iot-1", is_yuka=False)

    assert result.data is None
    assert http.get_stream_subscription.await_count == 2


# ---------------------------------------------------------------------------
# remove_device: account-shared cloud transport survives unless last device
# ---------------------------------------------------------------------------


async def _make_two_device_session() -> tuple[MammotionClient, DeviceHandle, DeviceHandle, MagicMock, AccountSession]:
    client = MammotionClient()
    shared = _make_connected_transport(TransportType.CLOUD_ALIYUN)

    handle_a = make_handle("dev-a", "Luba-A")
    handle_b = make_handle("dev-b", "Luba-B")
    await handle_a.add_transport(shared)
    await handle_b.add_transport(shared)
    await client._device_registry.register(handle_a)
    await client._device_registry.register(handle_b)

    session = AccountSession(account_id="user@test.com", email="user@test.com", password="pw")
    session.aliyun_transport = shared
    session.device_ids.update({"Luba-A", "Luba-B"})
    await client._account_registry.register(session)
    return client, handle_a, handle_b, shared, session


async def test_remove_device_keeps_shared_cloud_transport_for_remaining_devices() -> None:
    """Removing one of two devices must NOT disconnect the account-shared cloud
    transport — the surviving device still depends on it."""
    client, handle_a, handle_b, shared, session = await _make_two_device_session()

    await client.remove_device("Luba-A")

    shared.disconnect.assert_not_awaited()
    assert client._device_registry.get_by_name("Luba-A") is None
    assert client._device_registry.get_by_name("Luba-B") is handle_b
    assert handle_b.get_transport(TransportType.CLOUD_ALIYUN) is shared
    assert "Luba-A" not in session.device_ids
    await handle_b.stop()


async def test_remove_device_disconnects_shared_cloud_transport_for_last_device() -> None:
    """Removing the LAST device on the account may tear the shared cloud transport down."""
    client, handle_a, handle_b, shared, session = await _make_two_device_session()

    await client.remove_device("Luba-A")
    await client.remove_device("Luba-B")

    shared.disconnect.assert_awaited()
    assert client._device_registry.get_by_name("Luba-B") is None
    assert not session.device_ids
