"""Home Assistant core's facade over :class:`~pymammotion.client.MammotionClient`.

The Mammotion integration in Home Assistant core consumes the library through
:class:`HomeAssistantMowerApi`; the custom integration (HA-Luba) calls the client
directly.  Each method is a thin, typed call into the client or the device's handle,
which own every rule: queueing, the offline gate, saga de-duplication, map-sync deferral.
"""

from __future__ import annotations

from datetime import timedelta
from logging import getLogger
import time
from typing import TYPE_CHECKING, Any, cast

from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.device_capabilities import DeviceConfig
from pymammotion.data.model.device_config import OperationSettings, build_route_information
from pymammotion.device.handle import DeviceNotRegisteredError
from pymammotion.messaging.command_queue import Priority
from pymammotion.transport.base import CommandDroppedError, CommandTimeoutError, ConcurrentRequestError, TransportType
from pymammotion.utility.constant.device_constant import WorkMode
from pymammotion.utility.device_type import DeviceType

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from aiohttp import ClientSession

    from pymammotion.data.model import GenerateRouteInformation
    from pymammotion.data.model.device_limits import DeviceLimits
    from pymammotion.data.model.hash_list import Plan
    from pymammotion.data.model.pool_state import PoolPlan
    from pymammotion.device.handle import DeviceHandle
    from pymammotion.state.device_state import DeviceSnapshot
    from pymammotion.transport.base import Subscription

logger = getLogger(__name__)

#: Retry pacing for data we don't hold yet, not a refresh of what we do.
_CALL_INTERVALS: dict[str, timedelta] = {
    "check_maps": timedelta(hours=2),
    "read_plan": timedelta(minutes=30),
    "get_report_cfg": timedelta(hours=1),
    "get_maintenance": timedelta(hours=24),
    "device_info": timedelta(hours=24),
}

#: (command, reply field) per piece of version/model data, keyed by a check that it is already held.
_DEVICE_INFO_READS: tuple[tuple[str, str, Callable[[MowingDevice], object]], ...] = (
    ("get_device_version_main", "toapp_devinfo_resp", lambda device: device.mower_state.swversion),
    ("get_device_version_info", "toapp_dev_fw_info", lambda device: device.device_firmwares.main_controller),
    ("get_device_base_info", "toapp_devinfo_resp", lambda device: device.device_firmwares.device_version),
    ("get_device_product_model", "device_product_type_info", lambda device: device.mower_state.model_id),
)


