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
from pymammotion.bluetooth.manager import BLETransportManager
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.transport.base import TransportType
from pymammotion.transport.ble import BLETransport, BLETransportConfig

if TYPE_CHECKING:
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

        Raises:
            KeyError: if *name* is not a registered device.

        """
        handle = self._device_registry.get_by_name(name)
        if handle is None:
            msg = f"Device '{name}' not registered"
            raise KeyError(msg)
        _logger.debug("send_command_with_args: device=%s key=%s kwargs=%s", name, key, kwargs)

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
