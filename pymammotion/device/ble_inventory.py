"""BLE device inventory: which BLEDevice belongs to which handle, and attaching it.

Split out of ``MammotionClient``, which had no reason to hold a BLE cache alongside
accounts, transports and sagas.  Unlike the auth code (see ``client_auth.py``) this
is a real collaborator rather than a mixin: it needs three things from the client —
the device registry, the handle funnel, and nothing else — and it *owns* the
``BLETransportManager`` outright, so the cache leaves the client entirely.

BLE is the one per-device transport: exactly one handle holds a device's
``BLETransport`` (``DeviceRegistry.find_ble_owner``), and it stays there until
:meth:`BleInventory.move_ble_to_account` hands it over.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from pymammotion.account.registry import BLE_ONLY_ACCOUNT
from pymammotion.bluetooth.manager import BLETransportManager
from pymammotion.transport.base import TransportType
from pymammotion.transport.ble import BLETransport, BLETransportConfig

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bleak.backends.device import BLEDevice

    from pymammotion.bluetooth.manager import BLEDeviceEntry
    from pymammotion.data.model.device import MowingDevice
    from pymammotion.device.handle import DeviceHandle, DeviceRegistry

_logger = logging.getLogger(__name__)


class BleInventory:
    """Owns the BLEDevice cache and puts BLE transports onto the right handle."""

    def __init__(
        self,
        registry: DeviceRegistry,
        ensure_device_handle: Callable[..., Awaitable[DeviceHandle]],
    ) -> None:
        self._device_registry = registry
        #: The handle funnel — the single place a DeviceHandle is created or re-keyed,
        #: so BLE-only adoption goes through the same sentinel rules as a cloud login.
        self._ensure_device_handle = ensure_device_handle
        self._manager = BLETransportManager()

    def get_entry(self, device_id: str) -> BLEDeviceEntry | None:
        """Return the cached BLE entry for *device_id*, or None."""
        return self._manager.get_entry(device_id)

    async def attach_cached_ble(self, handle: DeviceHandle, device_id: str) -> None:
        """Give *handle* the cached BLEDevice for *device_id*, if there is one and it is free.

        Called when a cloud registration creates a handle for a device we already saw
        over BLE — without it the mower stays cloud-only until the next BLE advert.
        """
        if self._device_registry.find_ble_owner(device_id) is not None:
            return
        entry = self._manager.get_entry(device_id)
        if entry is None or entry.ble_device is None:
            return
        await self._attach_ble(handle, entry.ble_device, entry.rssi)

    async def add_ble_device(self, device_id: str, ble_device: BLEDevice, rssi: int | None = None) -> None:
        """Record an externally-discovered BLE device and attach it to its handle (hybrid mode).

        The advertisement is cached first, so a device seen before its cloud login
        completes is attached when the handle is created.  If a handle already exists,
        the BLE transport is created — or, when one is live, only its cached
        ``BLEDevice`` is refreshed; the link is never torn down to swap objects.

        Pass *rssi* (dBm, from the advertisement) so the transport's weak-signal
        gate can skip BLE when the link is too faint to connect.
        """
        self._manager.register_external_ble_client(device_id, ble_device, rssi)
        if (handle := self._ble_target(device_id)) is not None:
            await self._attach_ble(handle, ble_device, rssi)

    async def update_ble_device(self, device_id: str, ble_device: BLEDevice, rssi: int | None = None) -> bool:
        """Update the BLE advertisement for a known device.

        Always swaps the cached BLEDevice on the live :class:`BLETransport` (if
        wired) so ``bleak_retry_connector`` sees the freshest advertisement on
        the next connect — even when only the advertisement metadata changed.

        Does NOT clear a connect-failure cooldown.  HA pushes advertisements
        constantly; only an explicit :meth:`clear_ble_device` or a successful
        connect resets the failure tracker.

        Returns:
            ``True`` if the cached BLE address actually changed (or this is the
            first device set for this handle); ``False`` for a routine refresh
            of the same address or when no handle exists yet (the advertisement
            is cached for the handle's creation either way).

        """
        self._manager.update_external_ble_client(device_id, ble_device, rssi)
        if (handle := self._ble_target(device_id)) is None:
            return False
        return await self._attach_ble(handle, ble_device, rssi)

    async def clear_ble_device(self, device_id: str) -> None:
        """Forget the cached BLEDevice on the device's BLETransport.

        Forces the next BLE connect attempt to wait for a fresh advertisement
        (or fail with ``NoBLEAddressKnownError`` if the transport isn't in
        ``self_managed_scanning`` mode).  Resets the connect-failure tracker
        and any active cooldown.

        Use when the integration knows BLE is unrecoverable for now (e.g.
        explicit user action, mower confirmed offline) and wants
        :meth:`DeviceHandle.active_transport` to skip BLE until a fresh
        advertisement arrives.  No-op if no BLE transport is wired.
        """
        if (handle := self._device_registry.find_ble_owner(device_id)) is None:
            return
        ble = handle.get_transport(TransportType.BLE)
        if isinstance(ble, BLETransport):
            ble.clear_ble_device()

    async def add_ble_only_device(
        self,
        device_id: str,
        device_name: str,
        initial_device: MowingDevice,
        *,
        ble_device: BLEDevice | None = None,
        ble_address: str | None = None,
        self_managed_scanning: bool | None = None,
    ) -> DeviceHandle:
        """Register a device over BLE — no HTTP login or MQTT involved.

        Provide either a pre-discovered ``BLEDevice`` (e.g. from your own
        ``BleakScanner`` pass) or a MAC ``ble_address`` and let the transport scan
        for it on connect.  The handle is started; call ``transport.connect()`` (or
        :meth:`connect_ble`) to open the GATT connection.

        BLE is per device, not per account.  A handle nobody has claimed is
        registered under ``BLE_ONLY_ACCOUNT``; a later cloud login for the same
        ``device_id`` adopts that very handle (transport, state and ``prefer_ble``
        intact).  Conversely, if a cloud account already holds the device, the BLE
        transport is attached to that handle — one handle owns BLE at a time.

        Args:
            device_id:             Unique device identifier (e.g. ``"Luba-XXXXXX"``) —
                                   must match the cloud device name for adoption.
            device_name:           Human-readable name shown in HA.
            initial_device:        Empty or cached ``MowingDevice`` for initial state.
            ble_device:            Optional pre-discovered bleak ``BLEDevice``.
            ble_address:           Optional MAC.  Required when ``ble_device``
                                   is not supplied.  Stored in the transport
                                   config for self-managed scanning.
            self_managed_scanning: When True, the transport scans for the
                                   device by ``ble_address`` if no BLEDevice is
                                   cached at connect-time.  Defaults to True when
                                   only ``ble_address`` is supplied, False when
                                   ``ble_device`` is supplied (HA-style — scanning
                                   owned by the caller).  Pass explicitly to override.

        Returns:
            The registered ``DeviceHandle``.

        Raises:
            ValueError: when neither ``ble_device`` nor ``ble_address`` is supplied.

        """
        if ble_device is None and ble_address is None:
            raise ValueError("add_ble_only_device requires either ble_device or ble_address")
        if self_managed_scanning is None:
            self_managed_scanning = ble_device is None

        if (holder := self._device_registry.find_ble_owner(device_id)) is not None:
            _logger.info("add_ble_only_device: %s already has a BLE transport — reusing handle", device_name)
            if ble_device is not None:
                cast(BLETransport, holder.get_transport(TransportType.BLE)).set_ble_device(ble_device)
            return holder

        transport = self._new_ble_transport(
            device_id, ble_device, ble_address=ble_address, self_managed_scanning=self_managed_scanning
        )
        if (existing := self._device_registry.get(device_id)) is not None:
            _logger.info(
                "add_ble_only_device: %s is held by account %s — attaching BLE", device_name, existing.account_id
            )
            await existing.add_transport(transport)
            return existing

        handle = await self._ensure_device_handle(
            acct_session=None,
            device_id=device_id,
            device_name=device_name,
            initial_device=initial_device,
            ble=transport,
            prefer_ble=True,
        )
        _logger.info("BLE-only device registered: %s (%s)", device_name, device_id)
        return handle

    async def move_ble_to_account(self, device_id: str, account_id: str) -> None:
        """Hand a device's BLE transport to *account_id*'s handle for that device.

        Only one handle owns a device's BLE transport at a time, and it stays with its
        current holder until moved explicitly here.  The link is not dropped.  An
        unclaimed (``BLE_ONLY_ACCOUNT``) handle left with no transports is removed.

        Raises:
            KeyError: *account_id* holds no handle for *device_id*.

        """
        target = self._device_registry.get(account_id, device_id)
        if target is None:
            raise KeyError(f"account {account_id!r} holds no device {device_id!r}")
        owner = self._device_registry.find_ble_owner(device_id)
        if owner is None or owner is target:
            return
        await target.take_ble_from(owner)
        if owner.account_id == BLE_ONLY_ACCOUNT and not any(owner.has_transport(t) for t in TransportType):
            await self._device_registry.unregister(owner.account_id, owner.device_id)

    def _ble_target(self, device_id: str) -> DeviceHandle | None:
        """Return the handle that should carry *device_id*'s BLE: its current owner, else the resolved holder."""
        return self._device_registry.find_ble_owner(device_id) or self._device_registry.get(device_id)

    @staticmethod
    def _new_ble_transport(
        device_id: str,
        ble_device: BLEDevice | None,
        rssi: int | None = None,
        *,
        ble_address: str | None = None,
        self_managed_scanning: bool = False,
    ) -> BLETransport:
        transport = BLETransport(
            BLETransportConfig(
                device_id=device_id, ble_address=ble_address, self_managed_scanning=self_managed_scanning
            )
        )
        if ble_device is not None:
            transport.set_ble_device(ble_device, rssi)
        return transport

    async def _attach_ble(self, handle: DeviceHandle, ble_device: BLEDevice, rssi: int | None = None) -> bool:
        """Give *handle* a BLE transport for *ble_device*, or refresh the one it has.

        Returns ``True`` when a transport was created or its address changed.
        """
        if (ble := handle.get_transport(TransportType.BLE)) is not None:
            return cast(BLETransport, ble).set_ble_device(ble_device, rssi)
        await handle.add_transport(self._new_ble_transport(handle.device_id, ble_device, rssi))
        return True

    async def connect_ble(self, device_name: str, account_id: str | None = None) -> None:
        """Connect the BLE transport for a registered device.

        Works for both BLE-only devices and hybrid devices that have a BLE
        transport attached.  No-op when the device is unknown or the transport
        is already connected — matches the rest of the public API which
        warns/returns rather than raises on unknown devices.
        """
        handle = self._device_registry.get_by_name(device_name, account_id)
        if handle is None:
            _logger.warning("connect_ble: device %r not registered", device_name)
            return
        transport = handle.get_transport(TransportType.BLE)
        if transport is not None and not transport.is_connected:
            await transport.connect()

    async def add_ble_to_device(self, device_name: str, ble_device: BLEDevice, account_id: str | None = None) -> None:
        """Attach a BLE transport to an already-registered device, or refresh the one it has.

        Args:
            device_name: Registered device name.
            ble_device:  The bleak ``BLEDevice`` to use for the BLE connection.
            account_id:  Disambiguates a device several accounts hold.

        """
        handle = self._device_registry.get_by_name(device_name, account_id)
        if handle is None:
            _logger.warning("add_ble_to_device: device '%s' not registered", device_name)
            return
        await self._attach_ble(handle, ble_device)
