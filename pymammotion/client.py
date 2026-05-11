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
import json
import logging
import time
from typing import TYPE_CHECKING, Any, cast

from pymammotion.account.registry import BLE_ONLY_ACCOUNT, AccountRegistry, AccountSession
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.auth.token_manager import TokenManager
from pymammotion.bluetooth.manager import BLETransportManager
from pymammotion.data.model import GenerateRouteInformation
from pymammotion.data.model.device import MowerDevice, RTKBaseStationDevice
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.device.readiness import get_readiness_checker
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import CheckDeviceVersion, DeviceRecord, DeviceRecords, Response
from pymammotion.messaging.command_queue import Priority
from pymammotion.messaging.map_saga import MapFetchSaga
from pymammotion.proto import RptAct, RptInfoType
from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport
from pymammotion.transport.base import (
    AuthError,
    LoginFailedError,
    NoTransportAvailableError,
    ReLoginRequiredError,
    SessionExpiredError,
    Subscription,
    TransportError,
    TransportType,
)
from pymammotion.transport.ble import BLETransport, BLETransportConfig
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig
from pymammotion.utility.constant import WorkMode
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

    from aiohttp import ClientSession
    from bleak import BLEDevice

    from pymammotion.data.model.device import MowingDevice
    from pymammotion.data.mqtt.event import ThingEventMessage
    from pymammotion.data.mqtt.properties import ThingPropertiesMessage
    from pymammotion.data.mqtt.status import ThingStatusMessage
    from pymammotion.http.model.http import MQTTConnection

_logger = logging.getLogger(__name__)


