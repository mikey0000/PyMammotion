"""BLETransport — concrete Transport wrapping bleak for Mammotion BLE devices."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING, Any

from bleak import BleakScanner
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, BleakOutOfConnectionSlotsError, establish_connection

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
        min_rssi: Weakest advertisement RSSI (dBm) the transport will still
            consider usable.  When the last reported RSSI is below this, a GATT
            connection is unlikely to succeed, so ``is_usable`` returns False and
            routing falls back to MQTT until a stronger advertisement arrives.
            RSSI is only checked when it is known (pushed via
            :meth:`BLETransport.set_ble_device`); an unknown RSSI never gates.

    """

    device_id: str
    ble_address: str | None = None
    self_managed_scanning: bool = False
    scan_timeout: float = 10.0
    connect_failure_threshold: int = 1
    connect_cooldown_seconds: float = 120.0
    min_rssi: int = -90


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
        # Captured at connect() so disconnect callbacks (which may run on a non-asyncio
        # thread inside bleak's backend) can schedule async work safely.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._operation_lock: asyncio.Lock = asyncio.Lock()
        #: Serializes ``connect()`` calls so two concurrent writers (or a writer
        #: and an auto-reconnect from the disconnect callback) cannot both call
        #: ``establish_connection`` in parallel.  Distinct from ``_operation_lock``
        #: so a write that triggers reconnect doesn't deadlock when ``connect()``
        #: runs from inside the operation lock.
        self._connect_lock: asyncio.Lock = asyncio.Lock()
        #: Consecutive ``BleakError`` failures from ``establish_connection``.  Reset on
        #: successful connect or explicit ``clear_ble_device()``.  At
        #: ``config.connect_failure_threshold`` the transport self-clears and starts a cooldown.
        self._consecutive_failures: int = 0
        #: ``time.monotonic()`` deadline before another connect attempt is allowed.
        #: 0.0 when no cooldown is active.
        self._connect_cooldown_until: float = 0.0
        #: Last advertisement RSSI (dBm) pushed via ``set_ble_device``.  ``None``
        #: until a caller supplies one — an unknown RSSI never gates ``is_usable``.
        self._last_rssi: int | None = None

    # ------------------------------------------------------------------
    # Public device management
    # ------------------------------------------------------------------

    def set_ble_device(self, device: BLEDevice, rssi: int | None = None) -> bool:
        """Supply (or update) the bleak BLEDevice used for the next connect().

        Always swaps the cached pointer so ``bleak_retry_connector``'s
        ``ble_device_callback`` sees the freshest advertisement on the next attempt.
        Does NOT reset ``_consecutive_failures`` or the cooldown — a stream of
        advertisements doesn't prove the link can connect; only a successful
        ``connect()`` or an explicit ``clear_ble_device()`` does.

        Args:
            device: The freshest bleak ``BLEDevice`` from the advertisement.
            rssi: Optional advertisement RSSI (dBm).  bleak 3.x carries RSSI on
                the ``AdvertisementData``, not the ``BLEDevice``, so callers that
                have it must pass it here for the weak-signal gate in
                :attr:`is_usable` to take effect.  ``None`` leaves the last known
                RSSI untouched.

        Returns:
            ``True`` if the cached BLE address actually changed (or this is the
            first device set); ``False`` for a routine refresh of the same
            address.  Callers can short-circuit redundant work on False.

        """
        previous_address: str | None = self._ble_device.address if self._ble_device is not None else None
        new_address: str = device.address
        self._ble_device = device
        if rssi is not None:
            self._last_rssi = rssi
        return previous_address != new_address

    def clear_ble_device(self) -> None:
        """Forget the cached BLEDevice, reset failure tracking, and clear cooldown.

        After this call ``is_usable`` returns False until ``set_ble_device()``
        is called with a fresh advertisement.  This is the explicit "give up
        and wait for a new advertisement" entry point — distinct from the
        automatic ``connect()`` failure-threshold path which arms a cooldown
        while preserving the device pointer for re-use once the timer lapses.
        """
        self._ble_device = None
        self._consecutive_failures = 0
        self._connect_cooldown_until = 0.0
        self._last_rssi = None

    @property
    def ble_address(self) -> str | None:
        """Address of the cached BLEDevice, or None if no device is set."""
        return self._ble_device.address if self._ble_device is not None else None

    @property
    def is_usable(self) -> bool:
        """True when this transport has a BLEDevice, a workable signal, and isn't in cooldown.

        ``DeviceHandle.active_transport()`` reads this to decide whether to
        consider BLE for routing.  An "unusable" transport stays registered
        (its keepalive listeners and message handler stay wired) but is
        skipped over until it becomes usable again — either by an
        advertisement-driven ``set_ble_device()`` plus cooldown expiry, or
        by an explicit ``clear_ble_device()`` followed by ``set_ble_device()``.

        A known RSSI below ``config.min_rssi`` also marks the transport
        unusable: the advertisement is audible but too weak to establish a
        reliable GATT link, so routing falls back to MQTT until a stronger
        advertisement arrives.  An unknown RSSI (never pushed) does not gate.
        """
        if self._ble_device is None:
            return False
        if self._last_rssi is not None and self._last_rssi < self._config.min_rssi:
            return False
        return time.monotonic() >= self._connect_cooldown_until

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
        # Fast cooldown gate — refuse immediately without taking the lock so the
        # caller falls back to MQTT rather than burning a connection slot.
        remaining = self._connect_cooldown_until - time.monotonic()
        if remaining > 0:
            raise BLEUnavailableError(
                f"BLE connect for {self._config.device_id!r} is in cooldown ({remaining:.0f}s remaining)"
            )

        # Serialize concurrent connects.  Two writers racing through
        # ``_write_payload`` (or a write racing the disconnect-callback's
        # auto-reconnect) must not both call ``establish_connection`` —
        # bleak/the proxy don't tolerate parallel connects against the same client.
        async with self._connect_lock:
            # Re-check cooldown under the lock — another caller may have tripped
            # the threshold while we were waiting.
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

            # Re-check connection state under the lock — a previous holder may
            # have just established the connection on our behalf.
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
                    use_services_cache=True,
                    timeout=2,
                    max_attempts=1,
                    ble_device_callback=lambda: self._ble_device,  # type: ignore
                )
            except BleakError as exc:
                await self._notify_availability(TransportAvailability.DISCONNECTED)
                self._record_connect_failure(exc)
                raise BLEUnavailableError(f"BLE connection failed for {self._config.device_id!r}: {exc}") from exc

            self._message = BleMessage(self._client)

            # BlueZ may retain a stale notify subscription from a previous ungraceful
            # disconnect.  Release it proactively so start_notify doesn't get
            # [org.bluez.Error.NotPermitted] Notify acquired.
            with contextlib.suppress(Exception):
                await self._client.stop_notify(UUID_NOTIFICATION_CHARACTERISTIC)
            try:
                await self._client.start_notify(UUID_NOTIFICATION_CHARACTERISTIC, self._notification_handler)
            except BleakError as exc:
                if "Notify acquired" in str(exc):
                    # BlueZ reports the channel is already open — our previous
                    # connection's subscription is still live.  Notifications will
                    # continue to arrive, so there is nothing to do here.
                    _logger.debug(
                        "BLETransport: notify already acquired for %s — reusing existing subscription",
                        self._config.device_id,
                    )
                else:
                    await self._notify_availability(TransportAvailability.DISCONNECTED)
                    self._record_connect_failure()
                    raise BLEUnavailableError(f"BLE start_notify failed for {self._config.device_id!r}: {exc}") from exc
            await self._notify_availability(TransportAvailability.CONNECTED)
            _logger.debug("BLETransport connected to %s", self._config.device_id)

            # Successful connect resets the failure tracker.
            self._consecutive_failures = 0

            # One-shot sync on connect — subsequent periodic syncs are driven by
            # DeviceHandle._keep_alive_loop (20 s).
            await self._ble_sync()

    def _record_connect_failure(self, exc: BleakError | None = None) -> None:
        """Increment the failure counter; clear device and start cooldown at threshold.

        A :class:`BleakOutOfConnectionSlotsError` (the proxy/adapter is out of
        connection slots, or the device is no longer reachable) trips the cooldown
        **immediately**, bypassing the consecutive-failure threshold: an immediate
        retry cannot succeed — there is no free slot and the device may be out of
        range — so we drive ``is_usable`` False right away.  The handle's send paths
        already skip BLE (falling through to MQTT) while a transport is unusable, so
        this turns a per-send "BLE unavailable — falling back to MQTT" churn into a
        single attempt followed by quiet MQTT use until BLE is reachable again.
        After the cooldown lapses, the next advertisement re-arms a single retry.

        We deliberately *clear the cached BLEDevice* on trip even though HA will keep
        pushing fresh advertisements.  The cooldown timer still gates ``is_usable``,
        but clearing the device makes the next ``connect()`` raise
        ``NoBLEAddressKnownError`` (or trigger a fresh scan in self-managed mode) once
        the cooldown lapses — guaranteeing the retry uses a fresh BLEDevice rather
        than a stale pointer that already failed.
        """
        immediate = isinstance(exc, BleakOutOfConnectionSlotsError)
        self._consecutive_failures += 1
        if not immediate and self._consecutive_failures < self._config.connect_failure_threshold:
            return
        self._connect_cooldown_until = time.monotonic() + self._config.connect_cooldown_seconds
        _logger.info(
            "BLETransport[%s]: %s — cooling down for %.0fs (is_usable now False; sends use MQTT)",
            self._config.device_id,
            "out of connection slots / device unreachable"
            if immediate
            else f"{self._consecutive_failures} consecutive connect failures",
            self._config.connect_cooldown_seconds,
        )
        # Reset counter so the next post-cooldown attempt starts a fresh tally.
        self._consecutive_failures = 0
        # _ble_device is intentionally kept — the device may just be temporarily
        # out of range and is likely still reachable once the cooldown expires.
        # is_usable returns False during cooldown via the monotonic timer check,
        # and automatically recovers to True once the timer lapses.

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
        if self._client is not None and self._client.is_connected:
            try:
                await self._client.disconnect()
            except BleakError as exc:
                _logger.warning("BLETransport[%s]: failed to disconnect: %s", self._config.device_id, exc)
        self._client = None
        self._message = None
        await self._notify_availability(TransportAvailability.DISCONNECTED)

    async def _write_payload(self, payload: bytes) -> None:
        """Write *payload* over GATT. Raises TransportError on failure.

        The auto-reconnect, the connection re-check, and the GATT write all
        happen under ``_operation_lock``.  This serializes concurrent writers so
        two callers can't both observe ``not is_connected`` and race
        ``establish_connection``; it also prevents a write from running against
        ``_message``/``_client`` that the disconnect handler is in the middle
        of clearing.  ``connect()`` uses a separate ``_connect_lock`` so this
        nested call doesn't self-deadlock.
        """
        _logger.debug("BLETransport send: %d bytes to %s", len(payload), self._config.device_id)
        async with self._operation_lock:
            if self._client is None or not self._client.is_connected:
                await self.connect()
            if self._client is None or self._message is None:
                msg = f"BLETransport has no client; cannot send payload to {self._config.device_id!r}"
                raise TransportError(msg)
            try:
                await self._message.post_custom_data_bytes(payload)
            except (TimeoutError, BleakError, OSError) as exc:
                # Clear client refs immediately so is_connected returns False
                # before _on_disconnect_async runs — prevents the ble_loop from
                # retrying against a known-dead connection (GATT error 133 etc.).
                self._client = None
                self._message = None
                await self._notify_availability(TransportAvailability.DISCONNECTED)
                raise TransportError(f"BLE send failed for {self._config.device_id!r}: {exc}") from exc
            if not self._client.is_connected:
                self._client = None
                self._message = None
                await self._notify_availability(TransportAvailability.DISCONNECTED)
                raise TransportError(
                    f"BLE send failed for {self._config.device_id!r}: client disconnected during write"
                )

    async def send(self, payload: bytes, iot_id: str = "", firmware_version: str = "1.0.0.0") -> None:
        """Frame and write payload via the BleMessage codec."""
        _logger.debug("Sending BLE payload: %s, %s iot_id", payload, iot_id)
        self._last_send_monotonic = time.monotonic()
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
        backend.  We do **not** mutate any state here — every reader of
        ``_message``/``_client``/``_availability`` lives on the event loop, so
        cross-thread mutation could race a concurrent ``_write_payload`` that has
        already passed its is-connected check.  Instead, schedule
        ``_on_disconnect_async`` onto the captured loop and let it do all the work.

        Without a captured loop we can't dispatch — fall back to a synchronous
        flag flip so the next event-loop-side caller sees DISCONNECTED.  This is
        only safe before ``connect()`` has ever run (no listeners, no live writes).
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            self._availability = TransportAvailability.DISCONNECTED
            return
        loop.call_soon_threadsafe(self._dispatch_disconnect)

    def _dispatch_disconnect(self) -> None:
        """Schedule async disconnect handling.  Runs on the event loop."""
        asyncio.create_task(self._on_disconnect_async())

    async def _on_disconnect_async(self) -> None:
        """Process an unexpected disconnect on the event loop.

        Single-threaded once we're here: every other writer to ``_message``,
        ``_client``, and ``_availability`` is also on this loop, so no extra
        synchronization is required.

        Auto-reconnect is *not* attempted here — the higher-level loops in
        ``DeviceHandle`` decide when to revive BLE (on user command, on the
        BLE polling tick, on advertisement-driven cooldown expiry).  Doing it
        from the disconnect callback caused unconditional reconnect storms,
        including racing the explicit ``disconnect()`` path.
        """
        self._client = None
        self._message = None
        if self._availability is TransportAvailability.DISCONNECTED:
            return
        _logger.warning("BLETransport: device %s disconnected", self._config.device_id)
        await self._notify_availability(TransportAvailability.DISCONNECTED)

    async def _notification_handler(self, _characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Parse incoming BLE notifications through the BluFi codec and forward complete frames."""
        if self._message is None:
            return

        result = self._message.parseNotification(bytes(data))
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
    # BLE keepalive sync
    # ------------------------------------------------------------------

    async def _ble_sync(self) -> None:
        """Send a one-shot sync packet.

        Fired on connect (and as a courtesy on clean disconnect).  Periodic
        heartbeats are driven by ``ble_loop.ble_activity_loop``.
        """
        if self._client is None or not self._client.is_connected or self._message is None:
            return

        command_bytes = MammotionCommand(self._config.device_id, 0).send_todev_ble_sync(2)
        _logger.debug("BLETransport: sending one-shot todev_ble_sync(2) (connect/disconnect)")
        await self._message.post_custom_data_bytes(command_bytes)
