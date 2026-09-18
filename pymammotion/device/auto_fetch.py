"""State-change watchers that auto-trigger the fetch sagas.

Split out of ``MammotionClient``: this is a rule set — "when this field on the
device changes, go fetch that" — and it needs only the device registry plus the
three saga entry points, so it is a collaborator rather than a mixin.

It owns nothing about *cadence*.  How often the device is asked for fresh state
lives in ``DeviceHandle`` and its poll loops; these watchers only react to state
that has already arrived.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.generate_geojson import apply_mow_progress_geojson
from pymammotion.data.model.generate_route_information import GenerateRouteInformation
from pymammotion.utility.constant.device_enums import WorkMode
from pymammotion.utility.constant.poll_policy import MOWING_ACTIVE_MODES
from pymammotion.utility.device_type import DeviceType

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.device.handle import DeviceHandle, DeviceRegistry
    from pymammotion.transport.base import Subscription

_logger = logging.getLogger(__name__)


def _should_fetch_mow_path(device: MowerDevice, handle: DeviceHandle, path_hash: int) -> bool:
    """Return True if a MowPathSaga should be triggered.

    Mirrors the APK's HashDataManager.updateTotalHash() gate logic:
    - Not in firmware-update mode (DeviceWorkState.MODE_UPDATING == 16).
    - No saga already running (!isUpdateMap / is_saga_active).
    - path_hash (work field 2 = work.getPathHash()) is non-zero.
    - Device's current bol_hash matches our computed_bol_hash (j == getDBCmHash())
      — prevents fetching cover paths against a stale map.
    """
    if device.report_data.dev.sys_status == WorkMode.MODE_UPDATING:
        return False
    if handle.queue.is_saga_active:
        return False
    if path_hash == 0:
        return False
    current_bol_hash = device.report_data.locations[0].bol_hash if device.report_data.locations else 0
    return current_bol_hash != 0 and current_bol_hash == device.map.computed_bol_hash


class AutoFetchWatchers:
    """Wires ``DeviceHandle.watch_field`` subscriptions to the fetch sagas."""

    def __init__(
        self,
        registry: DeviceRegistry,
        *,
        start_map_sync: Callable[..., Awaitable[Any]],
        start_plan_sync: Callable[..., Awaitable[Any]],
        start_mow_path_saga: Callable[..., Awaitable[Any]],
    ) -> None:
        self._device_registry = registry
        self.start_map_sync = start_map_sync
        self.start_plan_sync = start_plan_sync
        self.start_mow_path_saga = start_mow_path_saga
        #: device_name -> the subscriptions set up for it, so teardown is exact.
        self._watcher_subscriptions: dict[str, list[Subscription]] = {}

    def setup_device_watchers(self, device_name: str) -> Subscription | None:
        """Register auto-fetch / auto-subscribe watchers for *device_name*.

        Installs field watchers on the device handle:

        * ``path_hash`` (work field 2) — fires ``MowPathSaga`` (fetch-only)
          when the hash transitions to a non-zero value, our map is current
          (computed_bol_hash == device bol_hash), and no matching cover path
          is cached.
        * ``(path_pos_x, path_pos_y)`` — rebuilds ``generated_mow_progress_geojson``
          as the mower progresses along the path.
        * ``bol_hash`` (from ``report_data.locations[0].bol_hash``) — fires
          ``MapFetchSaga`` when the device reports a different map hash,
          replacing the old ``MapStalenessWatcher`` for the maps case.
        * ``init_cfg_hash`` (from ``report_data.work.init_cfg_hash``) — fires
          ``PlanFetchSaga`` when the device reports a changed plan config hash,
          mirroring the APK's ``initCfgHash``-driven ``allpowerfullRW(5,1,1)``
          trigger in ``DeviceInitializationManager``.

        Cadence/streaming for ``sys_status`` lives in
        :class:`~pymammotion.device.handle.DeviceHandle` (BLE polling loop +
        MQTT cadence table) — not here.

        Call ``teardown_device_watchers`` to cancel.  Returns the first
        registered Subscription, or None if the device isn't registered yet.
        """
        handle = self._device_registry.get_by_name(device_name)
        if handle is None:
            return None

        async def _on_path_hashes_changed(path_hash: int) -> None:
            device = cast(MowerDevice, handle.snapshot.raw)
            if device.map.current_mow_path and device.map.has_mow_path_for_hash(path_hash):
                return  # Cache is valid for the current route
            if device.map.current_mow_path:
                # Cache exists but for a different route — clear it before fetching.
                device.map.invalidate_mow_path(0)
            if not _should_fetch_mow_path(device, handle, path_hash):
                return
            _logger.debug(
                "Device %s path_hash=%d — auto-fetching cover path",
                device_name,
                path_hash,
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
                apply_mow_progress_geojson(
                    device.map,
                    device.location.RTK,
                    work.now_index,
                    work.ub_path_hash,
                    work.path_pos_x,
                    work.path_pos_y,
                )

        async def _on_bol_hash_changed(bol_hash: int) -> None:
            # bol_hash changes when the device's map element DB has been edited —
            # trigger a re-fetch so our cached HashList stays current.
            #
            # Dynamics-line devices (lidar-enabled: LUBA_HM, ME, MB, LA, CM900, …)
            # continuously detect new obstacles (type=1 elements) during mowing,
            # so bol_hash changes every few seconds while running.  We still need
            # to pick up those new obstacle hashes — we just skip the area-name
            # step (step 1) because area names don't change during mowing and the
            # device may not respond to that query while busy.
            if handle.queue.is_saga_active:
                _logger.debug(
                    "Device %s bol_hash changed to %d but saga active — skipping map sync", device_name, bol_hash
                )
                return

            device_snapshot = cast(MowerDevice, handle.snapshot.raw)
            device_type = DeviceType.value_of_str(device_name)
            is_mowing = device_snapshot.report_data.dev.sys_status in MOWING_ACTIVE_MODES
            incremental = (
                device_type.is_support_dynamics_line(device_snapshot.device_firmwares.main_controller) and is_mowing
            )
            _logger.debug(
                "Device %s bol_hash changed to %d — syncing map if not mowing for lidar versions (incremental=%s)",
                device_name,
                bol_hash,
                incremental,
            )
            if incremental:
                # bol hash can change quite frequently for lidar machines
                return

            try:
                await self.start_map_sync(device_name, skip_area_names=incremental)
            except Exception:  # noqa: BLE001
                _logger.warning("Auto-trigger map sync failed for %s", device_name, exc_info=True)

        async def _on_init_cfg_hash_changed(cfg_hash: int) -> None:
            # init_cfg_hash changes when the device's plan/schedule configuration
            # changes — mirrors the APK's initCfgHash-driven allpowerfullRW(5,1,1)
            # trigger in DeviceInitializationManager.
            if not cfg_hash or handle.queue.is_saga_active:
                _logger.debug(
                    "Device %s init_cfg_hash changed to %d but saga active — skipping plan sync", device_name, cfg_hash
                )
                return
            _logger.debug(
                "Device %s init_cfg_hash changed to %d — syncing plans",
                device_name,
                cfg_hash,
            )
            try:
                await self.start_plan_sync(device_name)
            except Exception:  # noqa: BLE001
                _logger.warning("Auto-trigger plan sync failed for %s", device_name, exc_info=True)

        sub = handle.watch_field(
            lambda s: s.raw.report_data.work.path_hash,  # type: ignore
            _on_path_hashes_changed,
        )
        progress_sub = handle.watch_field(
            lambda s: (s.raw.report_data.work.path_pos_x, s.raw.report_data.work.path_pos_y),  # type: ignore
            _on_mow_progress_changed,
        )
        bol_hash_sub = handle.watch_field(
            lambda s: s.raw.report_data.locations[0].bol_hash if s.raw.report_data.locations else 0,  # type: ignore
            _on_bol_hash_changed,
        )
        init_cfg_hash_sub = handle.watch_field(
            lambda s: s.raw.report_data.work.init_cfg_hash,  # type: ignore
            _on_init_cfg_hash_changed,
        )

        # Cancel any previous watchers first: a plain overwrite leaves the old
        # Subscriptions live on the handle's state bus, double-firing every
        # map/plan sync trigger after a re-setup.
        for old_sub in self._watcher_subscriptions.pop(device_name, []):
            old_sub.cancel()
        self._watcher_subscriptions[device_name] = [
            sub,
            progress_sub,
            bol_hash_sub,
            init_cfg_hash_sub,
        ]
        return sub

    def teardown_device_watchers(self, device_name: str) -> None:
        """Cancel state-change subscriptions for *device_name*."""
        for sub in self._watcher_subscriptions.pop(device_name, []):
            sub.cancel()

    def setup_all_mower_watchers(self) -> None:
        """Set up state-change watchers for all registered mower devices.

        Skips RTK base stations and swimming-pool (Spino/S1/E1) devices.
        """
        for handle in self._device_registry.all_devices:
            name = handle.device_name
            if DeviceType.is_rtk(name, handle.product_key) or DeviceType.is_swimming_pool(name, handle.product_key):
                continue
            self.setup_device_watchers(name)
