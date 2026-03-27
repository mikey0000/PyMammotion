"""MammotionClient — top-level entry point for the new architecture.

Owns the DeviceRegistry, AccountRegistry, and BLETransportManager.
The HA integration interacts only with this class.

BLE-only mode
-------------
When a mower is only reachable over Bluetooth (no cloud account, or simply
not wanting MQTT), call ``add_ble_only_device()`` instead of going through
login/cloud.  The resulting DeviceHandle has ``prefer_ble=True`` and only a
BLETransport attached — no HTTP or MQTT calls are made.

Example::

    client = MammotionClient()
    await client.add_ble_only_device(
        device_id="Luba-XXXXXX",
        device_name="Luba-XXXXXX",
        ble_device=discovered_ble_device,   # bleak BLEDevice
        initial_device=MowingDevice(name="Luba-XXXXXX"),
    )
    await client.mower("Luba-XXXXXX").start()
    await client.send_command_with_args("Luba-XXXXXX", "get_report_cfg")
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from pymammotion.account.registry import AccountRegistry
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.auth.token_manager import TokenManager
from pymammotion.bluetooth.manager import BLETransportManager
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.device.readiness import get_readiness_checker
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import DeviceRecord, DeviceRecords, Response
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.messaging.command_queue import Priority
from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport
from pymammotion.transport.base import TransportType
from pymammotion.transport.ble import BLETransport, BLETransportConfig
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from bleak import BLEDevice

    from pymammotion.data.model import GenerateRouteInformation
    from pymammotion.data.model.device import MowingDevice
    from pymammotion.http.model.http import MQTTConnection

_logger = logging.getLogger(__name__)


def _apply_geojson(device: MowingDevice) -> None:
    """Generate and store the map GeoJSON on *device* using its current RTK/dock location."""
    from shapely.geometry import Point

    from pymammotion.data.model.generate_geojson import GeojsonGenerator
    from pymammotion.utility.map import CoordinateConverter

    rtk = device.location.RTK
    dock = device.location.dock
    conv = CoordinateConverter(rtk.latitude, rtk.longitude)
    rtk_ll = conv.enu_to_lla(0, 0)
    dock_ll = conv.enu_to_lla(dock.latitude, dock.longitude)
    dock_rotation = int(conv.get_transform_yaw_with_yaw(dock.rotation) + 180)
    device.map.generated_geojson = GeojsonGenerator.generate_geojson(
        device.map,
        Point(rtk_ll.latitude, rtk_ll.longitude),
        Point(dock_ll.latitude, dock_ll.longitude),
        dock_rotation,
    )


def _apply_mow_path_geojson(device: MowingDevice) -> None:
    """Generate and store the mow-path GeoJSON on *device* using its current RTK location."""
    from shapely.geometry import Point

    from pymammotion.data.model.generate_geojson import GeojsonGenerator
    from pymammotion.utility.map import CoordinateConverter

    rtk = device.location.RTK
    conv = CoordinateConverter(rtk.latitude, rtk.longitude)
    rtk_ll = conv.enu_to_lla(0, 0)
    device.map.generated_mow_path_geojson = GeojsonGenerator.generate_mow_path_geojson(
        device.map,
        Point(rtk_ll.latitude, rtk_ll.longitude),
    )


class MammotionClient:
    """Top-level client — stable HA-facing API for the new architecture."""

    def __init__(self) -> None:
        """Initialise the client with empty registries."""
        self._device_registry: DeviceRegistry = DeviceRegistry()
        self._account_registry: AccountRegistry = AccountRegistry()
        self._ble_manager: BLETransportManager = BLETransportManager()
        self._stopped: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()
        self._iot_id_to_device_id: dict[str, str] = {}
        self._aliyun_transport: AliyunMQTTTransport | None = None
        self._mammotion_transport: MQTTTransport | None = None
        self._user_account: int = 0
        self._cloud_client: CloudIOTGateway | None = None
        self._mammotion_http: MammotionHTTP | None = None
        self._token_manager: TokenManager | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def stop(self) -> None:
        """Idempotent shutdown: stop all registered device handles.

        Safe to call multiple times (e.g. from both unload callback and HA
        shutdown event).
        """
        async with self._lock:
            if self._stopped:
                return
            self._stopped = True
        for handle in self._device_registry.all_devices:
            await handle.stop()

    def remove_device(self, name: str) -> None:
        """Schedule removal of the named device (fire-and-forget async task)."""
        loop = asyncio.get_event_loop()
        handle = self._device_registry.get_by_name(name)
        if handle is not None:
            task = loop.create_task(self._device_registry.unregister(handle.device_id))
            del task  # RUF006: reference held briefly to satisfy linter, task is fire-and-forget

    # ------------------------------------------------------------------
    # Device access
    # ------------------------------------------------------------------

    def get_device_by_name(self, name: str) -> MowingDevice | None:
        """Return the MowingDevice state for the named device, or None."""
        handle = self._device_registry.get_by_name(name)
        if handle is None:
            return None
        return handle.snapshot.raw

    def mower(self, name: str) -> DeviceHandle | None:
        """Return the DeviceHandle for the named device, or None."""
        return self._device_registry.get_by_name(name)

    # ------------------------------------------------------------------
    # BLE
    # ------------------------------------------------------------------

    async def add_ble_device(self, device_id: str, ble_device: object) -> None:
        """Register an externally-discovered BLE device (hybrid MQTT+BLE mode)."""
        self._ble_manager.register_external_ble_client(device_id, ble_device)

    async def update_ble_device(self, device_id: str, ble_device: object) -> None:
        """Update the BLE advertisement for a known device."""
        self._ble_manager.update_external_ble_client(device_id, ble_device)

    async def add_ble_only_device(
        self,
        device_id: str,
        device_name: str,
        ble_device: BLEDevice,
        initial_device: MowingDevice,
    ) -> DeviceHandle:
        """Register a BLE-only device — no HTTP login or MQTT involved.

        Creates a DeviceHandle with ``prefer_ble=True`` and a BLETransport
        already wired up.  Call ``handle.start()`` to begin the command queue,
        then ``transport.connect()`` to open the GATT connection.

        Args:
            device_id:      Unique device identifier (e.g. ``"Luba-XXXXXX"``).
            device_name:    Human-readable name shown in HA.
            ble_device:     The bleak ``BLEDevice`` obtained from a BLE scan.
            initial_device: An empty or cached ``MowingDevice`` for initial state.

        Returns:
            The registered ``DeviceHandle``.

        """
        transport = BLETransport(BLETransportConfig(device_id=device_id))
        transport.set_ble_device(ble_device)

        handle = DeviceHandle(
            device_id=device_id,
            device_name=device_name,
            initial_device=initial_device,
            ble_transport=transport,
            prefer_ble=True,
        )
        await self._device_registry.register(handle)
        _logger.info("BLE-only device registered: %s (%s)", device_name, device_id)
        return handle

    # ------------------------------------------------------------------
    # Cloud / MQTT — public entry points
    # ------------------------------------------------------------------

    async def _sign_out_existing_session(self) -> None:
        """Disconnect active transports and sign out of any existing cloud session."""
        if self._aliyun_transport is not None:
            await self._aliyun_transport.disconnect()
            self._aliyun_transport = None
        if self._mammotion_transport is not None:
            await self._mammotion_transport.disconnect()
            self._mammotion_transport = None
        if self._mammotion_http is not None:
            try:
                await self._mammotion_http.logout()
            except Exception:
                _logger.warning("HTTP logout failed — proceeding with login anyway", exc_info=True)
            self._mammotion_http = None
        if self._cloud_client is not None:
            try:
                await self._cloud_client.sign_out()
            except Exception:
                _logger.warning("cloud sign_out failed — proceeding with login anyway", exc_info=True)
            self._cloud_client = None
        self._token_manager = None
        self._stopped = False

    async def login_and_initiate_cloud(
        self,
        account: str,
        password: str,
        session: ClientSession | None = None,
    ) -> None:
        """Log in to the Mammotion cloud and register all account devices.

        Creates an :class:`AliyunMQTTTransport` for pre-2025 devices and/or a
        :class:`MQTTTransport` for post-2025 devices as required by the discovered
        device set.

        Args:
            account:  Mammotion account (email or phone number).
            password: Account password.
            session:  Optional :class:`aiohttp.ClientSession` to reuse.

        """
        await self._sign_out_existing_session()
        mammotion_http = MammotionHTTP(session=session)
        self._mammotion_http = mammotion_http
        login_resp = await mammotion_http.login_v2(account, password)
        if login_resp.code != 0:
            raise Exception(login_resp.msg)

        device_list_resp = await mammotion_http.get_user_shared_device_page()
        device_page_resp = await mammotion_http.get_user_device_page()
        aliyun_devices: DeviceRecords = device_list_resp.data or []
        mammotion_records = (device_page_resp.data.records if device_page_resp.data else []) or []

        self._set_user_account(mammotion_http)

        if aliyun_devices:
            cloud_client = CloudIOTGateway(mammotion_http)
            await self._connect_iot(cloud_client)
            shared_notice = await cloud_client.get_shared_notice_list()
            if shared_notice.data and shared_notice.data.data:
                pending = [d.record_id for d in shared_notice.data.data if d.status == -1]
                if pending:
                    await cloud_client.confirm_share(pending)

            if cloud_client.aep_response is None or cloud_client.region_response is None:
                msg = "Aliyun setup incomplete — aep_response or region_response missing"
                raise RuntimeError(msg)
            if cloud_client.session_by_authcode_response.data is None:
                msg = "Aliyun setup incomplete — session_by_authcode_response.data missing"
                raise RuntimeError(msg)

            self._cloud_client = cloud_client
            self._token_manager = TokenManager(account, mammotion_http, cloud_client)
            transport = self._setup_aliyun_transport(cloud_client)
            for device in cloud_client.devices_by_account_response.data.data:
                if device.device_name:
                    await self._register_aliyun_device(device.device_name, device.iot_id, transport)
            await transport.connect()

        if mammotion_records:
            await mammotion_http.get_mqtt_credentials()
            if mammotion_http.mqtt_credentials is None:
                _logger.error("Could not obtain Mammotion MQTT credentials — skipping post-2025 devices")
            else:
                if self._token_manager is None:
                    self._token_manager = TokenManager(account, mammotion_http)
                transport = self._setup_mammotion_transport(mammotion_http.mqtt_credentials, mammotion_http)
                for record in mammotion_records:
                    if record.device_name:
                        await self._register_mammotion_device(record, transport)
                await transport.connect()

    def to_cache(self) -> dict[str, Any]:
        """Serialize current cloud credentials to a cache dictionary.

        The returned dict can be passed to :meth:`restore_credentials` in a future
        session to skip re-authentication. If an Aliyun cloud client is active its
        full serialization is used (which already includes the Mammotion HTTP data).
        For a Mammotion-MQTT-only setup a minimal dict is produced instead.

        Returns an empty dict when no cloud session has been established yet.
        """
        if self._cloud_client is not None:
            return self._cloud_client.to_cache()

        if self._mammotion_http is not None:
            raw: dict[str, Any] = {}
            if self._mammotion_http.response is not None:
                raw["mammotion_data"] = self._mammotion_http.response
            if self._mammotion_http.mqtt_credentials is not None:
                raw["mammotion_mqtt"] = self._mammotion_http.mqtt_credentials
            if self._mammotion_http.device_records.records:
                raw["mammotion_device_records"] = self._mammotion_http.device_records
            return raw

        return {}

    async def restore_credentials(
        self,
        account: str,
        password: str,
        cached_data: dict[str, Any],
        session: ClientSession | None = None,
        *,
        check_for_new_devices: bool = True,
    ) -> None:
        """Restore a previous cloud session from a serialized cache dictionary.

        Known devices from the cache are registered immediately without any cloud
        round-trips.  When *check_for_new_devices* is True (the default) a single
        discovery call is made to pick up any devices added since the cache was saved.

        Handles both credential types transparently:

        * **Aliyun** (pre-2025 devices) — detected by the presence of ``aep_data``
          in *cached_data*.  Uses :meth:`CloudIOTGateway.from_cache` which also
          refreshes the IoT session token if it has expired.
        * **Mammotion MQTT** (post-2025 devices) — detected by the presence of
          ``mammotion_mqtt`` and ``mammotion_device_records`` in *cached_data*.

        Args:
            account:               Mammotion account e-mail or phone number.
            password:              Account password (used only if a token refresh is needed).
            cached_data:           Dict previously returned by :meth:`to_cache`.
            session:               Optional :class:`aiohttp.ClientSession` to reuse.
            check_for_new_devices: When True, run a lightweight discovery call after
                                   restoring known devices to register any new ones.

        """
        if "aep_data" in cached_data:
            await self._restore_aliyun(account, password, cached_data, check_for_new_devices=check_for_new_devices)

        if "mammotion_mqtt" in cached_data and "mammotion_device_records" in cached_data:
            await self._restore_mammotion_mqtt(
                account, password, cached_data, session, check_for_new_devices=check_for_new_devices
            )

    @property
    def token_manager(self) -> TokenManager | None:
        """Return the active TokenManager, or None if no cloud session."""
        return self._token_manager

    async def refresh_login(self, account: str) -> None:
        """Refresh authentication credentials for the given account.

        Delegates to TokenManager.force_refresh() which refreshes HTTP,
        MQTT, and Aliyun credentials as needed.
        """
        if self._token_manager is not None:
            await self._token_manager.force_refresh()
            _logger.info("refresh_login: credentials refreshed for account=%s", account)
        else:
            _logger.warning("refresh_login: no token manager available for account=%s", account)

    # ------------------------------------------------------------------
    # Cloud — private helpers
    # ------------------------------------------------------------------

    def _set_user_account(self, mammotion_http: MammotionHTTP) -> None:
        """Extract and store the user account number from login_info."""
        if mammotion_http.login_info is not None:
            self._user_account = int(mammotion_http.login_info.userInformation.userAccount)

    def _setup_aliyun_transport(self, cloud_client: CloudIOTGateway) -> AliyunMQTTTransport:
        """Build an AliyunMQTTTransport from a ready CloudIOTGateway and store it."""
        aep = cloud_client.aep_response.data
        region_id = cloud_client.region_response.data.regionId
        session_data = cloud_client.session_by_authcode_response.data
        config = AliyunMQTTConfig(
            host=f"{aep.productKey}.iot-as-mqtt.{region_id}.aliyuncs.com",
            client_id_base=cloud_client.client_id,
            username=f"{aep.deviceName}&{aep.productKey}",
            device_name=aep.deviceName,
            product_key=aep.productKey,
            device_secret=aep.deviceSecret,
            iot_token=session_data.iotToken,
        )
        transport = AliyunMQTTTransport(config, cloud_client)
        transport.on_device_message = self._route_device_message
        self._aliyun_transport = transport
        return transport

    def _setup_mammotion_transport(self, mqtt_creds: MQTTConnection, mammotion_http: MammotionHTTP) -> MQTTTransport:
        """Build a MQTTTransport from MQTTConnection credentials and store it."""
        from urllib.parse import urlparse

        parsed = urlparse(mqtt_creds.host if "://" in mqtt_creds.host else "tcp://" + mqtt_creds.host)
        use_ssl = parsed.scheme in ("mqtts", "ssl")
        config = MQTTTransportConfig(
            host=parsed.hostname or mqtt_creds.host,
            client_id=mqtt_creds.client_id,
            username=mqtt_creds.username,
            password=mqtt_creds.jwt,
            port=parsed.port or (8883 if use_ssl else 1883),
            use_ssl=use_ssl,
        )
        transport = MQTTTransport(config, mammotion_http)
        transport.on_device_message = self._route_device_message
        self._mammotion_transport = transport
        return transport

    async def _register_aliyun_device(self, device_name: str, iot_id: str, transport: AliyunMQTTTransport) -> None:
        """Register a single Aliyun device in the device registry."""
        from pymammotion.data.model.device import MowingDevice

        handle = DeviceHandle(
            device_id=device_name,
            device_name=device_name,
            initial_device=MowingDevice(name=device_name),
            iot_id=iot_id,
            mqtt_transport=transport,
            readiness_checker=get_readiness_checker(device_name),
        )
        await self._device_registry.register(handle)
        await handle.start()
        self._enable_staleness_watcher(handle, device_name)
        self._iot_id_to_device_id[iot_id] = device_name
        _logger.info("Aliyun device registered: %s (iot_id=%s)", device_name, iot_id)

    async def _register_mammotion_device(self, record: DeviceRecord, transport: MQTTTransport) -> None:
        """Add MQTT topics and register a single Mammotion device in the device registry."""
        from pymammotion.data.model.device import MowingDevice

        for topic in (
            f"/sys/{record.product_key}/{record.device_name}/thing/event/+/post",
            f"/sys/proto/{record.product_key}/{record.device_name}/thing/event/+/post",
            f"/sys/{record.product_key}/{record.device_name}/app/down/thing/status",
        ):
            transport.add_topic(topic)
        transport.register_device(record.product_key, record.device_name, record.iot_id)

        handle = DeviceHandle(
            device_id=record.device_name,
            device_name=record.device_name,
            initial_device=MowingDevice(name=record.device_name),
            iot_id=record.iot_id,
            mqtt_transport=transport,
            readiness_checker=get_readiness_checker(record.device_name),
        )
        await self._device_registry.register(handle)
        await handle.start()
        self._enable_staleness_watcher(handle, record.device_name)
        self._iot_id_to_device_id[record.iot_id] = record.device_name
        _logger.info("Mammotion device registered: %s (iot_id=%s)", record.device_name, record.iot_id)

    def _enable_staleness_watcher(self, handle: DeviceHandle, device_name: str) -> None:
        """Enable auto-refetch of stale maps and plans for a device."""
        handle.enable_staleness_watcher(
            on_maps_stale=lambda: self.start_map_sync(device_name),
            on_plans_stale=lambda: self.start_plan_sync(device_name),
        )

    async def _restore_aliyun(
        self,
        account: str,
        password: str,
        cached_data: dict[str, Any],
        *,
        check_for_new_devices: bool,
    ) -> None:
        """Restore an Aliyun cloud session and register all known devices."""
        cloud_client = await CloudIOTGateway.from_cache(cached_data, account, password)
        if cloud_client is None:
            _logger.error("restore_credentials: CloudIOTGateway.from_cache returned None — falling back to full login")
            await self.login_and_initiate_cloud(account, password)
            return

        self._mammotion_http = cloud_client.mammotion_http
        self._cloud_client = cloud_client
        self._set_user_account(cloud_client.mammotion_http)

        transport = self._setup_aliyun_transport(cloud_client)

        known_ids: set[str] = set()
        if cloud_client.devices_by_account_response is not None and cloud_client.devices_by_account_response.data:
            for device in cloud_client.devices_by_account_response.data.data:
                if device.device_name:
                    await self._register_aliyun_device(device.device_name, device.iot_id, transport)
                    known_ids.add(device.device_name)

        await transport.connect()

        if check_for_new_devices:
            try:
                fresh = await cloud_client.list_binding_by_account()
                if fresh.data:
                    for device in fresh.data.data:
                        if device.device_name and device.device_name not in known_ids:
                            await self._register_aliyun_device(device.device_name, device.iot_id, transport)
            except Exception:
                _logger.warning("restore_credentials: new-device discovery failed (Aliyun)", exc_info=True)

    async def _restore_mammotion_mqtt(
        self,
        account: str,
        password: str,
        cached_data: dict[str, Any],
        session: ClientSession | None,
        *,
        check_for_new_devices: bool,
    ) -> None:
        """Restore a Mammotion MQTT session and register all known devices."""
        from pymammotion.http.model.http import LoginResponseData, MQTTConnection
        from pymammotion.http.model.response_factory import response_factory

        mammotion_http = MammotionHTTP(account, password, session=session)
        self._mammotion_http = mammotion_http

        mammotion_data = cached_data.get("mammotion_data")
        if mammotion_data is not None:
            response_data = (
                response_factory(Response[LoginResponseData], mammotion_data)
                if isinstance(mammotion_data, dict)
                else mammotion_data
            )
            mammotion_http.response = response_data
            mammotion_http.login_info = (
                LoginResponseData.from_dict(response_data.data)
                if isinstance(response_data.data, dict)
                else response_data.data
            )
            self._set_user_account(mammotion_http)

        mqtt_raw = cached_data["mammotion_mqtt"]
        mqtt_creds: MQTTConnection = MQTTConnection.from_dict(mqtt_raw) if isinstance(mqtt_raw, dict) else mqtt_raw
        mammotion_http.mqtt_credentials = mqtt_creds

        records_raw = cached_data["mammotion_device_records"]
        cached_records: DeviceRecords = (
            DeviceRecords.from_dict(records_raw) if isinstance(records_raw, dict) else records_raw
        )
        mammotion_http.device_records = cached_records

        transport = self._setup_mammotion_transport(mqtt_creds, mammotion_http)

        known_ids: set[str] = set()
        for record in cached_records.records:
            if record.device_name:
                await self._register_mammotion_device(record, transport)
                known_ids.add(record.device_name)

        await transport.connect()

        if check_for_new_devices:
            try:
                page_resp = await mammotion_http.get_user_device_page()
                for record in (page_resp.data.records if page_resp.data else []) or []:
                    if record.device_name and record.device_name not in known_ids:
                        await self._register_mammotion_device(record, transport)
            except Exception:
                _logger.warning("restore_credentials: new-device discovery failed (Mammotion)", exc_info=True)

    @staticmethod
    async def _connect_iot(cloud_client: CloudIOTGateway) -> None:
        """Run the Aliyun IoT gateway setup sequence (region, AEP, session, devices)."""
        mammotion_http = cloud_client.mammotion_http
        login_info = mammotion_http.login_info
        if login_info is None:
            msg = "login_info is None — call login_v2() before _connect_iot()"
            raise RuntimeError(msg)
        country_code = login_info.userInformation.domainAbbreviation
        if cloud_client.region_response is None:
            await cloud_client.get_region(country_code)
        await cloud_client.connect()
        await cloud_client.login_by_oauth(country_code)
        await cloud_client.aep_handle()
        await cloud_client.session_by_auth_code()
        await cloud_client.list_binding_by_account()

    async def _route_device_message(self, iot_id: str, payload: bytes) -> None:
        """Route an incoming cloud message to the correct DeviceHandle."""
        device_id = self._iot_id_to_device_id.get(iot_id)
        if device_id is None:
            _logger.debug("_route_device_message: unknown iot_id=%s, dropping message", iot_id)
            return
        handle = self._device_registry.get(device_id)
        if handle is None:
            _logger.debug("_route_device_message: handle gone for device_id=%s", device_id)
            return
        await handle._on_raw_message(payload)  # noqa: SLF001

    # ------------------------------------------------------------------
    # Map sync
    # ------------------------------------------------------------------

    async def start_map_sync(self, device_name: str) -> None:
        """Enqueue a MapFetchSaga to fetch the complete device map.

        The saga is enqueued on the device's command queue and runs exclusively
        (no other commands execute while the map fetch is in progress).
        Map data is automatically applied to device state as messages arrive.
        """
        from pymammotion.messaging.map_saga import MapFetchSaga
        from pymammotion.utility.device_type import DeviceType

        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("start_map_sync: device '%s' not registered", device_name)
            return
        commands = MammotionCommand(device_name, self._user_account)
        transport = handle.active_transport()
        _iot_id = handle.iot_id
        saga = MapFetchSaga(
            device_id=handle.device_id,
            device_name=handle.device_name,
            is_luba1=DeviceType.is_luba1(device_name),
            command_builder=commands,
            send_command=lambda cmd: transport.send(cmd, iot_id=_iot_id),
        )

        async def _on_map_complete() -> None:
            device = self.get_device_by_name(device_name)
            if device is not None and device.location.RTK.latitude != 0:
                _apply_geojson(device)

        await handle.enqueue_saga(saga, on_complete=_on_map_complete)

    async def start_plan_sync(self, device_name: str) -> None:
        """Enqueue a PlanFetchSaga to fetch all stored schedule plans.

        Plans arrive as ``todev_planjob_set`` messages which the StateReducer
        applies to ``device.map.plan`` automatically.  The saga also clears
        ``device.map.plans_stale`` once complete.
        """
        from pymammotion.messaging.plan_saga import PlanFetchSaga

        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("start_plan_sync: device '%s' not registered", device_name)
            return
        commands = MammotionCommand(device_name, self._user_account)
        _iot_id = handle.iot_id

        async def _send(cmd: bytes) -> None:
            await handle.active_transport().send(cmd, iot_id=_iot_id)

        saga = PlanFetchSaga(command_builder=commands, send_command=_send)
        await handle.enqueue_saga(saga)

    async def start_mow_path_saga(
        self,
        device_name: str,
        zone_hashs: list[int],
        route_info: GenerateRouteInformation | None = None,
        *,
        skip_planning: bool = False,
    ) -> None:
        """Enqueue a MowPathSaga to plan a route and collect the cover path.

        Args:
            device_name:   Registered device name.
            zone_hashs:    Area hash IDs for the mow zones.
            route_info:    Optional pre-built :class:`GenerateRouteInformation`.
            skip_planning: When True, skip the generate_route_information step.
                           Use this to fetch an already-computed path (e.g. when
                           the device started working externally).

        """
        from pymammotion.messaging.mow_path_saga import MowPathSaga

        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("start_mow_path_saga: device '%s' not registered", device_name)
            return
        commands = MammotionCommand(device_name, self._user_account)
        _iot_id = handle.iot_id

        async def _send(cmd: bytes) -> None:
            await handle.active_transport().send(cmd, iot_id=_iot_id)

        saga = MowPathSaga(
            command_builder=commands,
            send_command=_send,
            zone_hashs=zone_hashs,
            route_info=route_info,
            skip_planning=skip_planning,
        )

        async def _on_mow_path_complete() -> None:
            device = self.get_device_by_name(device_name)
            if device is not None and device.location.RTK.latitude != 0:
                _apply_mow_path_geojson(device)

        await handle.enqueue_saga(saga, on_complete=_on_mow_path_complete)

    async def start_edge_mapping(
        self,
        device_name: str,
        *,
        skip_start: bool = False,
    ) -> None:
        """Enqueue an EdgeMappingSaga to collect boundary/edge points from the device.

        The device streams ``toapp_edge_points`` frames during live border walking.
        Each frame is acknowledged automatically so the device continues sending.
        Collected points are stored in ``device.map.edge_points[hash]``.

        Args:
            device_name: Registered device name.
            skip_start:  When True, skip sending ``along_border()`` — use this
                         when the device is already mapping.

        """
        from pymammotion.messaging.edge_saga import EdgeMappingSaga

        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("start_edge_mapping: device '%s' not registered", device_name)
            return
        commands = MammotionCommand(device_name, self._user_account)
        _iot_id = handle.iot_id

        async def _send(cmd: bytes) -> None:
            await handle.active_transport().send(cmd, iot_id=_iot_id)

        saga = EdgeMappingSaga(command_builder=commands, send_command=_send, skip_start=skip_start)
        await handle.enqueue_saga(saga)

    # ------------------------------------------------------------------
    # BLE connection
    # ------------------------------------------------------------------

    async def connect_ble(self, device_id: str) -> None:
        """Connect the BLE transport for a registered device.

        Works for both BLE-only devices and hybrid devices that have a BLE
        transport attached.  Is a no-op if the transport is already connected.
        """
        handle = self._device_registry.get(device_id)
        if handle is None:
            msg = f"Device '{device_id}' not registered"
            raise KeyError(msg)
        transport = handle._transports.get(TransportType.BLE)  # noqa: SLF001
        if transport is not None and not transport.is_connected:
            await transport.connect()

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    @property
    def mammotion_http(self) -> MammotionHTTP | None:
        """Return the active MammotionHTTP client (Aliyun or direct)."""
        if self._cloud_client is not None:
            return self._cloud_client.mammotion_http
        return self._mammotion_http

    @property
    def cloud_http(self) -> MammotionHTTP | None:
        """Return the active MammotionHTTP client for cloud operations (OTA, firmware, etc.)."""
        return self.mammotion_http

    @property
    def cloud_gateway(self) -> CloudIOTGateway | None:
        """Return the Aliyun CloudIOTGateway, or None if no Aliyun session was established."""
        return self._cloud_client

    @property
    def aliyun_device_list(self) -> list[Any]:
        """Return the list of Device objects from the Aliyun cloud registry.

        Returns an empty list when there are no Aliyun devices or the cloud
        client has not yet been initialised.
        """
        if self._cloud_client is None:
            return []
        try:
            return self._cloud_client.devices_by_account_response.data.data  # type: ignore[no-any-return]
        except (AttributeError, TypeError):
            return []

    @property
    def mammotion_device_list(self) -> list[Any]:
        """Return Mammotion-direct devices as shimmed Device objects.

        Converts each :class:`DeviceRecord` from the Mammotion HTTP client into
        a :class:`~pymammotion.aliyun.model.dev_by_account_response.Device` so
        callers can treat both cloud paths uniformly.
        """
        if self._mammotion_http is None:
            return []
        return self.shim_devices_from_records(self._mammotion_http.device_records.records)

    @staticmethod
    def shim_devices_from_records(records: list[DeviceRecord]) -> list[Any]:
        """Convert Mammotion-direct :class:`DeviceRecord` objects to Aliyun Device format.

        The returned Device objects have all required fields populated from the
        record; fields not present in DeviceRecord are set to sensible defaults.
        """
        import time

        from pymammotion.aliyun.model.dev_by_account_response import Device

        result: list[Any] = []
        for rec in records:
            try:
                d = Device(
                    gmt_modified=int(time.time() * 1000),
                    node_type="DEVICE",
                    device_name=rec.device_name,
                    product_name=rec.device_name,
                    status=rec.status,
                    identity_id=rec.identity_id,
                    net_type="WIFI",
                    category_key="",
                    product_key=rec.product_key,
                    is_edge_gateway=False,
                    category_name="",
                    identity_alias=rec.device_name,
                    iot_id=rec.iot_id,
                    bind_time=rec.bind_time,
                    owned=rec.owned,
                    thing_type="DEVICE",
                )
                result.append(d)
            except Exception:  # noqa: BLE001
                _logger.warning("shim_devices_from_records: failed to shim record %s", rec.device_name)
        return result

    async def add_ble_to_device(
        self,
        device_name: str,
        ble_device: BLEDevice,
        *,
        disconnect_on_idle: bool = True,
    ) -> None:
        """Attach (or replace) a BLE transport on an already-registered device.

        Args:
            device_name:        Registered device name.
            ble_device:         The bleak ``BLEDevice`` to use for the BLE connection.
            disconnect_on_idle: When True, the BLE connection is dropped when the
                                device is idle (power-saving).  Set to False for
                                stay-connected Bluetooth mode.

        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("add_ble_to_device: device '%s' not registered", device_name)
            return
        transport = BLETransport(BLETransportConfig(device_id=device_name))
        transport.set_ble_device(ble_device)
        transport.set_disconnect_strategy(disconnect=disconnect_on_idle)
        await handle.add_transport(transport)

    async def get_stream_subscription(self, device_name: str, iot_id: str) -> Any:
        """Return a stream subscription response for the named device."""
        from pymammotion.utility.device_type import DeviceType

        http = self.mammotion_http
        if http is None:
            return None
        is_yuka = DeviceType.is_yuka(device_name)
        return await http.get_stream_subscription(iot_id, is_yuka)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def send_command_with_args(
        self,
        name: str,
        key: str,
        *,
        prefer_ble: bool = False,
        **kwargs: Any,
    ) -> None:
        """Send a named command to the device via the command queue.

        Builds a :class:`MammotionCommand` for the device, calls ``key(**kwargs)``
        to get the protobuf bytes, then enqueues the send via the device's command
        queue so it is properly ordered with respect to running sagas.

        Args:
            name:       Registered device name.
            key:        Method name on :class:`MammotionCommand`.
            prefer_ble: When True, prefer BLE over MQTT for this call only
                        (useful for movement commands that need low latency).
                        Does not mutate the handle's transport preference.

        Raises:
            KeyError:       if *name* is not a registered device.
            AttributeError: if *key* is not a valid command.

        """
        handle = self._device_registry.get_by_name(name)
        if handle is None:
            msg = f"Device '{name}' not registered"
            raise KeyError(msg)
        commands = MammotionCommand(name, self._user_account)
        command_bytes: bytes = getattr(commands, key)(**kwargs)
        _logger.debug(
            "send_command_with_args: device=%s key=%s prefer_ble=%s kwargs=%s",
            name,
            key,
            prefer_ble,
            kwargs,
        )
        iot_id = handle.iot_id
        _prefer_ble = prefer_ble

        async def _do_send() -> None:
            await handle.active_transport(prefer_ble=_prefer_ble).send(command_bytes, iot_id=iot_id)

        await handle.queue.enqueue(_do_send, priority=Priority.NORMAL)

    async def send_command_and_wait(
        self,
        name: str,
        key: str,
        expected_field: str,
        *,
        send_timeout: float = 5.0,
        **kwargs: Any,
    ) -> Any:
        """Send a command and wait for the matching protobuf response.

        Uses the broker's send_and_wait for request/response correlation.
        Returns the response LubaMsg.

        Args:
            name:           Registered device name.
            key:            Method name on :class:`MammotionCommand`.
            expected_field: Protobuf oneof field name expected in response.
            send_timeout:   Seconds to wait per attempt.
            **kwargs:       Arguments passed to the command builder.

        Raises:
            KeyError:             if *name* is not a registered device.
            CommandTimeoutError:  if no response after retries.

        """
        handle = self._device_registry.get_by_name(name)
        if handle is None:
            msg = f"Device '{name}' not registered"
            raise KeyError(msg)
        commands = MammotionCommand(name, self._user_account)
        command_bytes: bytes = getattr(commands, key)(**kwargs)

        async def _send() -> None:
            await handle.send_raw(payload=command_bytes)

        return await handle.broker.send_and_wait(
            send_fn=_send,
            expected_field=expected_field,
            send_timeout=send_timeout,
        )

    def set_prefer_ble(self, device_id: str, *, prefer_ble: bool) -> None:
        """Set transport preference for a registered device."""
        handle = self._device_registry.get(device_id)
        if handle is not None:
            handle.set_prefer_ble(value=prefer_ble)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def device_registry(self) -> DeviceRegistry:
        """Access the device registry."""
        return self._device_registry

    @property
    def account_registry(self) -> AccountRegistry:
        """Access the account registry."""
        return self._account_registry
