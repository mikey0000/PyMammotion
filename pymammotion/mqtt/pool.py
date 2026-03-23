"""Per-account MQTT connection pool — one connection per path (aliyun/mammotion)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

    from pymammotion.auth.token_manager import MQTTCredentials, TokenManager
    from pymammotion.http.model.http import DeviceInfo, DeviceRecord
    from pymammotion.transport.base import Transport

ConnectionKey = Literal["aliyun", "mammotion"]


@dataclass
class MQTTPoolEntry:
    """One MQTT connection and the set of device IDs that use it."""

    connection_key: ConnectionKey
    host: str
    transport: Transport
    device_ids: set[str] = field(default_factory=set)


class MQTTConnectionPool:
    """Manages up to two MQTT connections per account.

    Connections are keyed by Literal["aliyun", "mammotion"]. All devices
    discovered via get_user_device_list() share the aliyun connection; all
    devices from get_user_device_page() share the mammotion connection.
    """

    def __init__(
        self,
        account_id: str,
        token_manager: TokenManager,
        transport_factory: Callable[[str, MQTTCredentials], Transport],
    ) -> None:
        """Create a pool for a single account.

        Args:
            account_id: Identifier for the account that owns this pool.
            token_manager: Credential manager used to obtain MQTT credentials.
            transport_factory: Callable that creates a Transport given a host
                string and MQTTCredentials.  Keeps the pool decoupled from any
                concrete transport implementation.

        """
        self._account_id = account_id
        self._token_manager = token_manager
        self._transport_factory = transport_factory
        self._connections: dict[ConnectionKey, MQTTPoolEntry] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    async def register_aliyun_devices(
        self,
        device_infos: list[DeviceInfo],
        product_key: str,
        region_id: str,
    ) -> Transport:
        """Register devices that communicate via the Aliyun MQTT path.

        All devices in *device_infos* are attached to a single shared Transport
        whose host is derived from *product_key* and *region_id*.

        Args:
            device_infos: Devices returned by ``MammotionHTTP.get_user_device_list()``.
            product_key: Aliyun product key for the account's IoT project.
            region_id: Aliyun region identifier (e.g. ``"eu-central-1"``).

        Returns:
            The shared Transport for all aliyun devices on this account.

        """
        host = f"{product_key}.iot-as-mqtt.{region_id}.aliyuncs.com"
        async with self._lock:
            if "aliyun" not in self._connections:
                creds = await self._token_manager.get_mammotion_mqtt_credentials()
                transport = self._transport_factory(host, creds)
                self._connections["aliyun"] = MQTTPoolEntry(
                    connection_key="aliyun",
                    host=host,
                    transport=transport,
                )
            entry = self._connections["aliyun"]
            for device in device_infos:
                device_id = device.iot_id or device.device_id
                if device_id:
                    entry.device_ids.add(device_id)
            return entry.transport

    async def register_mammotion_devices(
        self,
        device_records: list[DeviceRecord],
        mqtt_creds: MQTTCredentials,
    ) -> Transport:
        """Register devices that communicate via the Mammotion MQTT path.

        All devices in *device_records* are attached to a single shared
        Transport whose host is taken from *mqtt_creds.host*.

        Args:
            device_records: Devices returned by ``MammotionHTTP.get_user_device_page()``.
            mqtt_creds: Credentials (including host) from ``MammotionHTTP.get_mqtt_credentials()``.

        Returns:
            The shared Transport for all mammotion devices on this account.

        """
        async with self._lock:
            if "mammotion" not in self._connections:
                transport = self._transport_factory(mqtt_creds.host, mqtt_creds)
                self._connections["mammotion"] = MQTTPoolEntry(
                    connection_key="mammotion",
                    host=mqtt_creds.host,
                    transport=transport,
                )
            entry = self._connections["mammotion"]
            for record in device_records:
                if record.iot_id:
                    entry.device_ids.add(record.iot_id)
            return entry.transport

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def get_transport(self, device_id: str) -> Transport | None:
        """Return the transport assigned to *device_id*, or ``None`` if not found."""
        for entry in self._connections.values():
            if device_id in entry.device_ids:
                return entry.transport
        return None

    def get_connection_key(self, device_id: str) -> ConnectionKey | None:
        """Return the connection key (``"aliyun"`` or ``"mammotion"``) for *device_id*."""
        for key, entry in self._connections.items():
            if device_id in entry.device_ids:
                return key
        return None

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    async def connect_all(self) -> None:
        """Call ``transport.connect()`` for every registered connection."""
        for entry in self._connections.values():
            await entry.transport.connect()

    async def disconnect_all(self) -> None:
        """Call ``transport.disconnect()`` for every registered connection."""
        for entry in self._connections.values():
            await entry.transport.disconnect()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def connections(self) -> dict[ConnectionKey, MQTTPoolEntry]:
        """Read-only view of the current connection pool."""
        return dict(self._connections)
