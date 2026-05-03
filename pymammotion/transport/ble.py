"""BLETransport — concrete Transport wrapping bleak for Mammotion BLE devices."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING, Any

from bleak import BleakScanner
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from pymammotion.bluetooth.ble_message import BleMessage
from pymammotion.bluetooth.const import UUID_NOTIFICATION_CHARACTERISTIC
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.transport.base import (
    BLEUnavailableError,
    NoBLEAddressKnownError,
    Transport,
    TransportAvailability,
    TransportError,
    TransportType,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bleak import BLEDevice
    from bleak.backends.characteristic import BleakGATTCharacteristic

_logger = logging.getLogger(__name__)

# How long to wait after the last command before dropping the idle BLE connection.
_DISCONNECT_DELAY = 10


@dataclass(frozen=True)
class BLETransportConfig:
    """Frozen configuration for a BLETransport instance.

    Attributes:
        device_id: Device-side identifier used in logging and the bleak retry loop.
        ble_address: Optional BLE MAC.  Required when ``self_managed_scanning``
            is True; otherwise informational.
        self_managed_scanning: When True, ``connect()`` runs a one-shot
            ``BleakScanner.find_device_by_address`` if no BLEDevice has been
            pushed via :meth:`BLETransport.set_ble_device`.  Use for standalone
            (non-HA) callers — HA-Luba leaves this False because HA owns scanning.
        scan_timeout: Seconds to wait for a self-managed scan.
        connect_failure_threshold: Consecutive ``BleakError`` failures from
            ``establish_connection`` before the transport self-clears the cached
            BLEDevice and enters a cooldown.
        connect_cooldown_seconds: How long to refuse new connect attempts after
            the failure threshold trips.  Advertisement pushes still update the
            cached BLEDevice but ``is_usable`` stays False until cooldown expires.

    """

    device_id: str
    ble_address: str | None = None
    self_managed_scanning: bool = False
    scan_timeout: float = 10.0
    connect_failure_threshold: int = 3
    connect_cooldown_seconds: float = 60.0


class BLETransport(Transport):
    """Concrete Transport wrapping bleak for Mammotion BLE devices.

    A BLEDevice must be supplied via set_ble_device() before calling connect().
    Incoming BLE notifications are forwarded to the on_message callback set by
    the broker layer.

    Outbound payloads are framed via BleMessage.post_custom_data_bytes() which
    applies the BluFi packet header, sequence numbering, and fragmentation
    required by the Mammotion BLE protocol.  Inbound notifications are
    reassembled by BleMessage.parseNotification() before being forwarded.
    """

    on_message: Callable[[bytes], Awaitable[None]] | None = None

    def __init__(self, config: BLETransportConfig) -> None:
        """Initialise the transport with the supplied configuration."""
        super().__init__()
        self._config = config
        self._ble_device: BLEDevice | None = None
        self._client: BleakClientWithServiceCache | None = None
        self._message: BleMessage | None = None
        self._availability: TransportAvailability = TransportAvailability.DISCONNECTED
        self._disconnect_on_idle: bool = True
        self._idle_disconnect_timer: asyncio.TimerHandle | None = None
        # Captured at connect() so disconnect callbacks (which may run on a non-asyncio
        # thread inside bleak's backend) can schedule async work safely.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._operation_lock: asyncio.Lock = asyncio.Lock()
        #: Consecutive ``BleakError`` failures from ``establish_connection``.  Reset on
        #: successful connect or explicit ``clear_ble_device()``.  At
        #: ``config.connect_failure_threshold`` the transport self-clears and starts a cooldown.
        self._consecutive_failures: int = 0
        #: ``time.monotonic()`` deadline before another connect attempt is allowed.
        #: 0.0 when no cooldown is active.
        self._connect_cooldown_until: float = 0.0

    # ------------------------------------------------------------------
    # Public device management
    # ------------------------------------------------------------------

    def set_ble_device(self, device: BLEDevice) -> bool:
        """Supply (or update) the bleak BLEDevice used for the next connect().

        Always swaps the cached pointer so ``bleak_retry_connector``'s
        ``ble_device_callback`` sees the freshest advertisement on the next attempt.
        Does NOT reset ``_consecutive_failures`` or the cooldown — a stream of
        advertisements doesn't prove the link can connect; only a successful
        ``connect()`` or an explicit ``clear_ble_device()`` does.

        Returns:
            ``True`` if the cached BLE address actually changed (or this is the
            first device set); ``False`` for a routine refresh of the same
            address.  Callers can short-circuit redundant work on False.

        """
        previous_address: str | None = self._ble_device.address if self._ble_device is not None else None
        new_address: str = device.address
        self._ble_device = device
        return previous_address != new_address

    def clear_ble_device(self) -> None:
        """Forget the cached BLEDevice, reset failure tracking, and clear cooldown.

        After this call ``is_usable`` returns False until ``set_ble_device()``
        is called with a fresh advertisement.  This is the explicit "give up
        and wait for a new advertisement" entry point — distinct from the
        automatic ``connect()`` failure-threshold path which preserves the
        cooldown so retries are paced.
        """
        self._ble_device = None
        self._consecutive_failures = 0
        self._connect_cooldown_until = 0.0

    @property
    def ble_address(self) -> str | None:
        """Address of the cached BLEDevice, or None if no device is set."""
        return self._ble_device.address if self._ble_device is not None else None

    @property
    def is_usable(self) -> bool:
        """True when this transport has a BLEDevice and isn't in connect-cooldown.

        ``DeviceHandle.active_transport()`` reads this to decide whether to
        consider BLE for routing.  An "unusable" transport stays registered
        (its keepalive listeners and message handler stay wired) but is
        skipped over until it becomes usable again — either by an
        advertisement-driven ``set_ble_device()`` plus cooldown expiry, or
        by an explicit ``clear_ble_device()`` followed by ``set_ble_device()``.
        """
        if self._ble_device is None:
            return False
        return time.monotonic() >= self._connect_cooldown_until

    def set_disconnect_strategy(self, *, disconnect: bool = True) -> None:
        """Set whether the BLE connection should be dropped when the device is idle.

        When disconnect=True (default) the transport will disconnect after
        commands complete, reducing power consumption.  When disconnect=False
        the connection is kept alive (suitable for stay-connected-Bluetooth mode).
        """
        self._disconnect_on_idle = disconnect

    # ------------------------------------------------------------------
    # Transport ABC
    # ------------------------------------------------------------------

    @property
    def transport_type(self) -> TransportType:
        """Return the transport type for this implementation."""
        return TransportType.BLE

    @property
    def is_connected(self) -> bool:
        """True when the bleak client exists and reports itself connected."""
        return self._client is not None and self._client.is_connected

    @property
    def availability(self) -> TransportAvailability:
        """Current availability state of this transport."""
        return self._availability

    async def connect(self) -> None:
        """Establish the BLE connection and start receiving notifications.

        Cooldown gate: if the failure threshold tripped recently, the call is
        rejected immediately with ``BLEUnavailableError`` — no bleak round-trip,
        no proxy slot taken.

        Self-managed scanning: if ``self_managed_scanning`` is set on the config
        and no BLEDevice has been pushed via :meth:`set_ble_device`, the
        transport runs a one-shot ``BleakScanner.find_device_by_address`` to
        discover the device.  HA-Luba leaves this disabled and relies on HA's
        bluetooth integration to push BLEDevices instead.

        Raises:
            BLEUnavailableError: in cooldown, scan failure, or
                ``establish_connection`` raised ``BleakError``.
            NoBLEAddressKnownError: no BLEDevice cached and self-managed scan
                disabled (or address is missing for the scan).

        """
        # Cooldown gate first — refuse immediately so the caller falls back to MQTT
        # rather than burning a connection slot on a doomed attempt.
        remaining = self._connect_cooldown_until - time.monotonic()
        if remaining > 0:
            raise BLEUnavailableError(
                f"BLE connect for {self._config.device_id!r} is in cooldown ({remaining:.0f}s remaining)"
            )

        if self._ble_device is None:
            if self._config.self_managed_scanning:
                await self._self_managed_discover()
            if self._ble_device is None:
                msg = (
                    f"No BLEDevice registered for device_id={self._config.device_id!r}; "
                    f"call set_ble_device() first or enable self_managed_scanning in the config"
                )
                raise NoBLEAddressKnownError(msg)

        if self.is_connected:
            _logger.debug("BLETransport.connect() called while already connected — ignoring")
            return

        # Capture the loop NOW so _handle_disconnect can dispatch back into it
        # even if bleak invokes the callback from a different thread.
        self._loop = asyncio.get_running_loop()

        await self._notify_availability(TransportAvailability.CONNECTING)
        _logger.debug("BLETransport connecting to %s", self._config.device_id)

        try:
            self._client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self._config.device_id,
                self._handle_disconnect,
                max_attempts=2,
                ble_device_callback=lambda: self._ble_device,  # type: ignore[arg-type,return-value]
            )
        except BleakError as exc:
            await self._notify_availability(TransportAvailability.DISCONNECTED)
            self._record_connect_failure()
            raise BLEUnavailableError(f"BLE connection failed for {self._config.device_id!r}: {exc}") from exc

        self._message = BleMessage(self._client)

        await self._client.start_notify(UUID_NOTIFICATION_CHARACTERISTIC, self._notification_handler)
        await self._notify_availability(TransportAvailability.CONNECTED)
        _logger.debug("BLETransport connected to %s", self._config.device_id)

        # Clear any stale idle-disconnect timer from a previous session.
        self._cancel_idle_disconnect_timer()
        # Successful connect resets the failure tracker.
        self._consecutive_failures = 0

        # One-shot sync on connect — subsequent periodic syncs are driven by
        # DeviceHandle._keep_alive_loop (20 s).
        await self._ble_sync()

    def _record_connect_failure(self) -> None:
        """Increment the failure counter; at threshold, clear device and start cooldown.

        We deliberately *clear the cached BLEDevice* on threshold trip even
        though HA will keep pushing fresh advertisements.  The cooldown timer
        still gates ``is_usable``, but clearing the device makes the next
        ``connect()`` raise ``NoBLEAddressKnownError`` (or trigger a fresh
        scan in self-managed mode) once the cooldown lapses — guaranteeing the
        retry uses a fresh BLEDevice rather than a stale pointer that already
        failed.
        """
        self._consecutive_failures += 1
        if self._consecutive_failures < self._config.connect_failure_threshold:
            return
        self._connect_cooldown_until = time.monotonic() + self._config.connect_cooldown_seconds
        _logger.info(
            "BLETransport[%s]: %d consecutive connect failures — cooling down for %.0fs",
            self._config.device_id,
            self._consecutive_failures,
            self._config.connect_cooldown_seconds,
        )
        # Reset counter so the next post-cooldown attempt starts a fresh tally.
        self._consecutive_failures = 0
        # Drop the stale BLEDevice; HA's next advertisement will repopulate.
        self._ble_device = None

    async def _self_managed_discover(self) -> None:
        """Run a one-shot bleak scan to populate ``_ble_device`` from ``ble_address``.

        Only called from ``connect()`` when ``self_managed_scanning=True``.
        On failure, leaves ``_ble_device`` as None — caller will raise
        ``NoBLEAddressKnownError``.
        """
        address = self._config.ble_address
        if not address:
            _logger.warning(
                "BLETransport[%s]: self_managed_scanning=True but no ble_address in config",
                self._config.device_id,
            )
            return
        _logger.debug(
            "BLETransport[%s]: self-managed scan for %s (timeout=%.0fs)",
            self._config.device_id,
            address,
            self._config.scan_timeout,
        )
        try:
            device = await BleakScanner.find_device_by_address(address, timeout=self._config.scan_timeout)
        except (BleakError, TimeoutError) as exc:
            _logger.debug("BLETransport[%s]: self-managed scan failed: %s", self._config.device_id, exc)
            return
        if device is None:
            _logger.debug(
                "BLETransport[%s]: self-managed scan found no device at %s",
                self._config.device_id,
                address,
            )
            return
        self._ble_device = device

    async def disconnect(self) -> None:
        """Gracefully disconnect the BLE client."""
        self._cancel_idle_disconnect_timer()
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()
        self._client = None
        self._message = None
        await self._notify_availability(TransportAvailability.DISCONNECTED)

    async def _write_payload(self, payload: bytes) -> None:
        """Write *payload* over GATT. Raises TransportError on failure."""
        if self._client is None or self._message is None:
            msg = "BLETransport has no client; cannot send payload"
            raise TransportError(msg)
        _logger.debug("BLETransport send: %d bytes to %s", len(payload), self._config.device_id)
        if not self._client.is_connected:
            await self.connect()
        try:
            async with self._operation_lock:
                await self._message.post_custom_data_bytes(payload)
        except (TimeoutError, BleakError, OSError) as exc:
            await self._notify_availability(TransportAvailability.DISCONNECTED)
            raise TransportError(f"BLE send failed for {self._config.device_id!r}: {exc}") from exc
        if not self._client.is_connected:
            await self._notify_availability(TransportAvailability.DISCONNECTED)
            raise TransportError(f"BLE send failed for {self._config.device_id!r}: client disconnected during write")

    async def send(self, payload: bytes, iot_id: str = "") -> None:
        """Frame and write payload via the BleMessage codec, then reset the idle-disconnect timer.

        Use this for real user commands.  For keepalive heartbeats use
        ``send_heartbeat()`` so the idle-disconnect timer is not disturbed.
        """
        _logger.debug("Sending BLE payload: %s, %s iot_id", payload, iot_id)
        await self._write_payload(payload)
        self._reset_idle_disconnect_timer()

    async def send_heartbeat(self, payload: bytes, iot_id: str = "") -> None:
        """Write a keepalive heartbeat without resetting the idle-disconnect timer.

        When ``stay_connected_bluetooth=False`` the idle-disconnect timer must
        only be reset by genuine user commands, not by periodic ble_sync pings.
        Calling ``send()`` for heartbeats would perpetually postpone the timer
        and prevent the idle-disconnect from ever firing.
        """
        _logger.debug("Sending BLE heartbeat %s iot_id", iot_id)
        await self._write_payload(payload)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    async def _notify_availability(self, state: TransportAvailability) -> None:
        """Update internal state and notify all availability listeners."""
        self._availability = state
        await self._fire_availability_listeners(state)

    def _handle_disconnect(self, _client: Any) -> None:
        """Handle unexpected disconnect reported by bleak.

        bleak may invoke this callback from a non-asyncio thread depending on the
        backend, so we cannot use asyncio.get_running_loop() here. Use the loop
        captured at connect() time and dispatch via call_soon_threadsafe().
        """
        if self._availability is TransportAvailability.DISCONNECTED:
            return

        _logger.warning("BLETransport: device %s disconnected", self._config.device_id)
        self._message = None
        self._availability = TransportAvailability.DISCONNECTED
        if not self._availability_listeners:
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            _logger.debug(
                "BLETransport[%s]: no captured loop, dropping disconnect notification",
                self._config.device_id,
            )
            return
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(  # - fire-and-forget dispatch
                self._fire_availability_listeners(TransportAvailability.DISCONNECTED)
            )
        )

    async def _notification_handler(self, _characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Parse incoming BLE notifications through the BluFi codec and forward complete frames."""
        if self._message is None:
            return

        result = self._message.parseNotification(data)
        if result != 0:
            # result == 1  → fragment received, waiting for more
            # result == 2  → duplicate sequence, already processed
            # result < 0   → parse error
            return

        payload = await self._message.parseBlufiNotifyData(return_bytes=True)
        self._message.clear_notification()

        if payload and self.on_message is not None:
            await self.on_message(bytes(payload))

    # ------------------------------------------------------------------
    # Idle disconnect
    # ------------------------------------------------------------------

    def _reset_idle_disconnect_timer(self) -> None:
        """(Re)start the idle-disconnect countdown after a send completes."""
        if not self._disconnect_on_idle:
            return
        self._cancel_idle_disconnect_timer()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._idle_disconnect_timer = loop.call_later(_DISCONNECT_DELAY, self._disconnect_from_idle_timer)

    def _cancel_idle_disconnect_timer(self) -> None:
        """Cancel the pending idle-disconnect timer, if any."""
        if self._idle_disconnect_timer is not None:
            self._idle_disconnect_timer.cancel()
            self._idle_disconnect_timer = None

    def _disconnect_from_idle_timer(self) -> None:
        """Timer callback: disconnect if idle, or reschedule if a send is in flight."""
        if self._operation_lock.locked() and self.is_connected:
            # A send is still in progress — postpone until it finishes.
            _logger.debug(
                "BLETransport: send in progress for %s — deferring idle disconnect",
                self._config.device_id,
            )
            self._reset_idle_disconnect_timer()
            return
        self._cancel_idle_disconnect_timer()
        try:
            loop = asyncio.get_running_loop()
            _task = loop.create_task(self._execute_idle_disconnect())
        except RuntimeError:
            pass

    async def _execute_idle_disconnect(self) -> None:
        """Disconnect the idle BLE connection (respects disconnect_on_idle flag)."""
        if not self._disconnect_on_idle:
            return
        _logger.debug(
            "BLETransport: idle timeout — disconnecting %s after %ss",
            self._config.device_id,
            _DISCONNECT_DELAY,
        )
        await self.disconnect()

    # ------------------------------------------------------------------
    # BLE keepalive sync
    # ------------------------------------------------------------------

    async def _ble_sync(self) -> None:
        """Send a one-shot ``todev_ble_sync(2)`` packet.

        Fired on connect (and as a courtesy on clean disconnect).  Periodic
        heartbeats are driven by ``DeviceHandle._keep_alive_loop`` (20 s).
        """
        if self._client is None or not self._client.is_connected or self._message is None:
            return

        command_bytes = MammotionCommand(self._config.device_id, 0).send_todev_ble_sync(2)
        await self._message.post_custom_data_bytes(command_bytes)
