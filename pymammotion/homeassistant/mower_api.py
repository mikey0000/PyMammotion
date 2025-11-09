"""Thin api layer between home assistant and pymammotion."""

import asyncio
from datetime import datetime, timedelta
from logging import getLogger
from typing import Any

from pymammotion.aliyun.cloud_gateway import (
    EXPIRED_CREDENTIAL_EXCEPTIONS,
    DeviceOfflineException,
    FailedRequestException,
    GatewayTimeoutException,
    NoConnectionException,
)
from pymammotion.data.model import GenerateRouteInformation
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.device_config import OperationSettings, create_path_order
from pymammotion.mammotion.devices import MammotionMowerDeviceManager
from pymammotion.mammotion.devices.mammotion import Mammotion
from pymammotion.proto import RptAct, RptInfoType
from pymammotion.utility.device_type import DeviceType

logger = getLogger(__name__)


class HomeAssistantMowerApi:
    """API for interacting with Mammotion Mowers for Home Assistant."""

    def __init__(self) -> None:
        self._plan_lock = asyncio.Lock()
        self.update_failures = 0
        self._mammotion = Mammotion()
        self._map_lock = asyncio.Lock()
        self._last_call_times: dict[str, datetime] = {}
        self._call_intervals = {
            "check_maps": timedelta(minutes=5),
            "read_plan": timedelta(minutes=30),
            "read_settings": timedelta(minutes=5),
            "get_errors": timedelta(minutes=1),
            "get_report_cfg": timedelta(seconds=5),
            "get_maintenance": timedelta(minutes=30),
            "device_version_upgrade": timedelta(hours=5),
        }

    @property
    def mammotion(self) -> Mammotion:
        return self._mammotion

    def _should_call_api(self, api_name: str, device: MowingDevice | None = None) -> bool:
        """Check if API should be called based on time or criteria."""
        # Time-based check
        if api_name not in self._last_call_times:
            return True

        last_call = self._last_call_times[api_name]
        interval = self._call_intervals.get(api_name, timedelta(seconds=10))

        # Criteria-based checks
        if api_name == "check_maps" and device:
            # Call immediately if map data is incomplete
            if len(device.map.area) == 0 or device.map.missing_hashlist():
                return True

        return datetime.now() - last_call >= interval

    def _mark_api_called(self, api_name: str) -> None:
        """Mark an API as called with the current timestamp."""
        self._last_call_times[api_name] = datetime.now()

    async def update(self, device_name: str) -> MowingDevice:
        device = self._mammotion.get_device_by_name(device_name)

        if device.has_queued_commands():
            return device.state

        if self._map_lock.locked():
            # if maps is not complete kick off the map sync process again
            if len(device.state.map.missing_hashlist()) > 0:
                await self._mammotion.start_map_sync(device_name)
                return device.state
            # if maps complete
            else:
                self._map_lock.release()

        # Check maps periodically
        if self._should_call_api("check_maps") and not self._map_lock.locked():
            await self._map_lock.acquire()
            await self.mammotion.start_map_sync(device_name)
            self._mark_api_called("check_maps")
            return device.state

        if self._should_call_api("read_plan"):
            if len(device.state.map.plan) == 0 or list(device.state.map.plan.values())[0].total_plan_num != len(
                device.state.map.plan
            ):
                await self.async_send_command(device_name, "read_plan", sub_cmd=2, plan_index=0)
                self._mark_api_called("read_plan")
                return device.state

        # Read settings less frequently
        if self._should_call_api("read_settings"):
            # await device.async_read_settings()
            self._mark_api_called("read_settings")

        # Check for errors periodically
        if self._should_call_api("get_errors"):
            await self.async_send_command(device_name, "get_error_code")
            await self.async_send_command(device_name, "get_error_timestamp")
            self._mark_api_called("get_errors")

        if self._should_call_api("get_report_cfg"):
            await self.async_send_command(device_name, "get_report_cfg")
            self._mark_api_called("get_report_cfg")

        if self._should_call_api("get_maintenance"):
            await self.async_send_command(device_name, "get_maintenance")
            self._mark_api_called("get_maintenance")

        if self._should_call_api("device_version_upgrade"):
            self._mark_api_called("device_version_upgrade")

        return device.state

    async def async_send_command(self, device_name: str, command: str, **kwargs: Any) -> bool | None:
        """Send command."""
        device = self._mammotion.get_device_by_name(device_name)

        try:
            # TODO check preference
            if device.cloud:
                return await self.async_send_cloud_command(device, command, **kwargs)
            elif device.ble:
                return await self.async_send_bluetooth_command(device, command, **kwargs)
        except (DeviceOfflineException, NoConnectionException) as ex:
            """Device is offline try bluetooth if we have it."""
            logger.error(f"Device offline: {ex.iot_id}")
            if ble := device.ble:
                # if we don't do this, it will stay connected and no longer update over Wi-Fi
                ble.set_disconnect_strategy(disconnect=True)
                await ble.queue_command(command, **kwargs)

                return True
            raise DeviceOfflineException(ex.args[0], device.iot_id)
        return False

    async def async_send_cloud_command(
        self, device: MammotionMowerDeviceManager, key: str, **kwargs: Any
    ) -> bool | None:
        """Send command."""
        if cloud := device.cloud:
            if not device.state.online:
                return False

            try:
                await cloud.command(key, **kwargs)
                self.update_failures = 0
                return True
            except FailedRequestException:
                self.update_failures += 1
                if self.update_failures < 5:
                    await cloud.command(key, **kwargs)
                    return True
                return False
            except EXPIRED_CREDENTIAL_EXCEPTIONS:
                self.update_failures += 1
                await self._mammotion.refresh_login(device.mammotion_http.account)
                # TODO tell home assistant the credentials have changed
                if self.update_failures < 5:
                    await cloud.command(key, **kwargs)
                    return True
                return False
            except GatewayTimeoutException as ex:
                logger.error(f"Gateway timeout exception: {ex.iot_id}")
                self.update_failures = 0
                return False
            except (DeviceOfflineException, NoConnectionException) as ex:
                """Device is offline try bluetooth if we have it."""
                logger.error(f"Device offline: {ex.iot_id}")
        return False

    @staticmethod
    async def async_send_bluetooth_command(device: MammotionMowerDeviceManager, key: str, **kwargs: Any) -> bool | None:
        """Send command."""
        if ble := device.ble:
            await ble.command(key, **kwargs)

            return True
        raise DeviceOfflineException("bluetooth command failed", device.iot_id)

    async def set_scheduled_updates(self, device_name: str, enabled: bool) -> None:
        device = self.mammotion.get_device_by_name(device_name)
        device.state.enabled = enabled
        if device.state.enabled:
            self.update_failures = 0
            if not device.state.online:
                device.state.online = True
            if device.cloud and device.cloud.stopped:
                await device.cloud.start()
        else:
            if device.cloud:
                await device.cloud.stop()
                if device.cloud.mqtt.is_connected():
                    device.cloud.mqtt.disconnect()
            if device.ble:
                await device.ble.stop()

    def is_online(self, device_name: str) -> bool:
        if device := self.mammotion.get_device_by_name(device_name):
            if ble := device.ble:
                return device.state.online or ble is not None and ble.client.is_connected
        return False

    async def update_firmware(self, device_name: str, version: str) -> None:
        """Update firmware."""
        device = self.mammotion.get_device_by_name(device_name)
        await device.mammotion_http.start_ota_upgrade(device.iot_id, version)

    async def async_start_stop_blades(self, device_name: str, start_stop: bool, blade_height: int = 60) -> None:
        """Start stop blades."""
        if DeviceType.is_luba1(device_name):
            if start_stop:
                await self.async_send_command(device_name, "set_blade_control", on_off=1)
            else:
                await self.async_send_command(device_name, "set_blade_control", on_off=0)
        elif start_stop:
            if DeviceType.is_yuka(device_name) or DeviceType.is_yuka_mini(device_name):
                blade_height = 0

            await self.async_send_command(
                "operate_on_device",
                main_ctrl=1,
                cut_knife_ctrl=1,
                cut_knife_height=blade_height,
                max_run_speed=1.2,
            )
        else:
            await self.async_send_command(
                "operate_on_device",
                main_ctrl=0,
                cut_knife_ctrl=0,
                cut_knife_height=blade_height,
                max_run_speed=1.2,
            )

    async def async_set_rain_detection(self, device_name: str, on_off: bool) -> None:
        """Set rain detection."""
        await self.async_send_command(device_name, "read_write_device", rw_id=3, context=int(on_off), rw=1)

    async def async_read_rain_detection(self, device_name: str) -> None:
        """Set rain detection."""
        await self.async_send_command(device_name, "read_write_device", rw_id=3, context=1, rw=0)

    async def async_set_sidelight(self, device_name: str, on_off: int) -> None:
        """Set Sidelight."""
        await self.async_send_command(device_name, "read_and_set_sidelight", is_sidelight=bool(on_off), operate=0)
        await self.async_read_sidelight(device_name)

    async def async_read_sidelight(self, device_name: str) -> None:
        """Set Sidelight."""
        await self.async_send_command(device_name, "read_and_set_sidelight", is_sidelight=False, operate=1)

    async def async_set_manual_light(self, device_name: str, manual_ctrl: bool) -> None:
        """Set manual night light."""
        await self.async_send_command(device_name, "set_car_manual_light", manual_ctrl=manual_ctrl)
        await self.async_send_command(device_name, "get_car_light", ids=1126)

    async def async_set_night_light(self, device_name: str, night_light: bool) -> None:
        """Set night light."""
        await self.async_send_command(device_name, "set_car_light", on_off=night_light)
        await self.async_send_command(device_name, "get_car_light", ids=1123)

    async def async_set_traversal_mode(self, device_name: str, context: int) -> None:
        """Set traversal mode."""
        await self.async_send_command(device_name, "traverse_mode", context=context)

    async def async_set_turning_mode(self, device_name: str, context: int) -> None:
        """Set turning mode."""
        await self.async_send_command(device_name, "turning_mode", context=context)

    async def async_blade_height(self, device_name: str, height: int) -> int:
        """Set blade height."""
        await self.async_send_command(device_name, "set_blade_height", height=height)
        return height

    async def async_set_cutter_speed(self, device_name: str, mode: int) -> None:
        """Set cutter speed."""
        await self.async_send_command(device_name, "set_cutter_mode", cutter_mode=mode)

    async def async_set_speed(self, device_name: str, speed: float) -> None:
        """Set working speed."""
        await self.async_send_command(device_name, "set_speed", speed=speed)

    async def async_leave_dock(self, device_name: str) -> None:
        """Leave dock."""
        await self.send_command_and_update(device_name, "leave_dock")

    async def async_cancel_task(self, device_name: str) -> None:
        """Cancel task."""
        await self.send_command_and_update(device_name, "cancel_job")

    async def async_move_forward(self, device_name: str, speed: float) -> None:
        """Move forward."""
        device = self.mammotion.get_device_by_name(device_name)
        await self.async_send_bluetooth_command(device, "move_forward", linear=speed)

    async def async_move_left(self, device_name: str, speed: float) -> None:
        """Move left."""
        device = self.mammotion.get_device_by_name(device_name)
        await self.async_send_bluetooth_command(device, "move_left", angular=speed)

    async def async_move_right(self, device_name: str, speed: float) -> None:
        """Move right."""
        device = self.mammotion.get_device_by_name(device_name)
        await self.async_send_bluetooth_command(device, "move_right", angular=speed)

    async def async_move_back(self, device_name: str, speed: float) -> None:
        """Move back."""
        device = self.mammotion.get_device_by_name(device_name)
        await self.async_send_bluetooth_command(device, "move_back", linear=speed)

    async def async_rtk_dock_location(self, device_name: str) -> None:
        """RTK and dock location."""
        await self.async_send_command(device_name, "read_write_device", rw_id=5, rw=1, context=1)

    async def async_get_area_list(self, device_name: str, iot_id: str) -> None:
        """Mowing area List."""
        await self.async_send_command(device_name, "get_area_name_list", device_id=iot_id)

    async def async_relocate_charging_station(self, device_name: str) -> None:
        """Reset charging station."""
        await self.async_send_command(device_name, "delete_charge_point")
        # fetch charging location?
        """
        nav {
          todev_get_commondata {
            pver: 1
            subCmd: 2
            action: 6
            type: 5
            totalFrame: 1
            currentFrame: 1
          }
        }
        """

    async def async_set_non_work_hours(self, device_name: str, start_time: str, end_time: str) -> None:
        """Set non work hours l1?."""
        device = self._mammotion.get_device_by_name(device_name)
        await self.async_send_command(
            device_name,
            "set_plan_unable_time",
            sub_cmd=device.state.non_work_hours.sub_cmd,
            device_id=device.iot_id,
            unable_end_time=end_time,
            unable_start_time=start_time,
        )

    async def async_set_job_dnd(self, device_name: str, start_time: str, end_time: str) -> None:
        """Set non work hours."""
        await self.async_send_command(
            device_name,
            "job_do_not_disturb",
            sub_cmd=1,
            trigger=1,
            unable_end_time=end_time,
            unable_start_time=start_time,
        )

    async def async_del_job_dnd(self, device_name: str) -> None:
        """Del non work hours."""
        await self.async_send_command(device_name, "job_do_not_disturb", sub_cmd=1, trigger=0)

    async def send_command_and_update(self, device_name: str, command_str: str, **kwargs: Any) -> None:
        """Send command and update."""
        await self.async_send_command(device_name, command_str, **kwargs)
        await self.async_request_iot_sync(device_name)

    async def async_request_iot_sync(self, device_name: str, stop: bool = False) -> None:
        """Sync specific info from device."""
        await self.async_send_command(
            device_name,
            "request_iot_sys",
            rpt_act=RptAct.RPT_STOP if stop else RptAct.RPT_START,
            rpt_info_type=[
                RptInfoType.RIT_DEV_STA,
                RptInfoType.RIT_DEV_LOCAL,
                RptInfoType.RIT_WORK,
                RptInfoType.RIT_MAINTAIN,
                RptInfoType.RIT_BASESTATION_INFO,
                RptInfoType.RIT_VIO,
            ],
            timeout=10000,
            period=3000,
            no_change_period=4000,
            count=0,
        )

    def generate_route_information(
        self, device_name: str, operation_settings: OperationSettings
    ) -> GenerateRouteInformation:
        """Generate route information."""
        device = self.mammotion.get_device_by_name(device_name)
        if device.state.report_data.dev:
            dev = device.state.report_data.dev
            if dev.collector_status.collector_installation_status == 0:
                operation_settings.is_dump = False

        if DeviceType.is_yuka(device_name):
            operation_settings.blade_height = -10

        route_information = GenerateRouteInformation(
            one_hashs=list(operation_settings.areas),
            rain_tactics=operation_settings.rain_tactics,
            speed=operation_settings.speed,
            ultra_wave=operation_settings.ultra_wave,  # touch no touch etc
            toward=operation_settings.toward,  # is just angle (route angle)
            toward_included_angle=operation_settings.toward_included_angle  # demond_angle
            if operation_settings.channel_mode == 1
            else 0,  # crossing angle relative to grid
            toward_mode=operation_settings.toward_mode,
            blade_height=operation_settings.blade_height,
            channel_mode=operation_settings.channel_mode,  # single, double, segment or none (route mode)
            channel_width=operation_settings.channel_width,  # path space
            job_mode=operation_settings.job_mode,  # taskMode grid or border first
            edge_mode=operation_settings.mowing_laps,  # perimeter/mowing laps
            path_order=create_path_order(operation_settings, device_name),
            obstacle_laps=operation_settings.obstacle_laps,
        )

        if DeviceType.is_luba1(device_name):
            route_information.toward_mode = 0
            route_information.toward_included_angle = 0
        return route_information

    async def async_plan_route(self, device_name: str, operation_settings: OperationSettings) -> bool | None:
        """Plan mow."""
        route_information = self.generate_route_information(device_name, operation_settings)

        # not sure if this is artificial limit
        # if (
        #     DeviceType.is_mini_or_x_series(device_name)
        #     and route_information.toward_mode == 0
        # ):
        #     route_information.toward = 0

        return await self.async_send_command(
            device_name, "generate_route_information", generate_route_information=route_information
        )

    async def async_modify_plan_route(self, device_name: str, operation_settings: OperationSettings) -> bool | None:
        """Modify plan mow."""
        device = self.mammotion.get_device_by_name(device_name)

        if work := device.state.work:
            operation_settings.areas = set(work.zone_hashs)
            operation_settings.toward = work.toward
            operation_settings.toward_mode = work.toward_mode
            operation_settings.toward_included_angle = work.toward_included_angle
            operation_settings.mowing_laps = work.edge_mode
            operation_settings.job_mode = work.job_mode
            operation_settings.job_id = work.job_id
            operation_settings.job_version = work.job_ver

        route_information = self.generate_route_information(device_name, operation_settings)
        if route_information.toward_mode == 0:
            route_information.toward = 0

        return await self.async_send_command(
            device_name, "modify_route_information", generate_route_information=route_information
        )

    async def start_task(self, device_name: str, plan_id: str) -> None:
        """Start task."""
        await self.async_send_command(device_name, "single_schedule", plan_id=plan_id)

    async def clear_update_failures(self, device_name: str) -> None:
        """Clear update failures."""
        self.update_failures = 0
        device = self.mammotion.get_device_by_name(device_name)
        if not device.state.online:
            device.state.online = True
        if cloud := device.cloud:
            if cloud.stopped:
                await cloud.start()
