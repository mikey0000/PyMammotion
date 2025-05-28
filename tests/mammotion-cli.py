#!/usr/bin/env python3

import asyncio
import json
import logging
import os
import random
from typing import Any, Callable, Coroutine, Optional, Dict, List, Tuple, Type
import dataclasses
import sys
import getpass
import math
import functools
from datetime import datetime, timedelta
from pprint import pprint

from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.hash_list import HashList
from pymammotion.data.model.device_config import OperationSettings, create_path_order
from pymammotion.data.model import GenerateRouteInformation
from pymammotion.data.model.mowing_modes import (
    CuttingMode, MowOrder, BorderPatrolMode, ObstacleLapsMode,
    PathAngleSetting, DetectionStrategy, TraversalMode, TurningMode
)
from pymammotion.data.state_manager import StateManager
from pymammotion.mammotion.devices.mammotion_cloud import MammotionCloud
from pymammotion.aliyun.cloud_gateway import (
    CloudIOTGateway, SetupException, DeviceOfflineException,
    GatewayTimeoutException, NoConnectionException
)
from pymammotion.http.http import MammotionHTTP
from pymammotion.mqtt.mammotion_mqtt import MammotionMQTT
from pymammotion.mammotion.devices.mammotion import MammotionBaseCloudDevice
from pymammotion.aliyun.model.dev_by_account_response import Device as AliyunDevice

from pymammotion.utility.constant.device_constant import device_mode, device_connection, PosType, WorkMode as PyMammotionWorkMode
from pymammotion.data.model.enums import RTKStatus
from pymammotion.proto import RptAct, RptInfoType
from pymammotion.utility.device_type import DeviceType
from aiohttp import ClientError # For network related errors

# --- Global Loggers (configured in main) ---
logger = logging.getLogger("mammotion_cli")
pymammotion_logger = logging.getLogger("pymammotion")
paho_mqtt_logger = logging.getLogger("paho.mqtt.client")
linkkit_logger = logging.getLogger("linkkit")
asyncio_logger = logging.getLogger("asyncio")

# --- Custom Exceptions ---
class MowerError(Exception):
    """Base exception for Mower CLI errors."""
    pass

class MowerConnectionError(MowerError):
    """Raised when mower connection or initialization fails."""
    pass

class MowerCommandError(MowerError):
    """Raised when a mower command execution fails after retries."""
    pass

# --- Constants ---
class Constants:
    CORE_RPT_INFO_TYPES_FOR_CONTINUOUS_REPORTING: List[RptInfoType] = [
        RptInfoType.RIT_DEV_STA, RptInfoType.RIT_DEV_LOCAL, RptInfoType.RIT_WORK,
        RptInfoType.RIT_MAINTAIN, RptInfoType.RIT_BASESTATION_INFO, RptInfoType.RIT_VIO,
    ]
    RPT_INFO_TYPES_FOR_SHUTDOWN_STOP: List[RptInfoType] = CORE_RPT_INFO_TYPES_FOR_CONTINUOUS_REPORTING

    ENUM_SETTINGS_MAP = {
        "job_mode": MowOrder, "border_mode": MowOrder, "mowing_laps": BorderPatrolMode,
        "obstacle_laps": ObstacleLapsMode, "channel_mode": CuttingMode,
        "ultra_wave": DetectionStrategy, "toward_mode": PathAngleSetting,
    }
    MIN_CHARGE_RATE_FOR_ESTIMATE = 0.05

# Exceptions that PyMammotion's queue_command might raise after its internal retries fail.
# These will be caught and wrapped in MowerCommandError.
PYMAMMOTION_COMMAND_FAILURE_EXCEPTIONS = (
    ClientError,  # From aiohttp, for general network issues if not caught by pymammotion
    SetupException, # from pymammotion.aliyun.cloud_gateway (might occur if session expires mid-command)
    DeviceOfflineException, GatewayTimeoutException, NoConnectionException, # from pymammotion.aliyun.cloud_gateway
    json.JSONDecodeError # If the library expects to parse JSON and fails at its boundary
)

# --- Configuration Management ---
@dataclasses.dataclass
class Config:
    email: Optional[str] = None
    password: Optional[str] = None
    log_level: str = "INFO"
    base_monitoring_interval: int = 20
    work_monitoring_divider: int = 4
    mqtt_connection_timeout: int = 20
    map_cache_file: str = "map_cache.json"
    mow_defaults_file: str = "mow_defaults.json"

    @classmethod
    def from_env_and_input(cls):
        config = cls()
        config.email = os.environ.get('EMAIL') or input("Enter Mammotion Email: ")
        config.password = os.environ.get('PASSWORD') or getpass.getpass("Enter Mammotion Password: ")
        config.log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
        return config

# --- Utility Functions ---
def get_enum_member_name_by_value(enum_class: Type[Any], value_int: int) -> Optional[str]:
    """Returns the string name of an enum member by its integer value."""
    for member_name, member_obj in enum_class.__members__.items():
        if member_obj.value == value_int:
            return member_name
    return None

def get_enum_value(enum_class: Type[Any], value_str: str) -> Optional[int]:
    for member_name in enum_class.__members__:
        if member_name.lower() == value_str.lower():
            return enum_class[member_name].value
        if member_name.lower() == value_str.replace("_", "").lower():
             return enum_class[member_name].value
        if member_name.replace("_", "").lower() == value_str.lower():
            return enum_class[member_name].value
    logger.warning(f"Could not parse '{value_str}' into a valid {enum_class.__name__} member. Parameter will not be set or will use library default.")
    return None

# --- Status Formatting ---
class StatusFormatter:
    @staticmethod
    def _format_field(label: str, value: Any, unit: str = "", default_val: str = "N/A") -> str:
        """Helper to format a single field for display."""
        if value is None or (isinstance(value, str) and value.strip() == ""):
            value_str = default_val
        else:
            if isinstance(value, float):
                # Show 1 decimal place for floats, unless it's an integer value like 0.0
                value_str = f"{value:.1f}" if value % 1 != 0 else f"{int(value)}"
            else:
                value_str = str(value)
        return f"{label.ljust(9)}: {value_str}{unit}"

    @staticmethod
    def format_summary_text(summary: Dict[str, Any]) -> str:
        if not summary or summary.get("error"):
            return "Status: No data or error fetching status."

        lines = []
        label_w = 9 # Standard label width

        # Line 1: Device Info & Update Time
        device_name_str = summary.get('device_name', 'N/A')
        nickname_str = summary.get('nickname')
        display_name = f"{device_name_str} ({nickname_str})" if nickname_str and nickname_str != "N/A" else device_name_str

        status_age_str = "N/A"
        last_update_ts = summary.get("sys_time_stamp")
        if last_update_ts:
            try:
                last_update_dt = datetime.fromtimestamp(int(last_update_ts))
                age_delta = datetime.now() - last_update_dt
                if age_delta.total_seconds() < 1: status_age_str = "<1s ago"
                elif age_delta.total_seconds() < 60: status_age_str = f"{int(age_delta.total_seconds())}s ago"
                elif age_delta.total_seconds() < 3600: status_age_str = f"{int(age_delta.total_seconds() / 60)}m ago"
                else: status_age_str = f"{int(age_delta.total_seconds() / 3600)}h ago"
            except (ValueError, TypeError): status_age_str = "InvalidTS"

        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        device_info_line = f"{display_name.ljust(40)} {current_datetime} Updated: {status_age_str}"
        lines.append(device_info_line)

        # Line 2: Core Status
        activity_str = str(summary.get('activity', 'N/A')).ljust(29)
        error_str = f"Error: {summary.get('error_code', 'OK')}"
        lines.append(f"Activity : {activity_str} {error_str}")

        # Line 3: Power Status
        bat_percent = summary.get('battery_percent')
        bat_str = f"{bat_percent}%" if bat_percent is not None else "N/A"
        
        docked_status = "Docked" if summary.get('is_docked') else "Undocked"
        charging_status = "Charging" if summary.get('is_charging') else "Not Charging"
        power_base_str = f"{StatusFormatter._format_field('Battery', bat_str)} ({docked_status}, {charging_status})"
        lines.append(power_base_str)

        if summary.get('is_charging'):
            charge_rate = summary.get('charge_rate_percent_per_minute')
            t_80 = summary.get('charge_time_to_80_min')
            t_100 = summary.get('charge_time_to_100_min')
            
            charge_details_parts = []
            if charge_rate is not None: charge_details_parts.append(f"Rate: {charge_rate:.1f}%/m")
            if t_80 is not None and t_80 > 0 : charge_details_parts.append(f"->80% {int(t_80)}m")
            if t_100 is not None and t_100 > 0: charge_details_parts.append(f"->100% {int(t_100)}m")
            
            if charge_details_parts:
                lines.append(f"{'Charge'.ljust(label_w)}: {', '.join(charge_details_parts)}")


        # Line 4: Positioning & RTK
        rtk_status_str = str(summary.get('rtk_status', "N/A"))
        rtk_stars = summary.get('rtk_gps_stars')
        l1_sats = summary.get('l1_satellites')
        l2_sats = summary.get('l2_satellites')
        rtk_details_parts = []
        if rtk_stars is not None: rtk_details_parts.append(f"{rtk_stars}*")
        if l1_sats is not None: rtk_details_parts.append(f"L1:{l1_sats}")
        if l2_sats is not None: rtk_details_parts.append(f"L2:{l2_sats}")
        rtk_details_str = f" ({', '.join(rtk_details_parts)})" if rtk_details_parts else ""
        
        pos_certainty = str(summary.get('position_certainty', "N/A"))
        rtk_line = f"{StatusFormatter._format_field('RTK', f'{rtk_status_str}{rtk_details_str}')}  Pos: {pos_certainty}"
        lines.append(rtk_line)

        # Line 5: Connectivity
        conn_type = summary.get('connection_type', "N/A")
        rssi_val = None
        rssi_unit = "dBm"
        if conn_type == "WiFi" and summary.get('wifi_rssi_dbm') is not None: rssi_val = summary.get('wifi_rssi_dbm')
        elif conn_type == "Mobile" and summary.get('mobile_net_rssi_dbm') is not None: rssi_val = summary.get('mobile_net_rssi_dbm')
        elif conn_type == "BLE" and summary.get('ble_rssi_dbm') is not None: rssi_val = summary.get('ble_rssi_dbm')
        
        conn_details = f"{conn_type}"
        if rssi_val is not None: conn_details += f" ({rssi_val}{rssi_unit})"
        if False : lines.append(StatusFormatter._format_field('Connect', conn_details))

        # Line 6: Work Area (if applicable)
        current_area = summary.get('current_working_area')
        sys_status_code = summary.get("sys_status_code")
        is_working_type_activity = sys_status_code in [
            PyMammotionWorkMode.MODE_WORKING, PyMammotionWorkMode.MODE_PAUSE, PyMammotionWorkMode.MODE_RETURNING
        ]
        if current_area and current_area != "N/A" and current_area != "Location Unknown" and current_area != "In dock":
            lines.append(StatusFormatter._format_field('Area', current_area))
        elif is_working_type_activity and current_area == "N/A": # Working but area name not resolved
            lines.append(StatusFormatter._format_field('Area', "Working (Area N/A)"))


        # Line 7: Work Progress (if working/paused)
        if summary.get('is_working') or summary.get('activity', '').lower() == 'paused':
            prog_percent = summary.get('work_progress_percent')
            rem_time = summary.get('remaining_job_time_min')
            blade_h = summary.get('blade_height_mm')
            speed_mps = summary.get('mowing_speed_mps')

            prog_line_parts = []
            if prog_percent is not None: prog_line_parts.append(f"Prog: {prog_percent}%")
            if rem_time is not None and rem_time >=0: prog_line_parts.append(f"Rem: {int(rem_time)}m")
            if prog_line_parts: lines.append("         " + "  ".join(prog_line_parts))


            work_val_parts = []
            if blade_h is not None: work_val_parts.append(f"Blade: {blade_h}mm")
            if speed_mps is not None: work_val_parts.append(f"Speed: {speed_mps:.1f}m/s")
            if work_val_parts: lines.append(f"{'WorkVals'.ljust(label_w)}: {', '.join(work_val_parts)}")
            
        return "\n".join(lines)

    @staticmethod
    def format_detailed_text(summary: Dict[str, Any]) -> str:
        if not summary or summary.get("error"):
            return "--- Current Mower Status ---\n  No data or error fetching status.\n-------------------------------------\n"

        output = ["\n--- Current Mower Status ---"]
        # Enhanced preferred order for better grouping in detailed view
        preferred_order = [
            # Device Info
            "device_name", "nickname", "serial_number",
            # Core Status
            "activity", "error_code", "sys_status_code",
            # Power
            "battery_percent", "is_charging", "is_docked", "charge_state_code",
            "charge_rate_percent_per_minute", "charge_time_to_80_min", "charge_time_to_100_min",
            # Work Progress
            "is_working", "work_progress_percent", "remaining_job_time_min", "total_job_time_min", "elapsed_job_time_min",
            "total_area_to_mow_sqm", "blade_height_mm", "mowing_speed_mps",
            # Location & Area
            "current_working_area", "work_zone_hash", "position_certainty", "position_certainty_code",
            "mower_latitude", "mower_longitude", "rtk_fix_latitude", "rtk_fix_longitude", "docked_inferred_rtk",
            # RTK
            "rtk_status", "rtk_status_code", "rtk_gps_stars", "l1_satellites", "l2_satellites",
            # Connectivity
            "connection_type", "wifi_rssi_dbm", "mobile_net_rssi_dbm", "ble_rssi_dbm",
            # Timestamp
            "sys_time_stamp"
        ]

        display_items = {}
        for key, value in summary.items():
            if value is None or (isinstance(value, str) and value.lower() == "n/a"):
                continue

            # Specific formatting for detailed view
            if key in ["charge_time_to_80_min", "charge_time_to_100_min",
                       "remaining_job_time_min", "total_job_time_min", "elapsed_job_time_min"]:
                if isinstance(value, (int, float)) and value >= 0: # Show 0 minutes if applicable
                    display_items[key] = f"{value:.0f} minutes"
                else: continue
            elif key == "charge_rate_percent_per_minute":
                 if isinstance(value, float): display_items[key] = f"{value:.2f} %/min"
                 else: continue
            elif key == "sys_time_stamp":
                try: display_items[key] = datetime.fromtimestamp(int(value)).isoformat()
                except: display_items[key] = str(value)
            elif isinstance(value, float): # General float formatting
                display_items[key] = f"{value:.2f}"
            else:
                display_items[key] = str(value)

        printed_keys = set()
        for key in preferred_order:
            if key in display_items:
                # Make keys more readable
                formatted_key = key.replace('_', ' ').replace(' dbm', ' dBm').title()
                output.append(f"  {formatted_key.ljust(35)}: {display_items[key]}")
                printed_keys.add(key)

        # Print any remaining items not in preferred_order
        for key, value_str in display_items.items():
            if key not in printed_keys:
                 formatted_key = key.replace('_', ' ').replace(' dbm', ' dBm').title()
                 output.append(f"  {formatted_key.ljust(35)}: {value_str}")

        output.append("-------------------------------------\n")
        return "\n".join(output)

