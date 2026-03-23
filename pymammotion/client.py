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
from pymammotion.bluetooth.manager import BLETransportManager
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.http.http import MammotionHTTP
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport
from pymammotion.transport.base import TransportType
from pymammotion.transport.ble import BLETransport, BLETransportConfig
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from bleak import BLEDevice

    from pymammotion.data.model.device import MowingDevice

_logger = logging.getLogger(__name__)


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
    # Cloud / MQTT
    # ------------------------------------------------------------------

    async def login_and_initiate_cloud(
        self,
        account: str,
        password: str,
        session: ClientSession | None = None,
    ) -> None:
        """Log in to the Mammotion cloud and register all account devices.

        Creates an :class:`AliyunMQTTTransport` for pre-2025 devices (returned by
        ``get_user_device_list``) and/or a :class:`MQTTTransport` for post-2025
        devices (returned by ``get_user_device_page``).  Only the transport(s)
        required by the discovered device set are created and connected.

        Args:
            account:  Mammotion account (email or phone number).
            password: Account password.
            session:  Optional :class:`aiohttp.ClientSession` to reuse.

        """
        from pymammotion.data.model.device import MowingDevice

        mammotion_http = MammotionHTTP(session=session)
        await mammotion_http.login_v2(account, password)

        # Discover devices on both the pre-2025 (Aliyun) and post-2025 (Mammotion) paths
        device_list_resp = await mammotion_http.get_user_device_list()
        device_page_resp = await mammotion_http.get_user_device_page()

        aliyun_devices = device_list_resp.data or []
        mammotion_records = (device_page_resp.data.records if device_page_resp.data else []) or []

        # Extract user_account for command building
        if mammotion_http.login_info is not None:
            self._user_account = int(mammotion_http.login_info.userInformation.userAccount)

        # ------------------------------------------------------------------
        # Pre-2025 devices — Aliyun IoT Gateway + AliyunMQTTTransport
        # ------------------------------------------------------------------
        if aliyun_devices:
            cloud_client = CloudIOTGateway(mammotion_http)
            await self._connect_iot(cloud_client)

            if cloud_client.aep_response is None or cloud_client.region_response is None:
                msg = "Aliyun setup incomplete — aep_response or region_response missing"
                raise RuntimeError(msg)
            session_data = cloud_client.session_by_authcode_response.data
            if session_data is None:
                msg = "Aliyun setup incomplete — session_by_authcode_response.data missing"
                raise RuntimeError(msg)

            aep = cloud_client.aep_response.data
            region_id = cloud_client.region_response.data.regionId
            aliyun_config = AliyunMQTTConfig(
                host=f"{aep.productKey}.iot-as-mqtt.{region_id}.aliyuncs.com",
                client_id_base=cloud_client.client_id,
                username=f"{aep.deviceName}&{aep.productKey}",
                device_name=aep.deviceName,
                product_key=aep.productKey,
                device_secret=aep.deviceSecret,
                iot_token=session_data.iotToken,
            )
            aliyun_transport = AliyunMQTTTransport(aliyun_config)
            aliyun_transport.on_device_message = self._route_device_message
            self._aliyun_transport = aliyun_transport
            self._cloud_client = cloud_client

            for device in cloud_client.devices_by_account_response.data.data:
                device_id = device.device_name
                iot_id = device.iot_id
                if not device_id:
                    continue
                handle = DeviceHandle(
                    device_id=device_id,
                    device_name=device_id,
                    initial_device=MowingDevice(name=device_id),
                    iot_id=iot_id,
                    mqtt_transport=aliyun_transport,
                )
                await self._device_registry.register(handle)
                self._iot_id_to_device_id[iot_id] = device_id
                _logger.info("Aliyun device registered: %s (iot_id=%s)", device_id, iot_id)

            await aliyun_transport.connect()

        # ------------------------------------------------------------------
        # Post-2025 devices — Mammotion MQTT + MQTTTransport
        # ------------------------------------------------------------------
        if mammotion_records:
            await mammotion_http.get_mqtt_credentials()
            mqtt_creds = mammotion_http.mqtt_credentials
            if mqtt_creds is None:
                _logger.error("Could not obtain Mammotion MQTT credentials — skipping post-2025 devices")
            else:
                from urllib.parse import urlparse

                parsed = urlparse(mqtt_creds.host if "://" in mqtt_creds.host else "tcp://" + mqtt_creds.host)
                use_ssl = parsed.scheme in ("mqtts", "ssl")
                mammotion_config = MQTTTransportConfig(
                    host=parsed.hostname or mqtt_creds.host,
                    client_id=mqtt_creds.client_id,
                    username=mqtt_creds.username,
                    password=mqtt_creds.jwt,
                    port=parsed.port or (8883 if use_ssl else 1883),
                    use_ssl=use_ssl,
                )
                mammotion_transport = MQTTTransport(mammotion_config)
                mammotion_transport.on_device_message = self._route_device_message
                self._mammotion_transport = mammotion_transport

                for record in mammotion_records:
                    device_id = record.device_name
                    iot_id = record.iot_id
                    if not device_id:
                        continue
                    # Subscribe to device-specific topics
                    for topic in (
                        f"/sys/{record.product_key}/{record.device_name}/thing/event/+/post",
                        f"/sys/proto/{record.product_key}/{record.device_name}/thing/event/+/post",
                        f"/sys/{record.product_key}/{record.device_name}/app/down/thing/status",
                    ):
                        mammotion_transport.add_topic(topic)
                    mammotion_transport.register_device(record.product_key, record.device_name, iot_id)

                    handle = DeviceHandle(
                        device_id=device_id,
                        device_name=device_id,
                        initial_device=MowingDevice(name=device_id),
                        iot_id=iot_id,
                        mqtt_transport=mammotion_transport,
                    )
                    await self._device_registry.register(handle)
                    self._iot_id_to_device_id[iot_id] = device_id
                    _logger.info("Mammotion device registered: %s (iot_id=%s)", device_id, iot_id)

                await mammotion_transport.connect()

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
        transport = handle._active_transport()  # noqa: SLF001
        saga = MapFetchSaga(
            device_id=handle.device_id,
            device_name=handle.device_name,
            is_luba1=DeviceType.is_luba1(device_name),
            command_builder=commands,
            send_command=transport.send,
        )
        await handle.enqueue_saga(saga)

    async def refresh_login(self, account: str) -> None:
        """Refresh authentication credentials for the given account.

        TODO: wire up to TokenManager.force_refresh() once token manager
        is integrated into the cloud login path.
        """
        _logger.warning("refresh_login: not yet implemented for account=%s", account)

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
    # Commands
    # ------------------------------------------------------------------

    async def send_command_with_args(self, name: str, key: str, **kwargs: Any) -> None:
        """Send a named command to the device.

        Builds a :class:`MammotionCommand` for the device, calls ``key(**kwargs)``
        to get the protobuf bytes, then sends them via the device's active transport.

        Args:
            name: Registered device name.
            key:  Method name on :class:`MammotionCommand` (e.g. ``"get_report_cfg"``).

        Raises:
            KeyError:     if *name* is not a registered device.
            AttributeError: if *key* is not a valid command.

        """
        handle = self._device_registry.get_by_name(name)
        if handle is None:
            msg = f"Device '{name}' not registered"
            raise KeyError(msg)
        commands = MammotionCommand(name, self._user_account)
        command_bytes: bytes = getattr(commands, key)(**kwargs)
        _logger.debug("send_command_with_args: device=%s key=%s kwargs=%s", name, key, kwargs)
        # Fire-and-forget send: responses are handled by _on_raw_message → StateReducer
        transport = handle._active_transport()  # noqa: SLF001
        await transport.send(command_bytes)

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