class HomeAssistantMowerApi:
    """Per-mower calls for Home Assistant, by device name.

    An unknown device name: the queries :meth:`is_online` and :meth:`device_limits` answer
    as for a device with no state (``False``, the family defaults); every other method
    raises :class:`~pymammotion.device.handle.DeviceNotRegisteredError`, a ``KeyError``.

    Background commands (:meth:`async_send_command` and the setters built on it) are
    queued behind any running saga and dropped quietly when nothing can carry them.  User
    commands (:meth:`async_send_user_command`, movement, dock, blades) are sent at once and
    raise when they do not land: ``NoTransportAvailableError``, ``DeviceOfflineException``,
    ``TooManyRequestsException`` or another ``TransportError`` (``AuthError`` included).
    """

    def __init__(self, ha_version: str, session: ClientSession | None = None) -> None:  # noqa: ARG002
        """Create the client.  *session* is unused: hand it to the login call instead."""
        self._device_config = DeviceConfig()
        self.update_failures = 0
        self._mammotion = MammotionClient(ha_version)
        #: device name -> api name -> monotonic time of the last call.
        self._last_call_times: dict[str, dict[str, float]] = {}

    @property
    def mammotion(self) -> MammotionClient:
        """Return the underlying client, for the account-level API (login, credentials, device lists, stop)."""
        return self._mammotion

    def _handle(self, device_name: str) -> DeviceHandle:
        if (handle := self._mammotion.mower(device_name)) is None:
            msg = f"Device '{device_name}' not registered"
            raise DeviceNotRegisteredError(msg)
        return handle

    def _device(self, device_name: str) -> MowingDevice:
        return cast("MowingDevice", self._handle(device_name).snapshot.raw)

    def _should_call_api(self, api_name: str, device_name: str) -> bool:
        last_call = self._last_call_times.get(device_name, {}).get(api_name)
        return last_call is None or time.monotonic() - last_call >= _CALL_INTERVALS[api_name].total_seconds()

    def _mark_api_called(self, api_name: str, device_name: str) -> None:
        self._last_call_times.setdefault(device_name, {})[api_name] = time.monotonic()

    def device_limits(self, device_name: str) -> DeviceLimits:
        """Return the named device's operating limits, or the family defaults when it is unknown."""
        if (device := self._mammotion.get_device_by_name(device_name)) is None:
            return self._device_config.get_best_default("")
        return device.device_limits

    def is_online(self, device_name: str) -> bool:
        """Return True if the named device currently has an active connection; False when it is unknown."""
        handle = self._mammotion.mower(device_name)
        return handle is not None and handle.snapshot.online

    async def update(self, device_name: str) -> MowingDevice:
        """Fetch what the device has not sent us yet, then return its state.

        Skipped while the queue has work.  Missing version/model data is read first, so it
        never waits behind a saga this call starts; then an incomplete map or plan set is
        synced, each retried at its own pacing and not at all while the device is unreachable.

        Raises:
            DeviceNotRegisteredError: *device_name* is not registered.
            NoTransportAvailableError: a version read found nothing to send over.
            DeviceOfflineException: the cloud refused a version read; the device is offline.
            AuthError: the cloud session behind a version read is dead.

        """
        handle = self._handle(device_name)
        if handle.has_queued_commands():
            return self._device(device_name)

        if self._should_call_api("device_info", device_name):
            await self._fetch_missing_device_info(device_name)
            self._mark_api_called("device_info", device_name)

        device = self._device(device_name)
        if handle.has_usable_transport:
            if self._map_sync_due(device) and self._should_call_api("check_maps", device_name):
                await self._mammotion.start_map_sync(device_name)
                self._mark_api_called("check_maps", device_name)
            if self._plan_sync_due(device) and self._should_call_api("read_plan", device_name):
                await self._mammotion.start_plan_sync(device_name)
                self._mark_api_called("read_plan", device_name)

        if self._should_call_api("get_report_cfg", device_name):
            await self.async_send_command(device_name, "get_report_cfg")
            self._mark_api_called("get_report_cfg", device_name)

        if self._should_call_api("get_maintenance", device_name):
            await self.async_send_command(device_name, "get_maintenance")
            await self.async_send_command(device_name, "basestation_info")
            self._mark_api_called("get_maintenance", device_name)

        return self._device(device_name)

    @staticmethod
    def _map_sync_due(device: MowingDevice) -> bool:
        # Before the first report the hash reads as 0, which is not a stale map.
        return bool(device.report_data.locations) and device.map_sync_due

    @staticmethod
    def _plan_sync_due(device: MowingDevice) -> bool:
        # plans_fetched separates "no schedules" from "never asked"; plans_stale is raised by the reducer.
        return not device.map.plans_fetched or device.map.plans_stale

    async def async_send_command(self, device_name: str, command: str, /, **kwargs: Any) -> bool:
        """Queue a background command (``Priority.NORMAL``); True once queued, False if it could not be built.

        Raises:
            DeviceNotRegisteredError: *device_name* is not registered.

        """
        try:
            await self._mammotion.send_command_with_args(device_name, command, **kwargs)
        except DeviceNotRegisteredError:
            raise
        except Exception as ex:  # noqa: BLE001 — a builder rejecting its arguments is logged, not raised
            logger.error("Command '%s' failed for %s: %s", command, device_name, ex)
            self.update_failures += 1
            return False
        self.update_failures = 0
        return True

    async def async_send_user_command(self, device_name: str, command: str, /, **kwargs: Any) -> None:
        """Send a command a person asked for now (``Priority.USER``), past a running saga.

        Raises:
            DeviceNotRegisteredError: *device_name* is not registered.
            Exception: whatever the send failed with; see the class docstring.

        """
        await self._mammotion.send_command_with_args(device_name, command, priority=Priority.USER, **kwargs)

    async def async_wait_for_mode(self, device_name: str, *modes: WorkMode, timeout: float = 30.0) -> WorkMode:
        """Return the first of *modes* the mower reports, requesting reports while it waits.

        Raises:
            DeviceNotRegisteredError: *device_name* is not registered.
            DeviceStateTimeoutError: none of *modes* was reported within *timeout* seconds.
            Exception: whatever a report request failed with; see the class docstring.

        """
        device = await self._mammotion.wait_for(
            device_name,
            lambda state: isinstance(state, MowingDevice) and state.report_data.dev.sys_status in modes,
            timeout=timeout,
        )
        return WorkMode(cast("MowingDevice", device).report_data.dev.sys_status)

    async def async_request_report(self, device_name: str) -> None:
        """Ask for a report in the background; skipped while one is fresh or the BLE stream is live."""
        await self._handle(device_name).request_report_snapshot()

    async def async_request_state_if_stale(self, device_name: str, max_age_s: float = 120.0) -> None:
        """Queue a background report request when the last telemetry is older than *max_age_s*; returns at once."""
        handle = self._handle(device_name)
        await self._mammotion.ensure_fresh_state(device_name, max_age_s=max_age_s, account_id=handle.account_id)

    async def async_refresh_state_if_stale(self, device_name: str, max_age_s: float = 120.0) -> None:
        """Request a report now when the last telemetry is older than *max_age_s*, and wait for it to land.

        Raises:
            DeviceNotRegisteredError: *device_name* is not registered.
            DeviceStateTimeoutError: the device sent no report in the request's window.
            Exception: whatever the request failed with; see the class docstring.

        """
        handle = self._handle(device_name)
        await self._mammotion.ensure_fresh_state(
            device_name, max_age_s=max_age_s, wait=True, account_id=handle.account_id
        )

    def restore_device(self, device_name: str, device: MowingDevice) -> None:
        """Seed the device's state with what the host saved last run."""
        self._handle(device_name).restore_device(device)

    def subscribe_state_changed(
        self, device_name: str, handler: Callable[[DeviceSnapshot], Awaitable[None]]
    ) -> Subscription:
        """Call *handler* with every new state snapshot; cancel the returned subscription to stop."""
        return self._handle(device_name).subscribe_state_changed(handler)

    async def set_scheduled_updates(self, device_name: str, enabled: bool) -> None:
        """Connect or disconnect the device's transports; see :meth:`MammotionClient.set_scheduled_updates`."""
        self._handle(device_name)
        await self._mammotion.set_scheduled_updates(device_name, enabled=enabled)

    async def update_firmware(self, device_name: str, version: str) -> None:
        """Start an OTA upgrade, clearing the cached version info so it is read again afterwards."""
        handle = self._handle(device_name)
        if (http := self._mammotion.http_for_device(device_name)) is None:
            logger.warning("update_firmware: '%s' has no cloud account", device_name)
            return
        self._device(device_name).clear_version_info()
        await http.start_ota_upgrade(handle.iot_id, version)

    async def async_wake_up(self, device_name: str) -> bool:
        """Wake a sleeping device; True means the cloud accepted the request, not that it is awake yet."""
        self._handle(device_name)
        return await self._mammotion.wake_device(device_name)

    async def async_start_stop_blades(self, device_name: str, start_stop: bool, blade_height: int = 60) -> None:
        """Start or stop the blades; a user command."""
        if DeviceType.is_luba1(device_name):
            await self.async_send_user_command(device_name, "set_blade_control", on_off=int(start_stop))
            return
        if start_stop and (DeviceType.is_yuka(device_name) or DeviceType.is_yuka_mini(device_name)):
            blade_height = 0
        await self.async_send_user_command(
            device_name,
            "operate_on_device",
            main_ctrl=int(start_stop),
            cut_knife_ctrl=int(start_stop),
            cut_knife_height=blade_height,
            max_run_speed=1.2,
        )

    async def async_set_rain_detection(self, device_name: str, on_off: bool) -> None:
        """Set rain detection."""
        await self.async_send_command(device_name, "read_write_device", rw_id=3, context=int(on_off), rw=1)

    async def async_read_rain_detection(self, device_name: str) -> None:
        """Read rain detection."""
        await self.async_send_command(device_name, "read_write_device", rw_id=3, context=1, rw=0)

    async def async_set_sidelight(self, device_name: str, on_off: int) -> None:
        """Set the sidelight, then re-read it: two queued sends."""
        await self.async_send_command(device_name, "read_and_set_sidelight", is_sidelight=bool(on_off), operate=0)
        await self.async_read_sidelight(device_name)

    async def async_read_sidelight(self, device_name: str) -> None:
        """Read the sidelight."""
        await self.async_send_command(device_name, "read_and_set_sidelight", is_sidelight=False, operate=1)

    async def async_set_manual_light(self, device_name: str, manual_ctrl: bool) -> None:
        """Set the manual night light, then re-read it: two queued sends."""
        await self.async_send_command(device_name, "set_car_manual_light", manual_ctrl=manual_ctrl)
        await self.async_send_command(device_name, "get_car_light", ids=1126)

    async def async_set_night_light(self, device_name: str, night_light: bool) -> None:
        """Set the night light, then re-read it: two queued sends."""
        await self.async_send_command(device_name, "set_car_light", on_off=night_light)
        await self.async_send_command(device_name, "get_car_light", ids=1123)

    async def async_set_traversal_mode(self, device_name: str, context: int) -> None:
        """Set traversal mode."""
        await self.async_send_command(device_name, "traverse_mode", context=context)

    async def async_set_turning_mode(self, device_name: str, context: int) -> None:
        """Set turning mode."""
        await self.async_send_command(device_name, "turning_mode", context=context)

    async def async_blade_height(self, device_name: str, height: int) -> int:
        """Set blade height; returns the height sent."""
        await self.async_send_command(device_name, "set_blade_height", height=height)
        return height

    async def async_set_cutter_speed(self, device_name: str, mode: int) -> None:
        """Set cutter speed."""
        await self.async_send_command(device_name, "set_cutter_mode", cutter_mode=mode)

    async def async_set_speed(self, device_name: str, speed: float) -> None:
        """Set working speed."""
        await self.async_send_command(device_name, "set_speed", speed=speed)

    async def async_leave_dock(self, device_name: str) -> None:
        """Leave the dock (a user command), then queue a one-shot report."""
        await self.async_send_user_command(device_name, "leave_dock")
        await self._mammotion.request_iot_sync(device_name)

    async def async_cancel_task(self, device_name: str) -> None:
        """Cancel the job (a user command), then queue a one-shot report."""
        await self.async_send_user_command(device_name, "cancel_job")
        await self._mammotion.request_iot_sync(device_name)

    async def async_move_forward(self, device_name: str, speed: float, *, use_wifi: bool = False) -> None:
        """Move forward (a user command); BLE is warmed up unless *use_wifi*."""
        await self._move(device_name, "move_forward", use_wifi=use_wifi, linear=speed)

    async def async_move_left(self, device_name: str, speed: float, *, use_wifi: bool = False) -> None:
        """Move left (a user command); BLE is warmed up unless *use_wifi*."""
        await self._move(device_name, "move_left", use_wifi=use_wifi, angular=speed)

    async def async_move_right(self, device_name: str, speed: float, *, use_wifi: bool = False) -> None:
        """Move right (a user command); BLE is warmed up unless *use_wifi*."""
        await self._move(device_name, "move_right", use_wifi=use_wifi, angular=speed)

    async def async_move_back(self, device_name: str, speed: float, *, use_wifi: bool = False) -> None:
        """Move back (a user command); BLE is warmed up unless *use_wifi*."""
        await self._move(device_name, "move_back", use_wifi=use_wifi, linear=speed)

    async def _move(self, device_name: str, command: str, *, use_wifi: bool, **kwargs: Any) -> None:
        await self._mammotion.send_command_with_args(
            device_name, command, prefer_ble=not use_wifi, priority=Priority.USER, **kwargs
        )

    async def async_rtk_dock_location(self, device_name: str) -> None:
        """Read the RTK and dock location."""
        await self.async_send_command(device_name, "read_write_device", rw_id=5, rw=1, context=1)

    async def async_get_area_list(self, device_name: str, iot_id: str) -> None:
        """Read the mowing area list."""
        await self.async_send_command(device_name, "get_area_name_list", device_id=iot_id)

    async def async_relocate_charging_station(self, device_name: str) -> None:
        """Reset the charging station position."""
        await self.async_send_command(device_name, "delete_charge_point")

    async def async_set_non_work_hours(self, device_name: str, start_time: str, end_time: str) -> None:
        """Set non-work hours."""
        await self.async_send_command(
            device_name,
            "set_plan_unable_time",
            sub_cmd=1,
            trigger=1,
            device_id=self._handle(device_name).iot_id,
            unable_end_time=end_time,
            unable_start_time=start_time,
        )

    async def async_set_job_dnd(self, device_name: str, start_time: str, end_time: str) -> None:
        """Set job do-not-disturb hours."""
        await self.async_send_command(
            device_name,
            "job_do_not_disturb",
            sub_cmd=1,
            trigger=1,
            unable_end_time=end_time,
            unable_start_time=start_time,
        )

    async def async_del_job_dnd(self, device_name: str) -> None:
        """Delete job do-not-disturb hours."""
        await self.async_send_command(device_name, "job_do_not_disturb", sub_cmd=1, trigger=0)

    async def send_command_and_update(self, device_name: str, command_str: str, /, **kwargs: Any) -> None:
        """Queue a background command, then a one-shot report."""
        await self.async_send_command(device_name, command_str, **kwargs)
        await self._mammotion.request_iot_sync(device_name)

    async def async_request_iot_sync(self, device_name: str, stop: bool = False) -> None:
        """Start (or stop) the continuous report stream; see :meth:`MammotionClient.request_iot_sync_continuous`."""
        await self._mammotion.request_iot_sync_continuous(device_name, stop=stop)

    def generate_route_information(
        self, device_name: str, operation_settings: OperationSettings
    ) -> GenerateRouteInformation:
        """Build the route a plan or modify sends, gated on the named device; mutates *operation_settings*."""
        return build_route_information(device_name, self._device(device_name), operation_settings)

    async def async_plan_route(self, device_name: str, operation_settings: OperationSettings) -> bool:
        """Plan a route and queue the MowPathSaga that collects its cover path.

        No areas means every area on the map.  The path lands in ``device.map.current_mow_path``
        and ``generated_mow_path_geojson``.  Returns False when the saga is gated off (cover-path
        fetches disabled over MQTT).
        """
        if not operation_settings.areas:
            operation_settings.areas = list(dict.fromkeys(self._device(device_name).map.area.keys()))
        route_information = self.generate_route_information(device_name, operation_settings)
        return await self._mammotion.start_mow_path_saga(
            device_name, zone_hashs=list(operation_settings.areas), route_info=route_information
        )

    async def async_modify_plan_route(self, device_name: str, operation_settings: OperationSettings) -> bool:
        """Modify the running job's route, keeping the settings the job reports."""
        if work := self._device(device_name).work:
            operation_settings.areas = list(dict.fromkeys(work.zone_hashs))
            operation_settings.toward = work.toward
            operation_settings.toward_mode = work.toward_mode
            operation_settings.toward_included_angle = work.toward_included_angle
            operation_settings.mowing_laps = work.edge_mode
            operation_settings.ride_boundary_distance = work.ride_boundary_distance
            if work.auto_change_direction is not None:
                operation_settings.auto_change_direction = int(work.auto_change_direction)
            operation_settings.job_mode = work.job_mode
            operation_settings.job_id = work.job_id
            operation_settings.job_version = work.job_ver

        route_information = self.generate_route_information(device_name, operation_settings)
        return await self.async_send_command(
            device_name, "modify_route_information", generate_route_information=route_information
        )

    async def start_task(self, device_name: str, plan_id: str) -> None:
        """Start the stored schedule *plan_id* now."""
        await self.async_send_command(device_name, "single_schedule", plan_id=plan_id)

    async def async_continue_last_job(self, device_name: str, work_id: int) -> bool:
        """Resume the interrupted job ``work_id`` (the latest cloud work report's ``workId``).

        The app offers this only in standby (MODE_READY) with at least 30 % battery.
        """
        return await self.async_send_command(device_name, "continue_last_job", work_id=work_id)

    async def create_mower_task(self, device_name: str, plan: Plan) -> None:
        """Create a mower schedule (``sub_cmd=1``); ``plan.plan_id`` comes from ``utility.plan_id.new_mower_plan_id``.

        Wire protocol: ``docs/tasks_and_schedules.md`` § 1.
        """
        await self.async_send_command(device_name, "create_plan", plan=plan)

    async def edit_mower_task(self, device_name: str, plan: Plan) -> None:
        """Edit a stored mower schedule (``sub_cmd=4``); ``plan.plan_id`` must already be on the device."""
        await self.async_send_command(device_name, "edit_plan", plan=plan)

    async def rename_mower_task(self, device_name: str, plan: Plan, new_name: str) -> None:
        """Rename a mower schedule — resent as an edit (``sub_cmd=4``)."""
        await self.async_send_command(device_name, "rename_plan", plan=plan, new_name=new_name)

    async def set_mower_task_enabled(self, device_name: str, plan: Plan, enabled: bool) -> None:
        """Toggle a mower schedule's enable flag (``reserved[2]``, ``sub_cmd=4``)."""
        await self.async_send_command(device_name, "enable_plan", plan=plan, enabled=enabled)

    async def delete_mower_task(self, device_name: str, plan_id: str) -> None:
        """Delete the mower schedule with ``plan_id`` (``sub_cmd=3``)."""
        await self.async_send_command(device_name, "delete_plan_by_id", plan_id=plan_id)

    async def copy_mower_task(self, device_name: str, plan: Plan, new_name: str, new_plan_id: str) -> None:
        """Duplicate a mower schedule under a new id and name (``sub_cmd=1``).

        ``new_plan_id`` comes from ``utility.plan_id.new_mower_plan_id`` and ``new_name`` from
        ``utility.plan_id.make_copy_name``.
        """
        await self.async_send_command(device_name, "copy_plan", plan=plan, new_name=new_name, new_plan_id=new_plan_id)

    async def create_spino_task(self, device_name: str, plan: PoolPlan) -> None:
        """Create a Spino schedule (``cmd = ADD = 1``); the caller assigns a fresh 64-bit ``plan.jobid``.

        Wire protocol: ``docs/tasks_and_schedules.md`` § 2.
        """
        await self.async_send_command(device_name, "create_spino_plan", plan=plan)

    async def edit_spino_task(self, device_name: str, plan: PoolPlan) -> None:
        """Edit a stored Spino schedule (``cmd = EDIT = 4``)."""
        await self.async_send_command(device_name, "edit_spino_plan", plan=plan)

    async def rename_spino_task(self, device_name: str, plan: PoolPlan, new_name: str) -> None:
        """Rename a Spino schedule — resent as an edit (``cmd = EDIT = 4``)."""
        await self.async_send_command(device_name, "rename_spino_plan", plan=plan, new_name=new_name)

    async def set_spino_task_enabled(self, device_name: str, plan: PoolPlan, enabled: bool) -> None:
        """Toggle a Spino schedule's enable flag (resent as ``cmd = EDIT``); the builder inverts it for the wire."""
        await self.async_send_command(device_name, "enable_spino_plan", plan=plan, enabled=enabled)

    async def delete_spino_task(self, device_name: str, jobid: int) -> None:
        """Delete the Spino schedule with the given ``jobid`` (``cmd = DELETE = 3``)."""
        await self.async_send_command(device_name, "delete_spino_plan", jobid=jobid)

    async def delete_all_spino_tasks(self, device_name: str) -> None:
        """Wipe every Spino schedule (``cmd = DELETE_ALL = 5``).

        The device sends no per-plan frames for the wipe; follow it with
        :meth:`MammotionClient.start_spino_plan_sync` to refresh ``device.plans``.
        """
        await self.async_send_command(device_name, "delete_all_spino_plans")

    async def copy_spino_task(self, device_name: str, plan: PoolPlan, new_name: str, new_jobid: int) -> None:
        """Duplicate a Spino schedule under a new 64-bit ``new_jobid`` and name (``cmd = ADD = 1``)."""
        await self.async_send_command(device_name, "copy_spino_plan", plan=plan, new_name=new_name, new_jobid=new_jobid)

    async def clear_update_failures(self, device_name: str) -> None:
        """Reset :attr:`update_failures` and reconnect any of the device's transports that are down."""
        handle = self._handle(device_name)
        self.update_failures = 0
        for transport_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION, TransportType.BLE):
            if handle.has_transport(transport_type) and not handle.is_transport_connected(transport_type):
                await handle.connect_transport(transport_type)

    async def async_check_firmware_version(self, device_name: str) -> None:
        """Ask the cloud which firmware the device can upgrade to, and log it."""
        handle = self._handle(device_name)
        if (http := self._mammotion.http_for_device(device_name)) is None:
            return
        ota_info = await http.get_device_ota_firmware([handle.iot_id])
        logger.debug("OTA info: %s", ota_info.data)

    async def async_setup_device(self, device_name: str) -> None:
        """Read the device's version/model data, skipping what is already held."""
        await self._fetch_missing_device_info(device_name)

    async def async_device_info(self, device_name: str) -> None:
        """Read any version/model data still missing (e.g. after an OTA cleared it)."""
        await self._fetch_missing_device_info(device_name)

    async def _fetch_missing_device_info(self, device_name: str) -> None:
        device = self._device(device_name)
        for command, reply_field, held in _DEVICE_INFO_READS:
            if held(device):
                continue
            try:
                await self._mammotion.queue_command_and_wait(device_name, command, reply_field)
            except (CommandTimeoutError, CommandDroppedError, ConcurrentRequestError) as ex:
                logger.warning("Device info command '%s' failed for %s: %s", command, device_name, ex)