# --- Mower Controller ---
class MowerController:
    def __init__(self, config: Config):
        self.config = config
        self.active_mower_device: Optional[MammotionBaseCloudDevice] = None
        self.cli_exit_event = asyncio.Event()
        self.continuous_reporting_started = False
        self._mammotion_http: Optional[MammotionHTTP] = None
        self._cloud_client: Optional[CloudIOTGateway] = None
        self._mqtt_client: Optional[MammotionMQTT] = None
        self._cloud_mqtt_wrapper: Optional[MammotionCloud] = None
        self.last_activity_for_notification: Optional[str] = None
        self.last_progress_for_notification: Optional[Any] = None
        self._periodic_status_task: Optional[asyncio.Task] = None
        self.mow_defaults: Dict[str, Any] = {}

        self._last_battery_reading_percent: Optional[int] = None
        self._last_battery_reading_time: Optional[datetime] = None
        self._charge_rate_ewma_percent_per_minute: Optional[float] = None
        self._EWMA_ALPHA: float = 0.3
        self._last_printed_sys_time_stamp: Optional[int] = None

    async def __aenter__(self):
        logger.info("MowerController entering context...")
        await self._load_mow_defaults()
        if not await self.connect_and_initialize_mower():
            logger.error("Failed to connect and initialize mower during context entry.")
        else:
            logger.info(f"Successfully connected to: {self.active_mower_device._cloud_device.deviceName if self.active_mower_device else 'Unknown'}")
            self._periodic_status_task = asyncio.create_task(self.periodic_status_monitor())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logger.info("MowerController exiting context. Initiating shutdown...")
        self.cli_exit_event.set()
        if self._periodic_status_task and not self._periodic_status_task.done():
            logger.info("Cancelling periodic status monitor task...")
            self._periodic_status_task.cancel()
            try:
                await self._periodic_status_task
            except asyncio.CancelledError:
                logger.info("Periodic status monitor task cancelled.")
            except Exception as e:
                logger.warning(f"Exception during periodic status monitor task cancellation: {e}")
        await self.save_map_to_cache()
        await self._app_shutdown_logic()
        logger.info("MowerController context exit complete.")

    async def _app_shutdown_logic(self):
        logger.info("Application shutdown sequence initiated by MowerController...")
        if self.active_mower_device:
            logger.info(f"Cleaning up resources for device: {self.active_mower_device._cloud_device.deviceName}...")
            try:
                if self.continuous_reporting_started:
                    logger.info("Stopping continuous IoT system reporting...")
                    stop_rpt_type_values = [rt.value for rt in Constants.RPT_INFO_TYPES_FOR_SHUTDOWN_STOP]
                    try:
                        await asyncio.wait_for(
                            self._execute_mower_command(
                                "request_iot_sys",
                                params={
                                    "rpt_act": RptAct.RPT_STOP.value,
                                    "rpt_info_type": stop_rpt_type_values,
                                    "timeout": 0, "period": 0, "no_change_period": 0, "count": 0
                                },
                                user_friendly_name="stop_iot_reporting"
                            ), timeout=3.0
                        )
                    except asyncio.TimeoutError:
                        logger.warning("Timeout stopping IoT sys reporting during shutdown.")
                    except MowerCommandError as e_stop_rpt_cmd:
                        logger.warning(f"MowerCommandError stopping IoT sys reporting: {e_stop_rpt_cmd}")
                    except Exception as e_stop_rpt:
                        logger.warning(f"Error stopping IoT sys reporting: {e_stop_rpt}")
                    self.continuous_reporting_started = False

                if hasattr(self.active_mower_device, 'stop_sync') and callable(getattr(self.active_mower_device, 'stop_sync')):
                    logger.info("Calling device stop_sync()...")
                    try:
                        if asyncio.iscoroutinefunction(self.active_mower_device.stop_sync):
                             await self.active_mower_device.stop_sync()
                        else:
                             self.active_mower_device.stop_sync()
                    except Exception as e_stop_sync:
                        logger.warning(f"Error during device stop_sync: {e_stop_sync}")

                if self._mqtt_client and self._mqtt_client.is_connected:
                    logger.info("Disconnecting MQTT client...")
                    self._mqtt_client.disconnect()
                    for _ in range(5):
                        if not self._mqtt_client.is_connected: break
                        await asyncio.sleep(0.1)
                    if self._mqtt_client.is_connected:
                        logger.warning("MQTT client still shows connected after disconnect request.")
                    else:
                        logger.info("MQTT client disconnected.")
            except Exception as e:
                logger.error(f"Error during device resource cleanup: {e}", exc_info=True)
            finally:
                self.active_mower_device = None

        if self._mammotion_http and hasattr(self._mammotion_http, 'close_session') and callable(self._mammotion_http.close_session):
            logger.info("Closing MammotionHTTP session...")
            await self._mammotion_http.close_session()

    async def _login_to_mammotion(self) -> bool:
        self._mammotion_http = MammotionHTTP()
        self._cloud_client = CloudIOTGateway(self._mammotion_http)
        logger.info("Attempting login...")
        login_successful = await self._mammotion_http.login(self.config.email, self.config.password)
        if not login_successful or not hasattr(self._mammotion_http, 'login_info') or not self._mammotion_http.login_info:
            raise MowerConnectionError("Login failed or login_info missing.")
        logger.info("Login successful.")
        return True

    async def _setup_cloud_gateway(self) -> Optional[str]:
        if not self._mammotion_http or not self._mammotion_http.login_info:
            raise MowerConnectionError("MammotionHTTP login_info not available for cloud setup.")
        country_code = self._mammotion_http.login_info.userInformation.domainAbbreviation

        logger.info("Setting up cloud gateway...")
        steps = [
            ("get_region", lambda: self._cloud_client.get_region(country_code)),
            ("cloud_connect", lambda: self._cloud_client.connect()),
            ("login_by_oauth", lambda: self._cloud_client.login_by_oauth(country_code)),
            ("aep_handle", lambda: self._cloud_client.aep_handle()),
            ("session_by_auth_code", lambda: self._cloud_client.session_by_auth_code()),
            ("list_binding_by_account", lambda: self._cloud_client.list_binding_by_account())
        ]
        for name, step_func in steps:
            logger.info(f"Executing cloud setup step: {name}...")
            if not await step_func():
                raise MowerConnectionError(f"Cloud setup step '{name}' failed.")

        logger.info("Cloud gateway setup complete.")
        return country_code

    async def _select_luba_device(self) -> Optional[AliyunDevice]:
        if not (hasattr(self._cloud_client, 'devices_by_account_response') and
                self._cloud_client.devices_by_account_response and
                self._cloud_client.devices_by_account_response.data and
                self._cloud_client.devices_by_account_response.data.data):
            logger.warning("No devices in devices_by_account_response.")
            return None

        all_aliyun_devices: List[AliyunDevice] = self._cloud_client.devices_by_account_response.data.data
        luba_device_objects = [d for d in all_aliyun_devices if d.deviceName.startswith(("Luba", "Yuka"))] # Include Yuka

        if not luba_device_objects:
            logger.warning("No Luba or Yuka (or compatible) devices found.")
            return None

        device_info_selected: Optional[AliyunDevice] = None
        if len(luba_device_objects) == 1:
            device_info_selected = luba_device_objects[0]
            logger.info(f"Found device: {device_info_selected.deviceName} (Nickname: {device_info_selected.nickName or 'N/A'}, IoT ID: {device_info_selected.iotId})")
        else:
            print("Multiple devices found. Please select one:")
            for idx, dev_obj in enumerate(luba_device_objects, 1):
                print(f"  {idx}. {dev_obj.deviceName} (Nickname: {dev_obj.nickName or 'N/A'})")
            while True:
                try:
                    choice_str = await asyncio.to_thread(input, f"Enter choice (1-{len(luba_device_objects)}): ")
                    choice_idx = int(choice_str) - 1
                    if 0 <= choice_idx < len(luba_device_objects):
                        device_info_selected = luba_device_objects[choice_idx]
                        logger.info(f"Selected device: {device_info_selected.deviceName} (Nickname: {device_info_selected.nickName or 'N/A'})")
                        break
                    else:
                        print("Invalid choice. Please try again.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
        return device_info_selected

    async def _initialize_mqtt_client(self) -> bool:
        if not self._cloud_client: raise MowerConnectionError("Cloud client not initialized for MQTT setup.")

        required_attrs = {
            ('region_response.data.regionId', self._cloud_client): "Missing regionId",
            ('aep_response.data.productKey', self._cloud_client): "Missing productKey",
            ('aep_response.data.deviceName', self._cloud_client): "Missing deviceName for MQTT",
            ('aep_response.data.deviceSecret', self._cloud_client): "Missing deviceSecret",
            ('session_by_authcode_response.data.iotToken', self._cloud_client): "Missing iotToken",
            ('client_id', self._cloud_client): "Missing client_id"
        }
        for (attr_path, obj), err_msg in required_attrs.items():
            current = obj
            try:
                for part in attr_path.split('.'): current = getattr(current, part)
                if not current: raise AttributeError(f"{attr_path} resolved to a falsy value.")
            except AttributeError as e:
                raise MowerConnectionError(f"MQTT Init Error: {err_msg} (Attribute Error: {e})")

        mqtt_region_id = self._cloud_client.region_response.data.regionId
        mqtt_product_key = self._cloud_client.aep_response.data.productKey
        mqtt_device_name_for_mqtt_auth = self._cloud_client.aep_response.data.deviceName
        mqtt_device_secret = self._cloud_client.aep_response.data.deviceSecret
        mqtt_iot_token = self._cloud_client.session_by_authcode_response.data.iotToken
        mqtt_client_id = self._cloud_client.client_id

        self._mqtt_client = MammotionMQTT(
            region_id=mqtt_region_id, product_key=mqtt_product_key,
            device_name=mqtt_device_name_for_mqtt_auth, device_secret=mqtt_device_secret,
            iot_token=mqtt_iot_token, client_id=mqtt_client_id, cloud_client=self._cloud_client
        )
        self._cloud_mqtt_wrapper = MammotionCloud(self._mqtt_client, cloud_client=self._cloud_client)
        self._cloud_mqtt_wrapper.connect_async()

        logger.info(f"Waiting up to {self.config.mqtt_connection_timeout} seconds for MQTT connection...")
        for i in range(self.config.mqtt_connection_timeout):
            if self._mqtt_client.is_connected:
                logger.info("MQTT connected successfully.")
                return True
            logger.debug(f"MQTT not connected, waiting... (attempt {i+1}/{self.config.mqtt_connection_timeout})")
            await asyncio.sleep(1.0)

        raise MowerConnectionError(f"MQTT client did not connect within {self.config.mqtt_connection_timeout}s.")

    async def _initialize_active_mower_device(self, device_info_selected: AliyunDevice):
        if not self._cloud_mqtt_wrapper:
            raise MowerConnectionError("MQTT wrapper not available for device initialization.")

        self.active_mower_device = MammotionBaseCloudDevice(
            mqtt=self._cloud_mqtt_wrapper, cloud_device=device_info_selected,
            state_manager=StateManager(MowingDevice())
        )
        logger.info(f"Device object for {self.active_mower_device._cloud_device.deviceName} initialized.")

    async def _request_continuous_status_updates(self, reason: str = "Command Executed"):
        if not self.active_mower_device:
            logger.warning(f"Cannot request continuous status updates ({reason}): Mower not connected.")
            return

        # Always re-request to ensure it's active, similar to HA's behavior.
        logger.info(f"Requesting continuous status reporting ({reason}) via request_iot_sys (count=0)...")
        try:
            rpt_type_values = [rt.value for rt in Constants.CORE_RPT_INFO_TYPES_FOR_CONTINUOUS_REPORTING]
            await self._execute_mower_command(
                "request_iot_sys",
                params={
                    "rpt_act": RptAct.RPT_START.value, "rpt_info_type": rpt_type_values,
                    "timeout": 10000, "period": 3000, "no_change_period": 4000, "count": 0
                },
                user_friendly_name=f"{reason}_start_continuous_reporting"
            )
            logger.info(f"Continuous status reporting requested ({reason}).")
            self.continuous_reporting_started = True # Set flag after successful request
        except MowerCommandError as e:
            logger.warning(f"Failed to request continuous IoT sys reporting ({reason}): {e}. Will rely on polls.")
        except Exception as e_req_status:
            logger.error(f"Unexpected error requesting continuous status updates ({reason}): {e_req_status}", exc_info=True)


    async def _perform_initial_device_sync(self):
        if not self.active_mower_device: raise MowerConnectionError("Active mower device not set for initial sync.")

        cached_map = await self.load_map_from_cache()
        if cached_map and self.active_mower_device.mower:
            self.active_mower_device.mower.map = cached_map
            logger.info("Loaded map data from cache.")

        await self._execute_mower_command("get_report_cfg", user_friendly_name="initial_get_report_cfg")

        await self._execute_mower_command( "allpowerfull_rw", params={"rw_id": 5, "rw": 1, "context": 1}, user_friendly_name="sync_rtk_dock_location" )
        await asyncio.sleep(0.5)
        await self.attempt_to_populate_maps(reason="Initial Connect")
        
        await self._request_continuous_status_updates(reason="initial_sync")


    async def connect_and_initialize_mower(self) -> bool:
        if not self.config.email or not self.config.password:
            logger.error("Email and Password are required in config.")
            return False
        try:
            await self._login_to_mammotion()
            await self._setup_cloud_gateway()

            device_info_selected = await self._select_luba_device()
            if not device_info_selected: return False

            await self._initialize_mqtt_client()
            await self._initialize_active_mower_device(device_info_selected)
            await self._perform_initial_device_sync()
            return True
        except (MowerConnectionError, MowerCommandError, ClientError, SetupException) as e:
            logger.error(f"Connect/init failed: {type(e).__name__} - {e}", exc_info=False)
            await self._cleanup_failed_connection()
            return False
        except Exception as e:
            logger.error(f"Unexpected error during connect/init: {e}", exc_info=True)
            await self._cleanup_failed_connection()
            return False

    async def _cleanup_failed_connection(self):
        self.active_mower_device = None
        self.continuous_reporting_started = False
        if self._mqtt_client and self._mqtt_client.is_connected:
            self._mqtt_client.disconnect()
        if self._mammotion_http and hasattr(self._mammotion_http, 'close_session'):
            await self._mammotion_http.close_session()
        self._mammotion_http = None
        self._cloud_client = None
        self._mqtt_client = None
        self._cloud_mqtt_wrapper = None

    async def load_map_from_cache(self) -> Optional[HashList]:
        if os.path.exists(self.config.map_cache_file):
            try:
                with open(self.config.map_cache_file, 'r') as f:
                    cached_data_dict = json.load(f)
                if cached_data_dict:
                    loaded_map = HashList.from_dict(cached_data_dict)
                    logger.info(f"Successfully loaded map data from {self.config.map_cache_file} using from_dict.")
                    return loaded_map
            except Exception as e:
                logger.error(f"Error loading map cache from {self.config.map_cache_file}: {type(e).__name__} - {e}")
        return None

    async def save_map_to_cache(self):
        if self.active_mower_device and self.active_mower_device.mower and self.active_mower_device.mower.map:
            try:
                map_data_dict = self.active_mower_device.mower.map.to_dict()
                with open(self.config.map_cache_file, 'w') as f:
                    json.dump(map_data_dict, f, indent=2)
                logger.info(f"Map data saved to cache: {self.config.map_cache_file}")
            except Exception as e:
                logger.error(f"Error saving map cache to {self.config.map_cache_file}: {e}")
        else:
            logger.info("No map data to save to cache or mower not active.")

    async def _load_mow_defaults(self):
        default_settings = {
            "speed": 0.4, "blade_height": 60, "mowing_laps": "ONE",
            "job_mode": "BORDER_FIRST", "obstacle_laps": "NONE",
            "channel_mode": "SINGLE_GRID", "ultra_wave": "NORMAL", 
            "channel_width": 25, "toward": 0, "toward_included_angle": 90,
            "toward_mode": "RELATIVE_ANGLE", "rain_tactics": 1,
        }
        try:
            if os.path.exists(self.config.mow_defaults_file):
                with open(self.config.mow_defaults_file, 'r') as f:
                    loaded_defaults = json.load(f)
                self.mow_defaults = {**default_settings, **loaded_defaults}
                logger.info(f"Loaded and merged mow defaults from {self.config.mow_defaults_file}")
            else:
                self.mow_defaults = default_settings
                logger.info(f"{self.config.mow_defaults_file} not found. Using hardcoded OperationSettings defaults.")
                await self._save_mow_defaults()
        except Exception as e:
            logger.error(f"Error loading mow defaults: {e}. Using hardcoded defaults.")
            self.mow_defaults = default_settings

    async def _save_mow_defaults(self):
        try:
            with open(self.config.mow_defaults_file, 'w') as f:
                json.dump(self.mow_defaults, f, indent=2)
            logger.info(f"Mow defaults saved to {self.config.mow_defaults_file}")
        except IOError as e:
            logger.error(f"Could not write mow defaults to {self.config.mow_defaults_file}: {e}")

    async def _execute_mower_command(self, pymammotion_cmd: str, params: Optional[Dict] = None, user_friendly_name: Optional[str] = None):
        log_cmd_name = user_friendly_name if user_friendly_name else pymammotion_cmd
        params_str = str(params) if params else "{}"
        if len(params_str) > 100: params_str = params_str[:100] + "..."
        logger.debug(f"Executing command '{log_cmd_name}' (library cmd: '{pymammotion_cmd}') with params: {params_str}")

        if not self.active_mower_device:
            err_msg = f"Cannot execute '{log_cmd_name}': Mower not connected."
            logger.error(err_msg)
            raise MowerCommandError(err_msg)

        try:
            result = await self.active_mower_device.queue_command(pymammotion_cmd, **(params or {}))
            result_str = str(result)
            if len(result_str) > 100: result_str = result_str[:100] + "..."
            logger.debug(f"Command '{log_cmd_name}' (library cmd: '{pymammotion_cmd}') executed successfully by library. Response snippet: {'N/A' if result is None else result_str}")
            return result
        except PYMAMMOTION_COMMAND_FAILURE_EXCEPTIONS as e_lib:
            err_msg = f"Command '{log_cmd_name}' (library cmd: '{pymammotion_cmd}') failed due to library/network error: {type(e_lib).__name__} - {e_lib}"
            logger.error(err_msg)
            raise MowerCommandError(f"Command '{log_cmd_name}' failed: {e_lib}") from e_lib
        except MowerCommandError as e_mower: #This case should ideally not happen if _execute itself is the one raising it
            err_msg = f"Command '{log_cmd_name}' (library cmd: '{pymammotion_cmd}') failed: {e_mower}"
            logger.error(err_msg)
            raise
        except Exception as e_unexpected:
            err_msg = f"Unexpected error during '{log_cmd_name}' (library cmd: '{pymammotion_cmd}') execution: {e_unexpected}"
            logger.error(err_msg, exc_info=True)
            raise MowerCommandError(f"Unexpected error executing {log_cmd_name}: {e_unexpected}") from e_unexpected

    async def attempt_to_populate_maps(self, reason: str = "Data Population", force_refresh: bool = False):
        if not self.active_mower_device or not self.active_mower_device.mower:
            logger.warning(f"Cannot populate maps ({reason}): Mower not connected or MowingDevice not initialized.")
            return
        map_is_sparse = not (self.active_mower_device.mower.map and self.active_mower_device.mower.map.plan)
        if not force_refresh and not map_is_sparse:
            logger.info(f"Map data seems populated from cache or previous fetch ({reason}). Skipping full refresh.")
            return
        logger.info(f"Attempting to populate map/plan data ({reason}, ForceRefresh: {force_refresh})...")
        if not self.active_mower_device.mower.map:
            self.active_mower_device.mower.map = HashList()
        if force_refresh or map_is_sparse:
            self.active_mower_device.mower.map = HashList()
            logger.info(f"Local map data cache re-initialized for refresh ({reason}).")
        device_iot_id = self.active_mower_device._cloud_device.iotId
        try:
            logger.info(f"({reason}) Requesting area name list (get_area_name_list)...")
            await self._execute_mower_command("get_area_name_list", params={"device_id": device_iot_id}, user_friendly_name=f"{reason}_get_area_names")
            await asyncio.sleep(1.5)
            logger.info(f"({reason}) Attempting to read plans with 'read_plan' (sub_cmd=2)...")
            await self._execute_mower_command("read_plan", params={"sub_cmd": 2, "plan_index": 0}, user_friendly_name=f"{reason}_read_plans")
            logger.info(f"({reason}) 'read_plan' (sub_cmd=2) command sent. Waiting for MQTT data to populate...")
            await asyncio.sleep(1.0)
            logger.info(f"Map/plan data request sequence ({reason}) completed. Check 'maps' command.")
        except AttributeError as e_attr: # This might happen if library changes and a command is no longer on MammotionBaseCloudDevice
            logger.warning(f"A command in '{reason}' sequence might not be directly callable on active_mower_device: {e_attr}")
        except MowerCommandError as e_cmd:
            logger.error(f"Error during '{reason}' map population command: {e_cmd}")
        except Exception as e:
            logger.error(f"Unexpected error during '{reason}' map population: {e}", exc_info=True)

    def _populate_device_static_info(self, summary_dict: Dict[str, Any]):
        summary_dict["device_name"] = getattr(self.active_mower_device._cloud_device, 'deviceName', 'N/A')
        summary_dict["nickname"] = getattr(self.active_mower_device._cloud_device, 'nickName', None) # Keep as None if not set

    def _populate_device_dynamic_info(self, summary_dict: Dict[str, Any], mower_data: MowingDevice):
        if hasattr(mower_data, 'report_data') and mower_data.report_data and mower_data.report_data.dev:
            rd_dev = mower_data.report_data.dev
            summary_dict["serial_number"] = getattr(rd_dev, 'sn', "N/A")
            summary_dict["battery_percent"] = getattr(rd_dev, 'battery_val', None)
            summary_dict["charge_state_code"] = getattr(rd_dev, 'charge_state', None)
            summary_dict["sys_status_code"] = getattr(rd_dev, 'sys_status', None)
            summary_dict["base_activity_str"] = device_mode(rd_dev.sys_status) if rd_dev.sys_status is not None else "Unknown Status"
            summary_dict["error_code"] = getattr(rd_dev, 'error_code', "OK") # PyMammotion seems to map 0 to "OK"
            summary_dict["sys_time_stamp"] = getattr(rd_dev, 'sys_time_stamp', None)
        else:
            summary_dict["base_activity_str"] = "Awaiting Data"

    def _populate_connection_info(self, summary_dict: Dict[str, Any], mower_data: MowingDevice):
        if hasattr(mower_data, 'report_data') and mower_data.report_data and mower_data.report_data.connect:
            rd_connect = mower_data.report_data.connect
            summary_dict["connection_type"] = device_connection(rd_connect)
            summary_dict["wifi_rssi_dbm"] = getattr(rd_connect, 'wifi_rssi', None)
            summary_dict["mobile_net_rssi_dbm"] = getattr(rd_connect, 'mnet_rssi', None)
            summary_dict["ble_rssi_dbm"] = getattr(rd_connect, 'ble_rssi', None)
        else:
            summary_dict["connection_type"] = "N/A"

    def _populate_rtk_info(self, summary_dict: Dict[str, Any], mower_data: MowingDevice):
        if hasattr(mower_data, 'report_data') and mower_data.report_data and mower_data.report_data.rtk:
            rd_rtk = mower_data.report_data.rtk
            summary_dict["rtk_gps_stars"] = getattr(rd_rtk, 'gps_stars', None)
            summary_dict["rtk_status_code"] = getattr(rd_rtk, 'status', None)
            summary_dict["rtk_status"] = str(RTKStatus.from_value(rd_rtk.status).name) if rd_rtk.status is not None else "N/A"
            if hasattr(rd_rtk, 'co_view_stars') and rd_rtk.co_view_stars is not None:
                summary_dict["l1_satellites"] = (rd_rtk.co_view_stars >> 0) & 255
                summary_dict["l2_satellites"] = (rd_rtk.co_view_stars >> 8) & 255
        else:
            summary_dict["rtk_status"] = "N/A"

    def _populate_work_info(self, summary_dict: Dict[str, Any], mower_data: MowingDevice):
        if hasattr(mower_data, 'report_data') and mower_data.report_data and mower_data.report_data.work:
            rd_work = mower_data.report_data.work
            if hasattr(rd_work, 'area') and rd_work.area is not None:
                summary_dict["work_progress_percent"] = (rd_work.area >> 16)
                summary_dict["total_area_to_mow_sqm"] = (rd_work.area & 0xFFFF)

            if hasattr(rd_work, 'progress') and rd_work.progress is not None:
                total_time_min = rd_work.progress & 0xFFFF
                remaining_time_min = rd_work.progress >> 16 # This is actually remaining, not elapsed from this field alone
                summary_dict["total_job_time_min"] = total_time_min if total_time_min != 0 else None # Can be 0 if not in job
                summary_dict["remaining_job_time_min"] = remaining_time_min if remaining_time_min != 0 and total_time_min !=0 else None
                if total_time_min is not None and remaining_time_min is not None and total_time_min >= remaining_time_min:
                     summary_dict["elapsed_job_time_min"] = total_time_min - remaining_time_min
                else:
                     summary_dict["elapsed_job_time_min"] = None


            summary_dict["blade_height_mm"] = getattr(rd_work, 'knife_height', None)
            summary_dict["mowing_speed_mps"] = rd_work.man_run_speed / 100.0 if hasattr(rd_work, 'man_run_speed') and rd_work.man_run_speed is not None else None
        else:
            summary_dict["work_progress_percent"] = None

    def _update_charge_rate_estimate(self, current_battery_percent: Optional[int], charge_state_code: Optional[int]):
        now = datetime.now()
        if charge_state_code == 1 and current_battery_percent is not None: # Charging
            if self._last_battery_reading_percent is not None and \
               self._last_battery_reading_time is not None:

                if current_battery_percent > self._last_battery_reading_percent: # Ensure battery actually increased
                    time_diff_seconds = (now - self._last_battery_reading_time).total_seconds()
                    percent_diff = current_battery_percent - self._last_battery_reading_percent

                    if time_diff_seconds > 10 and percent_diff > 0: # Min 10s interval and actual increase
                        current_rate_ppm = (percent_diff / time_diff_seconds) * 60.0

                        if self._charge_rate_ewma_percent_per_minute is None:
                            self._charge_rate_ewma_percent_per_minute = current_rate_ppm
                        else:
                            self._charge_rate_ewma_percent_per_minute = \
                                (current_rate_ppm * self._EWMA_ALPHA) + \
                                (self._charge_rate_ewma_percent_per_minute * (1 - self._EWMA_ALPHA))
                        logger.debug(f"Charge rate updated (EWMA): {self._charge_rate_ewma_percent_per_minute:.2f} %/min (sample: {current_rate_ppm:.2f} %/min over {time_diff_seconds:.1f}s)")

                # Update baseline even if not increasing, to keep time fresh for next increase
                self._last_battery_reading_percent = current_battery_percent
                self._last_battery_reading_time = now

            elif self._last_battery_reading_percent is None or self._last_battery_reading_time is None: # First reading while charging
                self._last_battery_reading_percent = current_battery_percent
                self._last_battery_reading_time = now
                logger.debug(f"Charge baseline set: {current_battery_percent}% at {now}")

        else: # Not charging or battery percent unknown
            if self._last_battery_reading_percent is not None or self._last_battery_reading_time is not None: # Log reset only if there was a baseline
                 logger.debug("Not charging or battery percent unknown, resetting charge baseline.")
            self._last_battery_reading_percent = None
            self._last_battery_reading_time = None

            if charge_state_code != 1: # Explicitly not charging
                 if self._charge_rate_ewma_percent_per_minute is not None: # Log reset only if there was a rate
                    logger.debug("Not charging, EWMA charge rate reset to None.")
                 self._charge_rate_ewma_percent_per_minute = None


    def _populate_charging_info(self, summary_dict: Dict[str, Any], mower_data: MowingDevice):
        is_charging_val = False
        is_docked_val = False

        charge_state_code = summary_dict.get("charge_state_code")
        sys_status_code = summary_dict.get("sys_status_code")

        if charge_state_code is not None:
            if charge_state_code == 1: # Charging
                is_charging_val = True
                is_docked_val = True
            elif charge_state_code == 2: # Docked, not charging (e.g. full)
                is_docked_val = True
            # If sys_status is READY and charge_state is not 0 (not off charger), it's docked
            if sys_status_code == PyMammotionWorkMode.MODE_READY and charge_state_code != 0:
                is_docked_val = True

        # Infer docked status from RTK if other indicators are missing
        if not is_docked_val and mower_data.location and mower_data.location.RTK and \
           hasattr(mower_data.location.RTK, 'on_charger') and mower_data.location.RTK.on_charger == 1:
            is_docked_val = True
            summary_dict["docked_inferred_rtk"] = True # For detailed view

        summary_dict["is_charging"] = is_charging_val
        summary_dict["is_docked"] = is_docked_val
        summary_dict["charge_rate_percent_per_minute"] = self._charge_rate_ewma_percent_per_minute

        current_battery_val = summary_dict.get("battery_percent")

        logger.debug(
            f"_populate_charging_info: is_charging={is_charging_val}, "
            f"current_bat={current_battery_val}, "
            f"ewma_rate={self._charge_rate_ewma_percent_per_minute}"
        )

        if is_charging_val and current_battery_val is not None and \
           self._charge_rate_ewma_percent_per_minute is not None and \
           self._charge_rate_ewma_percent_per_minute > Constants.MIN_CHARGE_RATE_FOR_ESTIMATE:

            rate = self._charge_rate_ewma_percent_per_minute
            logger.debug(f"Calculating charge times with rate: {rate:.2f}%/min")
            if current_battery_val < 80:
                summary_dict["charge_time_to_80_min"] = (80 - current_battery_val) / rate
            else:
                summary_dict["charge_time_to_80_min"] = 0

            if current_battery_val < 100:
                summary_dict["charge_time_to_100_min"] = (100 - current_battery_val) / rate
            else:
                summary_dict["charge_time_to_100_min"] = 0

            logger.debug(
                f"Calculated charge times: to_80={summary_dict.get('charge_time_to_80_min')}, "
                f"to_100={summary_dict.get('charge_time_to_100_min')}"
            )
        else:
            summary_dict["charge_time_to_80_min"] = None
            summary_dict["charge_time_to_100_min"] = None
            if not (is_charging_val and current_battery_val is not None):
                 logger.debug("Not calculating charge times: not charging or no battery value.")
            elif self._charge_rate_ewma_percent_per_minute is None:
                 logger.debug("Not calculating charge times: EWMA rate is None.")
            elif self._charge_rate_ewma_percent_per_minute is not None and \
                 self._charge_rate_ewma_percent_per_minute <= Constants.MIN_CHARGE_RATE_FOR_ESTIMATE:
                 logger.debug(f"Not calculating charge times: EWMA rate {self._charge_rate_ewma_percent_per_minute:.2f} <= min_rate {Constants.MIN_CHARGE_RATE_FOR_ESTIMATE}")


    def _populate_location_info(self, summary_dict: Dict[str, Any], mower_data: MowingDevice):
        if mower_data.location:
            summary_dict["position_certainty_code"] = getattr(mower_data.location, 'position_type', None)
            summary_dict["position_certainty"] = str(PosType(mower_data.location.position_type).name) if summary_dict["position_certainty_code"] is not None else "N/A"

            dev_loc = mower_data.location.device
            if dev_loc and hasattr(dev_loc, 'latitude') and dev_loc.latitude is not None:
                summary_dict["mower_latitude"] = f"{dev_loc.latitude:.7f}" # For detailed view
            if dev_loc and hasattr(dev_loc, 'longitude') and dev_loc.longitude is not None:
                summary_dict["mower_longitude"] = f"{dev_loc.longitude:.7f}" # For detailed view

            rtk_loc = mower_data.location.RTK
            if rtk_loc and hasattr(rtk_loc, 'latitude') and rtk_loc.latitude is not None:
                 summary_dict["rtk_fix_latitude"] = f"{rtk_loc.latitude * 180.0 / math.pi:.7f}" # For detailed view
            if rtk_loc and hasattr(rtk_loc, 'longitude') and rtk_loc.longitude is not None:
                 summary_dict["rtk_fix_longitude"] = f"{rtk_loc.longitude * 180.0 / math.pi:.7f}" # For detailed view

            summary_dict["work_zone_hash"] = getattr(mower_data.location, 'work_zone', None)
        else:
            summary_dict["position_certainty"] = "N/A"

    def _determine_activity_and_area(self, summary_dict: Dict[str, Any], mower_data: MowingDevice):
        base_activity_str = summary_dict.get("base_activity_str", "Unknown Status")
        sys_status_code = summary_dict.get("sys_status_code")
        is_charging = summary_dict.get("is_charging", False)
        is_docked = summary_dict.get("is_docked", False)
        activity_display = base_activity_str

        if is_charging: # Override base activity if charging
            activity_display = "Charging"
        elif is_docked and sys_status_code == PyMammotionWorkMode.MODE_READY : # Docked and ready
            activity_display = "Docked"
        # Add other overrides if needed, e.g., "Paused", "Returning", etc.

        is_working_activity = sys_status_code == PyMammotionWorkMode.MODE_WORKING
        summary_dict["is_working"] = is_working_activity
        summary_dict["activity"] = activity_display

        current_area_name_val = "Location Unknown" # Default
        if is_docked:
            current_area_name_val = "In dock"
        elif mower_data.location:
            work_zone_hash = summary_dict.get("work_zone_hash")
            position_certainty_code = summary_dict.get("position_certainty_code")
            position_certainty_str = summary_dict.get("position_certainty", "Unknown")


            if work_zone_hash is not None and work_zone_hash != 0: # In a numbered zone
                if hasattr(mower_data, 'map') and mower_data.map and hasattr(mower_data.map, 'area_name') and mower_data.map.area_name:
                    found_area_obj = next((area_obj for area_obj in mower_data.map.area_name if hasattr(area_obj, 'hash') and area_obj.hash == work_zone_hash), None)
                    if found_area_obj and getattr(found_area_obj, 'name', ''):
                        current_area_name_val = getattr(found_area_obj, 'name')
                    else: # Hash found but no name in map list, or name is empty
                        current_area_name_val = f"Zone {work_zone_hash}"
                else: # No map data to resolve name
                    current_area_name_val = f"Zone {work_zone_hash} (No Map)"
            elif position_certainty_code == PosType.AREA_INSIDE.value:
                 current_area_name_val = "Inside Area (Unspecified)" # Generic "inside"
            elif position_certainty_code is not None:
                 current_area_name_val = f"Outside ({position_certainty_str})"
        else: # No location data
            current_area_name_val = "Loc Data N/A"
        summary_dict["current_working_area"] = current_area_name_val

    def get_mower_status_summary(self) -> Dict[str, Any]:
        if not self.active_mower_device or not self.active_mower_device.mower:
            return {"error": "No MowerDevice data or mower not connected."}

        mower_data = self.active_mower_device.mower
        s: Dict[str, Any] = {}

        self._populate_device_static_info(s)
        self._populate_device_dynamic_info(s, mower_data)
        self._populate_connection_info(s, mower_data)
        self._populate_rtk_info(s, mower_data)
        self._populate_work_info(s, mower_data)

        current_battery_val = s.get("battery_percent")
        current_charge_state = s.get("charge_state_code")
        self._update_charge_rate_estimate(current_battery_val, current_charge_state)

        self._populate_charging_info(s, mower_data)
        self._populate_location_info(s, mower_data)
        self._determine_activity_and_area(s, mower_data)

        return s

    async def periodic_status_monitor(self):
        logger.info("Periodic status monitor started.")
        while not self.cli_exit_event.is_set():
            current_interval = self.config.base_monitoring_interval
            if not self.active_mower_device or not self.active_mower_device.mower:
                await asyncio.sleep(current_interval); continue

            summary_before_poll = self.get_mower_status_summary()

            sys_status_code = summary_before_poll.get("sys_status_code")
            is_actively_working = sys_status_code == PyMammotionWorkMode.MODE_WORKING
            is_undocked  = not summary_before_poll.get('is_docked', False)

            current_sys_time_stamp = summary_before_poll.get("sys_time_stamp")
            is_stale_or_no_timestamp = True
            if current_sys_time_stamp:
                try:
                    last_update_dt = datetime.fromtimestamp(int(current_sys_time_stamp))
                    is_stale_or_no_timestamp = (datetime.now() - last_update_dt).total_seconds() > 300 # 5 minutes
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse sys_time_stamp for stale check: {current_sys_time_stamp}")

            if is_actively_working:
                current_interval = self.config.base_monitoring_interval // self.config.work_monitoring_divider

            should_poll = False
            reason_for_poll = []
            if not self.continuous_reporting_started: reason_for_poll.append("ContRptOff"); should_poll = True
            if is_actively_working: reason_for_poll.append("Working"); should_poll = True
            if is_undocked and not is_actively_working : reason_for_poll.append("UndockedNotWorking"); should_poll = True
            if is_stale_or_no_timestamp: reason_for_poll.append("StaleData"); should_poll = True

            summary_to_print = summary_before_poll
            polled_and_got_new_data = False

            if should_poll:
                logger.debug(f"Polling (Reason: {', '.join(reason_for_poll)}): Requesting full update (get_report_cfg)...")
                previous_timestamp_before_poll = summary_before_poll.get("sys_time_stamp")
                try:
                    await self._execute_mower_command("get_report_cfg", user_friendly_name="periodic_get_report_cfg")
                    await asyncio.sleep(0.5) # Give a moment for data to be processed
                    summary_to_print = self.get_mower_status_summary()
                    new_timestamp_after_poll = summary_to_print.get("sys_time_stamp")

                    if new_timestamp_after_poll is not None and \
                       (previous_timestamp_before_poll is None or new_timestamp_after_poll > previous_timestamp_before_poll):
                        polled_and_got_new_data = True
                        logger.debug(f"Poll successful, new data timestamp: {new_timestamp_after_poll}")
                    elif new_timestamp_after_poll is not None and previous_timestamp_before_poll is not None and new_timestamp_after_poll == previous_timestamp_before_poll:
                        logger.info("Poll executed, but server did not provide newer status data (timestamp unchanged).")
                    else:
                        logger.info("Poll executed, but new status data seems incomplete or timestamp is missing/unchanged.")

                except MowerCommandError as e: logger.warning(f"Periodic get_report_cfg failed: {e}")
                except Exception as e: logger.warning(f"Unexpected error in periodic get_report_cfg: {e}")

            current_data_timestamp = summary_to_print.get("sys_time_stamp")
            should_print_this_cycle = False

            if current_data_timestamp is not None:
                if self._last_printed_sys_time_stamp is None or current_data_timestamp > self._last_printed_sys_time_stamp:
                    should_print_this_cycle = True
                elif should_poll and polled_and_got_new_data: # Force print if we explicitly polled and got new data, even if TS didn't change (unlikely but possible)
                    should_print_this_cycle = True
            elif self._last_printed_sys_time_stamp is None: # First time, print what we have
                 should_print_this_cycle = True

            if should_print_this_cycle:
                print(StatusFormatter.format_summary_text(summary_to_print)) # Use print for direct terminal output
                self._last_printed_sys_time_stamp = current_data_timestamp

            current_activity_for_notification = summary_to_print.get('activity')
            current_progress_for_notification_val = summary_to_print.get('work_progress_percent')

            if self.last_activity_for_notification and current_activity_for_notification:
                act_low = current_activity_for_notification.lower(); last_act_low = self.last_activity_for_notification.lower()
                was_working = "working" in last_act_low or "mowing" in last_act_low
                is_idle_or_completed = any(s in act_low for s in ["idle", "charging", "completed", "standby", "docked"]) or \
                                      (summary_to_print.get("sys_status_code") == PyMammotionWorkMode.MODE_READY)

                progress_val_prev = None
                if isinstance(self.last_progress_for_notification, (int, float)):
                    progress_val_prev = self.last_progress_for_notification
                elif isinstance(self.last_progress_for_notification, str) and '%' in self.last_progress_for_notification:
                    try: progress_val_prev = int(self.last_progress_for_notification.replace('%',''))
                    except ValueError: pass

                if was_working and is_idle_or_completed and progress_val_prev is not None and progress_val_prev >= 95:
                    logger.info(f"NOTIFICATION: Task likely completed! Prev State: {self.last_activity_for_notification} ({self.last_progress_for_notification}%), Current State: {current_activity_for_notification}")

            self.last_activity_for_notification = current_activity_for_notification
            self.last_progress_for_notification = current_progress_for_notification_val

            try:
                await asyncio.wait_for(self.cli_exit_event.wait(), timeout=current_interval)
            except asyncio.TimeoutError: pass
        logger.info("Periodic status monitor stopped.")

    async def handle_status_command(self, args: List[str]):
        summary = self.get_mower_status_summary()
        current_ts = summary.get("sys_time_stamp")
        is_stale_or_no_ts_current = True
        if current_ts:
             try: is_stale_or_no_ts_current = (datetime.now() - datetime.fromtimestamp(int(current_ts))).total_seconds() > 5
             except: pass

        if is_stale_or_no_ts_current:
            logger.debug("Status data for 'status' command is potentially stale (>5s old) or missing timestamp, triggering update...")
            try:
                await self._execute_mower_command("get_report_cfg", user_friendly_name="status_get_report_cfg")
                await asyncio.sleep(0.5)
                summary = self.get_mower_status_summary()
            except MowerCommandError as e:
                logger.warning(f"Update for 'status' command failed: {e}")

        print(StatusFormatter.format_detailed_text(summary))
        self._last_printed_sys_time_stamp = summary.get("sys_time_stamp")


    async def handle_raw_status_command(self, args: List[str]):
        if self.active_mower_device and self.active_mower_device.mower:
            summary = self.get_mower_status_summary() # Get current data for timestamp check
            current_ts = summary.get("sys_time_stamp")
            is_stale_or_no_ts_current = True
            if current_ts:
                try: is_stale_or_no_ts_current = (datetime.now() - datetime.fromtimestamp(int(current_ts))).total_seconds() > 5
                except: pass

            if is_stale_or_no_ts_current:
                logger.debug("Raw status data is potentially stale (>5s old) or missing timestamp, triggering update...")
                try:
                    await self._execute_mower_command("get_report_cfg", user_friendly_name="raw_status_get_report_cfg")
                    await asyncio.sleep(0.5) # Give a moment for data to be processed
                except MowerCommandError as e:
                    logger.warning(f"Update for 'raw_status' command failed: {e}")
            
            # After potential update, print the (possibly updated) raw data
            print("\n--- Full Raw MowingDevice Data ---")
            try:
                def custom_serializer(obj):
                    if isinstance(obj, (datetime, asyncio.Future, timedelta)): return str(obj)
                    if dataclasses.is_dataclass(obj) and not isinstance(obj, type): return dataclasses.asdict(obj)
                    # Attempt to_dict(), then __dict__, then repr() as fallbacks for complex objects
                    try: return obj.to_dict()
                    except AttributeError:
                        if hasattr(obj, '__dict__'): return obj.__dict__
                        return repr(obj) # Last resort

                # Use the potentially updated mower_data from self.active_mower_device.mower
                mower_dict_representation = self.active_mower_device.mower.to_dict()
                print(json.dumps(mower_dict_representation, indent=2, default=custom_serializer))
                self._last_printed_sys_time_stamp = self.active_mower_device.mower.report_data.dev.sys_time_stamp if self.active_mower_device.mower.report_data and self.active_mower_device.mower.report_data.dev else None

            except Exception as e:
                logger.error(f"Could not serialize MowingDevice data: {e}");
                pprint(self.active_mower_device.mower) # Fallback to pprint if json fails
            print("-------------------------------------\n")
        else: logger.info("No raw status data available.")


    async def handle_maps_plans_command(self, args: List[str]):
        if not (self.active_mower_device and self.active_mower_device.mower and
                hasattr(self.active_mower_device.mower, 'map') and self.active_mower_device.mower.map):
            logger.info("Map data missing. Try 'sync_maps' or ensure the mower is connected and has reported data.")
            return
        map_data = self.active_mower_device.mower.map
        print("\n--- Tasks/Plans (from mower.map.plan) ---")
        if map_data.plan and isinstance(map_data.plan, dict) and map_data.plan:
            collected_plans = list(map_data.plan.values())
            WEEKDAY_MAP = {1: "Sun", 2: "Mon", 3: "Tue", 4: "Wed", 5: "Thu", 6: "Fri", 7: "Sat"}
            plan_id_width, days_width, start_time_width, name_width, height_width = 21, 25, 10, 20, 6
            speed_header_str = "Speed"
            table_header_plans = ( "PlanId".ljust(plan_id_width) + " | " + "Days".ljust(days_width) + " | " +
                "Start Time".ljust(start_time_width) + " | " + "Name".ljust(name_width) + " | " +
                "Height".ljust(height_width) + " | " + speed_header_str )
            table_divider_plans = "-" * len(table_header_plans)
            print("\n" + table_header_plans + "\n" + table_divider_plans)
            try: sorted_plans = sorted(collected_plans, key=lambda p: getattr(p, 'remained_seconds', float('inf')))
            except TypeError: sorted_plans = sorted(collected_plans, key=lambda p: str(getattr(p, 'plan_id', '')))
            if not sorted_plans: print("  No plans to display.".ljust(len(table_header_plans)))
            for plan_obj in sorted_plans:
                plan_id_str = str(getattr(plan_obj, 'plan_id', 'N/A')); start_time_str = str(getattr(plan_obj, 'start_time', 'N/A'))
                task_name_str = str(getattr(plan_obj, 'task_name', 'Unnamed Plan')); knife_height_str = str(getattr(plan_obj, 'knife_height', 'N/A'))
                speed_val = getattr(plan_obj, 'speed', None); speed_str = f"{speed_val:.1f}" if isinstance(speed_val, (float, int)) else "N/A"
                days_list = [WEEKDAY_MAP.get(d, f"Day{d}") for d in getattr(plan_obj, 'weeks', []) if isinstance(d, int)]
                days_display_str = ", ".join(days_list) if days_list else "N/A"
                row = ( plan_id_str.ljust(plan_id_width) + " | " + days_display_str.ljust(days_width) + " | " +
                        start_time_str.ljust(start_time_width) + " | " + task_name_str.ljust(name_width) + " | " +
                        knife_height_str.ljust(height_width) + " | " + speed_str )
                print(row)
        else: print("  No detailed plan data found in 'mower.map.plan'.")
        if 'table_divider_plans' in locals(): print(table_divider_plans)
        print("\n\n--- Mapped Areas (from mower.map.area_name) ---")
        if map_data.area_name and isinstance(map_data.area_name, list) and map_data.area_name:
            area_name_width, area_hash_width, area_index_width = 30, 19, 5
            table_header_areas = ( "No.".ljust(area_index_width) + " | " + "Area Name".ljust(area_name_width) + " | " + "Hash".ljust(area_hash_width) )
            table_divider_areas = "-" * len(table_header_areas)
            print("\n" + table_header_areas + "\n" + table_divider_areas)
            sorted_areas = sorted(map_data.area_name, key=lambda a: getattr(a, 'name', 'zzzzzz'))
            if not sorted_areas: print("  No areas to display.".ljust(len(table_header_areas)))
            for i, area_obj in enumerate(sorted_areas):
                area_name_str = str(getattr(area_obj, 'name', 'N/A')); area_hash_str = str(getattr(area_obj, 'hash', 'N/A'))
                index_str = str(i + 1)
                row = ( index_str.ljust(area_index_width) + " | " + area_name_str.ljust(area_name_width) + " | " + area_hash_str.ljust(area_hash_width) )
                print(row)
        else: print("  No area name data found in 'mower.map.area_name'. Try 'sync_maps'.")
        if 'table_divider_areas' in locals(): print(table_divider_areas + "\n")

    async def handle_sync_maps_command(self, args: List[str]):
        try:
            await self.attempt_to_populate_maps(reason="CLI sync_maps", force_refresh=True)
            await self.save_map_to_cache()
        except MowerCommandError as e:
            logger.error(f"Error during map sync: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during map sync: {e}", exc_info=True)


    async def _display_mow_defaults_and_usage(self):
        logger.info("\n--- Current Mow Area Defaults ---")
        for key, value in self.mow_defaults.items():
            display_value = value
            if key in Constants.ENUM_SETTINGS_MAP:
                enum_class = Constants.ENUM_SETTINGS_MAP[key]
                if isinstance(value, int): # If stored as int (old way)
                    enum_name = get_enum_member_name_by_value(enum_class, value)
                    display_value = enum_name if enum_name else f"INVALID_INT_VAL({value})"
                elif isinstance(value, str): # if stored as string name (new way)
                    display_value = value 
            logger.info(f"  {key}: {display_value}")
        logger.info("--------------------------------")

        logger.info("\nUsage to start a mow: mow_areas <hash1>,<hash2>,... [setting1=value1] [setting2=value2]...")
        logger.info("Usage to show defaults: mow_areas show")
        logger.info("Usage to set defaults : mow_areas set <setting1>=<value1> [<setting2>=<value2> ...]")
        logger.info("\nIMPORTANT: For settings, use exact Enum member names (case-insensitive) from pymammotion library.")
        logger.info("           (Located in pymammotion/data/model/mowing_modes.py).")
        logger.info("  Valid Enum settings (examples):")
        for key, enum_class in Constants.ENUM_SETTINGS_MAP.items():
            member_examples = " | ".join(list(enum_class.__members__.keys())[:2])
            logger.info(f"    {key}={member_examples} ...")
        logger.info("  Other numeric settings (refer to current defaults or OperationSettings for typical ranges):")
        logger.info("    speed=0.8 (m/s) | blade_height=60 (mm) | channel_width=25 (cm)")
        logger.info("    toward=0 (degrees) | toward_included_angle=90 (degrees) | rain_tactics=1 (0=park, 1=continue)")
        logger.info(f"Defaults are loaded from '{self.config.mow_defaults_file}' if it exists, then overridden by CLI args for a specific job.")

    async def _handle_set_mow_defaults(self, params_to_set: List[str]):
        if not params_to_set:
            logger.error("No parameters provided to set. Usage: mow_areas set parameter=value ...")
            return

        temp_defaults = self.mow_defaults.copy()
        valid_changes = True

        for setting_str in params_to_set:
            if '=' not in setting_str:
                logger.error(f"Skipping invalid setting format: {setting_str}. Expected key=value.")
                valid_changes = False; continue

            key, value_str_cli = setting_str.split('=', 1)
            key_cli_norm = key.lower().strip()
            value_str_cli = value_str_cli.strip()

            if key_cli_norm not in temp_defaults:
                logger.error(f"Unknown default setting parameter: '{key_cli_norm}'. Cannot set.")
                valid_changes = False; continue
            
            original_type_or_enum_name = temp_defaults.get(key_cli_norm)
            is_enum_setting = key_cli_norm in Constants.ENUM_SETTINGS_MAP

            try:
                if is_enum_setting:
                    enum_class = Constants.ENUM_SETTINGS_MAP[key_cli_norm]
                    matched_member_name = None
                    # Try to match the input string (case-insensitive, with/without underscores) to an enum member name
                    for member_name_iter in enum_class.__members__:
                        if member_name_iter.lower() == value_str_cli.lower() or \
                           member_name_iter.lower() == value_str_cli.replace("_", "").lower() or \
                           member_name_iter.replace("_", "").lower() == value_str_cli.lower():
                            matched_member_name = member_name_iter # Store the canonical enum member name
                            break
                    if matched_member_name:
                        temp_defaults[key_cli_norm] = matched_member_name # Store as string name
                        logger.info(f"Default '{key_cli_norm}' will be set to '{matched_member_name}'.")
                    else:
                        logger.error(f"Invalid value '{value_str_cli}' for enum setting '{key_cli_norm}'. Valid names: {list(enum_class.__members__.keys())}")
                        valid_changes = False
                elif isinstance(original_type_or_enum_name, int):
                    temp_defaults[key_cli_norm] = int(value_str_cli)
                elif isinstance(original_type_or_enum_name, float):
                    temp_defaults[key_cli_norm] = float(value_str_cli)
                elif isinstance(original_type_or_enum_name, bool): # Check for bool if original was bool
                     temp_defaults[key_cli_norm] = value_str_cli.lower() in ['true', '1', 'yes', 'on']
                else: # Fallback to string if original type is not clear or was string
                    temp_defaults[key_cli_norm] = value_str_cli
                # No need for an extra log here as it was logged if successful in the enum case or will be implicitly okay for others
            except ValueError:
                expected_type_name = type(original_type_or_enum_name).__name__ if not is_enum_setting else "Enum Name"
                logger.error(f"Invalid value format for '{key_cli_norm}': '{value_str_cli}'. Expected type: {expected_type_name}.")
                valid_changes = False
            
            if not valid_changes: break # Stop processing if an error occurred

        if valid_changes:
            self.mow_defaults = temp_defaults
            await self._save_mow_defaults()
            logger.info("Mow defaults updated and saved successfully.")
        else:
            logger.error("One or more settings were invalid. Mow defaults not saved.")


    async def handle_mow_areas_command(self, args: List[str]):
        if not args or (len(args) == 1 and args[0].lower() == "show"):
            await self._display_mow_defaults_and_usage()
            return

        if len(args) > 0 and args[0].lower() == "set":
            await self._handle_set_mow_defaults(args[1:])
            return

        if not self.active_mower_device: logger.warning("Mower not connected. Cannot mow_areas."); return
        try:
            area_hashes_str = args[0]; area_hashes = [int(h.strip()) for h in area_hashes_str.split(',')]
            if not area_hashes: raise ValueError("No area hashes provided.")
        except (ValueError, IndexError): logger.error("Invalid area hashes for mowing job. Must be comma-separated integers."); return

        op_settings = OperationSettings() # Fresh OperationSettings instance for this job
        logger.info("Applying defaults to OperationSettings for current job...")

        # Apply defaults from self.mow_defaults (which stores enum names as strings)
        for key_default, value_from_defaults_dict in self.mow_defaults.items():
            key_norm = key_default.lower().strip()
            try:
                if key_norm in Constants.ENUM_SETTINGS_MAP:
                    enum_class = Constants.ENUM_SETTINGS_MAP[key_norm]
                    # value_from_defaults_dict is expected to be a string (enum member name)
                    enum_value_int = get_enum_value(enum_class, str(value_from_defaults_dict))
                    if enum_value_int is not None: setattr(op_settings, key_norm, enum_value_int)
                elif hasattr(op_settings, key_norm): # For non-enum settings
                    # Get the type of the attribute in OperationSettings to cast correctly
                    field_type = type(getattr(op_settings, key_norm, None))
                    if field_type == bool: setattr(op_settings, key_norm, str(value_from_defaults_dict).lower() in ['true', '1', 'yes'])
                    elif field_type is int: setattr(op_settings, key_norm, int(value_from_defaults_dict))
                    elif field_type is float: setattr(op_settings, key_norm, float(value_from_defaults_dict))
                    else: setattr(op_settings, key_norm, str(value_from_defaults_dict)) # Fallback to string if type is unknown
            except Exception as e_set_default: logger.warning(f"Could not apply default for {key_norm}={value_from_defaults_dict} to OperationSettings: {e_set_default}")

        logger.info("OperationSettings after applying defaults for current job:")
        pprint(dataclasses.asdict(op_settings)) # Shows current state of op_settings

        # Now, apply CLI overrides
        op_settings.areas = area_hashes # Set area hashes first

        for setting_str in args[1:]: # CLI overrides
            if '=' not in setting_str: logger.warning(f"Skipping invalid setting format: {setting_str}."); continue
            key, value_str_cli = setting_str.split('=', 1); key_cli_norm = key.lower().strip(); value_str_cli = value_str_cli.strip()
            try:
                if key_cli_norm in Constants.ENUM_SETTINGS_MAP:
                    enum_class = Constants.ENUM_SETTINGS_MAP[key_cli_norm]
                    enum_value_int = get_enum_value(enum_class, value_str_cli)
                    if enum_value_int is not None: setattr(op_settings, key_cli_norm, enum_value_int)
                elif hasattr(op_settings, key_cli_norm):
                    field_type = type(getattr(op_settings, key_cli_norm, None))
                    if field_type == bool: setattr(op_settings, key_cli_norm, value_str_cli.lower() in ['true', '1', 'yes'])
                    elif field_type is int: setattr(op_settings, key_cli_norm, int(value_str_cli))
                    elif field_type is float: setattr(op_settings, key_cli_norm, float(value_str_cli))
                    else: setattr(op_settings, key_cli_norm, value_str_cli)
                else: logger.warning(f"Unknown setting: {key_cli_norm}. Ignored for this job.")
            except ValueError as ve: logger.warning(f"Invalid value type for {key_cli_norm}: {value_str_cli}. Error: {ve}. Ignored.")
            except Exception as e_parse: logger.warning(f"Generic error parsing setting {key_cli_norm}={value_str_cli}: {e_parse}. Ignored.")

        mower_device_name = self.active_mower_device._cloud_device.deviceName
        if DeviceType.is_yuka(mower_device_name):
            logger.info("Yuka device detected. Setting blade_height to -10 in OperationSettings for this job.")
            op_settings.blade_height = -10

        logger.info(f"Final OperationSettings for this job (after CLI overrides):")
        pprint(dataclasses.asdict(op_settings))

        try:
            path_order_str = create_path_order(op_settings, mower_device_name)
            if not path_order_str or not path_order_str.strip(): logger.error(f"Generated path_order string is empty! Review op_settings."); return
            logger.info(f"Generated path_order string: '{path_order_str}'")
            gen_route_info = GenerateRouteInformation(
                one_hashs=op_settings.areas, rain_tactics=op_settings.rain_tactics, speed=op_settings.speed,
                ultra_wave=op_settings.ultra_wave, toward=op_settings.toward,
                toward_included_angle=op_settings.toward_included_angle, toward_mode=op_settings.toward_mode,
                blade_height=op_settings.blade_height, channel_mode=op_settings.channel_mode,
                channel_width=op_settings.channel_width, job_mode=op_settings.job_mode,
                edge_mode=op_settings.mowing_laps, path_order=path_order_str, obstacle_laps=op_settings.obstacle_laps )
            if DeviceType.is_luba1(mower_device_name):
                logger.info("Luba 1 device detected. Adjusting toward_mode and toward_included_angle to 0 for GenerateRouteInformation.")
                gen_route_info.toward_mode = 0; gen_route_info.toward_included_angle = 0
            logger.debug("Full GenerateRouteInformation object:"); pprint(dataclasses.asdict(gen_route_info))
            await self._execute_mower_command("generate_route_information", params={"generate_route_information": gen_route_info}, user_friendly_name="mow_generate_route")
            logger.info("'generate_route_information' sent. Waiting briefly..."); await asyncio.sleep(3.0)
            await self._execute_mower_command("start_job", user_friendly_name="mow_start_job")
            logger.info("Custom mowing job started via 'start_job'.")
            await self._request_continuous_status_updates(reason="mow_areas_job_start")
            logger.info("mow_areas sequence complete. Monitor status.")
        except (MowerCommandError, ValueError) as e: logger.error(f"Error during mow_areas execution: {e}", exc_info=isinstance(e, ValueError))
        except Exception as e_mow: logger.error(f"Unexpected error during mow_areas execution: {e_mow}", exc_info=True)


    async def handle_start_command(self, args: List[str]):
        if not args: logger.info("Usage: start <plan_id_or_name>"); return
        plan_ref = " ".join(args); plan_id_to_start = None
        if not (self.active_mower_device and self.active_mower_device.mower and
                hasattr(self.active_mower_device.mower, 'map') and self.active_mower_device.mower.map and
                hasattr(self.active_mower_device.mower.map, 'plan') and self.active_mower_device.mower.map.plan):
            logger.warning("Plan data not available. Cannot start by name. Try 'sync_maps' or use plan ID directly.")
            if plan_ref.isdigit(): plan_id_to_start = plan_ref
            else: logger.error("Cannot resolve plan name to ID without map data."); return
        else:
            if plan_ref.isdigit():
                plan_id_to_start = plan_ref; found_by_id = False
                for p_id_key, p_obj in self.active_mower_device.mower.map.plan.items():
                    if str(getattr(p_obj, 'plan_id', p_id_key)) == plan_ref:
                        plan_id_to_start = str(getattr(p_obj, 'plan_id', p_id_key))
                        logger.info(f"Matched plan by ID: '{getattr(p_obj, 'task_name', 'N/A')}' with ID: {plan_id_to_start}"); found_by_id = True; break
                if not found_by_id:
                     logger.warning(f"Plan ID {plan_ref} not found among actual plan IDs in local data. Will attempt to start with '{plan_ref}' as ID if it's purely numeric.")
                     if not plan_ref.isdigit(): plan_id_to_start = None # Ensure it's still None if not a digit after warning
            if not plan_id_to_start: # Try by name if not found by ID or if original input wasn't a digit
                found_plan_obj = None
                for p_id_key, p_obj in self.active_mower_device.mower.map.plan.items():
                    task_name = getattr(p_obj, 'task_name', None)
                    if task_name and task_name.lower() == plan_ref.lower(): found_plan_obj = p_obj; break
                if found_plan_obj:
                    plan_id_to_start = str(getattr(found_plan_obj, 'plan_id', None))
                    if not plan_id_to_start: logger.error(f"Found plan by name '{plan_ref}' but its ID is missing or invalid."); return
                    logger.info(f"Found plan by name: '{getattr(found_plan_obj, 'task_name', plan_ref)}' with ID: {plan_id_to_start}")
                else: logger.error(f"Plan with name or ID '{plan_ref}' not found in local map data."); return
        if not plan_id_to_start: logger.error(f"Could not determine a plan ID for '{plan_ref}'."); return
        logger.info(f"Attempting to start task with resolved plan_id: {plan_id_to_start}")
        try:
            await self._execute_mower_command("single_schedule", params={"plan_id": str(plan_id_to_start)}, user_friendly_name=f"start_plan_{plan_id_to_start}")
            logger.info(f"Start command ('single_schedule') sent for plan_id {plan_id_to_start}. Monitor status.")
            await self._request_continuous_status_updates(reason=f"start_plan_{plan_id_to_start}")
        except MowerCommandError as e_start: logger.error(f"Error sending 'single_schedule' command: {e_start}")
        except Exception as e_start_unexpected: logger.error(f"Unexpected error sending 'single_schedule': {e_start_unexpected}", exc_info=True)

    async def _dispatch_simple_command(self, user_command_name: str, pymammotion_cmd: str, params: Optional[Dict] = None, request_continuous_updates: bool = False):
        """Dispatches a simple command, logs errors, and optionally requests continuous updates."""
        logger.info(f"Dispatching command '{user_command_name}' (library cmd: '{pymammotion_cmd}')...")
        try:
            await self._execute_mower_command(pymammotion_cmd, params, user_friendly_name=user_command_name)
            logger.info(f"'{user_command_name}' command processed by library.")
            
            if request_continuous_updates:
                await self._request_continuous_status_updates(reason=f"{user_command_name}_command")
            else:
                # Fallback to a single poll if continuous updates are not specifically requested for this command
                await asyncio.sleep(0.5) # Brief pause for command to propagate
                if self.active_mower_device:
                    await self._execute_mower_command("get_report_cfg", user_friendly_name=f"post_{user_command_name}_update")
        except MowerCommandError as e: # Already logged by _execute_mower_command
            # No need to re-log the same error message, but we catch to prevent it from stopping the CLI loop for simple commands
            pass # Error is already logged by _execute_mower_command
        except Exception as e_simple_unexpected:
            logger.error(f"Unexpected error related to '{user_command_name}' command: {e_simple_unexpected}", exc_info=True)

    async def handle_blade_height_command(self, args: List[str]):
        if not args or not args[0].isdigit(): 
            logger.error("Usage: blade_height <height_in_mm>")
            return
        try:
            height = int(args[0])
            # request_continuous_updates defaults to False, so it will do a single poll.
            await self._dispatch_simple_command("set_blade_height", "set_blade_height", {"height": height})
        except ValueError: 
            logger.error("Invalid height. Must be an integer.")


    async def handle_raw_command(self, args: List[str]):
        if len(args) < 1:
            logger.error("Usage: rawcmd <command_name> [json_params_as_string_or_key=value pairs]"); return
        cmd_name = args[0]; param_args = args[1:]; params = {}
        if not param_args: pass # No params, just cmd_name
        elif param_args[0].startswith('{') and param_args[-1].endswith('}'): # Check if it looks like a JSON string
            json_params_str = " ".join(param_args) # Reconstruct if spaced out
            try:
                params = json.loads(json_params_str)
                if not isinstance(params, dict): logger.error("JSON params must be a valid JSON object."); return
            except json.JSONDecodeError as e: logger.error(f"Invalid JSON parameters: {e}"); return
        else: # Key-value pairs
            for p_arg in param_args:
                if '=' not in p_arg: logger.error(f"Invalid parameter format: {p_arg}. Expected key=value or a single JSON string."); return
                key, value_str = p_arg.split('=', 1)
                try: # Attempt to convert to int/float if possible, else bool, else string
                    if '.' in value_str: params[key] = float(value_str)
                    else: params[key] = int(value_str)
                except ValueError:
                    if value_str.lower() == 'true': params[key] = True
                    elif value_str.lower() == 'false': params[key] = False
                    elif value_str.lower() == 'null' or value_str.lower() == 'none': params[key] = None
                    else: params[key] = value_str # Fallback to string
            logger.info(f"Parsed rawcmd params: {params}")
        
        # For rawcmd, we don't know if it's a movement command, so continuous updates are not requested by default.
        # User can send 'request_iot_sys' manually if needed.
        await self._dispatch_simple_command(f"raw command {cmd_name}", cmd_name, params, request_continuous_updates=False)


    async def handle_help_command(self, args: List[str]):
        print("\nAvailable Commands:")
        print("  connect                       - Disconnect current and attempt to reconnect to the mower.")
        print("  status                        - Display summarized mower status.")
        print("  raw_status                    - Display full raw MowingDevice data.")
        print("  maps (or plans)               - List available tasks/plans and mapped areas.")
        print(f"  sync_maps                     - Attempt to refresh map/plan data (cache in {self.config.map_cache_file}).")
        print(f"  mow_areas <show|set <opts..._ HASHES [opts...]")
        print(f"                                - 'mow_areas show': Show current defaults from {self.config.mow_defaults_file} & usage.")
        print(f"                                - 'mow_areas set param=val ...': Set and save defaults to {self.config.mow_defaults_file}.")
        print(f"                                - 'mow_areas HASHES [opts...]': Start mow job with specified areas & overrides.")
        print("  start <plan_id_or_name>       - Start a predefined task/plan by its ID or name.")
        print("  dock (or charge)              - Send mower to dock.")
        print("  undock (or leave_dock)        - Command mower to leave the dock.")
        print("  pause                         - Pause the current mowing task.")
        print("  resume                        - Resume a paused mowing task.")
        print("  stop (or cancel)              - Stop/cancel the current job.")
        print("  blade_height <mm>             - Set blade cutting height (e.g., blade_height 60).")
        print("  rawcmd <cmd_name> [params]    - Send a raw command. Params can be key=value or a JSON string.")
        print("                                  Example: rawcmd set_report_cfg {\"rpt_dev_sta_inter\":3000} ")
        print("                                  Example: rawcmd request_iot_sys rpt_act=1 rpt_info_type=\"[1,2,3]\" count=0 ")
        print("  help                          - Show this help message.")
        print("  exit                          - Exit the CLI application.")
        print("----------------------------------------------------------------------------------\n")


    async def handle_exit_command(self, args: List[str]):
        logger.info("Exit command received. Shutting down...")
        self.cli_exit_event.set()

    async def handle_connect_command(self, args: List[str]):
        logger.info("Manual (re)connect requested.")
        if self.active_mower_device:
            logger.info(f"Disconnecting current device: {self.active_mower_device._cloud_device.deviceName}...")
            await self._app_shutdown_logic() # This will also set continuous_reporting_started to False
            self.active_mower_device = None
            # continuous_reporting_started is reset in _app_shutdown_logic if it was true
            logger.info("Previous device instance and associated resources (MQTT, etc.) cleared.")
        
        if await self.connect_and_initialize_mower():
            logger.info(f"Successfully reconnected to: {self.active_mower_device._cloud_device.deviceName}")
            if self._periodic_status_task and (self._periodic_status_task.done() or self._periodic_status_task.cancelled()):
                logger.info("Restarting periodic status monitor after reconnect.")
                self._periodic_status_task = asyncio.create_task(self.periodic_status_monitor())
            elif not self._periodic_status_task: # Should not happen if __aenter__ was successful, but good check.
                 logger.info("Starting periodic status monitor after successful connect.")
                 self._periodic_status_task = asyncio.create_task(self.periodic_status_monitor())
        else:
            logger.error("Reconnect attempt failed. Check credentials and network. Try 'connect' again or 'exit'.")

    # --- Specific command handlers that use _dispatch_simple_command ---
    async def _simple_dock_command(self, args: List[str]):
        await self._dispatch_simple_command("dock", "return_to_dock", request_continuous_updates=True)

    async def _simple_undock_command(self, args: List[str]):
        await self._dispatch_simple_command("undock", "leave_dock", request_continuous_updates=True)

    async def _simple_pause_command(self, args: List[str]):
        await self._dispatch_simple_command("pause", "pause_execute_task", request_continuous_updates=True)

    async def _simple_resume_command(self, args: List[str]):
        await self._dispatch_simple_command("resume", "resume_execute_task", request_continuous_updates=True)

    async def _simple_stop_command(self, args: List[str]):
        await self._dispatch_simple_command("stop", "cancel_job", request_continuous_updates=True)


# --- Command Registry ---
COMMAND_HANDLER_TYPE = Callable[[List[str]], Coroutine[Any, Any, None]]
class CommandRegistry:
    def __init__(self, controller: MowerController):
        self.controller = controller
        self._commands: Dict[str, COMMAND_HANDLER_TYPE] = {}
        self._aliases: Dict[str, str] = {}

    def register(self, name: str, handler_method_name: str, aliases: Optional[List[str]] = None):
        if not hasattr(self.controller, handler_method_name):
            raise ValueError(f"MowerController has no method '{handler_method_name}' for command '{name}'")
        
        bound_handler = getattr(self.controller, handler_method_name)
        self._commands[name] = bound_handler
        logger.debug(f"Registered command '{name}' to MowerController.{handler_method_name}")
        
        for alias in (aliases or []):
            self._aliases[alias] = name
            logger.debug(f"Registered alias '{alias}' for command '{name}'")

    async def dispatch(self, command_str: str):
        if not command_str.strip():
            return
        
        parts = command_str.strip().split()
        action_input = parts[0].lower()
        arguments = parts[1:]

        if not self.controller.active_mower_device and action_input not in ["exit", "help", "connect"]:
            logger.warning("Mower not connected. Available commands: connect, help, exit.")
            return
        
        actual_command_name = self._aliases.get(action_input, action_input)
        handler = self._commands.get(actual_command_name)

        if handler:
            try:
                await handler(arguments)
            except MowerCommandError as e: # This is already logged by _execute or _dispatch
                 pass # Error is already logged, just prevent CLI crash for these known errors.
            except Exception as e:
                logger.error(f"Unexpected error executing command '{actual_command_name}': {e}", exc_info=True)
        else:
            logger.warning(f"Unknown command: '{action_input}'. Type 'help' for available commands.")

def populate_command_registry(registry: CommandRegistry):
    registry.register("status", "handle_status_command")
    registry.register("raw_status", "handle_raw_status_command")
    registry.register("maps", "handle_maps_plans_command", aliases=["plans"])
    registry.register("sync_maps", "handle_sync_maps_command")
    registry.register("mow_areas", "handle_mow_areas_command")
    registry.register("start", "handle_start_command")
    registry.register("blade_height", "handle_blade_height_command")
    registry.register("rawcmd", "handle_raw_command")
    registry.register("help", "handle_help_command")
    registry.register("exit", "handle_exit_command")
    registry.register("connect", "handle_connect_command")

    # Simple commands routed through _dispatch_simple_command via their dedicated methods
    registry.register("dock", "_simple_dock_command", aliases=["charge"])
    registry.register("undock", "_simple_undock_command", aliases=["leave_dock"])
    registry.register("pause", "_simple_pause_command")
    registry.register("resume", "_simple_resume_command")
    registry.register("stop", "_simple_stop_command", aliases=["cancel"])


# --- Main CLI Loop ---
async def cli_main_loop(controller: MowerController, registry: CommandRegistry):
    logger.info("Starting Mammotion CLI main loop...")
    if controller.active_mower_device:
        logger.info(f"CLI Ready. Mower: {controller.active_mower_device._cloud_device.deviceName}")
    else:
        logger.warning("CLI Ready, but mower not connected. Try 'connect'.")

    while not controller.cli_exit_event.is_set():
        try:
            cmd_input = await asyncio.to_thread(input, "MowerControl> ")
            if controller.cli_exit_event.is_set(): # Check again after blocking input
                break
            await registry.dispatch(cmd_input)
        except (EOFError, KeyboardInterrupt):
            logger.info("Exiting due to EOF or Interrupt...")
            controller.cli_exit_event.set()
            break
        except RuntimeError as e: # Catch specific RuntimeError if event loop is closed during input
            if "Event loop is closed" in str(e) and controller.cli_exit_event.is_set():
                logger.info("Input thread caught loop closure during shutdown.")
                break
            logger.error(f"Runtime error in CLI loop: {e}", exc_info=True) # Log other RuntimeErrors
        await asyncio.sleep(0.1) # Small sleep to yield control
    
    logger.info("CLI input loop finished.")


# --- Async Exception Handler ---
def handle_async_exception(loop, context):
    msg = context.get("exception", context["message"])
    exception = context.get("exception")
    future = context.get("future")
    
    coro_repr = ""
    if future and hasattr(future, '_coro') and future._coro:
        coro_name = getattr(future._coro, '__qualname__', repr(future._coro))
        coro_repr = f"Coroutine: {coro_name}"

    # Specific handling for known internal PyMammotion JSONDecodeError scenarios
    if isinstance(exception, json.JSONDecodeError):
        # Keywords indicating internal PyMammotion parsing that can sometimes fail benignly
        problematic_coroutines_substrings = [
            "_parse_mqtt_response", "plan_callback", "_update_nav_data", 
            "read_plan", "handle_message" 
        ]
        # Check if the error originated from a coroutine known to have this issue
        # or if the traceback points to pymammotion library files
        if any(sub in coro_repr for sub in problematic_coroutines_substrings) or \
           (future and future._source_traceback and \
            any("pymammotion" in frame.filename.replace("\\", "/") for frame in future._source_traceback)):
             logger.debug(f"Handled known internal PyMammotion JSONDecodeError: {msg} | {coro_repr}")
             return # Suppress logging for these specific, known cases

    logger.error(f"Caught unhandled asyncio task exception: {msg}")
    if exception:
        logger.error("Exception traceback:", exc_info=exception)
    if coro_repr:
        logger.error(f"  Originating {coro_repr}")


# --- Main Application ---
async def main_application():
    config = Config.from_env_and_input()
    log_level_val = getattr(logging, config.log_level, logging.INFO)
    
    # Configure root logger first
    logging.basicConfig(level=log_level_val, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
    
    # Then set levels for specific loggers
    logger.setLevel(log_level_val) # mammotion_cli logger
    pymammotion_logger.setLevel(logging.WARNING if log_level_val > logging.DEBUG else logging.DEBUG)
    paho_mqtt_logger.setLevel(logging.WARNING) # Silence paho unless very verbose main log level
    linkkit_logger.setLevel(logging.INFO) # Aliyun linkkit, can be noisy
    asyncio_logger.setLevel(logging.INFO) # Default asyncio logger

    if os.name == 'nt': # Required for Windows if using aiohttp's default event loop policy with some Python versions
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    async with MowerController(config) as controller:
        registry = CommandRegistry(controller)
        populate_command_registry(registry)
        await cli_main_loop(controller, registry)
    
    logger.info("Main application logic after MowerController context finished.")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(handle_async_exception)
    main_task = None
    try:
        logger.info("Application starting...")
        main_task = loop.create_task(main_application())
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received in __main__. Initiating shutdown...")
        if main_task and not main_task.done():
            main_task.cancel()
    except asyncio.CancelledError:
        logger.info("Main application task was cancelled.")
    except Exception as e_outer:
        logger.critical(f"Unhandled exception in main execution block: {e_outer}", exc_info=True)
    finally:
        logger.info("Main execution block finished or interrupted. Running final cleanup...")
        if main_task and not main_task.done():
            logger.info("Main task not done, cancelling it now explicitly.")
            main_task.cancel()
        
        # Ensure main_task completion is awaited after potential cancellation
        if main_task:
            try:
                loop.run_until_complete(main_task)
            except asyncio.CancelledError:
                logger.info("Main task acknowledged cancellation during final cleanup.")
            except Exception as e_final_main:
                logger.error(f"Exception from main_task during final completion: {e_final_main}", exc_info=True)

        # Gracefully cancel all other outstanding tasks
        tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop)] # Exclude current task if any
        if tasks:
            logger.info(f"Cancelling {len(tasks)} outstanding asyncio tasks during final shutdown...")
            for task in tasks:
                task.cancel()
            try:
                # Wait for all tasks to complete their cancellation
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                logger.info("Outstanding tasks processed.")
            except Exception as e_gather:
                logger.error(f"Error gathering cancelled tasks: {e_gather}")
        
        # Shutdown async generators
        if hasattr(loop, "shutdown_asyncgens"): # Available in Python 3.6+
            logger.info("Shutting down async generators...")
            loop.run_until_complete(loop.shutdown_asyncgens())
        
        logger.info("Closing event loop...")
        loop.close()
        logger.info("Event loop closed. Application finished.")

