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
from typing import TYPE_CHECKING, Any, cast

import betterproto2

from pymammotion.account.registry import BLE_ONLY_ACCOUNT, AccountRegistry, AccountSession
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.auth.token_manager import TokenManager
from pymammotion.bluetooth.manager import BLETransportManager
from pymammotion.data.model.device import MowerDevice, RTKBaseStationDevice
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.device.readiness import get_readiness_checker
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import DeviceRecord, DeviceRecords, Response
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
from pymammotion.utility.constant import MOWING_ACTIVE_MODES
from pymammotion.utility.device_type import DeviceType

# Rapid report-stream subscription — see docs/report_channels.md for the full
# channel reference and rationale.
_RAPID_STREAM_ACTIVE_STATES: frozenset[int] = MOWING_ACTIVE_MODES
_RAPID_STREAM_CHANNELS: list[RptInfoType] = [
    RptInfoType.RIT_CONNECT,
    RptInfoType.RIT_WORK,
    RptInfoType.RIT_DEV_LOCAL,
    RptInfoType.RIT_DEV_STA,
    RptInfoType.RIT_VISION_POINT,
]
_RAPID_STREAM_PERIOD_MS: int = 1000  # 1 Hz, matches APK requestConnectingChannels

#: Channels for the continuous subscription (matches HA-Luba async_request_iot_sync_continuous).
_CONTINUOUS_STREAM_CHANNELS: list[RptInfoType] = [
    RptInfoType.RIT_DEV_STA,
    RptInfoType.RIT_DEV_LOCAL,
    RptInfoType.RIT_WORK,
    RptInfoType.RIT_MAINTAIN,
    RptInfoType.RIT_BASESTATION_INFO,
    RptInfoType.RIT_VIO,
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
#: Watchdog window when the mower is actively mowing / returning, or when the
#: active transport is BLE.  If no ``toapp_report_data`` arrives within this
#: many seconds, refire the continuous subscription (unless a saga is active).
_REPORT_DATA_SILENCE_SECONDS: float = 20.0
#: Extended watchdog window when the mower is docked/paused/idle AND the
#: active transport is MQTT.  Keeps cloud-path chatter low while docked.
_REPORT_DATA_IDLE_SILENCE_SECONDS: float = 600.0  # 10 minutes

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from aiohttp import ClientSession
    from bleak import BLEDevice

    from pymammotion.data.model import GenerateRouteInformation
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
        #: Per-device cleanup callbacks (cancels watchdog task + broker subscription).
        self._watchdog_cleanups: dict[str, Callable[[], None]] = {}
        self._ha_version: str | None = ha_version

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
    # Device state watchers
    # ------------------------------------------------------------------

    def setup_device_watchers(self, device_name: str) -> Subscription | None:
        """Register auto-fetch / auto-subscribe watchers for *device_name*.

        Installs three field watchers on the device handle:

        * ``(ub_path_hash, path_hash)`` — fires ``MowPathSaga`` (fetch-only)
          when either hash transitions to an active value while no cover path
          is cached.
        * ``(path_pos_x, path_pos_y)`` — rebuilds ``generated_mow_progress_geojson``
          as the mower progresses along the path.
        * ``sys_status`` — starts a 4 Hz ``report_info_cfg`` subscription on
          transition into WORKING/RETURNING and sends ``RPT_STOP`` on any
          other transition.

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
            if not has_active_job or device.map.current_mow_path:
                return
            if handle.queue.is_saga_active:
                return
            _logger.debug(
                "Device %s path_hash=%d ub_path_hash=%d — auto-fetching cover path",
                device_name,
                work.path_hash,
                work.ub_path_hash,
            )
            try:
                await self.start_mow_path_saga(device_name, zone_hashs=[], skip_planning=True)
            except Exception:  # noqa: BLE001
                _logger.warning("Auto-trigger MowPathSaga failed for %s", device_name, exc_info=True)

        async def _on_mow_progress_changed(_pos: tuple[int, int]) -> None:
            device = cast(MowerDevice, handle.snapshot.raw)
            if device.map.current_mow_path:
                work = device.report_data.work
                device.map.apply_mow_progress_geojson(
                    device.location.RTK,
                    work.now_index,
                    work.ub_path_hash,
                    work.path_pos_x,
                    work.path_pos_y,
                )
            else:
                await _on_path_hashes_changed((0, 0))

        async def _on_sys_status_changed(sys_status: int) -> None:
            try:
                if sys_status in _RAPID_STREAM_ACTIVE_STATES:
                    await self.send_command_with_args(
                        device_name,
                        "request_iot_sys",
                        rpt_act=RptAct.RPT_START,
                        rpt_info_type=_RAPID_STREAM_CHANNELS,
                        timeout=10000,
                        period=_RAPID_STREAM_PERIOD_MS,
                        no_change_period=4000,
                        count=0,
                    )
                    _logger.debug(
                        "Device %s sys_status=%d — started rapid report stream (%d Hz)",
                        device_name,
                        sys_status,
                        1000 // _RAPID_STREAM_PERIOD_MS,
                    )
                else:
                    await self.send_command_with_args(
                        device_name,
                        "request_iot_sys",
                        rpt_act=RptAct.RPT_STOP,
                        rpt_info_type=_RAPID_STREAM_CHANNELS,
                        timeout=10000,
                        period=_RAPID_STREAM_PERIOD_MS,
                        no_change_period=4000,
                        count=0,
                    )
                    _logger.debug(
                        "Device %s sys_status=%d — stopped rapid report stream",
                        device_name,
                        sys_status,
                    )
            except Exception:  # noqa: BLE001
                _logger.warning(
                    "Failed to toggle rapid report stream for %s (sys_status=%d)",
                    device_name,
                    sys_status,
                    exc_info=True,
                )

        sub = handle.watch_field(
            lambda s: (s.raw.report_data.work.ub_path_hash, s.raw.report_data.work.path_hash),
            _on_path_hashes_changed,
        )
        progress_sub = handle.watch_field(
            lambda s: (s.raw.report_data.work.path_pos_x, s.raw.report_data.work.path_pos_y),
            _on_mow_progress_changed,
        )
        sys_status_sub = handle.watch_field(
            lambda s: s.raw.report_data.dev.sys_status,
            _on_sys_status_changed,
        )
        self._watcher_subscriptions[device_name] = [sub, progress_sub, sys_status_sub]
        self._install_report_data_watchdog(device_name)
        self._install_saga_subscription_hooks(device_name)
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
            rpt_act=RptAct.RPT_STOP,
            rpt_info_type=_CONTINUOUS_STREAM_CHANNELS,
            count=1,
        )

    # ------------------------------------------------------------------
    # Report-data watchdog: refire continuous sub on 20 s of silence
    # ------------------------------------------------------------------

    def _install_report_data_watchdog(self, device_name: str) -> None:
        """Install a watchdog that refires the continuous sub after 20 s of silence.

        Subscribes to unsolicited ``toapp_report_data`` messages; each arrival
        resets the timer.  If no data arrives within ``_REPORT_DATA_SILENCE_SECONDS``
        the continuous subscription is resent — unless a saga is active, in
        which case we defer but keep the timer alive so detection resumes
        automatically once the saga finishes.

        Stores a cleanup callback in ``self._watchdog_cleanups[device_name]``
        so ``teardown_device_watchers`` can cancel both the asyncio task and
        the broker subscription.  Also exposes ``_arm()`` on the state dict
        so the saga-end hook can prime a fresh window after restarting the
        subscription.
        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            return

        state: dict[str, Any] = {"task": None, "arm": None}

        def _current_silence_window() -> float:
            """Pick the silence window based on active transport + sys_status.

            BLE always uses the short 20 s window.  MQTT uses the long 10 min
            window when the mower is docked/paused/idle.
            """
            try:
                transport = handle.active_transport()
            except NoTransportAvailableError:
                return _REPORT_DATA_SILENCE_SECONDS
            if transport.transport_type == TransportType.BLE:
                return _REPORT_DATA_SILENCE_SECONDS
            raw = handle.snapshot.raw
            report_data = getattr(raw, "report_data", None)
            sys_status = getattr(getattr(report_data, "dev", None), "sys_status", 0) if report_data else 0
            if sys_status in _RAPID_STREAM_ACTIVE_STATES:
                return _REPORT_DATA_SILENCE_SECONDS
            return _REPORT_DATA_IDLE_SILENCE_SECONDS

        async def _on_timeout() -> None:
            window = _current_silence_window()
            try:
                await asyncio.sleep(window)
            except asyncio.CancelledError:
                return
            if handle.queue.is_saga_active:
                _logger.debug(
                    "report_data watchdog [%s]: silence but saga active — deferring",
                    device_name,
                )
                # Keep the timer alive so detection resumes once the saga finishes.
                _arm()
                return
            _logger.debug(
                "report_data watchdog [%s]: %ds silence — refiring continuous subscription",
                device_name,
                int(window),
            )
            try:
                await self.request_iot_sync_continuous(device_name)
            except Exception:  # noqa: BLE001
                _logger.warning("report_data watchdog [%s]: refire failed", device_name, exc_info=True)
            _arm()

        def _arm() -> None:
            existing = state["task"]
            if existing is not None and not existing.done():
                existing.cancel()
            state["task"] = asyncio.create_task(_on_timeout())

        async def _on_report_data(msg: Any) -> None:
            sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
            if sub_name != "sys":
                return
            inner_name, _ = betterproto2.which_one_of(sub_val, "SubSysMsg")
            if inner_name == "toapp_report_data":
                _arm()

        broker_sub = handle.broker.subscribe_unsolicited(_on_report_data)
        state["arm"] = _arm
        _arm()  # prime the first window

        def _cleanup() -> None:
            task = state["task"]
            if task is not None and not task.done():
                task.cancel()
            state["task"] = None
            broker_sub.cancel()

        # Attach `arm` on the cleanup callable so saga-end can re-arm the timer
        # without needing a second lookup dict.
        _cleanup._arm = _arm  # type: ignore[attr-defined]
        self._watchdog_cleanups[device_name] = _cleanup

    def _install_saga_subscription_hooks(self, device_name: str) -> None:
        """Wire up DeviceCommandQueue so sagas pause/resume the continuous stream."""
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            return

        async def _on_saga_start() -> None:
            try:
                await self.request_iot_sync_continuous_stop(device_name)
            except Exception:  # noqa: BLE001
                _logger.debug("saga_start stop-stream failed [%s]", device_name, exc_info=True)

        async def _on_saga_end() -> None:
            try:
                await self.request_iot_sync_continuous(device_name)
            except Exception:  # noqa: BLE001
                _logger.debug("saga_end start-stream failed [%s]", device_name, exc_info=True)
            # Re-arm the watchdog so the fresh subscription is monitored again.
            cleanup = self._watchdog_cleanups.get(device_name)
            arm = getattr(cleanup, "_arm", None) if cleanup is not None else None
            if arm is not None:
                arm()

        handle.queue.on_saga_start = _on_saga_start
        handle.queue.on_saga_end = _on_saga_end

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
        """Cancel state-change subscriptions and the report-data watchdog for *device_name*."""
        for sub in self._watcher_subscriptions.pop(device_name, []):
            sub.cancel()
        cleanup = self._watchdog_cleanups.pop(device_name, None)
        if cleanup is not None:
            cleanup()
        # Drop the saga hooks so callbacks don't fire after teardown.
        handle = self._device_registry.get_by_name(device_name)
        if handle is not None:
            handle.queue.on_saga_start = None
            handle.queue.on_saga_end = None

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
            except:
                pass
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
                        import dataclasses

                        updated = dataclasses.replace(current, lora_version=rtk.lora)
                        snapshot, _ = handle.state_machine.apply(updated, handle.availability)
                        if not handle._stopping:  # noqa: SLF001
                            await handle._state_changed_bus.emit(snapshot)  # noqa: SLF001
                    break
        except Exception:  # noqa: BLE001
            _logger.warning("fetch_rtk_lora_info: failed to fetch RTK devices for %s", device_name, exc_info=True)

    # ------------------------------------------------------------------
    # BLE
    # ------------------------------------------------------------------

    async def add_ble_device(self, device_id: str, ble_device: object) -> None:
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
            _logger.info("BLE transport added to existing handle for device %s", device_id)

    async def update_ble_device(self, device_id: str, ble_device: object) -> None:
        """Update the BLE advertisement for a known device.

        Also updates the live BLETransport (if already wired to the handle) so
        bleak_retry_connector has the freshest advertisement on the next connect.
        """
        self._ble_manager.update_external_ble_client(device_id, ble_device)
        handle = self._device_registry.get(device_id)
        if handle is not None:
            from pymammotion.transport.ble import BLETransport as _BLETransport

            ble = handle._transports.get(TransportType.BLE)  # noqa: SLF001
            if isinstance(ble, _BLETransport):
                ble.set_ble_device(ble_device)

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
            al_transport = self._setup_aliyun_transport(cloud_client, acct_session)
            acct_session.aliyun_transport = al_transport
            ua = acct_session.user_account
            for device in cloud_client.devices_by_account_response.data.data:
                if device.device_name:
                    iot_id = owned_iot_id_map.get(device.device_name) or device.iot_id
                    await self._register_aliyun_device(device.device_name, iot_id, al_transport, ua, device.product_key)
                    acct_session.device_ids.add(device.device_name)
            await al_transport.connect()

        if mammotion_records:
            await mammotion_http.get_mqtt_credentials()
            if mammotion_http.mqtt_credentials is None:
                _logger.error("Could not obtain Mammotion MQTT credentials — skipping post-2025 devices")
            else:
                if acct_session.token_manager is None:
                    acct_session.token_manager = TokenManager(account, mammotion_http)
                transport = self._setup_mammotion_transport(
                    mammotion_http.mqtt_credentials, mammotion_http, acct_session, acct_session.token_manager
                )
                acct_session.mammotion_transport = transport
                ua = acct_session.user_account
                for record in mammotion_records:
                    if record.device_name:
                        iot_id_override = owned_iot_id_map.get(record.device_name, "")
                        await self._register_mammotion_device(record, transport, ua, iot_id_override)
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
            """Refresh Aliyun IoT credentials and update the bind token on the transport."""
            if token_manager is None:
                return False
            try:
                await token_manager.refresh_aliyun_credentials()
                creds = await token_manager.get_aliyun_credentials()
                transport.update_iot_token(creds.iot_token)
                _logger.info("Aliyun IoT token refreshed after bind token expiry")
                return True
            except ReLoginRequiredError:
                _logger.warning("Aliyun token refresh requires full re-login — attempting")
                try:
                    await self._full_relogin(acct_session)
                    creds = await token_manager.get_aliyun_credentials()
                    transport.update_iot_token(creds.iot_token)
                    _logger.info("Aliyun IoT token refreshed after full re-login")
                    return True
                except Exception:
                    _logger.exception("Full re-login failed after Aliyun bind token expiry")
                    return False

        transport.on_auth_failure = _on_aliyun_auth_failure
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
                # Update the transport config with the fresh JWT and reconnect.
                new_jwt = await _refresh_jwt()
                transport.update_jwt(new_jwt)
                await transport.connect()
                _logger.info("MQTT transport reconnected after full re-login")
            except Exception:
                _logger.exception("Full re-login failed for MQTT transport")

        transport.on_fatal_auth_error = _on_fatal_auth
        return transport

    async def _register_aliyun_device(
        self,
        device_name: str,
        iot_id: str,
        transport: AliyunMQTTTransport,
        user_account: int = 0,
        product_key: str = "",
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
        self._enable_staleness_watcher(handle, device_name)
        self._iot_id_to_device_id[iot_id] = device_name
        _logger.info("Aliyun device registered: %s (iot_id=%s)", device_name, iot_id)

    async def _register_mammotion_device(
        self,
        record: DeviceRecord,
        transport: MQTTTransport,
        user_account: int = 0,
        iot_id_override: str = "",
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
        self._enable_staleness_watcher(handle, record.device_name)
        self._iot_id_to_device_id[iot_id] = record.device_name
        _logger.info("Mammotion device registered: %s (iot_id=%s)", record.device_name, iot_id)

    def _enable_staleness_watcher(self, handle: DeviceHandle, device_name: str) -> None:
        """Enable auto-refetch of stale maps and plans for a mower device.

        RTK base stations and pool cleaners have no map or plan data, so the
        staleness watcher is a no-op for them.
        """
        from pymammotion.utility.device_type import DeviceType

        if DeviceType.is_rtk(device_name) or DeviceType.is_swimming_pool(device_name):
            return
        handle.enable_staleness_watcher(
            on_maps_stale=lambda: self.start_map_sync(device_name),
            on_plans_stale=lambda: self.start_plan_sync(device_name),
        )

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
                    await self._register_aliyun_device(device.device_name, iot_id, transport, ua, device.product_key)
                    known_ids.add(device.device_name)

        if check_for_new_devices:
            try:
                fresh = await cloud_client.list_binding_by_account()
                if fresh.data:
                    for device in fresh.data.data:
                        if device.device_name and device.device_name not in known_ids:
                            iot_id = owned_iot_id_map.get(device.device_name) or device.iot_id
                            await self._register_aliyun_device(
                                device.device_name, iot_id, transport, ua, device.product_key
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
                    await self._register_mammotion_device(record, transport, ua, iot_id_override)
                    known_ids.add(record.device_name)

            await transport.connect()

            if check_for_new_devices:
                try:
                    page_resp = await mammotion_http.get_user_device_page()
                    for record in (page_resp.data.records if page_resp.data else []) or []:
                        if record.device_name and record.device_name not in known_ids:
                            iot_id_override = owned_iot_id_map.get(record.device_name, "")
                            await self._register_mammotion_device(record, transport, ua, iot_id_override)
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

        handle = self._device_registry.get_by_name(device_name)
        if handle is not None:
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
                if device.location.RTK.latitude != 0:
                    device.map.generate_geojson(device.location.RTK, device.location.dock)

            await handle.enqueue_saga(saga, on_complete=_on_map_complete)
        else:
            _logger.warning("start_map_sync: device '%s' not registered", device_name)
            return

    async def start_area_name_sync(self, device_name: str) -> None:
        """Fetch area names for *device_name* without re-fetching the full map.

        Enqueues a MapFetchSaga in area-names-only mode.  Use this when the
        map hash is still valid (bol_hash matches) but area names are missing.
        """
        from pymammotion.messaging.map_saga import MapFetchSaga
        from pymammotion.utility.device_type import DeviceType

        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            _logger.warning("start_area_name_sync: device '%s' not registered", device_name)
            return
        if DeviceType.is_luba1(device_name):
            return  # Luba 1 has no area names
        commands = handle.commands
        transport = handle.active_transport()
        _iot_id = handle.iot_id
        device = self.get_device_by_name(device_name)
        existing_area_hashes = list(device.map.area.keys()) if device is not None else []
        saga = MapFetchSaga(
            device_id=handle.device_id,
            device_name=handle.device_name,
            is_luba1=False,
            command_builder=commands,
            send_command=lambda cmd: transport.send(cmd, iot_id=_iot_id),
            get_map=lambda: handle.snapshot.raw.map,
            area_names_only=True,
            existing_area_hashes=existing_area_hashes,
        )
        await handle.enqueue_saga(saga)

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

    async def refresh_stream_subscription(self, device_name: str, iot_id: str) -> Any:
        """Renew the Agora stream token and cycle the device's channel membership.

        Fetches a fresh stream subscription token, sends a leave-channel command
        to the device, then immediately sends a rejoin-channel command so the
        device streams to the new Agora session.  Returns the new subscription
        response so the caller can reinitialise the Agora engine.

        Handles STUN-timeout and ``on_p2p_lost`` events where the underlying
        peer-to-peer connection has silently dropped and the stream token must
        be refreshed before the Agora engine can reconnect.
        """
        subscription = await self.get_stream_subscription(device_name, iot_id)

        handle = self._device_registry.get_by_name(device_name)
        if handle is not None:
            commands = handle.commands
            await handle.send_command(commands.device_agora_join_channel_with_position(0), "set_video_ack")
            await handle.send_command(commands.device_agora_join_channel_with_position(1), "set_video_ack")

        return subscription

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

        _no_transport_max = 3
        _no_transport_delay = 2.0

        async def _do_send() -> None:
            # Gate: cloud has told us this device is offline — don't send unless BLE is available.
            if handle.availability.mqtt_reported_offline and not handle.has_transport(TransportType.BLE):
                _logger.debug(
                    "send_command_with_args '%s': device offline (cloud-reported) — skipping '%s'",
                    name,
                    key,
                )
                return

            for _attempt in range(1, _no_transport_max + 1):
                try:
                    await self._send_with_auth_retry(
                        lambda: handle.send_raw(command_bytes, prefer_ble=_prefer_ble),
                        _session,
                    )
                except NoTransportAvailableError:
                    if _attempt >= _no_transport_max:
                        _logger.warning(
                            "send_command_with_args '%s': no transport after %d attempts — dropping",
                            name,
                            _attempt,
                        )
                        return
                    _logger.debug(
                        "send_command_with_args '%s': no transport (attempt %d/%d) — retrying in %.1fs",
                        name,
                        _attempt,
                        _no_transport_max,
                        _no_transport_delay,
                    )
                    await asyncio.sleep(_no_transport_delay)
                else:
                    return

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
        commands = handle.commands
        command_bytes: bytes = getattr(commands, key)(**kwargs)
        _session = self._get_session_for_device(name)

        async def _send() -> None:
            await self._send_with_auth_retry(
                lambda: handle.send_raw(payload=command_bytes),
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
