"""MammotionClient — top-level entry point for the new architecture.

Owns the DeviceRegistry, AccountRegistry, and BLETransportManager.
The HA integration interacts only with this class.

BLE-only mode
-------------
When a mower is only reachable over Bluetooth (no cloud account, or simply
not wanting MQTT), call ``add_ble_only_device()`` instead of going through
login/cloud.  The resulting DeviceHandle has ``prefer_ble=True`` and only a
BLETransport attached — no HTTP or MQTT calls are made.

Two flavours of caller-provided BLE info are supported:

1. **Pre-discovered BLEDevice** — if you've already run a scan (or are using
   Home Assistant's bluetooth integration which gives you a fresh BLEDevice)::

    client = MammotionClient()
    await client.add_ble_only_device(
        device_id="Luba-XXXXXX",
        device_name="Luba-XXXXXX",
        initial_device=MowingDevice(name="Luba-XXXXXX"),
        ble_device=discovered_ble_device,   # bleak BLEDevice
    )
    await client.mower("Luba-XXXXXX").start()
    handle = client.mower("Luba-XXXXXX")
    await handle.get_transport(TransportType.BLE).connect()

2. **MAC address only** — the transport runs a one-shot bleak scan when
   ``connect()`` is called and re-scans on later reconnects::

    await client.add_ble_only_device(
        device_id="Luba-XXXXXX",
        device_name="Luba-XXXXXX",
        initial_device=MowingDevice(name="Luba-XXXXXX"),
        ble_address="AA:BB:CC:DD:EE:FF",
    )
    # self_managed_scanning defaults to True when only an address is given.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from functools import partial
import json
import logging
import time
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

from pymammotion.account.registry import BLE_ONLY_ACCOUNT, AccountRegistry, AccountSession
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.client_auth import _AUTH_REJECTED, CloudAuthMixin
from pymammotion.data.model import GenerateRouteInformation
from pymammotion.data.model.device import MowerDevice, MowingDevice, RTKBaseStationDevice, create_device
from pymammotion.data.model.generate_geojson import (
    apply_area_geojson,
    apply_dynamics_line_geojson,
    apply_mowing_geojson,
)
from pymammotion.data.model.hash_list import PathType
from pymammotion.data.model.svg import chunk_svg_messages
from pymammotion.device.auto_fetch import AutoFetchWatchers, _should_fetch_mow_path
from pymammotion.device.ble_inventory import BleInventory
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.device.inbound_router import InboundRouter
from pymammotion.device.readiness import get_readiness_checker
from pymammotion.http.model.http import CheckDeviceVersion, DeviceRecord, MQTTConnection
from pymammotion.messaging.command_queue import Priority, execute_command
from pymammotion.messaging.common_data_saga import CommonDataSaga
from pymammotion.messaging.edge_saga import EdgeMappingSaga
from pymammotion.messaging.map_saga import MapFetchSaga
from pymammotion.messaging.mow_path_saga import MowPathSaga
from pymammotion.messaging.plan_saga import PlanFetchSaga
from pymammotion.messaging.spino_plan_saga import SpinoPlanFetchSaga
from pymammotion.messaging.svg_saga import SvgSendSaga
from pymammotion.proto import RptAct, RptInfoType
from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport
from pymammotion.transport.base import (
    AuthError,
    NoTransportAvailableError,
    ReLoginRequiredError,
    SessionExpiredError,
    Subscription,
    TransportError,
    TransportType,
)
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig
from pymammotion.utility.device_type import DeviceType

#: Channels for the continuous subscription (matches HA-Luba async_request_iot_sync_continuous).
_CONTINUOUS_STREAM_CHANNELS: list[RptInfoType] = [
    RptInfoType.RIT_DEV_STA,
    RptInfoType.RIT_DEV_LOCAL,
    RptInfoType.RIT_WORK,
    RptInfoType.RIT_MAINTAIN,
    RptInfoType.RIT_BASESTATION_INFO,
    RptInfoType.RIT_VIO,
    RptInfoType.RIT_CONNECT,
]
#: Full channel list used by the one-shot request_iot_sync.
#: Seconds to wait before each Aliyun→Mammotion unbound-migration attempt (first is
#: immediate).  The cloud-side migration after a firmware update can take minutes.
_UNBOUND_MIGRATION_DELAYS: tuple[float, ...] = (0.0, 30.0, 60.0, 120.0, 180.0)

_ONE_SHOT_CHANNELS: list[RptInfoType] = [
    RptInfoType.RIT_DEV_STA,
    RptInfoType.RIT_DEV_LOCAL,
    RptInfoType.RIT_WORK,
    RptInfoType.RIT_MAINTAIN,
    RptInfoType.RIT_BASESTATION_INFO,
    RptInfoType.RIT_VIO,
    RptInfoType.RIT_CONNECT,
    RptInfoType.RIT_FW_INFO,
    RptInfoType.RIT_VISION_POINT,
    RptInfoType.RIT_VISION_STATISTIC,
    RptInfoType.RIT_CUTTER_INFO,
    RptInfoType.RIT_RTK,
]
if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bleak import BLEDevice

    from pymammotion.auth.token_manager import MQTTCredentials, TokenManager
    from pymammotion.data.model.device import Device as DeviceModel
    from pymammotion.data.mqtt.event import ThingEventMessage
    from pymammotion.data.mqtt.properties import ThingPropertiesMessage
    from pymammotion.data.mqtt.status import ThingStatusMessage
    from pymammotion.http.http import MammotionHTTP
    from pymammotion.transport.base import Transport
    from pymammotion.transport.ble import BLETransport

_logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class _CloudBinding:
    """What a cloud registration contributes to a DeviceHandle beyond the transport."""

    transport: Transport
    iot_id: str
    product_key: str
    user_account: int
    token_manager: TokenManager | None


class MammotionClient(CloudAuthMixin):
    """Top-level client — stable HA-facing API for the new architecture."""

    def __init__(self, ha_version: str | None = None) -> None:
        """Initialise the client with empty registries.

        Args:
            ha_version: Optional Home Assistant integration version string,
                surfaced to Mammotion servers via the ``App-Version`` HTTP header
                (e.g. ``"Home Assistant,0.5.7"``).

        """
        self._device_registry: DeviceRegistry = DeviceRegistry()
        self._account_registry: AccountRegistry = AccountRegistry()
        self._ble = BleInventory(self._device_registry, self._ensure_device_handle)
        self._stopped: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()
        #: ``(account_id, iot_id)`` → registry key.  iot_ids are scoped per account on the
        #: cloud side, so the same physical device shared to two accounts stays distinct.
        self._inbound = InboundRouter(self._device_registry)
        # RAII subscriptions for state-change watchers (keyed by device_name)
        self._watchers = AutoFetchWatchers(
            self._device_registry,
            start_map_sync=self.start_map_sync,
            start_plan_sync=self.start_plan_sync,
            start_mow_path_saga=self.start_mow_path_saga,
        )
        self._ha_version: str | None = ha_version
        #: Fired when all automatic auth recovery attempts (relogin, token refresh,
        #: reconnect) have been exhausted and human intervention is required.
        #: Called with ``(account_id, transport_type, exc)`` so the host can mark
        #: exactly the affected account's mowers-on-that-transport as needing
        #: re-auth.  HA-Luba wires this to ``entry.async_start_reauth()``.
        self.on_unrecoverable_auth_error: Callable[[str, TransportType, Exception], Awaitable[None]] | None = None
        #: Fired (async) with ``(device_name, iot_id)`` when a device is unbound from
        #: the cloud (Aliyun 29004) and is no longer present on EITHER cloud after
        #: re-discovery — i.e. genuinely removed from the account.  HA-Luba wires this
        #: to delete the device + its entities from the HA device/entity registry.
        self.on_device_removed: Callable[[str, str], Awaitable[None]] | None = None
        #: Fired (async) whenever any credential type is successfully refreshed.
        #: Integrations can wire this to persist the updated token cache.
        self._on_credentials_updated: Callable[[], Awaitable[None]] | None = None

    @property
    def on_credentials_updated(self) -> Callable[[], Awaitable[None]] | None:
        """Callback fired after any successful credential refresh."""
        return self._on_credentials_updated

    @on_credentials_updated.setter
    def on_credentials_updated(self, value: Callable[[], Awaitable[None]] | None) -> None:
        self._on_credentials_updated = value
        # Forward to every account's token manager, not just the default session's:
        # each account refreshes its own credentials and each rotation needs persisting.
        for session in self._account_registry.all_sessions:
            if session.token_manager is not None:
                session.token_manager.on_credentials_updated = value

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
        for session in self._account_registry.all_sessions:
            if session.token_manager is not None:
                # Cancel before the handles go: the scheduler is a bare asyncio task
                # and would otherwise keep renewing tokens for a client that is gone.
                await session.token_manager.stop_refresh_scheduler()
        for handle in self._device_registry.all_devices:
            await handle.stop()

    async def remove_device(self, name: str, account_id: str | None = None) -> None:
        """Stop and remove the named device from the registry.

        Account-shared cloud transports (Aliyun / Mammotion MQTT) are detached —
        NOT disconnected — while other devices on the same account remain, since
        ``handle.stop()`` disconnects every transport still attached and would
        otherwise tear down cloud connectivity for every surviving mower.  Only
        the account's last device takes the shared transport down with it.
        """
        handle = self._device_registry.get_by_name(name, account_id)
        if handle is None:
            return
        self.teardown_device_watchers(name)
        self._inbound.unbind(handle.account_id, handle.iot_id)
        if (session := self._get_session_for_handle(handle)) is not None:
            session.device_ids.discard(name)
            if session.device_ids:
                for transport_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
                    handle.detach_transport(transport_type)
        await self._device_registry.unregister(handle.account_id, handle.device_id)

    # ------------------------------------------------------------------
    # Device state watchers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Auto-fetch watchers — see pymammotion/device/auto_fetch.py
    # ------------------------------------------------------------------

    def setup_device_watchers(self, device_name: str) -> Subscription | None:
        """Wire the state-change watchers that auto-trigger the fetch sagas.

        Returns the first registered :class:`Subscription`, or ``None`` when the device
        is not registered yet — the caller may cancel it directly, though
        :meth:`teardown_device_watchers` is what drops the whole set.
        """
        return self._watchers.setup_device_watchers(device_name)

    def teardown_device_watchers(self, device_name: str) -> None:
        """Drop the watchers wired for *device_name*."""
        self._watchers.teardown_device_watchers(device_name)

    def setup_all_mower_watchers(self) -> None:
        """Wire watchers for every currently-registered mower."""
        self._watchers.setup_all_mower_watchers()

    # ------------------------------------------------------------------
    # IoT reporting — request_iot_sys helpers (ported from HA-Luba)
    # ------------------------------------------------------------------

    async def request_iot_sync(self, device_name: str, *, stop: bool = False) -> None:
        """Send a one-shot request_iot_sys (count=1) covering the full channel list."""
        await self.send_command_with_args(
            device_name,
            "request_iot_sys",
            rpt_act=RptAct.RPT_STOP if stop else RptAct.RPT_START,
            rpt_info_type=_ONE_SHOT_CHANNELS,
            timeout=10000,
            period=3000,
            no_change_period=4000,
            count=1,
        )

    async def request_iot_sync_continuous(
        self,
        device_name: str,
        *,
        stop: bool = False,
        period: int = 1000,
        no_change_period: int = 4000,
    ) -> None:
        """Start (or stop, via ``stop=True``) a continuous (count=0) report stream."""
        await self.send_command_with_args(
            device_name,
            "request_iot_sys",
            _record_cmd=False,
            rpt_act=RptAct.RPT_STOP if stop else RptAct.RPT_START,
            rpt_info_type=_CONTINUOUS_STREAM_CHANNELS,
            timeout=10000,
            period=period,
            no_change_period=no_change_period,
            count=0,
        )

    async def request_iot_sync_continuous_stop(self, device_name: str) -> None:
        """Explicit stop of the continuous stream — use before an exclusive saga."""
        await self.send_command_with_args(
            device_name,
            "request_iot_sys",
            _record_cmd=False,
            rpt_act=RptAct.RPT_STOP,
            rpt_info_type=_CONTINUOUS_STREAM_CHANNELS,
            count=1,
        )

    async def request_report_snapshot(self, device_name: str) -> None:
        """Fire a one-shot count=1 report, skipped if the BLE stream is already active.

        Use after state-changing commands or on state-change watchers to get a fresh
        snapshot without fighting an in-progress BLE continuous feed.
        """
        if handle := self._device_registry.get_by_name(device_name):
            await handle.request_report_snapshot()

    async def request_reports(self, device_name: str, *, count: int = 1, timeout: int = 1000) -> None:
        """Fire a one-shot count=count report, skipped if the BLE stream is already active.

        ``timeout`` is the device-side ``request_iot_sys`` report window in ms — a wire
        field, not an asyncio deadline.
        """
        if handle := self._device_registry.get_by_name(device_name):
            await handle.request_reports(count=count, timeout=timeout)

    async def start_report_stream(self, device_name: str, duration_ms: int = 300_000) -> None:
        """Start a transient count=0 continuous report window lasting ``duration_ms`` ms.

        Repeated calls reset the window.  Safe to call while BLE is streaming —
        the RPT_START is skipped but the stop timer is still armed.
        """
        if handle := self._device_registry.get_by_name(device_name):
            await handle.start_report_stream(duration_ms)

    async def ensure_fresh_state(self, device_name: str, *, max_age_s: float = 120.0) -> None:
        """Fire a one-shot snapshot if the last inbound report is older than ``max_age_s`` seconds.

        Intended for use at the top of user-action handlers (start/dock/pause/cancel)
        to avoid acting on stale state after a long idle period.  Fire-and-forget:
        the response arrives asynchronously.
        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            return
        if time.monotonic() - handle.last_report_at > max_age_s:
            await handle.request_report_snapshot()

    def subscribe_device_status(
        self,
        device_name: str,
        handler: Callable[[ThingStatusMessage], Awaitable[None]],
    ) -> Subscription | None:
        """Subscribe to thing/status messages for a device. Returns RAII Subscription, or None if not found."""
        handle = self._device_registry.get_by_name(device_name)
        return handle.subscribe_device_status(handler) if handle is not None else None

    def subscribe_device_properties(
        self,
        device_name: str,
        handler: Callable[[ThingPropertiesMessage], Awaitable[None]],
    ) -> Subscription | None:
        """Subscribe to thing/properties messages for a device. Returns RAII Subscription, or None if not found."""
        handle = self._device_registry.get_by_name(device_name)
        return handle.subscribe_device_properties(handler) if handle is not None else None

    def subscribe_device_event(
        self,
        device_name: str,
        handler: Callable[[ThingEventMessage], Awaitable[None]],
    ) -> Subscription | None:
        """Subscribe to non-protobuf thing/events messages for a device. Returns RAII Subscription, or None if not found."""
        handle = self._device_registry.get_by_name(device_name)
        return handle.subscribe_device_event(handler) if handle is not None else None

    # ------------------------------------------------------------------
    # Account session helpers
    # ------------------------------------------------------------------

    def _get_session_for_handle(self, handle: DeviceHandle) -> AccountSession | None:
        """Return the AccountSession that owns *handle*, or ``None`` for an unclaimed (BLE-only) handle."""
        if handle.account_id == BLE_ONLY_ACCOUNT:
            return None
        return self._account_registry.get(handle.account_id)

    def _get_session_for_device(self, device_name: str) -> AccountSession | None:
        """Return the AccountSession that owns *device_name*, or None."""
        handle = self._device_registry.get_by_name(device_name)
        return None if handle is None else self._get_session_for_handle(handle)

    def _get_default_session(self) -> AccountSession | None:
        """Return the first registered cloud session (convenience for single-account setups)."""
        sessions = self._account_registry.all_sessions
        return sessions[0] if sessions else None

    # ------------------------------------------------------------------
    # Auth-retry helper
    # ------------------------------------------------------------------

    async def _refresh_for_transport(self, transport_type: TransportType, session: AccountSession | None) -> None:
        """Refresh credentials for a specific transport type."""
        if session is None or session.token_manager is None:
            return
        if transport_type == TransportType.CLOUD_ALIYUN:
            await session.token_manager.refresh_aliyun_credentials()
        elif transport_type == TransportType.CLOUD_MAMMOTION:
            await session.token_manager.refresh_mqtt_credentials()

    async def _quiesce_account(self, session: AccountSession, reason: str, exc: Exception) -> None:
        """Shut down all cloud activity for *session* — its HTTP login is terminally dead.

        Fired exactly once by ``TokenManager.on_reauth_required`` on the None → reason
        transition of ``reauth_required``, regardless of which refresh path found the
        rejection (scheduler, ``refresh_http``, ``refresh_invoke_token``, or a decorated
        endpoint).  After this runs, nothing for the account touches the network: both
        cloud transports are marked unrecoverable and disconnected (so every queue item,
        poll tick, and saga fails fast at ``active_transport()``), the refresh scheduler
        is stopped, and ``MammotionHTTP`` already fails fast on its own terminal flag.
        BLE is untouched — it needs no cloud credentials.
        """
        _logger.warning(
            "Account %s requires re-authentication (%s) — stopping all cloud activity for it",
            session.account_id,
            reason,
        )
        if session.token_manager is not None:
            await session.token_manager.stop_refresh_scheduler()
        for transport in (session.aliyun_transport, session.mammotion_transport):
            if transport is None:
                continue
            # Mark before disconnecting so queued connect() callbacks refuse to
            # resurrect the receive loop.
            transport.mark_unrecoverable_auth_failure()
            with contextlib.suppress(Exception):
                await transport.disconnect()
        affected = self._device_registry.for_account(session.account_id)
        # Handles keep their registry key — a re-authentication adopts them back — but
        # the dead cloud transports come off so active_transport() falls to BLE cleanly.
        await self._detach_cloud_from_account(session, rekey=False)
        for handle in affected:
            with contextlib.suppress(Exception):
                await handle.notify_critical_error(exc)
        if self.on_unrecoverable_auth_error is not None:
            primary = TransportType.CLOUD_ALIYUN if session.cloud_client is not None else TransportType.CLOUD_MAMMOTION
            with contextlib.suppress(Exception):
                await self.on_unrecoverable_auth_error(session.account_id, primary, exc)

    async def _signal_transport_unrecoverable(
        self, session: AccountSession, transport_type: TransportType, exc: Exception
    ) -> None:
        """Signal that *transport_type* has permanently failed auth for *session*.

        Fires the per-device error bus for the account's mowers that use this
        transport, so the host marks exactly those unavailable.  Deliberately does
        NOT fire the global ``on_unrecoverable_auth_error`` callback: hosts treat
        that as "prompt the user to re-authenticate", which is the wrong response
        to a transport-scoped failure — the login, the cached credentials, and the
        account's other transport must survive.  Account-wide death is signalled
        exclusively by ``_quiesce_account`` on the ``reauth_required`` transition.
        """
        affected = [
            handle
            for handle in self._device_registry.for_account(session.account_id)
            if handle.get_transport(transport_type) is not None
        ]
        _logger.warning(
            "%s permanently unavailable for account %s — %d mower(s) affected (account login unaffected)",
            transport_type.value,
            session.account_id,
            len(affected),
        )
        for handle in affected:
            with contextlib.suppress(Exception):
                await handle.notify_critical_error(exc)

    async def _send_with_auth_retry(
        self, send_fn: Callable[[], Awaitable[None]], session: AccountSession | None = None
    ) -> None:
        """Call *send_fn*; on an auth failure refresh that transport's credentials once and retry.

        There is exactly one recovery attempt and it is scoped to the transport that
        failed, so a dead Aliyun session never causes the Mammotion MQTT credentials
        (or the HTTP login) to be touched, and vice versa.

        If the refresh is itself rejected the error propagates: ``ReLoginRequiredError``
        reaches the host, which prompts the user to re-authenticate.  Nothing here
        re-logins with a stored password — that would bypass the prompt and, during a
        server-side outage, fire a password grant per queued command.
        """
        try:
            await send_fn()
        except SessionExpiredError as exc:
            _logger.debug("Session expired on %s — refreshing that transport's credentials", exc.transport_type.value)
            await self._refresh_for_transport(exc.transport_type, session)
            await send_fn()
        except NoTransportAvailableError:
            raise  # let send_command_with_args retry when transport reconnects
        except AuthError:
            # AuthError subclasses TransportError, so this clause MUST precede the
            # TransportError catch below — otherwise ReLoginRequiredError would be
            # swallowed into a log line and the host would never prompt for re-auth.
            raise
        except TransportError as ex:
            _logger.warning(ex)

    # ------------------------------------------------------------------
    # Device access
    # ------------------------------------------------------------------

    def get_device_by_name(self, name: str, account_id: str | None = None) -> MowingDevice | None:
        """Return the MowingDevice state for the named device, or None."""
        handle = self._device_registry.get_by_name(name, account_id)
        if handle is None:
            return None
        return handle.snapshot.raw  # type: ignore

    def regenerate_stale_geojson(self, device_name: str | None = None) -> None:
        """Regenerate GeoJSON for any device whose stored map was built with a different RTK yaw.

        Call this after restoring device state (e.g. after ``handle.restore_device()``
        in the HA coordinator) so that maps generated without the RTK heading correction
        are immediately fixed without waiting for the next full map sync.

        Args:
            device_name: Regenerate only this device.  When ``None`` (default),
                         checks every registered mower device.

        """
        handles = (
            [self._device_registry.get_by_name(device_name)] if device_name else list(self._device_registry.all_devices)
        )
        for handle in handles:
            if handle is None:
                continue
            device = handle.snapshot.raw
            if not isinstance(device, MowingDevice):
                continue
            if not device.map.area:
                continue
            rtk = device.location.RTK
            if device.map.geojson_needs_regeneration(rtk):
                _logger.info(
                    "regenerate_stale_geojson [%s]: regenerating (stored_yaw=%.3f current_yaw=%.3f)",
                    handle.device_name,
                    device.map.geojson_yaw,
                    rtk.yaw,
                )
                apply_area_geojson(device.map, rtk, device.location.dock)

    def mower(self, name: str, account_id: str | None = None) -> DeviceHandle | None:
        """Return the DeviceHandle for the named device, or None.

        *account_id* disambiguates a device visible to several accounts; without it the
        unique holder is returned, else the BLE owner, else the first cloud holder.
        """
        return self._device_registry.get_by_name(name, account_id)

    def rtk_device(self, name: str, account_id: str | None = None) -> DeviceHandle | None:
        """Return the DeviceHandle for the named RTK base station, or None."""
        return self._device_registry.get_by_name(name, account_id)

    def pool_cleaner_device(self, name: str, account_id: str | None = None) -> DeviceHandle | None:
        """Return the DeviceHandle for the named Spino pool cleaner, or None."""
        return self._device_registry.get_by_name(name, account_id)

    async def fetch_rtk_lora_info(self, device_name: str) -> None:
        """Fetch LoRa version info for an RTK device via HTTP and apply it to device state.

        Calls the ``/rtk/devices`` HTTP endpoint, finds the entry matching
        *device_name*, and writes the ``lora`` field into the RTK device's
        state machine so it is available on ``handle.snapshot.raw.lora_version``.

        No-op if the device is not registered, is not an RTK base station, or
        if no HTTP session is available.
        """

        if not DeviceType.is_rtk(device_name):
            return
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            return
        session = self._get_session_for_device(device_name) or self._get_default_session()
        if session is None or session.mammotion_http is None:
            return

        try:
            response = await session.mammotion_http.get_rtk_devices()
            if not response.data:
                return
            for rtk in response.data:
                if rtk.device_name == device_name:
                    current = handle.snapshot.raw
                    if isinstance(current, RTKBaseStationDevice):
                        updated = dataclasses.replace(current, lora_version=rtk.lora)
                        snapshot, _ = handle.state_machine.apply(updated, handle.availability)
                        await handle.emit_state_changed(snapshot)
                    break
        except Exception:  # noqa: BLE001
            _logger.warning("fetch_rtk_lora_info: failed to fetch RTK devices for %s", device_name, exc_info=True)

    async def fetch_rtk_properties(self, device_name: str) -> None:
        """Fetch RTK device properties from the Aliyun gateway and apply them to device state.

        Retrieves networkInfo, coordinate, deviceVersion, and OTA progress for
        the named RTK base station and writes them into the device state machine.

        No-op if the device is not registered, not an RTK base station, not an
        Aliyun device, or if no cloud gateway session is available.
        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            return
        current = handle.snapshot.raw
        if not isinstance(current, RTKBaseStationDevice):
            return
        if not current.iot_id or not DeviceType.is_aliyun_product_key(current.product_key):
            return
        gateway = self.cloud_gateway
        if gateway is None:
            return

        try:
            response = await gateway.get_device_properties(current.iot_id)
            if response.code != 200:
                return
            data = response.data
            updated = current
            if ota_progress := data.otaProgress:  # type: ignore
                updated = dataclasses.replace(updated, update_check=CheckDeviceVersion.from_dict(ota_progress.value))  # type: ignore
            if network_info := data.networkInfo:  # type: ignore
                network = json.loads(network_info.value)  # type: ignore
                updated = dataclasses.replace(
                    updated,
                    wifi_rssi=network["wifi_rssi"],
                    wifi_mac=network["wifi_sta_mac"],
                    bt_mac=network["bt_mac"],
                )
            if coordinate := data.coordinate:  # type: ignore
                coord_val = json.loads(coordinate.value)  # type: ignore
                _logger.debug("Raw RTK coordinate payload: %s", coord_val)
                if coord_val["lat"] != 0:
                    updated = dataclasses.replace(updated, lat=coord_val["lat"])
                if coord_val["lon"] != 0:
                    updated = dataclasses.replace(updated, lon=coord_val["lon"])
            if device_version := data.deviceVersion:  # type: ignore
                updated = dataclasses.replace(updated, device_version=device_version.value)
            if updated is not current:
                snapshot, _ = handle.state_machine.apply(updated, handle.availability)
                await handle.emit_state_changed(snapshot)
        except Exception:  # noqa: BLE001
            _logger.warning("fetch_rtk_properties: failed for %s", device_name, exc_info=True)

    async def apply_device_properties(self, device_name: str, properties: ThingPropertiesMessage) -> None:
        """Apply a thing/properties message to the named device's state machine.

        Routes *properties* through :meth:`DeviceHandle.on_device_properties`,
        which runs the reducer's ``apply_properties`` (OTA progress, networkInfo,
        coordinate, etc.) and emits a state-changed event so all subscribers
        (including HA coordinators) see the update.

        No-op if the device is not registered.
        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            return
        await handle.on_device_properties(properties)

    # ------------------------------------------------------------------
    # BLE
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # BLE inventory — delegates to pymammotion/device/ble_inventory.py
    # ------------------------------------------------------------------

    async def add_ble_device(self, device_id: str, ble_device: BLEDevice, rssi: int | None = None) -> None:
        """Record an externally-discovered BLE device and attach it to its handle (hybrid mode)."""
        await self._ble.add_ble_device(device_id, ble_device, rssi)

    async def update_ble_device(self, device_id: str, ble_device: BLEDevice, rssi: int | None = None) -> bool:
        """Update the BLE advertisement for a known device."""
        return await self._ble.update_ble_device(device_id, ble_device, rssi)

    async def clear_ble_device(self, device_id: str) -> None:
        """Forget the cached BLEDevice on the device's BLETransport."""
        await self._ble.clear_ble_device(device_id)

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
        """Register a device over BLE — no HTTP login or MQTT involved."""
        return await self._ble.add_ble_only_device(
            device_id,
            device_name,
            initial_device,
            ble_device=ble_device,
            ble_address=ble_address,
            self_managed_scanning=self_managed_scanning,
        )

    async def move_ble_to_account(self, device_id: str, account_id: str) -> None:
        """Hand a device's BLE transport to *account_id*'s handle for that device."""
        await self._ble.move_ble_to_account(device_id, account_id)

    async def connect_ble(self, device_name: str, account_id: str | None = None) -> None:
        """Connect the BLE transport for a registered device."""
        await self._ble.connect_ble(device_name, account_id)

    async def add_ble_to_device(self, device_name: str, ble_device: BLEDevice, account_id: str | None = None) -> None:
        """Attach a BLE transport to an already-registered device, or refresh the one it has."""
        await self._ble.add_ble_to_device(device_name, ble_device, account_id)

    def _wire_transport_callbacks(self, transport: Any, account_id: str) -> None:
        """Attach the six :class:`InboundRouter` route callbacks to *transport*, bound to its account.

        Sets all six unconditionally; transports that don't fire a given
        callback simply never read its attribute, so the extra assignment is
        harmless and keeps Aliyun / Mammotion wiring from drifting apart.
        """
        transport.on_device_message = partial(self._inbound.route_message, account_id)
        transport.on_device_status = partial(self._inbound.route_status, account_id)
        transport.on_device_properties = partial(self._inbound.route_properties, account_id)
        transport.on_device_event = partial(self._inbound.route_event, account_id)
        transport.on_device_mammotion_properties = partial(self._inbound.route_mammotion_properties, account_id)
        transport.on_device_notification = partial(self._inbound.route_notification, account_id)

    async def _register_device_on_transport(
        self,
        *,
        device_name: str,
        iot_id: str,
        product_key: str,
        transport: Transport,
        user_account: int,
        acct_session: AccountSession,
    ) -> None:
        """Register (or adopt) the DeviceHandle for a cloud device on *acct_session*.

        Shared by Aliyun and Mammotion device registration; the topic-subscription
        step that's Mammotion-specific stays in ``_register_mammotion_device``.
        """
        await self._ensure_device_handle(
            acct_session=acct_session,
            device_id=device_name,
            device_name=device_name,
            initial_device=create_device(device_name, product_key),
            cloud=_CloudBinding(transport, iot_id, product_key, user_account, acct_session.token_manager),
        )

    async def _ensure_device_handle(
        self,
        *,
        acct_session: AccountSession | None,
        device_id: str,
        device_name: str,
        initial_device: DeviceModel,
        cloud: _CloudBinding | None = None,
        ble: BLETransport | None = None,
        prefer_ble: bool | None = None,
    ) -> DeviceHandle:
        """Return the one DeviceHandle for *device_id* on *acct_session*, creating or adopting it.

        The single registration path for every transport.  Lookup order: the account's
        own handle; for a cloud account, the unclaimed (``BLE_ONLY_ACCOUNT``) handle for
        the device, which is re-keyed onto the account — same object, BLE transport,
        state and ``prefer_ble`` intact; otherwise a new handle.  A cloud binding then
        attaches the transport (identical shared objects are not re-wired), fills in
        ``iot_id`` / ``user_account`` / readiness, records the device on the session,
        and subscribes the token manager once.  A handle created for a cloud transport
        also picks up a BLE advertisement cached before login.  The handle is started.
        """
        account_id = BLE_ONLY_ACCOUNT if acct_session is None else acct_session.account_id
        registry = self._device_registry
        handle = registry.get(account_id, device_id)
        if handle is None and cloud is not None and (orphan := registry.get(BLE_ONLY_ACCOUNT, device_id)) is not None:
            await registry.rekey(orphan, account_id)
            handle = orphan
            _logger.info("Device %s: BLE-only handle adopted by account %s", device_name, account_id)
        if handle is None and (by_name := registry.get_by_name(device_name, account_id)) is None and cloud is not None:
            by_name = registry.get_by_name(device_name, BLE_ONLY_ACCOUNT)
        if handle is None and by_name is not None:
            _logger.warning(
                "Device %s is registered under device_id %r, not %r — using the existing handle",
                device_name,
                by_name.device_id,
                device_id,
            )
            if by_name.account_id != account_id:
                await registry.rekey(by_name, account_id)
            handle = by_name
        created = handle is None
        if handle is None:
            handle = DeviceHandle(
                device_id=device_id,
                device_name=device_name,
                initial_device=initial_device,
                iot_id=cloud.iot_id if cloud is not None else "",
                user_account=cloud.user_account if cloud is not None else 0,
                mqtt_transport=cloud.transport if cloud is not None else None,
                ble_transport=ble,
                prefer_ble=(ble is not None) if prefer_ble is None else prefer_ble,
                readiness_checker=get_readiness_checker(device_name, cloud.product_key) if cloud is not None else None,
                account_id=account_id,
                product_key=cloud.product_key if cloud is not None else "",
            )
            await registry.register(handle)
        elif ble is not None and not handle.has_transport(TransportType.BLE):
            await handle.add_transport(ble)

        if cloud is not None:
            if handle.iot_id != cloud.iot_id:
                self._inbound.unbind(account_id, handle.iot_id)
                handle.iot_id = cloud.iot_id
            if not handle.user_account:
                handle.user_account = cloud.user_account
            if not handle.product_key:
                handle.product_key = cloud.product_key
            if handle.readiness_checker is None:
                handle.readiness_checker = get_readiness_checker(device_name, cloud.product_key)
            handle.on_device_unbound = self._on_device_unbound
            if not created:
                await handle.add_transport(cloud.transport)
            # handle.device_id, not device_id: the by-name adoption branch above keeps an
            # existing handle registered under a different id, and the router resolves
            # through the registry — binding the argument would drop every inbound frame.
            self._inbound.bind(account_id, cloud.iot_id, (account_id, handle.device_id))
            if acct_session is not None:
                acct_session.device_ids.add(device_name)
            if cloud.token_manager is not None:
                cloud.token_manager.subscribe_handle(handle)
            if created:
                await self._ble.attach_cached_ble(handle, device_id)

        if not handle.is_started:
            await handle.start()
        return handle

    async def _detach_cloud_from_account(self, session: AccountSession, *, rekey: bool) -> None:
        """Take *session*'s cloud transports off its handles without disconnecting them.

        The shared transport objects are the session's to disconnect.  With *rekey*
        a handle that owns BLE is returned to ``BLE_ONLY_ACCOUNT`` and keeps running,
        a cloud-only handle is stopped and removed, and ``device_ids`` is cleared;
        without it the handles keep their key so a re-authentication adopts them back.
        """
        for handle in self._device_registry.for_account(session.account_id):
            for transport_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
                handle.detach_transport(transport_type)
            self._inbound.unbind(session.account_id, handle.iot_id)
            if not rekey:
                continue
            if handle.has_transport(TransportType.BLE):
                await self._device_registry.rekey(handle, BLE_ONLY_ACCOUNT)
            else:
                await self._device_registry.unregister(handle.account_id, handle.device_id)
        if rekey:
            session.device_ids.clear()

    async def _release_to_ble_only(self, handle: DeviceHandle, session: AccountSession | None) -> None:
        """Leave *handle* running on BLE alone after its cloud binding is gone for good."""
        for transport_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
            handle.detach_transport(transport_type)
        if session is not None:
            self._inbound.unbind(session.account_id, handle.iot_id)
            session.device_ids.discard(handle.device_name)
        await self._device_registry.rekey(handle, BLE_ONLY_ACCOUNT)

    def _setup_aliyun_transport(
        self, cloud_client: CloudIOTGateway, acct_session: AccountSession
    ) -> AliyunMQTTTransport:
        """Build an AliyunMQTTTransport from a ready CloudIOTGateway."""
        aep = cloud_client.aep_response.data  # type: ignore
        region_id = cloud_client.region_response.data.regionId  # type: ignore
        session_data = cloud_client.session_by_authcode_response.data  # type: ignore
        config = AliyunMQTTConfig(
            host=f"{aep.productKey}.iot-as-mqtt.{region_id}.aliyuncs.com",
            client_id_base=cloud_client.client_id,
            username=f"{aep.deviceName}&{aep.productKey}",
            device_name=aep.deviceName,
            product_key=aep.productKey,
            device_secret=aep.deviceSecret,
            iot_token=session_data.iotToken,  # type: ignore
        )
        transport = AliyunMQTTTransport(config, cloud_client)
        self._wire_transport_callbacks(transport, acct_session.account_id)

        token_manager = acct_session.token_manager

        async def _on_aliyun_auth_failure() -> bool:
            """Handle a 2043/460 bind rejection by refreshing the Aliyun session once.

            ``refresh_aliyun_credentials`` covers both recoverable cases: an expired
            iotToken, and a 2401 rejection of the IoT refreshToken (which it rebuilds
            from the existing HTTP login's authCode chain — no password involved).

            If that fails, the Aliyun session is unrenewable.  We do NOT escalate to
            an email/password re-login: it hammers Aliyun while the account is very
            likely already blocked, and it would tear down a perfectly good HTTP
            login and Mammotion MQTT transport to fix a problem confined to Aliyun.
            Returning False gives up on this transport alone.
            """
            if token_manager is None:
                return False
            _logger.warning("Aliyun bind rejected — attempting targeted credential refresh")
            try:
                await token_manager.refresh_aliyun_credentials()
                creds = await token_manager.get_aliyun_credentials()
            except Exception:
                _logger.exception("Aliyun credential refresh failed — giving up on the Aliyun transport")
                return False
            transport.update_iot_token(creds.iot_token)
            _logger.info("Aliyun IoT token refreshed via targeted credential refresh")
            return True

        transport.on_auth_failure = _on_aliyun_auth_failure

        async def _on_aliyun_fatal_auth(exc: Exception) -> None:
            """Give up on the Aliyun transport; leave the rest of the account alone.

            The refresh above already exhausted every recovery that does not require
            the user.  Retrying on a timer cannot help — a rejected IoT refreshToken
            does not become valid by waiting — which is why the previous
            re-login-and-circuit-break cycle is gone.

            Scope matters here: only this transport's mowers are signalled.  The HTTP
            session, its cached credentials, and any Mammotion MQTT transport on the
            same account stay up.
            """
            _logger.error("Aliyun transport auth unrecoverable for account %s: %s", acct_session.account_id, exc)
            transport.mark_unrecoverable_auth_failure()
            await self._signal_transport_unrecoverable(acct_session, TransportType.CLOUD_ALIYUN, exc)

        transport.on_fatal_auth_error = _on_aliyun_fatal_auth

        # Keep the transport's bind token current on every proactive refresh so that
        # reconnects after a network blip don't carry a stale iotToken.
        if token_manager is not None:
            token_manager.on_aliyun_token_refreshed = transport.update_iot_token
        return transport

    def _setup_mammotion_transport(
        self,
        mqtt_creds: MQTTConnection | MQTTCredentials,
        mammotion_http: MammotionHTTP,
        acct_session: AccountSession,
        token_manager: TokenManager,
    ) -> MQTTTransport:
        """Build a MQTTTransport from a set of Mammotion MQTT broker credentials."""
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

        # Build a creds_refresher that uses the TokenManager to get a fresh
        # credential set (host/client_id/username/jwt — not just the JWT, since a
        # re-login can rotate client_id/username the broker binds the JWT to).
        #   force=False → routine pre-connect check (refresh only if near expiry).
        #   force=True  → full refresh after a broker auth rejection, refresh-token
        #                 based and STRICTLY no login_v2 (Mammotion never re-logins).
        # Both hold the TokenManager lock so concurrent refresh paths serialize.

        async def _refresh_creds(force: bool) -> MQTTCredentials:
            if force:
                return await token_manager.refresh_mqtt_credentials()
            return await token_manager.get_mammotion_mqtt_credentials()

        # Invariant: the transport and its TokenManager MUST share one MammotionHTTP.
        # If they diverge, a 401-driven token refresh updates a different login
        # session than mqtt_invoke reads, producing a permanent 401 loop that ends in
        # "Mammotion MQTT auth unrecoverable".  Warn loudly rather than fail silently.
        if token_manager.http is not mammotion_http:
            _logger.error(
                "Mammotion transport for %s wired with a MammotionHTTP that differs from its "
                "TokenManager's — token refreshes will not reach mqtt_invoke; expect a 401 loop",
                acct_session.account_id,
            )

        transport = MQTTTransport(config, mammotion_http, token_manager, creds_refresher=_refresh_creds)
        self._wire_transport_callbacks(transport, acct_session.account_id)

        # Mammotion MQTT never re-logins.  The transport already refreshed
        # credentials in full and retried; if the broker still rejects, we give up:
        # mark this account's Mammotion transport unrecoverable (which gates exactly
        # the account's mowers-on-this-transport via active_transport()/is_usable)
        # and signal them so the host can prompt re-auth.  Recovery is a fresh
        # login by the user (HA reconfigure), not an automatic retry.
        async def _on_fatal_auth(exc: Exception) -> None:
            _logger.error(
                "Mammotion MQTT auth unrecoverable for account %s — giving up on %s for its mowers: %s",
                acct_session.account_id,
                TransportType.CLOUD_MAMMOTION.value,
                exc,
            )
            transport.mark_unrecoverable_auth_failure()
            await self._signal_transport_unrecoverable(acct_session, TransportType.CLOUD_MAMMOTION, exc)

        transport.on_fatal_auth_error = _on_fatal_auth
        return transport

    async def _register_aliyun_device(
        self,
        device_name: str,
        iot_id: str,
        transport: AliyunMQTTTransport,
        user_account: int = 0,
        product_key: str = "",
        *,
        acct_session: AccountSession,
    ) -> None:
        """Register a single Aliyun device in the device registry."""
        await self._register_device_on_transport(
            device_name=device_name,
            iot_id=iot_id,
            product_key=product_key,
            transport=transport,
            user_account=user_account,
            acct_session=acct_session,
        )
        _logger.info("Aliyun device registered: %s (iot_id=%s)", device_name, iot_id)

    async def _register_mammotion_device(
        self,
        record: DeviceRecord,
        transport: MQTTTransport,
        user_account: int = 0,
        iot_id_override: str = "",
        *,
        acct_session: AccountSession,
    ) -> None:
        """Add MQTT topics and register a single Mammotion device in the device registry.

        Args:
            record:          DeviceRecord from the Mammotion device page API.
            transport:       Mammotion MQTT transport to register the device on.
            user_account:    Numeric user-account identifier (0 if unknown).
            iot_id_override: When non-empty, replace ``record.iot_id`` with this
                             value.  Use this to supply the authoritative iot_id
                             from ``get_user_device_list()`` when the device-page
                             record carries a stale or incorrect value.

        """
        iot_id = iot_id_override or record.iot_id
        await self._subscribe_mammotion_topics(transport, record.product_key, record.device_name, iot_id)

        await self._register_device_on_transport(
            device_name=record.device_name,
            iot_id=iot_id,
            product_key=record.product_key,
            transport=transport,
            user_account=user_account,
            acct_session=acct_session,
        )
        _logger.info("Mammotion device registered: %s (iot_id=%s)", record.device_name, iot_id)

    @staticmethod
    async def _subscribe_mammotion_topics(
        transport: MQTTTransport, product_key: str, device_name: str, iot_id: str
    ) -> None:
        """Subscribe the per-device Mammotion MQTT topics and map the iot_id for routing.

        Shared by first-time registration (``_register_mammotion_device``) and the
        runtime Aliyun→Mammotion migration (``_on_device_unbound``).
        """
        for topic in (
            f"/sys/{product_key}/{device_name}/thing/event/+/post",
            f"/sys/proto/{product_key}/{device_name}/thing/event/+/post",
            f"/sys/{product_key}/{device_name}/app/down/thing/status",
            # f"/sys/{product_key}/{device_name}/app/down/thing/properties",
        ):
            await transport.add_topic(topic)
        transport.register_device(product_key, device_name, iot_id)

    async def _ensure_mammotion_transport(
        self, account: str, mammotion_http: MammotionHTTP, acct_session: AccountSession
    ) -> MQTTTransport | None:
        """Return the account's Mammotion MQTT transport, creating+connecting one if absent.

        Reuses ``acct_session.mammotion_transport`` when present; otherwise fetches MQTT
        credentials, ensures a TokenManager, builds the transport via
        ``_setup_mammotion_transport`` and connects it.

        Returns ``None`` when the Mammotion MQTT JWT is unrenewable while the HTTP
        login is still healthy — a *transport-scoped* failure.  Callers skip the
        post-2025 devices and carry on, so the account still gets registered, still
        starts its refresh scheduler, and keeps any Aliyun transport it has.  An
        *account-scoped* failure (the HTTP refresh token itself was rejected)
        propagates instead: no cloud path for the account can work.
        """
        if acct_session.mammotion_transport is not None:
            return acct_session.mammotion_transport
        # Fetch via the TokenManager, not raw HTTP: its getter fails fast on the
        # reauth_required / mqtt_unavailable terminal flags and shares the refresh lock.
        token_manager = await self._ensure_token_manager(acct_session, mammotion_http)
        try:
            mqtt_creds = await token_manager.get_mammotion_mqtt_credentials()
        except ReLoginRequiredError:
            # The getter signals both failure scopes with this one type, so the flags
            # are what separate them.  ``_mark_mqtt_unavailable`` deliberately leaves
            # ``reauth_required`` alone precisely so this transport can be given up on
            # its own; letting its error escape here would tear down a healthy login.
            if token_manager.reauth_required is not None:
                raise
            _logger.error(
                "Mammotion MQTT unavailable for account %s (%s) — continuing without that transport",
                account,
                token_manager.mqtt_unavailable,
            )
            return None
        transport = self._setup_mammotion_transport(mqtt_creds, mammotion_http, acct_session, token_manager)
        await transport.connect()
        acct_session.mammotion_transport = transport
        return transport

    async def _on_device_unbound(self, handle: DeviceHandle) -> None:
        """Re-discover an unbound device (Aliyun 29004) and migrate it, or remove it.

        Fired by ``DeviceHandle._on_device_unbound`` after the Aliyun transport has
        been detached (non-disconnecting) from the device.  Re-fetches the Mammotion
        device list: if the device now lives on Mammotion MQTT, attach that transport
        to the SAME handle (keeping its state/history); if it is gone from the account
        entirely, remove it.
        """
        device_name = handle.device_name
        session = self._get_session_for_handle(handle)
        try:
            # The Aliyun→Mammotion cloud migration after a firmware update is NOT
            # instantaneous: the 29004 unbind lands before the device is listed on
            # the Mammotion side.  A one-shot check here removed devices mid-flight
            # (issue #819) or left them permanently transport-less (#808), so retry
            # over several minutes before concluding the device is really gone.
            for attempt, delay in enumerate(_UNBOUND_MIGRATION_DELAYS, start=1):
                if attempt > 1:
                    await asyncio.sleep(delay)
                last_attempt = attempt == len(_UNBOUND_MIGRATION_DELAYS)
                try:
                    if await self._try_migrate_unbound(handle, session, final_attempt=last_attempt):
                        return
                except Exception:
                    _logger.exception(
                        "Device '%s' unbound: migration attempt %d/%d failed",
                        device_name,
                        attempt,
                        len(_UNBOUND_MIGRATION_DELAYS),
                    )
        finally:
            handle.reset_unbound_migration()

    async def _try_migrate_unbound(
        self, handle: DeviceHandle, session: AccountSession | None, *, final_attempt: bool
    ) -> bool:
        """Run one Aliyun→Mammotion migration attempt.

        Returns True when settled (migrated, removed, or deliberately left BLE-only)
        — False means "retry later".

        Removal only happens on the *final* attempt, and never while the handle still
        has a usable BLE transport (a BLE-only device keeps working without any cloud).
        """
        device_name = handle.device_name

        def _keep_or_remove(reason: str) -> bool:
            if not final_attempt:
                _logger.debug("Device '%s' unbound: %s — will retry", device_name, reason)
                return False
            if handle.get_transport(TransportType.BLE) is not None:
                _logger.warning("Device '%s' unbound: %s — keeping as BLE-only", device_name, reason)
                return True
            return False  # caller removes below

        if session is None or session.mammotion_http is None:
            settled = _keep_or_remove("no Mammotion session to re-discover")
            if settled:
                await self._release_to_ble_only(handle, session)
            if settled or not final_attempt:
                return settled
            _logger.warning("Device '%s' unbound but no Mammotion session to re-discover — removing", device_name)
            await self._remove_unbound_device(handle, session)
            return True

        mammotion_http = session.mammotion_http
        device_list_resp = await mammotion_http.get_user_device_list()
        owned_iot_id_map = {
            d.device_name: d.iot_id for d in (device_list_resp.data or []) if d.device_name and d.iot_id
        }
        page_resp = await mammotion_http.get_user_device_page()
        records = (page_resp.data.records if page_resp.data else []) or []
        record = next((r for r in records if r.device_name == device_name), None)
        if record is None:
            settled = _keep_or_remove("not on Mammotion MQTT yet")
            if settled:
                await self._release_to_ble_only(handle, session)
            if settled or not final_attempt:
                return settled
            _logger.warning("Device '%s' unbound and not on Mammotion MQTT either — removing", device_name)
            await self._remove_unbound_device(handle, session)
            return True

        transport = await self._ensure_mammotion_transport(session.account_id, mammotion_http, session)
        if transport is None:
            _logger.error("Device '%s' unbound: could not set up Mammotion transport — will retry", device_name)
            return False

        iot_id = owned_iot_id_map.get(device_name) or record.iot_id
        await self._subscribe_mammotion_topics(transport, record.product_key, device_name, iot_id)
        await self._ensure_device_handle(
            acct_session=session,
            device_id=handle.device_id,
            device_name=device_name,
            initial_device=create_device(device_name, record.product_key),
            cloud=_CloudBinding(transport, iot_id, record.product_key, session.user_account, session.token_manager),
        )
        _logger.info("Device '%s' migrated from Aliyun to Mammotion MQTT (iot_id=%s)", device_name, iot_id)
        return True

    async def _remove_unbound_device(self, handle: DeviceHandle, session: AccountSession | None) -> None:
        """Fully remove a device that is unbound from all clouds.

        Safe because the Aliyun transport was already detached (non-disconnecting)
        before this runs, so stopping the handle only disconnects the device's own
        remaining transports (e.g. BLE), never the account-shared Aliyun connection.
        Fires ``on_device_removed`` so the host can delete the device from its registry.
        """
        device_name = handle.device_name
        iot_id = handle.iot_id
        if session is not None:
            session.device_ids.discard(device_name)
        await self.remove_device(device_name, account_id=handle.account_id)
        _logger.warning("Device '%s' unbound from all clouds — removed", device_name)
        if self.on_device_removed is not None:
            with contextlib.suppress(Exception):
                await self.on_device_removed(device_name, iot_id)

    async def _restore_aliyun(
        self,
        account: str,
        cached_data: dict[str, Any],
        acct_session: AccountSession,
        *,
        check_for_new_devices: bool,
    ) -> None:
        """Restore an Aliyun cloud session and register all known devices.

        The account's login session and TokenManager are already established by
        ``restore_credentials``; this adds the Aliyun gateway and transport to them.
        An Aliyun session that cannot be restored is rebuilt from that login, and a
        rebuild that fails costs this transport only.
        """
        mammotion_http = acct_session.mammotion_http
        if mammotion_http is None:
            _logger.error("_restore_aliyun: no login session for %s — skipping the Aliyun transport", account)
            return

        cloud_client = await CloudIOTGateway.from_cache(cached_data, mammotion_http)
        if cloud_client is None:
            # The cached Aliyun data is unusable, but an Aliyun session is minted from
            # the HTTP login and nothing else — and that login has just been validated.
            # Rebuild the gateway from it via the authCode chain rather than throwing
            # away a healthy login to re-derive the same thing from a password.
            _logger.warning(
                "restore_credentials: cached Aliyun session for %s is unusable — rebuilding it from the HTTP login",
                account,
            )
            cloud_client = CloudIOTGateway(mammotion_http)
            try:
                await self._connect_iot(cloud_client)
            except Exception:  # noqa: BLE001
                _logger.warning(
                    "restore_credentials: could not rebuild the Aliyun session for %s — "
                    "skipping the Aliyun transport this cycle (the HTTP login is unaffected)",
                    account,
                    exc_info=True,
                )
                return
            if (
                cloud_client.aep_response is None
                or cloud_client.region_response is None
                or cloud_client.session_by_authcode_response is None
                or cloud_client.session_by_authcode_response.data is None
            ):
                _logger.warning(
                    "restore_credentials: rebuilt Aliyun session for %s is incomplete — skipping its transport", account
                )
                return

        acct_session.cloud_client = cloud_client
        token_manager = await self._ensure_token_manager(acct_session, mammotion_http)
        token_manager.attach_cloud_gateway(cloud_client)
        transport = self._setup_aliyun_transport(cloud_client, acct_session)
        acct_session.aliyun_transport = transport

        # Fetch the authoritative iot_id map from Mammotion's device-list API so that
        # stale Aliyun binding iot_ids (e.g. for RTK base stations) are corrected.
        owned_iot_id_map: dict[str, str] = {}
        try:
            owned_resp = await cloud_client.mammotion_http.get_user_device_list()
            owned_iot_id_map = {d.device_name: d.iot_id for d in (owned_resp.data or []) if d.device_name and d.iot_id}
        except _AUTH_REJECTED:
            raise
        except Exception:  # noqa: BLE001
            _logger.warning("restore_credentials: failed to fetch device iot_id map (Aliyun restore)", exc_info=True)

        known_ids: set[str] = set()
        ua = acct_session.user_account
        if cloud_client.devices_by_account_response is not None and cloud_client.devices_by_account_response.data:
            for device in cloud_client.devices_by_account_response.data.data:
                if device.device_name:
                    iot_id = owned_iot_id_map.get(device.device_name) or device.iot_id
                    await self._register_aliyun_device(
                        device.device_name, iot_id, transport, ua, device.product_key, acct_session=acct_session
                    )
                    known_ids.add(device.device_name)

        discovery_failed = False
        if check_for_new_devices:
            try:
                # Force-refresh the restored Aliyun session before the device-list call.
                # On a cold restore the cached iotToken cannot be trusted: HA may have been
                # offline for hours, and Aliyun's single-session-per-identity model means the
                # phone app (or another client) logging in rotates/invalidates our token well
                # before its nominal 20 h expiry.  The freshness-gated check would see the
                # token as still valid and skip the refresh, so list_binding_by_account would
                # send the stale token and get a 401 "request auth error".  force=True always
                # mints a fresh token via the (longer-lived) refreshToken.
                await cloud_client.check_or_refresh_session(force=True)
                session_data = (
                    cloud_client.session_by_authcode_response.data
                    if cloud_client.session_by_authcode_response is not None
                    else None
                )
                if session_data is None or not session_data.iotToken:
                    _logger.warning(
                        "restore_credentials: skipping list_binding_by_account — iotToken not available"
                        " (credentials not fully restored)"
                    )
                else:
                    fresh = await cloud_client.list_binding_by_account()
                    if fresh.data:
                        for device in fresh.data.data:
                            if device.device_name and device.device_name not in known_ids:
                                iot_id = owned_iot_id_map.get(device.device_name) or device.iot_id
                                await self._register_aliyun_device(
                                    device.device_name,
                                    iot_id,
                                    transport,
                                    ua,
                                    device.product_key,
                                    acct_session=acct_session,
                                )
                                known_ids.add(device.device_name)
            except Exception:  # noqa: BLE001
                discovery_failed = True
                _logger.warning(
                    "restore_credentials: new-device discovery failed for account %s (Aliyun)",
                    account,
                    exc_info=True,
                )

        if not known_ids:
            if discovery_failed:
                # The device-list call errored (e.g. 401 iotToken rejected) — we
                # could NOT confirm the device list, so "no devices" is unproven.
                # Skip the MQTT connection this cycle; the next refresh retries.
                _logger.warning(
                    "Aliyun device discovery failed for account %s — device list unconfirmed; "
                    "skipping Aliyun MQTT connection this cycle (will retry next refresh)",
                    account,
                )
            else:
                _logger.info("No Aliyun devices found for account %s — skipping Aliyun MQTT connection", account)
            acct_session.aliyun_transport = None
            return

        await transport.connect()

    async def _restore_mammotion_mqtt(self, account: str, acct_session: AccountSession) -> None:
        """Restore a Mammotion MQTT session and register all known devices.

        Reads the login session, MQTT credentials and device records off the account's
        :class:`MammotionHTTP` — ``restore_credentials`` has already hydrated it from
        the same cache and validated it, so there is nothing to decode here and no
        second login session to keep in step.
        """
        mammotion_http = acct_session.mammotion_http
        if mammotion_http is None:
            _logger.error(
                "_restore_mammotion_mqtt: no login session for %s — skipping the Mammotion transport", account
            )
            return

        cached_records = mammotion_http.device_records

        if mqtt_creds := mammotion_http.mqtt_credentials:
            token_manager = await self._ensure_token_manager(acct_session, mammotion_http)
            transport = self._setup_mammotion_transport(mqtt_creds, mammotion_http, acct_session, token_manager)
            await transport.connect()
            acct_session.mammotion_transport = transport

            # Fetch the authoritative iot_id map so stale cached iot_ids are corrected.
            owned_iot_id_map: dict[str, str] = {}
            try:
                owned_resp = await mammotion_http.get_user_device_list()
                owned_iot_id_map = {
                    d.device_name: d.iot_id for d in (owned_resp.data or []) if d.device_name and d.iot_id
                }
            except _AUTH_REJECTED:
                raise
            except Exception:  # noqa: BLE001
                _logger.warning(
                    "restore_credentials: failed to fetch device iot_id map (Mammotion restore)", exc_info=True
                )

            ua = acct_session.user_account
            for record in cached_records.records:
                if record.device_name:
                    iot_id_override = owned_iot_id_map.get(record.device_name, "")
                    await self._register_mammotion_device(
                        record, transport, ua, iot_id_override, acct_session=acct_session
                    )

    async def _bootstrap_mammotion_mqtt(
        self,
        account: str,
        mammotion_http: MammotionHTTP,
        acct_session: AccountSession,
        owned_iot_id_map: dict[str, str],
        *,
        skip_ids: set[str] | None = None,
    ) -> None:
        """Accept pending share invitations then register all post-2025 Mammotion MQTT devices.

        Handles two scenarios transparently:

        * **No transport yet** — fetches fresh MQTT credentials, calls
          :meth:`_setup_mammotion_transport`, registers every device returned by
          the device-page API, then connects.  This is the path taken by
          ``login_and_initiate_cloud`` and by ``restore_credentials`` when a
          post-2025 device appears for the first time on an account that previously
          had only Aliyun devices.

        * **Transport already connected** — reuses the existing transport to
          register any device returned by the device-page API that is not in
          *skip_ids*.  ``restore_credentials`` passes the IDs already registered
          from cache so that only genuinely new devices are added.

        Args:
            account:          Mammotion account e-mail or phone number.
            mammotion_http:   Active :class:`MammotionHTTP` session.
            acct_session:     Account session to update with the new transport and IDs.
            owned_iot_id_map: ``device_name → iot_id`` map from ``get_user_device_list()``.
            skip_ids:         Device names already registered; new devices not in this set
                              are registered.  ``None`` means register all returned devices.

        """
        # Accept any pending Mammotion-side share invitations before fetching the list.
        shared_resp = await mammotion_http.get_user_shared_device_page()
        if shared_resp.data and shared_resp.data.records:
            pending_by_batch: dict[str, list[int]] = {}
            for record in shared_resp.data.records:
                if record.is_receiver == 1 and record.status == -1:
                    pending_by_batch.setdefault(record.batch_id, []).append(int(record.record_id))
            for batch_id, record_ids in pending_by_batch.items():
                await mammotion_http.confirm_share(batch_id, record_ids)

        page_resp = await mammotion_http.get_user_device_page()
        mammotion_records = (page_resp.data.records if page_resp.data else []) or []
        if not mammotion_records:
            return

        transport = await self._ensure_mammotion_transport(account, mammotion_http, acct_session)
        if transport is None:
            _logger.error("_bootstrap_mammotion_mqtt: no MQTT transport — skipping post-2025 devices")
            return

        ua = acct_session.user_account
        already_known = skip_ids or set()
        for record in mammotion_records:
            if record.device_name and record.device_name not in already_known:
                iot_id_override = owned_iot_id_map.get(record.device_name, "")
                await self._register_mammotion_device(record, transport, ua, iot_id_override, acct_session=acct_session)

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

    # ------------------------------------------------------------------
    # Map sync
    # ------------------------------------------------------------------

    async def start_map_sync(self, device_name: str, *, skip_area_names: bool = False) -> None:
        """Enqueue a MapFetchSaga to fetch the complete device map.

        The saga is enqueued on the device's command queue and runs exclusively
        (no other commands execute while the map fetch is in progress).
        Map data is automatically applied to device state as messages arrive.

        *skip_area_names* suppresses step 1 (``get_area_name_list``); pass
        ``True`` for incremental mowing-time updates where area names are
        stable and the device may not respond to the query while busy.
        """

        if handle := self._device_registry.get_by_name(device_name):
            _logger.debug(
                "start_map_sync [%s]: enqueuing MapFetchSaga (skip_area_names=%s)", device_name, skip_area_names
            )
            commands = handle.commands
            saga = MapFetchSaga(
                device_id=handle.device_id,
                device_name=handle.device_name,
                is_luba1=DeviceType.is_luba1(device_name),
                command_builder=commands,
                send_command=handle.send_raw,
                get_map=lambda: cast(MowerDevice, handle.snapshot.raw).map,
                # None — not 0 — when no report frame has arrived yet: 0 is a real
                # bol_hash meaning "no areas", so returning it here would make the
                # saga wipe a good cached manifest on every pre-report sync.
                get_bol_hash=lambda: (
                    locs[0].bol_hash if (locs := cast(MowerDevice, handle.snapshot.raw).report_data.locations) else None
                ),
                sync_type=2 if handle.is_transport_connected(TransportType.BLE) else 3,
                skip_area_names=skip_area_names,
            )

            async def _on_map_complete() -> None:
                _logger.debug("start_map_sync [%s]: saga complete", device_name)
                device = self.get_device_by_name(device_name)
                if device is None:
                    return
                # Restore root_hash_lists from the saga result.  Reports arriving
                # during the sync may have cleared device.map.root_hash_lists via
                # invalidate_maps() because the partial area set didn't hash-match.
                # Copying the completed saga's list ensures the next invalidate_maps()
                # call sees a consistent hash and doesn't immediately clear it again.
                if saga.result is not None:
                    _logger.debug(f"Restoring root_hash_lists for {device.map} from saga result")
                    _logger.debug(f"Restoring root_hash_lists for {saga.result} from saga result")
                    device.map.root_hash_lists = saga.result.root_hash_lists
                device.map.update_hash_lists(device.map.hashlist)
                if device.location.RTK.latitude != 0.0:
                    apply_area_geojson(device.map, device.location.RTK, device.location.dock)
                # Notify map_updated subscribers after a successful saga, matching
                # ``handle.subscribe_map_updated`` 's docstring promise.  Without
                # this emit, downstream subscribers (e.g. Mammotion-HA's area-switch
                # builder) only fire on ``toapp_all_hash_name`` messages, which
                # some Mammotion cloud sessions never deliver — leaving zone
                # entities permanently missing even though the saga successfully
                # populated ``device.map.area``.
                await handle.emit_map_updated()

            await handle.enqueue_saga(saga, on_complete=_on_map_complete)
        else:
            _logger.warning("start_map_sync: device '%s' not registered", device_name)
            return

    async def start_plan_sync(self, device_name: str) -> None:
        """Enqueue a PlanFetchSaga to fetch all stored schedule plans.

        Plans arrive as ``todev_planjob_set`` messages which the StateReducer
        applies to ``device.map.plan`` automatically.  The saga also clears
        ``device.map.plans_stale`` once complete.
        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("start_plan_sync: device '%s' not registered", device_name)
            return
        _logger.debug("start_plan_sync [%s]: enqueuing PlanFetchSaga", device_name)
        saga = PlanFetchSaga(command_builder=handle.commands, send_command=handle.send_raw)

        async def _on_plan_complete() -> None:
            # The saga walks every plan index and the reducer applies each
            # todev_planjob_set frame to device.map.plan; once complete the
            # stored set is authoritative, so clear the stale flag that the
            # reducer raised on all_plan_task.  plans_fetched records that this
            # happened at all, so a device that simply has no schedules stored
            # isn't re-asked on every interval.
            if device := self.get_device_by_name(device_name):
                device.map.plans_stale = False
                device.map.plans_fetched = True

        await handle.enqueue_saga(saga, on_complete=_on_plan_complete)

    async def start_spino_plan_sync(self, device_name: str) -> None:
        """Enqueue a :class:`SpinoPlanFetchSaga` to fetch all Spino cleaning plans.

        Mirror of :meth:`start_plan_sync` for swimming-pool cleaners — plans
        arrive as ``LubaMsg.ctrl.plan_job_set`` frames which the
        :class:`PoolStateReducer` applies to ``device.plans`` automatically.
        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("start_spino_plan_sync: device '%s' not registered", device_name)
            return
        saga = SpinoPlanFetchSaga(command_builder=handle.commands, send_command=handle.send_raw)
        await handle.enqueue_saga(saga)

    async def send_svg(
        self,
        device_name: str,
        svg_message: Any,
        *,
        on_complete: Any | None = None,
    ) -> None:
        """Send an SVG tile to the device via :class:`~pymammotion.messaging.svg_saga.SvgSendSaga`.

        Chunks *svg_message* with
        :func:`~pymammotion.data.model.svg.chunk_svg_messages` and enqueues the
        resulting saga on the device's command queue.

        After the saga finishes the device returns a hash that uniquely
        identifies the stored tile.  Pass *on_complete* to receive it::

            async def got_hash(device_hash: int | None) -> None:
                # store device_hash for later UPDATE / DELETE calls
                ...

            await client.send_svg(device_name, msg, on_complete=got_hash)

        Build *svg_message* with one of the helpers in
        :mod:`pymammotion.data.model.svg`:

        - :func:`~pymammotion.data.model.svg.build_svg_for_area` — **ADD** a new tile
        - :func:`~pymammotion.data.model.svg.build_svg_update` — **UPDATE** an existing tile
        - :func:`~pymammotion.data.model.svg.build_svg_delete` — **DELETE** a tile

        Args:
            device_name: Registered device name.
            svg_message: :class:`~pymammotion.data.model.hash_list.SvgMessage`
                         produced by one of the svg utility builders.
            on_complete: Optional async callable ``(device_hash: int | None) -> None``
                         invoked once the saga finishes.  *device_hash* is
                         ``None`` if the saga did not return a hash (e.g. DELETE).

        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("send_svg: device '%s' not registered", device_name)
            return

        chunks = chunk_svg_messages(svg_message)
        saga = SvgSendSaga(chunks=chunks, command_builder=handle.commands, send_command=handle.send_raw)

        async def _on_complete() -> None:
            if on_complete is not None:
                await on_complete(saga.result_hash)

        await handle.enqueue_saga(saga, on_complete=_on_complete)

    async def check_and_get_mow_path(self, device_name: str) -> None:
        """Fetch the cover path for the current route unless a valid one is already cached."""
        if handle := self._device_registry.get_by_name(device_name):
            device = cast(MowerDevice, handle.snapshot.raw)
            work = device.report_data.work
            if device.map.current_mow_path and device.map.has_mow_path_for_hash(work.path_hash):
                return  # Cache is valid for the current route
            if device.map.current_mow_path:
                device.map.invalidate_mow_path(0)
            if not _should_fetch_mow_path(device, handle, work.path_hash):
                return
            _logger.debug(
                "Device %s path_hash=%d — auto-fetching cover path",
                device_name,
                work.path_hash,
            )
            try:
                current_work = GenerateRouteInformation.from_current_task_settings(device.work)
                await self.start_mow_path_saga(device_name, zone_hashs=[], route_info=current_work, skip_planning=True)
            except Exception:  # noqa: BLE001
                _logger.warning("Auto-trigger MowPathSaga failed for %s", device_name, exc_info=True)

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
        if handle := self._device_registry.get_by_name(device_name):
            # MQTT-only gate: skip when mow_path_fetch_enabled is False AND BLE
            # isn't actively connected (so this would go over MQTT).  BLE-routed
            # fetches always run.
            if not handle.mow_path_fetch_enabled and not handle.is_transport_connected(TransportType.BLE):
                _logger.debug(
                    "start_mow_path_saga '%s': mow_path_fetch_enabled=False over MQTT — skipping",
                    device_name,
                )
                return
            saga = MowPathSaga(
                command_builder=handle.commands,
                send_command=handle.send_raw,
                get_map=lambda: handle.snapshot.raw.map,  # type: ignore
                zone_hashs=zone_hashs,
                route_info=route_info,
                skip_planning=skip_planning,
                device_name=device_name,
                sync_type=2 if handle.is_transport_connected(TransportType.BLE) else 3,
            )

            async def _on_mow_path_complete() -> None:
                device = self.get_device_by_name(device_name)
                if device is not None and device.location.RTK.latitude != 0.0:
                    apply_mowing_geojson(device.map, device.location.RTK)

            await handle.enqueue_saga(saga, on_complete=_on_mow_path_complete)

    async def get_dynamics_line(self, device_name: str) -> None:
        """Fetch the live mow-progress path for *device_name* via a CommonDataSaga.

        Sends ``NavGetCommData(action=8, type=18)`` to the device and collects
        the multi-frame ``toapp_get_commondata_ack`` response.  On completion the
        assembled ``list[CommDataCouple]`` is stored in
        ``device.map.dynamics_line``, replacing any previous value.

        The saga is enqueued on the device's command queue, so it will not
        interrupt other in-progress commands.  Callers should rate-limit
        invocations to avoid flooding the device — the APK uses a 1-second
        minimum gap between requests and calls this every ~10 seconds while
        mowing is active.

        Args:
            device_name: Registered device name.

        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("get_dynamics_line: device '%s' not registered", device_name)
            return

        saga = CommonDataSaga(
            command_builder=handle.commands,
            send_command=handle.send_raw,
            action=8,
            type=PathType.DYNAMICS_LINE,
        )

        async def _on_complete() -> None:
            device = self.get_device_by_name(device_name)
            if device is not None and saga.result:
                device.map.update_dynamics_line(saga.result)
                apply_dynamics_line_geojson(device.map, device.location.RTK)

        await handle.enqueue_saga(saga, on_complete=_on_complete)

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
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("start_edge_mapping: device '%s' not registered", device_name)
            return
        saga = EdgeMappingSaga(command_builder=handle.commands, send_command=handle.send_raw, skip_start=skip_start)
        await handle.enqueue_saga(saga)

    # ------------------------------------------------------------------
    # Scheduled-updates control (called from HA schedule_updates switch)
    # ------------------------------------------------------------------

    async def set_scheduled_updates(self, device_name: str, *, enabled: bool) -> None:
        """Connect or disconnect all transports for *device_name*.

        Called by HA when the user toggles the 'schedule updates' switch.

        When *enabled* is True, all registered transports are reconnected.
        The activity loop restarts automatically via ``update_availability``
        once the transport reports CONNECTED.
        When *enabled* is False, all transports are disconnected, which exits
        the activity loop automatically.
        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            return
        if (ble_transport := handle.get_transport(TransportType.BLE)) and ble_transport.is_usable:
            await ble_transport.connect() if enabled else await ble_transport.disconnect()

        if enabled:
            for t_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
                await handle.connect_transport(t_type)
        else:
            for t_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
                await handle.disconnect_transport(t_type)

    # ------------------------------------------------------------------
    # BLE connection
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    @property
    def mammotion_http(self) -> MammotionHTTP | None:
        """Return the active MammotionHTTP client (Aliyun or direct)."""
        session = self._get_default_session()
        if session is None:
            return None
        if session.cloud_client is not None:
            return session.cloud_client.mammotion_http
        return session.mammotion_http

    async def wake_device(self, name: str, account_id: str | None = None) -> bool:
        """Wake a device out of low-power sleep and re-arm its poll loop.

        Sleep drops the device's broker connection, so no command reaches it and
        ``MammotionHTTP.wake_up_device`` is the only route back.  Lives here rather
        than on the HA facade because this is the one object holding both the handle
        and the account's HTTP session.

        Re-arming matters as much as the wake itself: the poll loop backs off for
        ``_SLEEPING_RECHECK_INTERVAL`` while a device sleeps, so without this the
        first look at a woken mower could be an hour away.

        Returns True when the cloud accepted the request — not that the device is
        awake yet; it reappears in its own time.
        """
        handle = self.mower(name, account_id)
        if handle is None:
            _logger.error("wake_device: device '%s' not found", name)
            return False
        # The handle's own account, not cloud_http's default session: waking with
        # another account's bearer token is rejected by the cloud.
        session = self._get_session_for_handle(handle)
        http = session.mammotion_http if session is not None else None
        if http is None:
            _logger.warning("wake_device: no cloud session available for '%s'", name)
            return False
        response = await http.wake_up_device(handle.device_name)
        if response.data is not True:
            _logger.warning("wake_device: cloud refused to wake '%s': %s", name, response)
            return False
        handle.record_user_command()
        return True

    @property
    def cloud_http(self) -> MammotionHTTP | None:
        """Return the active MammotionHTTP client for cloud operations (OTA, firmware, etc.)."""
        return self.mammotion_http

    @property
    def cloud_gateway(self) -> CloudIOTGateway | None:
        """Return the Aliyun CloudIOTGateway, or None if no Aliyun session was established."""
        session = self._get_default_session()
        return session.cloud_client if session else None

    @property
    def aliyun_device_list(self) -> list[Any]:
        """Return the list of Device objects from the Aliyun cloud registry."""
        session = self._get_default_session()
        if session is None or session.cloud_client is None:
            return []
        try:
            return session.cloud_client.devices_by_account_response.data.data  # type: ignore
        except (AttributeError, TypeError):
            return []

    @property
    def mammotion_device_list(self) -> list[Any]:
        """Return Mammotion-direct devices as shimmed Device objects."""
        session = self._get_default_session()
        if session is None or session.mammotion_http is None:
            return []
        return self.shim_devices_from_records(session.mammotion_http.device_records.records)

    @staticmethod
    def shim_devices_from_records(records: list[DeviceRecord]) -> list[Any]:
        """Convert Mammotion-direct :class:`DeviceRecord` objects to Aliyun Device format.

        The returned Device objects have all required fields populated from the
        record; fields not present in DeviceRecord are set to sensible defaults.
        """
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

    async def _fetch_stream_subscription(self, http: MammotionHTTP, iot_id: str, is_yuka: bool) -> Any:
        """Fetch the stream subscription token, retrying once if the response carries no data.

        The Mammotion stream-token endpoint intermittently returns an empty ``data``
        payload; a single immediate retry usually succeeds.  The empty response is
        logged at error level so the failure is visible even when the retry recovers.
        """
        subscription = await http.get_stream_subscription(iot_id, is_yuka)
        if subscription is None or subscription.data is None:
            _logger.error(
                "get_stream_subscription for %s returned no data (response=%s) — retrying once",
                iot_id,
                subscription,
            )
            subscription = await http.get_stream_subscription(iot_id, is_yuka)
        return subscription

    async def get_stream_subscription(self, device_name: str, iot_id: str) -> Any:
        """Fetch an Agora stream token for the named device and start it streaming.

        For old-firmware devices (those whose device state lacks ``fpv_info``,
        i.e. ``getNewversionfpv() == false`` in the APK), also sends
        ``device_agora_join_channel_with_position(1)`` after the token fetch to
        start the video stream — mirroring the APK's ``getVideoResp`` logic.
        New-firmware devices start streaming without a device-side command; the
        cloud nudges them off the back of the token request.

        Starting a stream never sends ``vi_switch=0``.  That is a teardown verb
        with exactly one home, :meth:`stop_stream`, and on new firmware there is
        no ``vi_switch=1`` to undo it — a pre-emptive leave here switches the
        camera off and races the cloud's own start, so the device joins the
        channel and immediately quits.  The APK's only two ``vi_switch=0`` sends
        are terminal (``onDestroy``, the idle timeout), both after leaving the
        channel; its reconnect path re-runs this same flow with no leave.
        """
        http = self.mammotion_http
        if http is None:
            return None
        is_yuka = DeviceType.is_yuka(device_name)
        subscription = await self._fetch_stream_subscription(http, iot_id, is_yuka)

        if handle := self._device_registry.get_by_name(device_name):
            try:
                new_fpv = handle.snapshot.raw.report_data.dev.fpv_info is not None  # type: ignore
            except AttributeError:
                new_fpv = False
            if not new_fpv:
                await self.send_command_with_args(device_name, "device_agora_join_channel_with_position", enter_state=1)

        return subscription

    async def refresh_stream_subscription(self, device_name: str, iot_id: str) -> Any:
        """Renew the Agora stream token and rejoin the device's channel.

        Identical to :meth:`get_stream_subscription` — the APK re-runs the same
        ``getVideoResp`` flow for the initial join and for every reconnect
        (STUN-timeout, ``on_p2p_lost``).  Kept as a separate name because hosts
        call it to express intent.
        """
        return await self.get_stream_subscription(device_name, iot_id)

    async def stop_stream(self, device_name: str) -> None:
        """Tell the device to stop publishing video (Agora ``vi_switch=0``).

        The only place in the library that sends ``vi_switch=0``.  Call it when
        a viewing session is deliberately over, after leaving the Agora channel
        — never as part of starting or refreshing a stream.
        """
        await self.send_command_with_args(device_name, "device_agora_join_channel_with_position", enter_state=0)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def send_command_with_args(
        self,
        name: str,
        key: str,
        *,
        prefer_ble: bool | None = None,
        skip_if_saga_active: bool = False,
        priority: Priority = Priority.NORMAL,
        account_id: str | None = None,
        _record_cmd: bool = True,
        **kwargs: Any,
    ) -> None:
        """Send a named command to the device via the command queue.

        Builds a :class:`MammotionCommand` for the device, calls ``key(**kwargs)``
        to get the protobuf bytes, then enqueues the send via the device's command
        queue so it is properly ordered with respect to running sagas.

        A direct *priority* (``USER`` / ``EMERGENCY``) skips the queue instead: see
        the *priority* argument below.

        Args:
            name:                Registered device name.
            key:                 Method name on :class:`MammotionCommand`.
            prefer_ble:          Per-call override of the handle's transport preference;
                                 ``None`` (the default) defers to it.  Does not mutate it.
                                 Note this no longer selects the transport — a connected
                                 BLE always wins and a usable MQTT otherwise, see
                                 ``active_transport``.  All it still does is decide whether
                                 a *disconnected* BLE gets warmed up in the background, so
                                 passing True on a handle the user configured
                                 ``prefer_ble=False`` reconnects Bluetooth they turned off.
                                 That is why the default defers rather than asserting.
            skip_if_saga_active: When True, the command is silently dropped if a
                                 saga (map/plan/mow-path fetch) is currently running.
                                 Use for fire-and-forget UI ops (volume, knife height,
                                 light toggle) that the user expects to take effect
                                 immediately rather than queue behind a long fetch.
                                 Ignored for direct priorities, which never queue.
            priority:            ``Priority.USER`` (or ``EMERGENCY``) dispatches the
                                 command here and now, on the caller's task: it cannot
                                 wait behind a saga, cannot be TTL-dropped, and spends
                                 past the self-imposed send quota.  A cloud-imposed 429
                                 ban still blocks it, and a missing transport raises
                                 rather than returning silently, so the caller learns
                                 the command did not land.
                                 Pass this only for genuine user actions — the quota
                                 exists to pace polling, and defaulting everything to
                                 USER would make it inert.
            _record_cmd:         Internal flag — set False for watchdog-initiated sends
                                 so they do not wake the poll loop.

        Raises:
            KeyError:       if *name* is not a registered device.
            AttributeError: if *key* is not a valid command.
            Exception:      on a *direct* priority only, whatever the send failed with —
                that is the point of dispatching on the caller's task.  A host is
                expected to handle at least ``NoTransportAvailableError`` (nothing to
                send over), ``TooManyRequestsException`` (the cloud answered 429) and
                ``TransportRateLimitedError`` (we declined to transmit: the 429 ban is
                still running, or the self-imposed quota is spent).  The last one is
                easy to miss because it is the only one that never reaches the network
                and the only one a queued command never surfaces — the queue logs and
                absorbs it.

        """
        handle = self._device_registry.get_by_name(name, account_id)
        if handle is None:
            msg = f"Device '{name}' not registered"
            raise KeyError(msg)
        if _record_cmd:
            handle.record_user_command()
        commands = handle.commands
        command_bytes: bytes = getattr(commands, key)(**kwargs)
        _logger.debug(
            "send_command_with_args: device=%s key=%s prefer_ble=%s kwargs=%s",
            name,
            key,
            prefer_ble,
            kwargs,
        )
        _prefer_ble = prefer_ble
        _session = self._get_session_for_handle(handle)

        async def _do_send() -> None:
            # Single offline gate via the centralized property — covers
            # mqtt_reported_offline + no BLE, BLE-in-cooldown + no MQTT, and
            # nothing-registered.  active_transport() is the source of truth.
            #
            # We don't retry here: when no transport is usable the wait isn't
            # bounded by something the queue can fix on its own — recovery
            # depends on the cloud pushing thing/status (clears
            # mqtt_reported_offline) or BLE coming back (rearm event).  Both
            # naturally re-arm the poll loop, and the user can re-issue the
            # command then.
            #
            # A direct command skips the gate and lets send_raw's active_transport()
            # raise instead: a person pressed a button, so silently doing nothing is
            # the one outcome they cannot act on.
            if not priority.is_direct and not handle.has_usable_transport:
                _logger.debug(
                    "send_command_with_args '%s': no usable transport — skipping '%s'",
                    name,
                    key,
                )
                return
            await self._send_with_auth_retry(
                lambda: handle.send_raw(command_bytes, prefer_ble=_prefer_ble, user_initiated=priority.is_direct),
                _session,
            )

        if priority.is_direct:
            # Dispatched on the caller's task, not the queue: the processor is strictly
            # sequential, so anything queued behind an in-flight saga waits for it no
            # matter how it is ranked.  execute_command keeps the queue's retry and
            # error classification; reraise lets the host see a command that didn't land.
            await execute_command(
                _do_send,
                device_name=name,
                on_critical_error=handle.queue.on_critical_error,
                reraise=True,
            )
            return

        await handle.queue.enqueue(_do_send, priority=priority, skip_if_saga_active=skip_if_saga_active)

    async def send_command_and_wait(
        self,
        name: str,
        key: str,
        expected_field: str,
        *,
        send_timeout: float = 5.0,
        prefer_ble: bool | None = None,
        priority: Priority = Priority.NORMAL,
        account_id: str | None = None,
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
            prefer_ble:     Per-call override of the handle's transport preference;
                            ``None`` (the default) defers to it.  This used to default to
                            ``True``, which meant every caller that omitted it — including
                            ``MammotionMowerAPI`` — pre-emptively reconnected BLE on a
                            handle configured ``prefer_ble=False``.
            priority:       ``Priority.USER`` (or ``EMERGENCY``) spends past the
                            self-imposed send quota.  This method never used the
                            command queue — it drives the broker directly — so the
                            quota exemption is the only thing a direct priority
                            changes here.
            **kwargs:       Arguments passed to the command builder.

        Raises:
            KeyError:             if *name* is not a registered device.
            CommandTimeoutError:  if no response after retries.
            TransportRateLimitedError: if the send is refused before it reaches the
                network — a cloud 429 ban, or the self-imposed quota on a non-direct
                priority.  This method never used the queue, so nothing absorbs it here
                regardless of *priority*.

        """
        handle = self._device_registry.get_by_name(name, account_id)
        if handle is None:
            msg = f"Device '{name}' not registered"
            raise KeyError(msg)
        handle.record_user_command()
        commands = handle.commands
        command_bytes: bytes = getattr(commands, key)(**kwargs)
        _session = self._get_session_for_handle(handle)

        async def _send() -> None:
            await self._send_with_auth_retry(
                lambda: handle.send_raw(
                    payload=command_bytes, prefer_ble=prefer_ble, user_initiated=priority.is_direct
                ),
                _session,
            )

        return await handle.broker.send_and_wait(
            send_fn=_send,
            expected_field=expected_field,
            send_timeout=send_timeout,
        )

    def set_prefer_ble(self, device_id: str, *, prefer_ble: bool, account_id: str | None = None) -> None:
        """Set transport preference for a registered device."""
        handle = (
            self._device_registry.get(device_id)
            if account_id is None
            else self._device_registry.get(account_id, device_id)
        )
        if handle is not None:
            handle.set_prefer_ble(value=prefer_ble)

    def set_mow_path_fetch_enabled(self, device_id: str, *, enabled: bool) -> None:
        """Toggle the MQTT-side mow path fetch gate for a registered device.

        When False, MowPathSaga is skipped for any send that would go over
        MQTT.  BLE-routed fetches always run regardless.
        """
        handle = self._device_registry.get(device_id)
        if handle is not None:
            handle.set_mow_path_fetch_enabled(value=enabled)

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