class MammotionClient:
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
        self._ble_manager: BLETransportManager = BLETransportManager()
        self._stopped: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()
        self._iot_id_to_device_id: dict[str, str] = {}
        # RAII subscriptions for state-change watchers (keyed by device_name)
        self._watcher_subscriptions: dict[str, list[Subscription]] = {}
        self._ha_version: str | None = ha_version
        #: Fired when all automatic auth recovery attempts (relogin, token refresh,
        #: reconnect) have been exhausted and human intervention is required.
        #: HA-Luba wires this to ``entry.async_start_reauth()``.
        self.on_unrecoverable_auth_error: Callable[[Exception], Awaitable[None]] | None = None
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
        # Forward to token_manager if it is already initialised.
        tm = self.token_manager
        if tm is not None:
            tm.on_credentials_updated = value

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

    async def remove_device(self, name: str) -> None:
        """Stop and remove the named device from the registry."""
        if handle := self._device_registry.get_by_name(name):
            await self._device_registry.unregister(handle.device_id)

    # ------------------------------------------------------------------
    # Device state watchers
    # ------------------------------------------------------------------

    def setup_device_watchers(self, device_name: str) -> Subscription | None:
        """Register auto-fetch / auto-subscribe watchers for *device_name*.

        Installs field watchers on the device handle:

        * ``(ub_path_hash, path_hash)`` — fires ``MowPathSaga`` (fetch-only)
          when either hash transitions to an active value while no cover path
          is cached.
        * ``(path_pos_x, path_pos_y)`` — rebuilds ``generated_mow_progress_geojson``
          as the mower progresses along the path.
        * ``bol_hash`` (from ``report_data.locations[0].bol_hash``) — fires
          ``MapFetchSaga`` when the device reports a different map hash,
          replacing the old ``MapStalenessWatcher`` for the maps case.  Plan
          staleness is not watched — we don't yet know which field indicates
          plan changes.

        Cadence/streaming for ``sys_status`` lives in
        :class:`~pymammotion.device.handle.DeviceHandle` (BLE polling loop +
        MQTT cadence table) — not here.

        Call ``teardown_device_watchers`` to cancel.  Returns the first
        registered Subscription, or None if the device isn't registered yet.
        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            return None

        async def _on_path_hashes_changed(_hashes: tuple[int, int]) -> None:
            device = cast(MowerDevice, handle.snapshot.raw)
            work = device.report_data.work
            # path_hash in (0, 1) means "no job" / "job ended".
            has_active_job = work.ub_path_hash != 0 or work.path_hash not in (0, 1)
            if not has_active_job:
                return
            if device.map.current_mow_path:
                # Cache exists — validate it against the current active segment hash.
                # ub_path_hash appears directly as path_packets[0].path_hash inside the
                # cover-path frames (confirmed via APK HashDataManager and device data).
                # If ub_path_hash is 0 we can't validate a specific segment, so keep.
                if work.ub_path_hash == 0 or device.map.has_mow_path_for_hash(work.ub_path_hash):
                    return  # Cache is valid for the current job segment
                # Cache exists but doesn't contain the current segment — stale.
                # Clear it so the saga fetches fresh data below.
                device.map.invalidate_mow_path(0)
            if handle.queue.is_saga_active:
                return
            _logger.debug(
                "Device %s path_hash=%d ub_path_hash=%d — auto-fetching cover path",
                device_name,
                work.path_hash,
                work.ub_path_hash,
            )
            try:
                current_work = GenerateRouteInformation.from_current_task_settings(device.work)
                await self.start_mow_path_saga(device_name, zone_hashs=[], route_info=current_work, skip_planning=True)
            except Exception:  # noqa: BLE001
                _logger.warning("Auto-trigger MowPathSaga failed for %s", device_name, exc_info=True)

        async def _on_mow_progress_changed(_pos: tuple[int, int]) -> None:
            device = cast(MowerDevice, handle.snapshot.raw)
            if device.map.current_mow_path and device.report_data.dev.sys_status == WorkMode.MODE_WORKING:
                work = device.report_data.work
                device.map.apply_mow_progress_geojson(
                    device.location.RTK,
                    work.now_index,
                    work.ub_path_hash,
                    work.path_pos_x,
                    work.path_pos_y,
                )

        async def _on_bol_hash_changed(bol_hash: int) -> None:
            # bol_hash changes when the device's map data has been edited or
            # re-synced on the device side — trigger a re-fetch so our
            # cached HashList reflects the new topology.
            if handle.queue.is_saga_active:
                return
            _logger.debug(
                "Device %s bol_hash changed to %d — syncing map",
                device_name,
                bol_hash,
            )
            try:
                await self.start_map_sync(device_name)
            except Exception:  # noqa: BLE001
                _logger.warning("Auto-trigger map sync failed for %s", device_name, exc_info=True)

        sub = handle.watch_field(
            lambda s: (s.raw.report_data.work.ub_path_hash, s.raw.report_data.work.path_hash),
            _on_path_hashes_changed,
        )
        progress_sub = handle.watch_field(
            lambda s: (s.raw.report_data.work.path_pos_x, s.raw.report_data.work.path_pos_y),
            _on_mow_progress_changed,
        )
        bol_hash_sub = handle.watch_field(
            lambda s: s.raw.report_data.locations[0].bol_hash if s.raw.report_data.locations else 0,
            _on_bol_hash_changed,
        )
        self._watcher_subscriptions[device_name] = [
            sub,
            progress_sub,
            bol_hash_sub,
        ]
        return sub

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

    async def request_reports(self, device_name: str, *, count: int = 1, timeout: int = 10000) -> None:
        """Fire a one-shot count=count report, skipped if the BLE stream is already active."""
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

    def teardown_device_watchers(self, device_name: str) -> None:
        """Cancel state-change subscriptions for *device_name*."""
        for sub in self._watcher_subscriptions.pop(device_name, []):
            sub.cancel()

    def setup_all_mower_watchers(self) -> None:
        """Set up state-change watchers for all registered mower devices.

        Skips RTK base stations and swimming-pool (Spino/S1/E1) devices.
        """
        from pymammotion.utility.device_type import DeviceType

        for handle in self._device_registry.all_devices:
            name = handle.device_name
            if DeviceType.is_rtk(name) or DeviceType.is_swimming_pool(name):
                continue
            self.setup_device_watchers(name)

    # ------------------------------------------------------------------
    # Account session helpers
    # ------------------------------------------------------------------

    def _get_session_for_device(self, device_name: str) -> AccountSession | None:
        """Return the AccountSession that owns *device_name*, or None."""
        return self._account_registry.find_by_device(device_name)

    def _get_default_session(self) -> AccountSession | None:
        """Return the first registered session (convenience for single-account setups)."""
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

    async def _full_relogin(self, session: AccountSession | None) -> None:
        """Re-login with stored credentials and refresh all tokens.

        Called when token refresh fails (ReLoginRequiredError).
        Raises LoginFailedError if the re-login itself fails.
        """
        if session is None or not session.email or not session.password:
            msg = "No stored credentials available for re-login"
            raise LoginFailedError("", msg)  # noqa: EM101
        if session.mammotion_http is None:
            msg = "No HTTP client available for re-login"
            raise LoginFailedError(session.email, msg)
        try:
            try:
                await session.mammotion_http.logout()
            except Exception as logout_exc:  # noqa: BLE001 - best-effort logout before re-login
                _logger.debug("Logout before re-login failed (continuing): %s", logout_exc)
            login_resp = await session.mammotion_http.login_v2(session.email, session.password)
            if login_resp.code != 0:
                raise LoginFailedError(session.email, login_resp.msg)
            if session.token_manager is not None:
                await session.token_manager.force_refresh()
        except LoginFailedError:
            raise
        except Exception as exc:
            raise LoginFailedError(session.email, str(exc)) from exc

    async def _send_with_auth_retry(
        self, send_fn: Callable[[], Awaitable[None]], session: AccountSession | None = None
    ) -> None:
        """Call *send_fn*; on auth failure, refresh credentials and retry.

        Cascade:
          1. SessionExpiredError → targeted refresh for the failing transport → retry.
          2. Still fails → force_refresh (all credentials) → retry.
          3. force_refresh raises ReLoginRequiredError → full re-login with stored credentials → retry.
          4. Re-login fails → LoginFailedError propagates to the caller.
        """
        tm = session.token_manager if session else None
        try:
            await send_fn()
        except SessionExpiredError as exc:
            _logger.debug("Session expired on %s — refreshing targeted credentials", exc.transport_type.value)
            try:
                await self._refresh_for_transport(exc.transport_type, session)
                await send_fn()
            except ReLoginRequiredError:
                _logger.debug("Targeted refresh requires re-login — attempting full re-login")
                await self._full_relogin(session)
                await send_fn()
            except (SessionExpiredError, AuthError):
                _logger.debug("Targeted refresh failed — attempting full credential refresh")
                try:
                    if tm is not None:
                        await tm.force_refresh()
                    await send_fn()
                except ReLoginRequiredError:
                    _logger.debug("Full refresh requires re-login — attempting full re-login")
                    await self._full_relogin(session)
                    await send_fn()
        except ReLoginRequiredError:
            _logger.debug("Auth requires re-login — attempting full re-login")
            await self._full_relogin(session)
            await send_fn()
        except AuthError:
            _logger.debug("Auth error — attempting full credential refresh")
            try:
                if tm is not None:
                    await tm.force_refresh()
                await send_fn()
            except ReLoginRequiredError:
                _logger.debug("Full refresh requires re-login — attempting full re-login")
                await self._full_relogin(session)
                await send_fn()
        except NoTransportAvailableError:
            raise  # let send_command_with_args retry when transport reconnects
        except TransportError as ex:
            _logger.warning(ex)

    # ------------------------------------------------------------------
    # Device access
    # ------------------------------------------------------------------

    def get_device_by_name(self, name: str) -> MowingDevice | None:
        """Return the MowingDevice state for the named device, or None."""
        handle = self._device_registry.get_by_name(name)
        if handle is None:
            return None
        return handle.snapshot.raw

    def regenerate_stale_geojson(self, device_name: str | None = None) -> None:
        """Regenerate GeoJSON for any device whose stored map was built with a different RTK yaw.

        Call this after restoring device state (e.g. after ``handle.restore_device()``
        in the HA coordinator) so that maps generated without the RTK heading correction
        are immediately fixed without waiting for the next full map sync.

        Args:
            device_name: Regenerate only this device.  When ``None`` (default),
                         checks every registered mower device.

        """
        from pymammotion.data.model.device import MowingDevice

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
                device.map.generate_geojson(rtk, device.location.dock)

    def mower(self, name: str) -> DeviceHandle | None:
        """Return the DeviceHandle for the named device, or None."""
        return self._device_registry.get_by_name(name)

    def rtk_device(self, name: str) -> DeviceHandle | None:
        """Return the DeviceHandle for the named RTK base station, or None."""
        return self._device_registry.get_by_name(name)

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
            if ota_progress := data.otaProgress:
                updated = dataclasses.replace(updated, update_check=CheckDeviceVersion.from_dict(ota_progress.value))
            if network_info := data.networkInfo:
                network = json.loads(network_info.value)
                updated = dataclasses.replace(
                    updated,
                    wifi_rssi=network["wifi_rssi"],
                    wifi_mac=network["wifi_sta_mac"],
                    bt_mac=network["bt_mac"],
                )
            if coordinate := data.coordinate:
                coord_val = json.loads(coordinate.value)
                _logger.debug("Raw RTK coordinate payload: %s", coord_val)
                if coord_val["lat"] != 0:
                    updated = dataclasses.replace(updated, lat=coord_val["lat"])
                if coord_val["lon"] != 0:
                    updated = dataclasses.replace(updated, lon=coord_val["lon"])
            if device_version := data.deviceVersion:
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

    async def add_ble_device(self, device_id: str, ble_device: BLEDevice) -> None:
        """Register an externally-discovered BLE device (hybrid MQTT+BLE mode).

        If the device handle is already registered (cloud login happened first),
        a BLETransport is created and wired to the handle immediately.  If the
        handle does not exist yet, the BLE device is stored in the manager so
        that the transport can be added once the handle is registered.
        """
        self._ble_manager.register_external_ble_client(device_id, ble_device)
        handle = self._device_registry.get(device_id)
        if handle is not None:
            transport = BLETransport(BLETransportConfig(device_id=device_id))
            transport.set_ble_device(ble_device)
            await handle.add_transport(transport)
            _logger.debug("BLE transport added to existing handle for device %s", device_id)

    async def update_ble_device(self, device_id: str, ble_device: BLEDevice) -> bool:
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
            of the same address.  HA-side callers can short-circuit redundant
            work (logging, downstream task creation) on False.

        """
        self._ble_manager.update_external_ble_client(device_id, ble_device)
        handle = self._device_registry.get(device_id)
        if handle is None:
            return False
        ble = handle.get_transport(TransportType.BLE)
        if not isinstance(ble, BLETransport):
            return False
        return ble.set_ble_device(ble_device)

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
        handle = self._device_registry.get(device_id)
        if handle is None:
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
        """Register a BLE-only device — no HTTP login or MQTT involved.

        Standalone (non-HA) entry point.  Provide either a pre-discovered
        ``BLEDevice`` (e.g. from your own ``BleakScanner`` pass) or a MAC
        ``ble_address`` and let the transport scan for it on connect.

        Creates a :class:`DeviceHandle` with ``prefer_ble=True`` and a
        :class:`BLETransport` already wired up.  Call ``handle.start()`` to
        begin the command queue, then ``transport.connect()`` to open the
        GATT connection.  When ``self_managed_scanning`` is True, the
        transport runs a one-shot ``BleakScanner.find_device_by_address`` at
        connect-time if no BLEDevice is cached.

        Args:
            device_id:             Unique device identifier (e.g. ``"Luba-XXXXXX"``).
            device_name:           Human-readable name shown in HA.
            initial_device:        Empty or cached ``MowingDevice`` for initial state.
            ble_device:            Optional pre-discovered bleak ``BLEDevice``.
            ble_address:           Optional MAC.  Required when ``ble_device``
                                   is not supplied.  Stored in the transport
                                   config for self-managed scanning.
            self_managed_scanning: When True, the transport scans for the
                                   device by ``ble_address`` if no BLEDevice
                                   is cached at connect-time.  Defaults to
                                   True when only ``ble_address`` is supplied,
                                   False when ``ble_device`` is supplied
                                   (HA-style — scanning owned by the caller).
                                   Pass explicitly to override.

        Returns:
            The registered ``DeviceHandle``.

        Raises:
            ValueError: when neither ``ble_device`` nor ``ble_address`` is supplied.

        """
        if ble_device is None and ble_address is None:
            raise ValueError("add_ble_only_device requires either ble_device or ble_address")

        # Idempotency: if this device is already registered (e.g. a config-entry reload
        # races with the previous teardown), reuse the existing handle rather than
        # replacing it and orphaning the live BLE connection.
        existing = self._device_registry.get(device_id)
        if existing is not None:
            _logger.info("add_ble_only_device: %s already registered — reusing handle", device_name)
            if ble_device is not None:
                ble_t = existing.get_transport(TransportType.BLE)
                if ble_t is not None:
                    cast(BLETransport, ble_t).set_ble_device(ble_device)
                else:
                    await self.add_ble_to_device(device_name, ble_device)
            return existing

        if self_managed_scanning is None:
            self_managed_scanning = ble_device is None

        transport = BLETransport(
            BLETransportConfig(
                device_id=device_id,
                ble_address=ble_address,
                self_managed_scanning=self_managed_scanning,
            )
        )
        if ble_device is not None:
            transport.set_ble_device(ble_device)

        handle = DeviceHandle(
            device_id=device_id,
            device_name=device_name,
            initial_device=initial_device,
            ble_transport=transport,
            prefer_ble=True,
        )
        await self._device_registry.register(handle)
        # Add to BLE-only account session
        ble_session = self._account_registry.get(BLE_ONLY_ACCOUNT)
        if ble_session is None:
            ble_session = AccountSession(account_id=BLE_ONLY_ACCOUNT)
            await self._account_registry.register(ble_session)
        ble_session.device_ids.add(device_name)
        _logger.info("BLE-only device registered: %s (%s)", device_name, device_id)
        return handle

    # ------------------------------------------------------------------
    # Cloud / MQTT — public entry points
    # ------------------------------------------------------------------

    async def _sign_out_session(self, session: AccountSession) -> None:
        """Disconnect transports and sign out a single account session."""
        if session.aliyun_transport is not None:
            await session.aliyun_transport.disconnect()
            session.aliyun_transport = None
        if session.mammotion_transport is not None:
            await session.mammotion_transport.disconnect()
            session.mammotion_transport = None
        if session.mammotion_http is not None:
            try:
                await session.mammotion_http.logout()
            except Exception:  # noqa: BLE001
                _logger.warning("HTTP logout failed — proceeding with login anyway", exc_info=True)
            session.mammotion_http = None
        if session.cloud_client is not None:
            try:
                await session.cloud_client.sign_out()
            except Exception:  # noqa: BLE001
                _logger.warning("cloud sign_out failed — proceeding with login anyway", exc_info=True)
            session.cloud_client = None
        session.token_manager = None
        await self._account_registry.unregister(session.account_id)

    async def _sign_out_existing_session(self, account_id: str | None = None) -> None:
        """Disconnect active transports and sign out cloud session(s).

        Args:
            account_id: Sign out only this account.  When ``None``, sign out
                        all cloud sessions (BLE-only sessions are preserved).

        """
        if account_id is not None:
            session = self._account_registry.get(account_id)
            if session is not None:
                await self._sign_out_session(session)
        else:
            for session in self._account_registry.all_sessions:
                if session.account_id == BLE_ONLY_ACCOUNT:
                    continue
                await self._sign_out_session(session)
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
        await self._sign_out_existing_session(account)
        mammotion_http = MammotionHTTP(session=session, ha_version=self._ha_version)
        login_resp = await mammotion_http.login_v2(account, password)
        if login_resp.code != 0:
            raise LoginFailedError(account, login_resp.msg)

        device_list_owned_resp = await mammotion_http.get_user_device_list()
        device_list_resp = await mammotion_http.get_user_shared_device_page()
        device_page_resp = await mammotion_http.get_user_device_page()
        aliyun_devices: DeviceRecords = device_list_resp.data or []
        mammotion_records = (device_page_resp.data.records if device_page_resp.data else []) or []

        # Build an authoritative device_name→iot_id map from /device-server/v1/device/list.
        # This endpoint returns the canonical Mammotion iot_id for every owned device and
        # is used to correct stale or wrong iot_ids that may appear in the Aliyun binding
        # list or the Mammotion device-page records (particularly for RTK base stations).
        owned_iot_id_map: dict[str, str] = {
            d.device_name: d.iot_id for d in (device_list_owned_resp.data or []) if d.device_name and d.iot_id
        }

        acct_session = AccountSession(
            account_id=account,
            email=account,
            password=password,
            mammotion_http=mammotion_http,
        )
        acct_session.user_account = self._extract_user_account(mammotion_http)

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

            acct_session.cloud_client = cloud_client
            acct_session.token_manager = TokenManager(account, mammotion_http, cloud_client)
            acct_session.token_manager.on_credentials_updated = self._on_credentials_updated
            al_transport = self._setup_aliyun_transport(cloud_client, acct_session)
            acct_session.aliyun_transport = al_transport
            ua = acct_session.user_account
            for device in cloud_client.devices_by_account_response.data.data:
                if device.device_name:
                    iot_id = owned_iot_id_map.get(device.device_name) or device.iot_id
                    await self._register_aliyun_device(
                        device.device_name,
                        iot_id,
                        al_transport,
                        ua,
                        device.product_key,
                        token_manager=acct_session.token_manager,
                    )
                    acct_session.device_ids.add(device.device_name)
            await al_transport.connect()

        if mammotion_records:
            await mammotion_http.get_mqtt_credentials()
            if mammotion_http.mqtt_credentials is None:
                _logger.error("Could not obtain Mammotion MQTT credentials — skipping post-2025 devices")
            else:
                if acct_session.token_manager is None:
                    acct_session.token_manager = TokenManager(account, mammotion_http)
                    acct_session.token_manager.on_credentials_updated = self._on_credentials_updated
                transport = self._setup_mammotion_transport(
                    mammotion_http.mqtt_credentials, mammotion_http, acct_session, acct_session.token_manager
                )
                acct_session.mammotion_transport = transport
                ua = acct_session.user_account
                for record in mammotion_records:
                    if record.device_name:
                        iot_id_override = owned_iot_id_map.get(record.device_name, "")
                        await self._register_mammotion_device(
                            record, transport, ua, iot_id_override, token_manager=acct_session.token_manager
                        )
                        acct_session.device_ids.add(record.device_name)
                await transport.connect()

        await self._account_registry.register(acct_session)

    def to_cache(self) -> dict[str, Any]:
        """Serialize current cloud credentials to a cache dictionary.

        The returned dict can be passed to :meth:`restore_credentials` in a future
        session to skip re-authentication. If an Aliyun cloud client is active its
        full serialization is used (which already includes the Mammotion HTTP data).
        For a Mammotion-MQTT-only setup a minimal dict is produced instead.

        Returns an empty dict when no cloud session has been established yet.
        """
        session = self._get_default_session()
        if session is None:
            return {}
        if session.cloud_client is not None:
            return session.cloud_client.to_cache()
        if session.mammotion_http is not None:
            raw: dict[str, Any] = {}
            if session.mammotion_http.response is not None:
                raw["mammotion_data"] = session.mammotion_http.response
            if session.mammotion_http.mqtt_credentials is not None:
                raw["mammotion_mqtt"] = session.mammotion_http.mqtt_credentials
            if session.mammotion_http.device_records.records:
                raw["mammotion_device_records"] = session.mammotion_http.device_records
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
        # Get or create the session for this account
        acct_session = self._account_registry.get(account)
        if acct_session is None:
            acct_session = AccountSession(account_id=account, email=account, password=password)
            await self._account_registry.register(acct_session)
        else:
            acct_session.password = password

        if "aep_data" in cached_data:
            await self._restore_aliyun(
                account, password, cached_data, acct_session, check_for_new_devices=check_for_new_devices
            )

        if "mammotion_mqtt" in cached_data and "mammotion_device_records" in cached_data:
            await self._restore_mammotion_mqtt(
                account, password, cached_data, session, acct_session, check_for_new_devices=check_for_new_devices
            )

    @property
    def token_manager(self) -> TokenManager | None:
        """Return the active TokenManager, or None if no cloud session."""
        session = self._get_default_session()
        return session.token_manager if session else None

    async def refresh_login(self, account: str) -> None:
        """Refresh authentication credentials for the given account."""
        session = self._account_registry.get(account) or self._get_default_session()
        if session is not None and session.token_manager is not None:
            await session.token_manager.refresh_aliyun_credentials()
            _logger.info("refresh_login: credentials refreshed for account=%s", account)
        else:
            _logger.warning("refresh_login: no token manager available for account=%s", account)

    # ------------------------------------------------------------------
    # Cloud — private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_user_account(mammotion_http: MammotionHTTP) -> int:
        """Extract the numeric user account from login_info, or 0."""
        if mammotion_http.login_info is not None:
            return int(mammotion_http.login_info.userInformation.userAccount)
        return 0

    def _setup_aliyun_transport(
        self, cloud_client: CloudIOTGateway, acct_session: AccountSession
    ) -> AliyunMQTTTransport:
        """Build an AliyunMQTTTransport from a ready CloudIOTGateway."""
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
        transport.on_device_status = self._route_device_status
        transport.on_device_event = self._route_device_event
        transport.on_device_properties = self._route_device_properties

        token_manager = acct_session.token_manager

        async def _on_aliyun_auth_failure() -> bool:
            """Handle a 2043/460 bind rejection.

            Strategy:
            1. Try a targeted Aliyun credential refresh (check_or_refresh_session).
               This is sufficient when the iotToken simply expired or Aliyun returned
               460 "iotToken blank" — the refreshToken is still valid.
            2. Only if that raises ReLoginRequiredError (refreshToken also exhausted /
               account blocked after repeated failures) do we escalate to a full
               email/password re-login.  Skipping straight to _full_relogin on every
               2043/460 fires unnecessary login_v2 calls that hammer Aliyun further
               and extend any account block.
            """
            if token_manager is None:
                return False
            _logger.warning("Aliyun bind rejected — attempting targeted credential refresh")
            try:
                await token_manager.refresh_aliyun_credentials()
                creds = await token_manager.get_aliyun_credentials()
                transport.update_iot_token(creds.iot_token)
                _logger.info("Aliyun IoT token refreshed via targeted credential refresh")
                return True
            except ReLoginRequiredError:
                # refreshToken exhausted (2401 repeatedly) — escalate to full re-login.
                _logger.warning("Aliyun refreshToken exhausted — escalating to full re-login")
            try:
                await self._full_relogin(acct_session)
                creds = await token_manager.get_aliyun_credentials()
                transport.update_iot_token(creds.iot_token)
                _logger.info("Aliyun IoT token refreshed after full re-login")
                return True
            except Exception as exc:
                _logger.exception("Full re-login failed after Aliyun bind token expiry")
                raise ReLoginRequiredError(
                    acct_session.email if acct_session else "",
                    f"Full re-login failed after Aliyun bind rejection: {exc}",
                ) from exc

        transport.on_auth_failure = _on_aliyun_auth_failure

        # When on_auth_failure itself fails (full re-login exhausted), the
        # transport raises ReLoginRequiredError and fires this callback.
        # Mirror the Mammotion MQTT pattern: attempt a final full re-login
        # and reconnect so the integration can recover without user action.
        async def _on_aliyun_fatal_auth(exc: ReLoginRequiredError) -> None:
            _logger.warning("Aliyun transport fatal auth error — attempting final re-login: %s", exc)
            try:
                await self._full_relogin(acct_session)
                # Same safety net: explicit push in case callback path was skipped.
                if token_manager is not None:
                    creds = await token_manager.get_aliyun_credentials()
                    transport.update_iot_token(creds.iot_token)
                # Schedule connect() for after the current _run() task exits.
                # Calling it directly here is a no-op because the task is still running.
                asyncio.get_running_loop().call_soon(lambda: asyncio.ensure_future(transport.connect()))
                _logger.info("Aliyun transport reconnect scheduled after final re-login")
            except Exception as relogin_exc:
                _logger.exception("Final re-login failed for Aliyun transport — user must re-authenticate")
                if self.on_unrecoverable_auth_error is not None:
                    with contextlib.suppress(Exception):
                        await self.on_unrecoverable_auth_error(relogin_exc)

        transport.on_fatal_auth_error = _on_aliyun_fatal_auth

        # Keep the transport's bind token current on every proactive refresh so that
        # reconnects after a network blip don't carry a stale iotToken.
        if token_manager is not None:
            token_manager.on_aliyun_token_refreshed = transport.update_iot_token
        return transport

    def _setup_mammotion_transport(
        self,
        mqtt_creds: MQTTConnection,
        mammotion_http: MammotionHTTP,
        acct_session: AccountSession,
        token_manager: TokenManager,
    ) -> MQTTTransport:
        """Build a MQTTTransport from MQTTConnection credentials."""
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

        # Build a jwt_refresher that uses the TokenManager to get a fresh JWT.

        async def _refresh_jwt() -> str:
            creds = await token_manager.refresh_mqtt_creds()
            if creds is None:
                raise ReLoginRequiredError(token_manager.account_id, "No JWT available after credential refresh")
            return str(creds.jwt)

        transport = MQTTTransport(config, mammotion_http, jwt_refresher=_refresh_jwt, token_manager=token_manager)
        transport.on_device_message = self._route_device_message
        transport.on_device_status = self._route_device_status
        transport.on_device_properties = self._route_device_properties

        # When the connection loop permanently fails auth, trigger a full
        # re-login and reconnect so the integration recovers automatically.
        async def _on_fatal_auth(exc: Exception) -> None:
            _logger.warning("MQTT transport fatal auth error — attempting full re-login: %s", exc)
            try:
                await self._full_relogin(acct_session)
                new_jwt = await _refresh_jwt()
                transport.update_jwt(new_jwt)
                # Schedule connect() for after the current _run() task exits.
                asyncio.get_running_loop().call_soon(lambda: asyncio.ensure_future(transport.connect()))
                _logger.info("MQTT transport reconnect scheduled after full re-login")
            except Exception as relogin_exc:
                _logger.exception("Full re-login failed for MQTT transport")
                if self.on_unrecoverable_auth_error is not None:
                    with contextlib.suppress(Exception):
                        await self.on_unrecoverable_auth_error(relogin_exc)

        transport.on_fatal_auth_error = _on_fatal_auth
        return transport

    async def _register_aliyun_device(
        self,
        device_name: str,
        iot_id: str,
        transport: AliyunMQTTTransport,
        user_account: int = 0,
        product_key: str = "",
        token_manager: TokenManager | None = None,
    ) -> None:
        """Register a single Aliyun device in the device registry."""
        from pymammotion.data.model.device import create_device

        handle = DeviceHandle(
            device_id=device_name,
            device_name=device_name,
            initial_device=create_device(device_name, product_key),
            iot_id=iot_id,
            user_account=user_account,
            mqtt_transport=transport,
            readiness_checker=get_readiness_checker(device_name, product_key),
        )
        await self._device_registry.register(handle)
        await handle.start()
        if token_manager is not None:
            token_manager.subscribe_handle(handle)
        self._iot_id_to_device_id[iot_id] = device_name
        _logger.info("Aliyun device registered: %s (iot_id=%s)", device_name, iot_id)

    async def _register_mammotion_device(
        self,
        record: DeviceRecord,
        transport: MQTTTransport,
        user_account: int = 0,
        iot_id_override: str = "",
        token_manager: TokenManager | None = None,
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
        from pymammotion.data.model.device import create_device

        iot_id = iot_id_override or record.iot_id
        for topic in (
            f"/sys/{record.product_key}/{record.device_name}/thing/event/+/post",
            f"/sys/proto/{record.product_key}/{record.device_name}/thing/event/+/post",
            f"/sys/{record.product_key}/{record.device_name}/app/down/thing/status",
            # f"/sys/{record.product_key}/{record.device_name}/app/down/thing/properties",
        ):
            transport.add_topic(topic)
        transport.register_device(record.product_key, record.device_name, iot_id)

        handle = DeviceHandle(
            device_id=record.device_name,
            device_name=record.device_name,
            initial_device=create_device(record.device_name, record.product_key),
            iot_id=iot_id,
            user_account=user_account,
            mqtt_transport=transport,
            readiness_checker=get_readiness_checker(record.device_name, record.product_key),
        )
        await self._device_registry.register(handle)
        await handle.start()
        if token_manager is not None:
            token_manager.subscribe_handle(handle)
        self._iot_id_to_device_id[iot_id] = record.device_name
        _logger.info("Mammotion device registered: %s (iot_id=%s)", record.device_name, iot_id)

    async def _restore_aliyun(
        self,
        account: str,
        password: str,
        cached_data: dict[str, Any],
        acct_session: AccountSession,
        *,
        check_for_new_devices: bool,
    ) -> None:
        """Restore an Aliyun cloud session and register all known devices."""
        cloud_client = await CloudIOTGateway.from_cache(cached_data, account, password, ha_version=self._ha_version)
        if cloud_client is None:
            _logger.error("restore_credentials: CloudIOTGateway.from_cache returned None — falling back to full login")
            await self.login_and_initiate_cloud(account, password)
            return

        acct_session.mammotion_http = cloud_client.mammotion_http
        acct_session.cloud_client = cloud_client
        acct_session.user_account = self._extract_user_account(cloud_client.mammotion_http)
        acct_session.token_manager = TokenManager(account, cloud_client.mammotion_http, cloud_client)
        acct_session.token_manager.on_credentials_updated = self._on_credentials_updated
        transport = self._setup_aliyun_transport(cloud_client, acct_session)
        acct_session.aliyun_transport = transport

        # Fetch the authoritative iot_id map from Mammotion's device-list API so that
        # stale Aliyun binding iot_ids (e.g. for RTK base stations) are corrected.
        owned_iot_id_map: dict[str, str] = {}
        try:
            owned_resp = await cloud_client.mammotion_http.get_user_device_list()
            owned_iot_id_map = {d.device_name: d.iot_id for d in (owned_resp.data or []) if d.device_name and d.iot_id}
        except Exception:  # noqa: BLE001
            _logger.warning("restore_credentials: failed to fetch device iot_id map (Aliyun restore)", exc_info=True)

        known_ids: set[str] = set()
        ua = acct_session.user_account
        if cloud_client.devices_by_account_response is not None and cloud_client.devices_by_account_response.data:
            for device in cloud_client.devices_by_account_response.data.data:
                if device.device_name:
                    iot_id = owned_iot_id_map.get(device.device_name) or device.iot_id
                    await self._register_aliyun_device(
                        device.device_name,
                        iot_id,
                        transport,
                        ua,
                        device.product_key,
                        token_manager=acct_session.token_manager,
                    )
                    known_ids.add(device.device_name)

        if check_for_new_devices:
            try:
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
                                token_manager=acct_session.token_manager,
                            )
                            known_ids.add(device.device_name)
            except Exception:  # noqa: BLE001
                _logger.warning("restore_credentials: new-device discovery failed (Aliyun)", exc_info=True)

        if not known_ids:
            _logger.info("No Aliyun devices found — skipping Aliyun MQTT connection")
            acct_session.aliyun_transport = None
            return

        acct_session.device_ids.update(known_ids)
        await transport.connect()

    async def _restore_mammotion_mqtt(
        self,
        account: str,
        password: str,
        cached_data: dict[str, Any],
        session: ClientSession | None,
        acct_session: AccountSession,
        *,
        check_for_new_devices: bool,
    ) -> None:
        """Restore a Mammotion MQTT session and register all known devices."""
        from pymammotion.http.model.http import LoginResponseData, MQTTConnection
        from pymammotion.http.model.response_factory import response_factory

        mammotion_http = MammotionHTTP(account, password, session=session, ha_version=self._ha_version)
        acct_session.mammotion_http = mammotion_http

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
            acct_session.user_account = self._extract_user_account(mammotion_http)

        if mammotion_http.login_info is None:
            # No cached login data (missing mammotion_data or malformed) — do a fresh login so
            # decorated HTTP methods don't crash when they try to refresh a non-existent token.
            login_resp = await mammotion_http.login_v2(account, password)
            if login_resp.code != 0:
                raise LoginFailedError(account, login_resp.msg or "login failed during Mammotion MQTT restore")
            acct_session.user_account = self._extract_user_account(mammotion_http)

        mqtt_raw = cached_data["mammotion_mqtt"]

        records_raw = cached_data["mammotion_device_records"]
        cached_records: DeviceRecords = (
            DeviceRecords.from_dict(records_raw) if isinstance(records_raw, dict) else records_raw
        )
        mammotion_http.device_records = cached_records
        known_ids: set[str] = set()

        if mqtt_creds := MQTTConnection.from_dict(mqtt_raw) if isinstance(mqtt_raw, dict) else mqtt_raw:
            mammotion_http.mqtt_credentials = mqtt_creds
            if acct_session.token_manager is None:
                acct_session.token_manager = TokenManager(account, mammotion_http)
                acct_session.token_manager.on_credentials_updated = self._on_credentials_updated
            transport = self._setup_mammotion_transport(
                mqtt_creds, mammotion_http, acct_session, acct_session.token_manager
            )
            acct_session.mammotion_transport = transport

            # Fetch the authoritative iot_id map so stale cached iot_ids are corrected.
            owned_iot_id_map: dict[str, str] = {}
            try:
                owned_resp = await mammotion_http.get_user_device_list()
                owned_iot_id_map = {
                    d.device_name: d.iot_id for d in (owned_resp.data or []) if d.device_name and d.iot_id
                }
            except Exception:  # noqa: BLE001
                _logger.warning(
                    "restore_credentials: failed to fetch device iot_id map (Mammotion restore)", exc_info=True
                )

            ua = acct_session.user_account
            for record in cached_records.records:
                if record.device_name:
                    iot_id_override = owned_iot_id_map.get(record.device_name, "")
                    await self._register_mammotion_device(
                        record, transport, ua, iot_id_override, token_manager=acct_session.token_manager
                    )
                    known_ids.add(record.device_name)

            await transport.connect()

            if check_for_new_devices:
                try:
                    page_resp = await mammotion_http.get_user_device_page()
                    for record in (page_resp.data.records if page_resp.data else []) or []:
                        if record.device_name and record.device_name not in known_ids:
                            iot_id_override = owned_iot_id_map.get(record.device_name, "")
                            await self._register_mammotion_device(
                                record, transport, ua, iot_id_override, token_manager=acct_session.token_manager
                            )
                            known_ids.add(record.device_name)
                except Exception:  # noqa: BLE001
                    _logger.warning("restore_credentials: new-device discovery failed (Mammotion)", exc_info=True)

        acct_session.device_ids.update(known_ids)

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

    def _handle_for_iot_id(self, iot_id: str, caller: str) -> DeviceHandle | None:
        """Look up a DeviceHandle by iot_id, logging if not found."""
        device_id = self._iot_id_to_device_id.get(iot_id)
        if device_id is None:
            _logger.debug("%s: unknown iot_id=%s, dropping", caller, iot_id)
            return None
        return self._device_registry.get(device_id)

    async def _route_device_message(self, iot_id: str, payload: bytes) -> None:
        """Route an incoming cloud message to the correct DeviceHandle."""
        handle = self._handle_for_iot_id(iot_id, "_route_device_message")
        if handle is None:
            return
        await handle.on_raw_message(payload)

    async def _route_device_status(self, iot_id: str, msg: ThingStatusMessage) -> None:
        """Update a device handle's MQTT availability and status_properties from a thing/status message."""
        from pymammotion.data.mqtt.status import StatusType
        from pymammotion.transport.base import TransportAvailability

        handle = self._handle_for_iot_id(iot_id, "_route_device_status")
        if handle is None:
            return
        transport_type = (
            TransportType.CLOUD_MAMMOTION
            if handle.has_transport(TransportType.CLOUD_MAMMOTION)
            else TransportType.CLOUD_ALIYUN
        )
        online = msg.params.status.value is StatusType.CONNECTED
        avail = TransportAvailability.CONNECTED if online else TransportAvailability.DISCONNECTED
        handle.update_availability(transport_type, avail, mqtt_reported_offline=not online)
        await handle.on_status_message(msg)
        _logger.info(
            "Device '%s' is now %s (thing/status)",
            self._iot_id_to_device_id.get(iot_id),
            "online" if online else "offline",
        )

    async def _route_device_event(self, iot_id: str, event: ThingEventMessage) -> None:
        """Forward a non-protobuf thing.events message to the correct DeviceHandle."""
        handle = self._handle_for_iot_id(iot_id, "_route_device_event")
        if handle is None:
            return
        await handle.on_device_event(event)

    async def _route_device_properties(self, iot_id: str, properties: ThingPropertiesMessage) -> None:
        """Forward a thing.properties message to the correct DeviceHandle."""
        handle = self._handle_for_iot_id(iot_id, "_route_device_properties")
        if handle is None:
            return
        await handle.on_device_properties(properties)

    # ------------------------------------------------------------------
    # Map sync
    # ------------------------------------------------------------------

    async def start_map_sync(self, device_name: str) -> None:
        """Enqueue a MapFetchSaga to fetch the complete device map.

        The saga is enqueued on the device's command queue and runs exclusively
        (no other commands execute while the map fetch is in progress).
        Map data is automatically applied to device state as messages arrive.
        """

        if handle := self._device_registry.get_by_name(device_name):
            commands = handle.commands
            transport = handle.active_transport()
            _iot_id = handle.iot_id
            saga = MapFetchSaga(
                device_id=handle.device_id,
                device_name=handle.device_name,
                is_luba1=DeviceType.is_luba1(device_name),
                command_builder=commands,
                send_command=lambda cmd: transport.send(cmd, iot_id=_iot_id),
                get_map=lambda: cast(MowerDevice, handle.snapshot.raw).map,
            )

            async def _on_map_complete() -> None:
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
                if device.location.RTK.latitude != 0:
                    device.map.generate_geojson(device.location.RTK, device.location.dock)
                # Notify map_updated subscribers after a successful saga, matching
                # ``handle.subscribe_map_updated`` 's docstring promise.  Without
                # this emit, downstream subscribers (e.g. Mammotion-HA's area-switch
                # builder) only fire on ``toapp_all_hash_name`` messages, which
                # some Mammotion cloud sessions never deliver — leaving zone
                # entities permanently missing even though the saga successfully
                # populated ``device.map.area``.
                await handle._map_updated_bus.emit(None)

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
        from pymammotion.messaging.plan_saga import PlanFetchSaga

        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("start_plan_sync: device '%s' not registered", device_name)
            return
        commands = handle.commands
        _iot_id = handle.iot_id

        async def _send(cmd: bytes) -> None:
            await handle.active_transport().send(cmd, iot_id=_iot_id)

        saga = PlanFetchSaga(command_builder=commands, send_command=_send)
        await handle.enqueue_saga(saga)

    async def check_and_get_mow_path(self, device_name: str) -> None:
        if handle := self._device_registry.get_by_name(device_name):
            device = cast(MowerDevice, handle.snapshot.raw)
            work = device.report_data.work
            # path_hash in (0, 1) means "no job" / "job ended".
            has_active_job = work.ub_path_hash != 0 or work.path_hash not in (0, 1)
            if not has_active_job:
                return
            if device.map.current_mow_path:
                # Cache exists — validate it against the current active segment hash.
                # ub_path_hash appears directly as path_packets[0].path_hash inside the
                # cover-path frames (confirmed via APK HashDataManager and device data).
                # If ub_path_hash is 0 we can't validate a specific segment, so keep.
                if work.ub_path_hash == 0 or device.map.has_mow_path_for_hash(work.ub_path_hash):
                    return  # Cache is valid for the current job segment
                # Cache exists but doesn't contain the current segment — stale.
                # Clear it so the saga fetches fresh data below.
                device.map.invalidate_mow_path(0)
            if handle.queue.is_saga_active:
                return
            _logger.debug(
                "Device %s path_hash=%d ub_path_hash=%d — auto-fetching cover path",
                device_name,
                work.path_hash,
                work.ub_path_hash,
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
        from pymammotion.messaging.mow_path_saga import MowPathSaga

        if handle := self._device_registry.get_by_name(device_name):
            commands = handle.commands
            _iot_id = handle.iot_id

            async def _send(cmd: bytes) -> None:
                await handle.active_transport().send(cmd, iot_id=_iot_id)

            saga = MowPathSaga(
                command_builder=commands,
                send_command=_send,
                get_map=lambda: handle.snapshot.raw.map,
                zone_hashs=zone_hashs,
                route_info=route_info,
                skip_planning=skip_planning,
                device_name=device_name,
            )

            async def _on_mow_path_complete() -> None:
                device = self.get_device_by_name(device_name)
                if device is not None and device.location.RTK.latitude != 0:
                    device.map.generate_mowing_geojson(device.location.RTK)

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
        from pymammotion.data.model.hash_list import PathType
        from pymammotion.messaging.common_data_saga import CommonDataSaga

        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("get_dynamics_line: device '%s' not registered", device_name)
            return

        _iot_id = handle.iot_id

        async def _send(cmd: bytes) -> None:
            await handle.active_transport().send(cmd, iot_id=_iot_id)

        saga = CommonDataSaga(
            command_builder=handle.commands,
            send_command=_send,
            action=8,
            type=PathType.DYNAMICS_LINE,
        )

        async def _on_complete() -> None:
            device = self.get_device_by_name(device_name)
            if device is not None and saga.result:
                device.map.update_dynamics_line(saga.result)
                device.map.apply_dynamics_line_geojson(device.location.RTK)

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
        from pymammotion.messaging.edge_saga import EdgeMappingSaga

        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("start_edge_mapping: device '%s' not registered", device_name)
            return
        commands = handle.commands
        _iot_id = handle.iot_id

        async def _send(cmd: bytes) -> None:
            await handle.active_transport().send(cmd, iot_id=_iot_id)

        saga = EdgeMappingSaga(command_builder=commands, send_command=_send, skip_start=skip_start)
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
        if enabled:
            for t_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION, TransportType.BLE):
                await handle.connect_transport(t_type)
        else:
            for t_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION, TransportType.BLE):
                await handle.disconnect_transport(t_type)

    # ------------------------------------------------------------------
    # BLE connection
    # ------------------------------------------------------------------

    async def connect_ble(self, device_name: str) -> None:
        """Connect the BLE transport for a registered device.

        Works for both BLE-only devices and hybrid devices that have a BLE
        transport attached.  No-op when the device is unknown or the transport
        is already connected — matches the rest of the public API which
        warns/returns rather than raises on unknown devices.
        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("connect_ble: device %r not registered", device_name)
            return
        transport = handle.get_transport(TransportType.BLE)
        if transport is not None and not transport.is_connected:
            await transport.connect()

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
            return session.cloud_client.devices_by_account_response.data.data  # type: ignore[no-any-return]
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
    ) -> None:
        """Attach (or replace) a BLE transport on an already-registered device.

        Args:
            device_name: Registered device name.
            ble_device:  The bleak ``BLEDevice`` to use for the BLE connection.

        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("add_ble_to_device: device '%s' not registered", device_name)
            return
        if handle.has_transport(TransportType.BLE) and (bleTransport := handle.get_transport(TransportType.BLE)):
            _logger.debug("add_ble_to_device: device '%s' already has BLE transport", device_name)
            cast(BLETransport, bleTransport).set_ble_device(ble_device)
            return
        transport = BLETransport(BLETransportConfig(device_id=device_name))
        transport.set_ble_device(ble_device)
        await handle.add_transport(transport)

    async def get_stream_subscription(self, device_name: str, iot_id: str) -> Any:
        """Return a stream subscription response for the named device.

        For old-firmware devices (those whose device state lacks ``fpv_info``,
        i.e. ``getNewversionfpv() == false`` in the APK), also sends
        ``device_agora_join_channel_with_position(1)`` to the device to start
        the video stream — mirroring the APK's ``getVideoResp`` logic.
        New-firmware devices start streaming without a device-side command.
        """
        from pymammotion.utility.device_type import DeviceType

        http = self.mammotion_http
        if http is None:
            return None
        is_yuka = DeviceType.is_yuka(device_name)
        subscription = await http.get_stream_subscription(iot_id, is_yuka)

        if handle := self._device_registry.get_by_name(device_name):
            try:
                new_fpv = handle.snapshot.raw.report_data.dev.fpv_info is not None
            except AttributeError:
                new_fpv = False
            if not new_fpv:
                await self._send_agora_join_over_mqtt(handle)

        return subscription

    async def refresh_stream_subscription(self, device_name: str, iot_id: str) -> Any:
        """Renew the Agora stream token and rejoin the device's channel.

        Fetches a fresh stream subscription token then sends a join-channel
        command to the device so it streams to the new Agora session.  Mirrors
        the APK's refresh path (STUN-timeout, ``on_p2p_lost``) which re-runs
        the same flow as the initial join without a preceding leave command.
        """
        from pymammotion.utility.device_type import DeviceType

        http = self.mammotion_http
        if http is None:
            return None
        is_yuka = DeviceType.is_yuka(device_name)
        subscription = await http.get_stream_subscription(iot_id, is_yuka)

        if handle := self._device_registry.get_by_name(device_name):
            try:
                new_fpv = handle.snapshot.raw.report_data.dev.fpv_info is not None
            except AttributeError:
                new_fpv = False
            if not new_fpv:
                await self._send_agora_join_over_mqtt(handle)

        return subscription

    async def _send_agora_join_over_mqtt(self, handle: DeviceHandle) -> None:
        """Fire the Agora join-channel command over MQTT only, without waiting for an ack."""
        command_bytes = handle.commands.device_agora_join_channel_with_position(enter_state=1)
        for transport_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
            mqtt_transport = handle.get_transport(transport_type)
            if mqtt_transport is not None and mqtt_transport.is_connected:
                await handle._send_marked(mqtt_transport, command_bytes)
                break

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def send_command_with_args(
        self,
        name: str,
        key: str,
        *,
        prefer_ble: bool = False,
        _record_cmd: bool = True,
        **kwargs: Any,
    ) -> None:
        """Send a named command to the device via the command queue.

        Builds a :class:`MammotionCommand` for the device, calls ``key(**kwargs)``
        to get the protobuf bytes, then enqueues the send via the device's command
        queue so it is properly ordered with respect to running sagas.

        Args:
            name:        Registered device name.
            key:         Method name on :class:`MammotionCommand`.
            prefer_ble:  When True, prefer BLE over MQTT for this call only
                         (useful for movement commands that need low latency).
                         Does not mutate the handle's transport preference.
            _record_cmd: Internal flag — set False for watchdog-initiated sends
                         so they do not stamp _last_user_command_ts and
                         inadvertently lock the watchdog into the 60 s window.

        Raises:
            KeyError:       if *name* is not a registered device.
            AttributeError: if *key* is not a valid command.

        """
        handle = self._device_registry.get_by_name(name)
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
        _session = self._get_session_for_device(name)

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
            if not handle.has_usable_transport:
                _logger.debug(
                    "send_command_with_args '%s': no usable transport — skipping '%s'",
                    name,
                    key,
                )
                return
            await self._send_with_auth_retry(
                lambda: handle.send_raw(command_bytes, prefer_ble=_prefer_ble),
                _session,
            )

        await handle.queue.enqueue(_do_send, priority=Priority.NORMAL)

    async def send_command_and_wait(
        self,
        name: str,
        key: str,
        expected_field: str,
        *,
        send_timeout: float = 5.0,
        prefer_ble: bool = True,
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
            :param prefer_ble:

        """
        handle = self._device_registry.get_by_name(name)
        if handle is None:
            msg = f"Device '{name}' not registered"
            raise KeyError(msg)
        handle.record_user_command()
        commands = handle.commands
        command_bytes: bytes = getattr(commands, key)(**kwargs)
        _session = self._get_session_for_device(name)

        async def _send() -> None:
            await self._send_with_auth_retry(
                lambda: handle.send_raw(payload=command_bytes, prefer_ble=prefer_ble),
                _session,
            )

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
