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
from datetime import datetime
from pprint import pprint

from pymammotion.data.model.device import MowingDevice, HashList
from pymammotion.data.model.device_config import OperationSettings, create_path_order
from pymammotion.data.model import GenerateRouteInformation
from pymammotion.data.model.mowing_modes import (
    CuttingMode, MowOrder, BorderPatrolMode, ObstacleLapsMode,
    PathAngleSetting, DetectionStrategy, TraversalMode, TurningMode
)
from pymammotion.data.state_manager import StateManager
from pymammotion.mammotion.devices.mammotion_cloud import MammotionCloud
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.http.http import MammotionHTTP
from pymammotion.mqtt.mammotion_mqtt import MammotionMQTT
from pymammotion.mammotion.devices.mammotion import MammotionBaseCloudDevice

from pymammotion.utility.constant.device_constant import device_mode, device_connection, PosType, WorkMode
from pymammotion.data.model.enums import RTKStatus
from pymammotion.proto import RptAct, RptInfoType
from pymammotion.utility.device_type import DeviceType

# --- Global Loggers (configured in main) ---
logger = logging.getLogger("mammotion_cli")
# Third-party loggers (levels also set in main)
mammotion_mqtt_logger = logging.getLogger("pymammotion.mqtt.mammotion_mqtt")
paho_mqtt_logger = logging.getLogger("paho.mqtt.client")
linkkit_logger = logging.getLogger("linkkit")
asyncio_logger = logging.getLogger("asyncio")


# --- Configuration Management ---
@dataclasses.dataclass
class Config:
    email: Optional[str] = None
    password: Optional[str] = None
    log_level: str = "INFO"
    max_retries: int = 3
    initial_retry_delay: float = 1.0
    max_retry_delay: float = 10.0
    base_monitoring_interval: int = 20
    work_monitoring_divider: int = 4
    mqtt_connection_timeout: int = 20 # Seconds to wait for MQTT client to connect

    @classmethod
    def from_env_and_input(cls):
        config = cls()
        config.email = os.environ.get('EMAIL') or input("Enter Mammotion Email: ")
        config.password = os.environ.get('PASSWORD') or getpass.getpass("Enter Mammotion Password: ")
        config.log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
        # Can add more env vars for other settings if needed
        return config

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

    # MQTT timeouts (besides initial connect)
    MQTT_RECONNECT_DELAY = 5 # Not directly used by current pymammotion, but good to have

    # Retry settings (defaults for exponential_backoff if not overridden by Config)
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_RETRY_DELAY = 1.0
    DEFAULT_MAX_RETRY_DELAY = 10.0

# --- Utility Functions ---
def get_enum_value(enum_class: Type[Any], value_str: str) -> Optional[int]:
    """
    Tries to match value_str (case-insensitively) to an enum member name.
    Returns the integer value of the enum member if found, otherwise None.
    """
    for member_name in enum_class.__members__:
        if member_name.lower() == value_str.lower():
            return enum_class[member_name].value
        # Attempt to match if user typed underscores for CamelCase or vice-versa
        if member_name.lower() == value_str.replace("_", "").lower():
             return enum_class[member_name].value
        if member_name.replace("_", "").lower() == value_str.lower():
            return enum_class[member_name].value

    logger.warning(f"Could not parse '{value_str}' into a valid {enum_class.__name__} member. Parameter will not be set or will use library default.")
    return None

async def exponential_backoff(
    func: Callable[[], Coroutine[Any, Any, Any]],
    func_name: str = "Unnamed Function",
    max_retries: int = Constants.DEFAULT_MAX_RETRIES, # Can be overridden by Config values when called
    initial_delay: float = Constants.DEFAULT_INITIAL_RETRY_DELAY,
    max_delay: float = Constants.DEFAULT_MAX_RETRY_DELAY,
    jitter: bool = True
) -> Optional[Any]:
    for attempt in range(max_retries):
        try:
            result = await func()
            # Handle empty responses, which some commands might return on success
            if result == b'' or result == '': # Check for empty bytes or string
                logger.debug(f"Empty response from {func_name} (attempt {attempt + 1}/{max_retries}), potentially OK.")
                # Some commands are fire-and-forget and return empty, consider this success for them.
                # If we need to differentiate, the caller must handle it.
                # For now, let's assume empty response is fine if no exception.
                # If a command *must* return data, the parsing later will fail (e.g. JSONDecodeError for expected JSON).
                return result # Return the empty response
            return result # Non-empty response
        except json.JSONDecodeError as e_json_decode:
            # This often means the command succeeded but the server sent no JSON body (e.g., HTTP 204 or just empty)
            logger.warning(f"{func_name} resulted in JSONDecodeError (likely empty server response, this might be OK for some commands): {e_json_decode}")
            if attempt == max_retries - 1:
                logger.warning(f"Final attempt for {func_name} failed with JSONDecodeError. Returning None.")
                return None # Treat as success with no data if it's the last try
            # Don't retry on JSONDecodeError if it's likely an empty "success" response
            return None # Consider it handled, command likely went through.
        except Exception as e:
            logger.debug(f"Attempt {attempt+1}/{max_retries} for {func_name} failed: {type(e).__name__} - {e}")
            if attempt == max_retries - 1:
                logger.error(f"Final attempt failed for {func_name}: {type(e).__name__} - {e}")
                raise MowerCommandError(f"Command '{func_name}' failed after {max_retries} retries: {e}") from e
        
        delay = initial_delay * (2 ** attempt)
        sleep_time = min(delay, max_delay)
        if jitter: sleep_time = random.uniform(0.5 * sleep_time, sleep_time)
        logger.info(f"Retrying {func_name} in {sleep_time:.2f}s (attempt {attempt+2 if attempt+1 < max_retries else 'final'} of {max_retries}).")
        await asyncio.sleep(sleep_time)
    return None # Should be unreachable if MowerCommandError is raised


# --- Status Formatting ---
class StatusFormatter:
    @staticmethod
    def format_summary_text(summary: Dict[str, Any]) -> str:
        if not summary or summary.get("error"):
            return "Status: No data or error fetching status."

        last_update_str = summary.get("sys_time_stamp")
        status_age = 0
        if last_update_str:
            last_update = datetime.fromtimestamp(int(last_update_str))
            if (datetime.now() - last_update).total_seconds() > 600:
                logger.debug("Raw status data is stale (>5s old), triggering update...")
                self.safe_command_execution("get_report_cfg")
                asyncio.sleep(0.5)  # Give time for update
        if last_update_str:
            last_update = datetime.fromtimestamp(int(last_update_str))
            status_age = (datetime.now() - last_update).total_seconds()

        lines = [
            f"Act: {summary.get('activity', 'N/A')}, "
            f"Bat: {summary.get('battery_percent', 'N/A')}%, "
            f"Age: {status_age:2.1f}s"
            f"\n"
            f"Prog: {summary.get('work_progress_percent', 'N/A')}%, "
            f"RTK: {summary.get('rtk_status', 'N/A')} ({summary.get('rtk_gps_stars', 'N/A')}*), "
            f"Err: {summary.get('error_code', 'OK')}, "
            f"Area: {summary.get('current_working_area', 'N/A')}",
        ]
        return "\n".join(lines)

    @staticmethod
    def format_detailed_text(summary: Dict[str, Any]) -> str:
        if not summary or summary.get("error"):
            return "--- Current Mower Status ---\n  No data or error fetching status.\n-------------------------------------\n"
        
        output = ["\n--- Current Mower Status ---"]
        for k, v in summary.items():
            output.append(f"  {k.replace('_', ' ').title()}: {v}")
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
        self._mqtt_client: Optional[MammotionMQTT] = None # The actual MQTT client instance
        self._cloud_mqtt_wrapper: Optional[MammotionCloud] = None # Pymammotion wrapper for MQTT

        # For status change notifications
        self.last_activity_for_notification: Optional[str] = None
        self.last_progress_for_notification: Optional[Any] = None # Can be str or int

        self._periodic_status_task: Optional[asyncio.Task] = None


    async def __aenter__(self):
        logger.info("MowerController entering context...")
        if not await self.connect_and_initialize_mower():
            logger.error("Failed to connect and initialize mower during context entry.")
            # Allow CLI to start for 'connect', 'help', 'exit'
        else:
            logger.info(f"Successfully connected to: {self.active_mower_device._cloud_device.deviceName if self.active_mower_device else 'Unknown'}")
            self._periodic_status_task = asyncio.create_task(self.periodic_status_monitor())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logger.info("MowerController exiting context. Initiating shutdown...")
        self.cli_exit_event.set() # Signal all loops to stop

        if self._periodic_status_task and not self._periodic_status_task.done():
            logger.info("Cancelling periodic status monitor task...")
            self._periodic_status_task.cancel()
            try:
                await self._periodic_status_task
            except asyncio.CancelledError:
                logger.info("Periodic status monitor task cancelled.")
            except Exception as e:
                logger.warning(f"Exception during periodic status monitor task cancellation: {e}")
        
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
                        # Use a timeout for this potentially blocking call during shutdown
                        await asyncio.wait_for(
                            self.active_mower_device.queue_command(
                                "request_iot_sys", rpt_act=RptAct.RPT_STOP.value,
                                rpt_info_type=stop_rpt_type_values,
                                timeout=0, period=0, no_change_period=0, count=0
                            ), timeout=3.0 
                        )
                    except asyncio.TimeoutError:
                        logger.warning("Timeout stopping IoT sys reporting during shutdown.")
                    except Exception as e_stop_rpt:
                        logger.warning(f"Error stopping IoT sys reporting: {e_stop_rpt}")
                    self.continuous_reporting_started = False

                if hasattr(self.active_mower_device, 'stop_sync') and callable(getattr(self.active_mower_device, 'stop_sync')):
                    logger.info("Calling device stop_sync()...")
                    await self.active_mower_device.stop_sync() # This might not be async, Pymammotion needs check

                # Disconnect MQTT via the MammotionMQTT instance directly
                if self._mqtt_client and self._mqtt_client.is_connected:
                    logger.info("Disconnecting MQTT client...")
                    self._mqtt_client.disconnect()
                    for _ in range(5): # Wait a bit for disconnect
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
        
        # HTTP client cleanup if needed (e.g., close session)
        if self._mammotion_http and hasattr(self._mammotion_http, 'close_session') and callable(self._mammotion_http.close_session):
            logger.info("Closing MammotionHTTP session...")
            await self._mammotion_http.close_session()


    async def connect_and_initialize_mower(self) -> bool:
        if not self.config.email or not self.config.password:
            logger.error("Email and Password are required in config.")
            return False

        try:
            self._mammotion_http = MammotionHTTP()
            self._cloud_client = CloudIOTGateway(self._mammotion_http)
            
            logger.info("Attempting login...")
            await exponential_backoff(
                lambda: self._mammotion_http.login(self.config.email, self.config.password),
                "login", max_retries=self.config.max_retries
            )
            if not hasattr(self._mammotion_http, 'login_info') or not self._mammotion_http.login_info:
                raise MowerConnectionError("Login succeeded but login_info missing.")
            logger.info("Login successful.")
            
            country_code = self._mammotion_http.login_info.userInformation.domainAbbreviation
            logger.info("Setting up cloud gateway...")
            
            cloud_setup_steps = {
                "get_region": lambda: self._cloud_client.get_region(country_code),
                "cloud_connect": lambda: self._cloud_client.connect(),
                "login_by_oauth": lambda: self._cloud_client.login_by_oauth(country_code),
                "aep_handle": lambda: self._cloud_client.aep_handle(),
                "session_by_auth_code": lambda: self._cloud_client.session_by_auth_code(),
                "list_binding_by_account": lambda: self._cloud_client.list_binding_by_account()
            }

            for step_name, step_lambda in cloud_setup_steps.items():
                logger.info(f"Executing cloud setup step: {step_name}...")
                result = await exponential_backoff(step_lambda, step_name, max_retries=self.config.max_retries)
                if result is None and step_name in ["aep_handle", "session_by_auth_code"]: 
                    logger.warning(f"Cloud setup step {step_name} completed with potentially empty/None result. Assuming OK for now.")
                elif not result and step_name not in ["aep_handle"]:
                     raise MowerConnectionError(f"Cloud setup step {step_name} failed or returned falsy value: {result}.")
                logger.info(f"Cloud setup step {step_name} successful.")

            logger.info("Cloud gateway & device listing complete.")

            if not (hasattr(self._cloud_client, 'devices_by_account_response') and
                    self._cloud_client.devices_by_account_response and
                    self._cloud_client.devices_by_account_response.data and
                    self._cloud_client.devices_by_account_response.data.data):
                logger.warning("No devices in devices_by_account_response."); return False # Changed to return False

            all_devices = self._cloud_client.devices_by_account_response.data.data
            luba_devices_info = [(idx, d) for idx, d in enumerate(all_devices) if d.deviceName.startswith("Luba")]

            if not luba_devices_info: logger.warning("No Luba devices found."); return False # Changed

            device_info_selected = None
            if len(luba_devices_info) == 1:
                device_info_selected = luba_devices_info[0][1]
                logger.info(f"Found Luba: {device_info_selected.deviceName} (IoT ID: {device_info_selected.iotId})")
            else:
                print("Multiple Luba devices found. Please select one:")
                for idx, (original_idx, dev) in enumerate(luba_devices_info):
                    print(f"  {idx + 1}. {dev.deviceName} (Nickname: {dev.nickName or 'N/A'})")
                while True:
                    try:
                        choice_str = await asyncio.to_thread(input, f"Enter choice (1-{len(luba_devices_info)}): ")
                        choice = int(choice_str) - 1
                        if 0 <= choice < len(luba_devices_info):
                            device_info_selected = luba_devices_info[choice][1]
                            logger.info(f"Selected Luba: {device_info_selected.deviceName}")
                            break
                        else: print("Invalid choice. Please try again.")
                    except ValueError: print("Invalid input. Please enter a number.")
            
            if not device_info_selected: 
                logger.error("Device selection failed.")
                return False # Changed
            
            # MQTT Initialization checks
            required_attrs = {
                (self._cloud_client, 'region_response.data.regionId'): "Missing regionId",
                (self._cloud_client, 'aep_response.data.productKey'): "Missing productKey",
                (self._cloud_client, 'aep_response.data.deviceName'): "Missing deviceName for MQTT",
                (self._cloud_client, 'aep_response.data.deviceSecret'): "Missing deviceSecret",
                (self._cloud_client, 'session_by_authcode_response.data.iotToken'): "Missing iotToken",
                (self._cloud_client, 'client_id'): "Missing client_id"
            }
            for (obj, attr_path), err_msg in required_attrs.items():
                current = obj
                try:
                    for part in attr_path.split('.'): current = getattr(current, part)
                    if not current: raise AttributeError # Handle empty string for client_id
                except AttributeError:
                    raise MowerConnectionError(f"MQTT Init Error: {err_msg} in cloud_client.")

            mqtt_region_id = self._cloud_client.region_response.data.regionId
            mqtt_product_key = self._cloud_client.aep_response.data.productKey
            mqtt_device_name_for_mqtt_auth = self._cloud_client.aep_response.data.deviceName # This is AEP device name
            mqtt_device_secret = self._cloud_client.aep_response.data.deviceSecret
            mqtt_iot_token = self._cloud_client.session_by_authcode_response.data.iotToken
            mqtt_client_id = self._cloud_client.client_id

            self._mqtt_client = MammotionMQTT(
                region_id=mqtt_region_id,
                product_key=mqtt_product_key,
                device_name=mqtt_device_name_for_mqtt_auth, # Use AEP deviceName for MQTT layer
                device_secret=mqtt_device_secret,
                iot_token=mqtt_iot_token,
                client_id=mqtt_client_id,
                cloud_client=self._cloud_client
            )
            logger.info(f"MammotionMQTT instance created. Target Luba for control: {device_info_selected.deviceName}.")

            self._cloud_mqtt_wrapper = MammotionCloud(self._mqtt_client, cloud_client=self._cloud_client)
            self._cloud_mqtt_wrapper.connect_async()

            logger.info(f"Waiting up to {self.config.mqtt_connection_timeout} seconds for MQTT connection...")
            for i in range(self.config.mqtt_connection_timeout):
                if self._mqtt_client.is_connected:
                    logger.info("MQTT connected successfully.")
                    break
                logger.debug(f"MQTT not connected, waiting... (attempt {i+1}/{self.config.mqtt_connection_timeout})")
                await asyncio.sleep(1.0)
            else:
                raise MowerConnectionError(f"MQTT client did not connect within the {self.config.mqtt_connection_timeout}-second timeout.")

            self.active_mower_device = MammotionBaseCloudDevice(
                mqtt=self._cloud_mqtt_wrapper, 
                cloud_device=device_info_selected, # The specific Luba selected by user
                state_manager=StateManager(MowingDevice())
            )
            logger.info(f"Device object for specific Luba {self.active_mower_device._cloud_device.deviceName} initialized.")
            
            # Initial setup commands
            await self.safe_command_execution("allpowerfull_rw", rw_id=5, rw=1, context=1)
            await asyncio.sleep(0.5)
            await self.safe_command_execution("get_report_cfg")
            await asyncio.sleep(0.5)

            await self.attempt_to_populate_maps(reason="Initial Connect")

            logger.info("Attempting to start continuous status reporting (request_iot_sys count=0)...")
            try:
                rpt_type_values = [rt.value for rt in Constants.CORE_RPT_INFO_TYPES_FOR_CONTINUOUS_REPORTING]
                await self.safe_command_execution(
                    "request_iot_sys",
                    rpt_act=RptAct.RPT_START.value, rpt_info_type=rpt_type_values,
                    timeout=10000, period=3000, no_change_period=4000, count=0
                )
                logger.info("Continuous status reporting requested for core types.")
                self.continuous_reporting_started = True
            except MowerCommandError as e: # Catch specific error from safe_command_execution
                logger.warning(f"Failed to start continuous IoT sys reporting: {e}. Will rely on polls.")
                self.continuous_reporting_started = False
            
            return True

        except (MowerConnectionError, MowerCommandError) as e: # Catch our custom errors
            logger.error(f"Connect/init failed: {e}", exc_info=False) # exc_info=False for cleaner known errors
            await self._cleanup_failed_connection()
            return False
        except Exception as e:
            logger.error(f"Unexpected error during connect/init: {e}", exc_info=True)
            await self._cleanup_failed_connection()
            return False

    async def _cleanup_failed_connection(self):
        """Internal helper to clean up resources on connection failure."""
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


    async def attempt_to_populate_maps(self, reason: str = "Data Population"):
        if not self.active_mower_device:
            logger.warning(f"Cannot populate maps ({reason}): Mower not connected.")
            return

        logger.info(f"Attempting to populate map/plan data ({reason})...")
        if self.active_mower_device.mower and hasattr(self.active_mower_device.mower, 'map') and self.active_mower_device.mower.map:
            if hasattr(self.active_mower_device.mower.map, 'clear_all'):
                self.active_mower_device.mower.map.clear_all()
                logger.info("Local map data cache cleared using clear_all().")
            else: # Fallback, should not be needed if clear_all exists
                self.active_mower_device.mower.map = HashList()
                logger.info("Local map data cache re-initialized.")

        device_iot_id = self.active_mower_device._cloud_device.iotId
        try:
            logger.info(f"({reason}) Requesting area name list (get_area_name_list)...")
            await self.safe_command_execution("get_area_name_list", device_id=device_iot_id)
            await asyncio.sleep(1.5)

            logger.info(f"({reason}) Attempting to read plans with 'read_plan' (sub_cmd=2)...")
            await self.safe_command_execution("read_plan", sub_cmd=2, plan_index=0)
            logger.info(f"({reason}) 'read_plan' (sub_cmd=2) command sent. Waiting for MQTT data to populate...")
            await asyncio.sleep(10.0) # Give time for MQTT updates
            logger.info(f"Map/plan data request sequence ({reason}) completed. Check 'maps' command.")
        except AttributeError as e_attr: # Should not happen with safe_command_execution
            logger.warning(f"A command in '{reason}' sequence might not be directly callable on active_mower_device: {e_attr}")
        except MowerCommandError as e_cmd:
            logger.error(f"Error during '{reason}' map population command: {e_cmd}")
        except Exception as e: # Catch any other unexpected error
            logger.error(f"Unexpected error during '{reason}' map population: {e}", exc_info=True)

    def get_mower_status_summary(self) -> Dict[str, Any]:
        if not self.active_mower_device or not self.active_mower_device.mower:
            return {"error": "No MowerDevice data or mower not connected."}
        
        mower_data = self.active_mower_device.mower
        s = {}
        s["device_name"] = getattr(self.active_mower_device._cloud_device, 'deviceName', 'N/A')
        s["nickname"] = getattr(self.active_mower_device._cloud_device, 'nickName', 'N/A')

        if hasattr(mower_data, 'report_data') and mower_data.report_data:
            rd = mower_data.report_data
            if rd.dev:
                s["serial_number"] = rd.dev.sn if hasattr(rd.dev, 'sn') and rd.dev.sn else "N/A"
                s["battery_percent"] = rd.dev.battery_val if hasattr(rd.dev, 'battery_val') else "N/A"

                base_activity_str = device_mode(rd.dev.sys_status) if hasattr(rd.dev, 'sys_status') else "Unknown Status"
                activity_display = base_activity_str
                is_charging_val = False
                is_docked_val = False

                if hasattr(rd.dev, 'sys_time_stamp'):
                    s["sys_time_stamp"] = rd.dev.sys_time_stamp
                if hasattr(rd.dev, 'charge_state') and rd.dev.charge_state is not None:
                    s["charge_state_code"] = rd.dev.charge_state
                    if rd.dev.charge_state == 1: # Charging
                        is_charging_val = True
                        is_docked_val = True # Implicitly docked if charging
                        activity_display = "Charging"
                    elif rd.dev.charge_state == 0: # Not charging (could be docked or undocked)
                        is_charging_val = False
                    
                    # If ready and charge_state is not 0, it implies docked (even if not actively charging, e.g. full)
                    if "MODE_READY" in base_activity_str.upper() and rd.dev.charge_state != 0:
                        is_docked_val = True
                        if not is_charging_val: activity_display = "Docked" # Overrides "Ready" if docked but not charging
                else: # charge_state not available
                     if "MODE_READY" in base_activity_str.upper() and hasattr(rd.dev, 'sys_status') and rd.dev.sys_status == 0: # Luba 1 idle on charger shows sys_status 0 (MODE_READY)
                        # This is a heuristic; better if charge_state is reliable
                        # Check if RTK is also on charger (often sys_status 0 means on charger for Luba1)
                        if mower_data.location and mower_data.location.RTK and mower_data.location.RTK.on_charger == 1:
                            is_docked_val = True
                            activity_display = "Docked (推定)" # Estimated
                        
                s["is_charging"] = is_charging_val
                s["is_docked"] = is_docked_val
                s["activity"] = activity_display
                s["error_code"] = getattr(rd.dev, 'error_code', "OK")

            if rd.connect:
                s["connection_type"] = device_connection(rd.connect) if hasattr(rd.connect, 'wifi_conn_level') else "N/A" # Adapt based on actual fields
                s["wifi_rssi_dbm"] = rd.connect.wifi_rssi if hasattr(rd.connect, 'wifi_rssi') else "N/A"
                s["mobile_net_rssi_dbm"] = rd.connect.mnet_rssi if hasattr(rd.connect, 'mnet_rssi') else "N/A"
                s["ble_rssi_dbm"] = rd.connect.ble_rssi if hasattr(rd.connect, 'ble_rssi') else "N/A"
            else: s["connection_type"] = "N/A"

            if rd.rtk:
                s["rtk_gps_stars"] = rd.rtk.gps_stars if hasattr(rd.rtk, 'gps_stars') else "N/A"
                s["rtk_status"] = str(RTKStatus.from_value(rd.rtk.status).name) if hasattr(rd.rtk, 'status') else "N/A"
                if hasattr(rd.rtk, 'co_view_stars'):
                    s["l1_satellites"] = (rd.rtk.co_view_stars >> 0) & 255
                    s["l2_satellites"] = (rd.rtk.co_view_stars >> 8) & 255
            else: s["rtk_status"] = "N/A"

            if rd.work:
                s["work_progress_percent"] = (rd.work.area >> 16) if hasattr(rd.work, 'area') else "N/A"
                s["total_area_to_mow_sqm"] = (rd.work.area & 65535) if hasattr(rd.work, 'area') else "N/A"
                if hasattr(rd.work, 'progress'):
                    total_time_min, remaining_time_min = rd.work.progress & 65535, rd.work.progress >> 16
                    s["total_job_time_min"] = total_time_min
                    s["remaining_job_time_min"] = remaining_time_min
                    s["elapsed_job_time_min"] = total_time_min - remaining_time_min if total_time_min >= remaining_time_min else "N/A"
                if hasattr(rd.work, 'knife_height'): s["blade_height_mm"] = rd.work.knife_height
                s["mowing_speed_mps"] = rd.work.man_run_speed / 100 if hasattr(rd.work, 'man_run_speed') else "N/A"
            else: s["work_progress_percent"] = "N/A"
        else: # report_data missing
            s["activity"] = "Awaiting Data"
            s["battery_percent"] = "N/A"
            # fill other fields with N/A if report_data is missing

        current_area_name_val = "N/A"
        if mower_data.location:
            s["position_certainty"] = str(PosType(mower_data.location.position_type).name) if hasattr(mower_data.location, 'position_type') else "N/A"

            dev_loc = mower_data.location.device
            if dev_loc and hasattr(dev_loc, 'latitude') and hasattr(dev_loc, 'longitude'):
                s["mower_latitude"] = f"{dev_loc.latitude:.7f}" if dev_loc.latitude is not None else "N/A"
                s["mower_longitude"] = f"{dev_loc.longitude:.7f}" if dev_loc.longitude is not None else "N/A"
            else:
                s["mower_latitude"], s["mower_longitude"] = "N/A", "N/A"

            rtk_loc = mower_data.location.RTK
            if rtk_loc and hasattr(rtk_loc, 'latitude') and hasattr(rtk_loc, 'longitude'):
                 s["rtk_fix_latitude"] = f"{rtk_loc.latitude * 180.0 / math.pi:.7f}" if rtk_loc.latitude is not None else "N/A"
                 s["rtk_fix_longitude"] = f"{rtk_loc.longitude * 180.0 / math.pi:.7f}" if rtk_loc.longitude is not None else "N/A"
            else:
                s["rtk_fix_latitude"], s["rtk_fix_longitude"] = "N/A", "N/A"
            
            if hasattr(mower_data, 'map') and mower_data.map and hasattr(mower_data.map, 'area_name') and mower_data.map.area_name and hasattr(mower_data.location, 'work_zone'):
                current_work_zone_hash = mower_data.location.work_zone
                if current_work_zone_hash is not None and current_work_zone_hash != 0:
                    found_area = False
                    for area_obj in mower_data.map.area_name: # area_name is a list of AreaName objects
                        if hasattr(area_obj, 'hash') and area_obj.hash == current_work_zone_hash:
                            current_area_name_val = getattr(area_obj, 'name', f"Unknown Area (Hash: {current_work_zone_hash})")
                            found_area = True; break
                    if not found_area:
                        current_area_name_val = f"In Zone (Unknown Name, Hash: {current_work_zone_hash})"
                elif s.get("position_certainty") == "AREA_INSIDE": # String comparison
                     current_area_name_val = "Inside an area (specific name not resolved)"
                else:
                    current_area_name_val = "Outside defined areas / Unknown"
            else: # map or area_name or work_zone not available
                 current_area_name_val = "Area data not available"
                 if s.get("position_certainty") == "AREA_INSIDE":
                     current_area_name_val = "Inside an area (map data needed for name)"
        else: # mower_data.location missing
            s["position_certainty"], s["mower_latitude"], s["mower_longitude"] = "N/A", "N/A", "N/A"

        s["current_working_area"] = current_area_name_val
        return s

    async def periodic_status_monitor(self):
        logger.info("Periodic status monitor started.")
        while not self.cli_exit_event.is_set():
            current_interval = self.config.base_monitoring_interval
            if not self.active_mower_device or not self.active_mower_device.mower:
                await asyncio.sleep(current_interval)
                continue

            summary = self.get_mower_status_summary()
            activity_for_interval_check = summary.get('activity', "").lower()
            is_working = "working" in activity_for_interval_check or "mowing" in activity_for_interval_check
            is_undocked  = not summary.get('is_docked', False)
            last_update_str = summary.get("sys_time_stamp")
            if last_update_str:
                last_update = datetime.fromtimestamp(int(last_update_str))
                is_stale = (datetime.now() - last_update).total_seconds() > 300
            else:
                is_stale = False

            if is_working:
                current_interval = self.config.base_monitoring_interval // self.config.work_monitoring_divider

            # Always poll if continuous reporting failed or if mower is working (to get more frequent updates)
            if not self.continuous_reporting_started or is_working or is_undocked or is_stale:
                logger.debug(f"Polling (State: {activity_for_interval_check}, ContinuousRpt: {self.continuous_reporting_started}): Requesting full update (get_report_cfg)...")
                try:
                    await self.safe_command_execution("get_report_cfg") # Use safe_command_execution
                    await asyncio.sleep(0.5) # Give time for MQTT to update state
                except MowerCommandError as e:
                    logger.warning(f"Periodic get_report_cfg failed: {e}")
                except Exception as e: # Catch any other error
                    logger.warning(f"Unexpected error in periodic get_report_cfg: {e}")

            # Refresh summary after potential poll
            summary_after_poll = self.get_mower_status_summary()
            logger.info(f"STATUS: {StatusFormatter.format_summary_text(summary_after_poll)}")
            
            # Notification logic
            current_activity_for_notification = summary_after_poll.get('activity')
            current_progress_for_notification = summary_after_poll.get('work_progress_percent')

            if self.last_activity_for_notification and current_activity_for_notification:
                act_low = current_activity_for_notification.lower()
                last_act_low = self.last_activity_for_notification.lower()
                was_working = "working" in last_act_low or "mowing" in last_act_low
                is_idle_or_completed = any(s in act_low for s in ["idle", "charging", "completed", "standby", "docked", "mode_ready"])

                progress_val = None
                if isinstance(self.last_progress_for_notification, (int, float)):
                    progress_val = self.last_progress_for_notification
                elif isinstance(self.last_progress_for_notification, str) and self.last_progress_for_notification.replace('%','').isdigit():
                    try: progress_val = int(self.last_progress_for_notification.replace('%',''))
                    except ValueError: pass
                
                if was_working and is_idle_or_completed and progress_val is not None and progress_val >= 95:
                    logger.info(
                        f"NOTIFICATION: Task likely completed! "
                        f"Prev State: {self.last_activity_for_notification} ({self.last_progress_for_notification}%), "
                        f"Current State: {current_activity_for_notification}"
                    )
            
            self.last_activity_for_notification = current_activity_for_notification
            self.last_progress_for_notification = current_progress_for_notification
            
            try:
                await asyncio.wait_for(self.cli_exit_event.wait(), timeout=current_interval)
            except asyncio.TimeoutError:
                pass # Normal timeout, continue loop
        logger.info("Periodic status monitor stopped.")

    async def safe_command_execution(self, command_name: str, **kwargs):
        """Execute command with proper error handling and logging, using exponential_backoff."""
        if not self.active_mower_device:
            raise MowerCommandError(f"Cannot execute '{command_name}': Mower not connected.")
        
        try:
            # Use config for retries, or defaults from exponential_backoff if not set in config
            max_retries = self.config.max_retries if hasattr(self.config, 'max_retries') else Constants.DEFAULT_MAX_RETRIES
            initial_delay = self.config.initial_retry_delay if hasattr(self.config, 'initial_retry_delay') else Constants.DEFAULT_INITIAL_RETRY_DELAY
            max_delay = self.config.max_retry_delay if hasattr(self.config, 'max_retry_delay') else Constants.DEFAULT_MAX_RETRY_DELAY

            result = await exponential_backoff(
                lambda: self.active_mower_device.queue_command(command_name, **kwargs),
                func_name=f"cmd_{command_name}",
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay
            )
            # Check for JSONDecodeError specifically for empty responses (handled by exponential_backoff returning None)
            if result is None and "JSONDecodeError" in str(kwargs.get("_last_error_type_from_backoff", "")): # Hypothetical way to pass error type
                 logger.warning(f"Command '{command_name}' completed but returned empty/non-JSON response (likely OK for some commands).")
            else:
                logger.debug(f"Command '{command_name}' executed successfully (or final attempt made). Response snippet: {'N/A' if result is None else str(result)[:50]}")
            return result # Return result for handlers that might need it
        except MowerCommandError as e: # Raised by exponential_backoff on final failure
            logger.error(f"Command '{command_name}' failed after all retries: {e}")
            raise # Re-raise to be caught by command handler if needed
        except Exception as e: # Catch any other unexpected error
            logger.error(f"Unexpected error during '{command_name}' execution: {e}", exc_info=True)
            # Wrap in MowerCommandError for consistent error type from this function
            raise MowerCommandError(f"Unexpected error executing {command_name}: {e}") from e

    # --- Command Handler Methods ---
    async def handle_status_command(self, args: List[str]):
        summary = self.get_mower_status_summary()
        last_update_str = summary.get("sys_time_stamp")
        if last_update_str:
            last_update = datetime.fromtimestamp(int(last_update_str))
            if (datetime.now() - last_update).total_seconds() > 5:
                logger.debug("Status data is stale (>5s old), triggering update...")
                await self.safe_command_execution("get_report_cfg")
                await asyncio.sleep(0.5)  # Give time for update
                summary = self.get_mower_status_summary()  # Get fresh data
        print(StatusFormatter.format_detailed_text(summary))

    async def handle_raw_status_command(self, args: List[str]):
        if self.active_mower_device and self.active_mower_device.mower:
            summary = self.get_mower_status_summary()
            last_update_str = summary.get("sys_time_stamp")
            if last_update_str:
                last_update = datetime.fromtimestamp(int(last_update_str))
                if (datetime.now() - last_update).total_seconds() > 5:
                    logger.debug("Raw status data is stale (>5s old), triggering update...")
                    await self.safe_command_execution("get_report_cfg")
                    await asyncio.sleep(0.5)  # Give time for update
            
            print("\n--- Full Raw MowingDevice Data ---")
            try:
                print(json.dumps(self.active_mower_device.mower.to_dict(), indent=2, default=str))
            except Exception as e:
                logger.error(f"Could not serialize MowingDevice data: {e}")
                print(str(self.active_mower_device.mower)) # Fallback to string representation
            print("-------------------------------------\n")
        else:
            logger.info("No raw status data available.")

    async def handle_maps_plans_command(self, args: List[str]):
        if not (self.active_mower_device and self.active_mower_device.mower and
                hasattr(self.active_mower_device.mower, 'map') and self.active_mower_device.mower.map):
            logger.info("Map data missing. Try 'sync_maps' or ensure the mower is connected and has reported data.")
            return

        map_data = self.active_mower_device.mower.map
        
        # --- Tasks/Plans (from mower.map.plan) ---
        print("\n--- Tasks/Plans (from mower.map.plan) ---")
        if map_data.plan and isinstance(map_data.plan, dict) and map_data.plan:
            collected_plans: List[Plan] = list(map_data.plan.values())

            WEEKDAY_MAP = {
                1: "Sun", 2: "Mon", 3: "Tue", 4: "Wed", 5: "Thu", 6: "Fri", 7: "Sat"
            }

            plan_id_width = 21
            days_width = 25
            start_time_width = 10
            name_width = 20
            height_width = 6
            speed_header_str = "Speed" 

            table_header_plans = (
                "PlanId".ljust(plan_id_width) + " | " +
                "Days".ljust(days_width) + " | " +
                "Start Time".ljust(start_time_width) + " | " +
                "Name".ljust(name_width) + " | " +
                "Height".ljust(height_width) + " | " +
                speed_header_str
            )
            table_divider_plans = "-" * len(table_header_plans)
            print("\n" + table_header_plans + "\n" + table_divider_plans)
            
            sorted_plans = sorted(collected_plans, key=lambda p: getattr(p, 'remained_seconds', 0))

            if not sorted_plans:
                print("  No plans to display in table format.".ljust(len(table_header_plans)))

            for plan_obj in sorted_plans:
                plan_id_str = str(getattr(plan_obj, 'plan_id', 'N/A'))
                start_time_str = str(getattr(plan_obj, 'start_time', 'N/A'))
                task_name_str = str(getattr(plan_obj, 'task_name', 'Unnamed Plan'))
                
                knife_height_val = getattr(plan_obj, 'knife_height', 'N/A')
                knife_height_str = str(knife_height_val)

                speed_val = getattr(plan_obj, 'speed', None)
                if isinstance(speed_val, (float, int)):
                    speed_str = f"{speed_val:.1f}"
                else:
                    speed_str = "N/A"

                days_list = []
                plan_weeks = getattr(plan_obj, 'weeks', None)
                if plan_weeks and isinstance(plan_weeks, list):
                    for day_num in plan_weeks:
                        if isinstance(day_num, int):
                            days_list.append(WEEKDAY_MAP.get(day_num, f"Day{day_num}"))
                
                days_display_str = ", ".join(days_list) if days_list else "N/A"

                row = (
                    plan_id_str.ljust(plan_id_width) + " | " +
                    days_display_str.ljust(days_width) + " | " +
                    start_time_str.ljust(start_time_width) + " | " +
                    task_name_str.ljust(name_width) + " | " +
                    knife_height_str.ljust(height_width) + " | " +
                    speed_str 
                )
                print(row)
        else:
            print("  No detailed plan data found in 'mower.map.plan'.")
            print("  Suggestions: 'sync_maps', or ensure app/HA has populated this if first time.")

        # --- Areas (from mower.map.area_name) ---
        print("\n\n--- Mapped Areas (from mower.map.area_name) ---") 
        if map_data.area_name and isinstance(map_data.area_name, list) and map_data.area_name:
            area_name_width = 30
            area_hash_width = 19
            area_index_width = 5 # For numbering

            table_header_areas = (
                "No.".ljust(area_index_width) + " | " +
                "Area Name".ljust(area_name_width) + " | " +
                "Hash".ljust(area_hash_width)
            )
            table_divider_areas = "-" * len(table_header_areas)
            print("\n" + table_header_areas + "\n" + table_divider_areas)

            # Sort areas by name for consistent display, if names exist
            sorted_areas = sorted(map_data.area_name, key=lambda a: getattr(a, 'name', 'zzzzzz'))


            if not sorted_areas:
                print("  No areas to display in table format.".ljust(len(table_header_areas)))

            for i, area_obj in enumerate(sorted_areas):
                area_name_str = str(getattr(area_obj, 'name', 'N/A'))
                area_hash_str = str(getattr(area_obj, 'hash', 'N/A'))
                index_str = str(i + 1)

                row = (
                    index_str.ljust(area_index_width) + " | " +
                    area_name_str.ljust(area_name_width) + " | " +
                    area_hash_str.ljust(area_hash_width)
                )
                print(row)
        else:
            print("  No area name data found in 'mower.map.area_name'. Try 'sync_maps'.")
        if 'table_divider_areas' in locals():
            print(table_divider_areas + "\n")


    async def handle_sync_maps_command(self, args: List[str]):
        await self.attempt_to_populate_maps(reason="CLI sync_maps")

    async def handle_mow_areas_command(self, args: List[str]):
        if not args:
            logger.info("Usage: mow_areas <hash1>,<hash2>,... [setting1=value1] [setting2=value2]...")
            # ... (keep detailed help from original)
            logger.info("IMPORTANT: Use exact Enum member names from your pymammotion library for settings like job_mode, mowing_laps, etc.")
            logger.info("           (Located in pymammotion/data/model/mowing_modes.py). Case-insensitive matching is attempted.")
            logger.info("  job_mode=GRID_FIRST (or BORDER_FIRST, etc.)")
            logger.info("  mowing_laps=ONE (or NONE, TWO, LAP_1, etc.)")
            logger.info("  obstacle_laps=ONE (or NONE, TWO, LAP_1, etc.)")
            logger.info("  channel_mode=SINGLE_GRID (or DOUBLE_GRID, NO_GRID, etc.)")
            logger.info("  ultra_wave=NORMAL (or SENSITIVE, NO_TOUCH, etc.)")
            logger.info("  toward_mode=ABSOLUTE_ANGLE (for specified angle) or RELATIVE_ANGLE (for optimal)")
            logger.info("Other numeric settings:")
            logger.info("  speed=0.8 (float, m/s)")
            logger.info("  blade_height=60 (integer, mm, e.g. 30-70 for Luba 1, 25-60 for Luba 2, -10 for Yuka)")
            logger.info("  channel_width=25 (integer, cm)")
            logger.info("  toward=0 (integer, degrees, for toward_mode=ABSOLUTE_ANGLE)")
            logger.info("  toward_included_angle=90 (integer, degrees)")
            logger.info("  rain_tactics=1 (integer, 0=park and wait, 1=continue mowing)")
            logger.info("Example: mow_areas 123,456 speed=0.6 mowing_laps=TWO job_mode=GRID_FIRST toward_mode=ABSOLUTE_ANGLE toward=30")
            return

        if not self.active_mower_device:
            logger.warning("Mower not connected. Cannot mow_areas.")
            return

        try:
            area_hashes_str = args[0]
            area_hashes = [int(h.strip()) for h in area_hashes_str.split(',')]
            if not area_hashes: raise ValueError("No area hashes provided.")
        except (ValueError, IndexError):
            logger.error("Invalid area hashes. Must be comma-separated integers as the first argument after mow_areas.")
            return

        op_settings = OperationSettings() # Uses defaults from pymammotion
        # Override with our preferences ..
        op_settings.mowing_laps = 2         # Perimenters
        op_settings.speed = 0.4             # Speed in m/s
        op_settings.blade_height = 65       # Height in mm
        op_settings.job_mode = 1            # 0(border_first), 1(grid_first)
        op_settings.ultra_wave = 10         # Default
        op_settings.obstacle_laps = 0       # Not needed by default
        op_settings.channel_mode = 0        # 0(single_grid), 1(double_grid), 2(segment_grid), 3(no_grid)
        op_settings.channel_width = 12      # Luba 2 mini awd
        op_settings.rain_tactics = 1        # 0(pause), 1(continue)
        op_settings.toward = 0              # Angle for toward_mode (does not work with segment_grid)
        op_settings.toward_included_angle = 90 # For checkerboard / double grid
        op_settings.toward_mode = 0         # 0(relative_angle), 1(absolute_angle), 2(random_angle)
        op_settings.border_mode = 1         # 0(border_first), 1(grid_first)

        op_settings.areas = area_hashes 

        for setting_str in args[1:]:
            if '=' not in setting_str:
                logger.warning(f"Skipping invalid setting format: {setting_str}. Expected key=value.")
                continue
            key, value_str = setting_str.split('=', 1)
            key = key.lower().strip()
            value_str = value_str.strip()

            try:
                # Enum-based settings with unified handling
                enum_settings = {
                    "job_mode": MowOrder,
                    "border_mode": MowOrder,
                    "mowing_laps": BorderPatrolMode,
                    "obstacle_laps": ObstacleLapsMode,
                    "channel_mode": CuttingMode,
                    "ultra_wave": DetectionStrategy,
                    "toward_mode": PathAngleSetting,
                }
                
                if key in enum_settings:
                    enum_class = enum_settings[key]
                    new_value = None
                    
                    # Try by name first (case-insensitive)
                    for enum_item in enum_class:
                        if enum_item.name.lower() == value_str.lower():
                            new_value = enum_item
                            break
                    
                    # Try by index if name lookup failed
                    if new_value is None:
                        try:
                            index = int(value_str)
                            enum_list = list(enum_class)
                            new_value = enum_list[index] if 0 <= index < len(enum_list) else None
                        except (ValueError, IndexError):
                            pass
                    
                    if new_value is not None:
                        setattr(op_settings, key, new_value.value)
                    else:
                        valid_values = [f"{i}({e.name})" for i, e in enumerate(enum_class)]
                        logger.warning(f"Invalid value for {key}: {value_str}. Valid values: {', '.join(valid_values)}")
                
                # Non-enum settings
                elif key == "speed": 
                    op_settings.speed = float(value_str)
                elif key == "blade_height": 
                    op_settings.blade_height = int(value_str)
                elif key == "channel_width": 
                    op_settings.channel_width = int(value_str)
                elif key == "toward": 
                    op_settings.toward = int(value_str)
                elif key == "toward_included_angle": 
                    op_settings.toward_included_angle = int(value_str)
                elif key == "rain_tactics": 
                    op_settings.rain_tactics = int(value_str)
                else: 
                    logger.warning(f"Unknown setting: {key}. Ignored.")
                    
            except ValueError as ve: 
                logger.warning(f"Invalid value type for {key}: {value_str}. Error: {ve}. Ignored.")
            except Exception as e_parse: 
                logger.warning(f"Generic error parsing setting {key}={value_str}: {e_parse}. Ignored.")

        mower_device_name = self.active_mower_device._cloud_device.deviceName
        if DeviceType.is_yuka(mower_device_name): # Yuka: blade_height should be -10
            logger.info("Yuka device detected. Setting blade_height to -10 in OperationSettings for this job.")
            op_settings.blade_height = -10
        
        logger.info(f"Final OperationSettings (after parsing): Areas={op_settings.areas}, JobMode={op_settings.job_mode}, MowingLaps={op_settings.mowing_laps}, BladeHeight={op_settings.blade_height}, Speed={op_settings.speed}")
        pprint(op_settings.__dict__)
        # return		# TODO
        
        try:
            path_order_str = create_path_order(op_settings, mower_device_name)
            if not path_order_str or not path_order_str.strip():
                logger.error(f"Generated path_order string is empty! This will likely cause 'generate_route_information' to fail. Review op_settings.")
                return
            logger.info(f"Generated path_order string: '{path_order_str}'")

            gen_route_info = GenerateRouteInformation(
                one_hashs=op_settings.areas,
                rain_tactics=op_settings.rain_tactics, speed=op_settings.speed,
                ultra_wave=op_settings.ultra_wave, toward=op_settings.toward,
                toward_included_angle=op_settings.toward_included_angle, toward_mode=op_settings.toward_mode,
                blade_height=op_settings.blade_height, channel_mode=op_settings.channel_mode,
                channel_width=op_settings.channel_width, job_mode=op_settings.job_mode, 
                edge_mode=op_settings.mowing_laps, # Maps to border patrol mode (mowing_laps)
                path_order=path_order_str,
                obstacle_laps=op_settings.obstacle_laps
            )
            
            # Luba 1 specific adjustments for GenerateRouteInformation
            # Pymammotion itself handles some of this in create_path_order based on device type
            # but GenerateRouteInformation might need direct adjustment as seen in HA core.
            if DeviceType.is_luba1(mower_device_name):
                logger.info("Luba 1 device detected. Adjusting toward_mode and toward_included_angle for GenerateRouteInformation to 0.")
                gen_route_info.toward_mode = 0 
                gen_route_info.toward_included_angle = 0

            logger.info(f"Prepared GenerateRouteInformation (sample): one_hashs={gen_route_info.one_hashs}, path_order='{gen_route_info.path_order}'")
            
            await self.safe_command_execution("generate_route_information", generate_route_information=gen_route_info)
            logger.info("'generate_route_information' sent. Waiting briefly for mower to plan...")
            await asyncio.sleep(3.0)
            
            await self.safe_command_execution("start_job")
            logger.info("Custom mowing job started via 'start_job'.")

            if DeviceType.is_luba1(mower_device_name):
                logger.info("Luba 1 specific: Attempting to ensure blades are engaged with 'set_blade_control(on_off=1)'...")
                await asyncio.sleep(1.5) 
                await self.safe_command_execution("set_blade_control", on_off=1)
                logger.info("Luba 1 'set_blade_control' command sent.")

            logger.info("mow_areas sequence complete. Monitor status.")

        except (MowerCommandError, ValueError) as e:
            logger.error(f"Error during mow_areas execution: {e}", exc_info=isinstance(e, ValueError)) # More detail for ValueError
        except Exception as e_mow: # Catch any other unexpected error
            logger.error(f"Unexpected error during mow_areas execution: {e_mow}", exc_info=True)


    async def handle_start_command(self, args: List[str]):
        if not args:
            logger.info("Usage: start <plan_id_or_name>")
            return

        plan_ref = " ".join(args)
        plan_id_to_start = None

        if not (self.active_mower_device and self.active_mower_device.mower and
                hasattr(self.active_mower_device.mower, 'map') and self.active_mower_device.mower.map and
                hasattr(self.active_mower_device.mower.map, 'plan') and self.active_mower_device.mower.map.plan):
            logger.warning("Plan data not available. Cannot start by name. Try 'sync_maps' or use plan ID directly.")
            if plan_ref.isdigit():
                plan_id_to_start = plan_ref
            else:
                logger.error("Cannot resolve plan name to ID without map data.")
                return
        else:
            # Try to match by ID first if it's a digit
            if plan_ref.isdigit():
                plan_id_to_start = plan_ref
                # Check if this ID exists in the plan dict keys (which are string representations of plan_id)
                if plan_id_to_start not in self.active_mower_device.mower.map.plan:
                     logger.warning(f"Plan ID {plan_id_to_start} not found in local map data keys. Will attempt to start anyway.")
                # No, we need to verify against plan_obj.plan_id for safety.
                # Or, assume keys of map.plan are the correct stringified plan_ids.
                # Let's iterate to be safe.
                found_by_id = False
                for p_id_key, p_obj in self.active_mower_device.mower.map.plan.items():
                    if str(getattr(p_obj, 'plan_id', p_id_key)) == plan_ref:
                        plan_id_to_start = str(getattr(p_obj, 'plan_id', p_id_key)) # Ensure it's the actual ID
                        logger.info(f"Matched plan by ID: '{getattr(p_obj, 'task_name', 'N/A')}' with ID: {plan_id_to_start}")
                        found_by_id = True
                        break
                if not found_by_id:
                     logger.warning(f"Plan ID {plan_ref} not found among actual plan IDs. Will attempt to start with '{plan_ref}' as ID if it's purely numeric.")
                     if not plan_ref.isdigit(): # If it wasn't purely numeric and not found by ID, it must be a name search
                         plan_id_to_start = None # Reset to trigger name search

            # If not found by ID or input wasn't purely numeric, search by name
            if not plan_id_to_start:
                found_plan_obj = None
                for p_id_key, p_obj in self.active_mower_device.mower.map.plan.items():
                    task_name = getattr(p_obj, 'task_name', None)
                    if task_name and task_name.lower() == plan_ref.lower():
                        found_plan_obj = p_obj
                        break
                if found_plan_obj:
                    plan_id_to_start = str(getattr(found_plan_obj, 'plan_id', None)) # Ensure string
                    if not plan_id_to_start:
                        logger.error(f"Found plan by name '{plan_ref}' but its ID is missing or invalid.")
                        return
                    logger.info(f"Found plan by name: '{getattr(found_plan_obj, 'task_name', plan_ref)}' with ID: {plan_id_to_start}")
                else:
                    logger.error(f"Plan with name or ID '{plan_ref}' not found in local map data.")
                    return

        if not plan_id_to_start:
            logger.error(f"Could not determine a plan ID for '{plan_ref}'.")
            return

        logger.info(f"Attempting to start task with resolved plan_id: {plan_id_to_start}")
        try:
            # The 'single_schedule' command expects plan_id as a string.
            await self.safe_command_execution("single_schedule", plan_id=str(plan_id_to_start))
            logger.info(f"Start command ('single_schedule') sent for plan_id {plan_id_to_start}. Monitor status.")
        except MowerCommandError as e_start:
            logger.error(f"Error sending 'single_schedule' command: {e_start}")
        except Exception as e_start_unexpected:
            logger.error(f"Unexpected error sending 'single_schedule': {e_start_unexpected}", exc_info=True)

    async def _execute_simple_command(self, user_command_name: str, pymammotion_cmd: str, params: Optional[Dict] = None):
        logger.info(f"Executing simple command '{user_command_name}' (pymammotion: '{pymammotion_cmd}')...")
        try:
            await self.safe_command_execution(pymammotion_cmd, **(params or {}))
            logger.info(f"'{user_command_name}' command sent successfully.")
        except MowerCommandError as e:
            logger.error(f"Failed to execute '{user_command_name}': {e}")
        except Exception as e_simple_unexpected:
             logger.error(f"Unexpected error executing '{user_command_name}': {e_simple_unexpected}", exc_info=True)


    async def handle_blade_height_command(self, args: List[str]):
        if not args or not args[0].isdigit():
            logger.error("Usage: blade_height <height_in_mm>")
            return
        try:
            height = int(args[0])
            await self._execute_simple_command("set_blade_height", "set_blade_height", {"height": height})
        except ValueError:
            logger.error("Invalid height. Must be an integer.")

    async def handle_raw_command(self, args: List[str]):
        if len(args) < 1:
            logger.error("Usage: rawcmd <command_name> [json_params_as_string_or_key=value pairs]")
            logger.error("Example       : rawcmd get_report_cfg")
            logger.error("Example (JSON): rawcmd set_work_parms {\"type\":1,\"value\":30}")
            logger.error("Example  (k=v):  rawcmd allpowerfull_rw rw_id=5 rw=1 context=1")
            return
        
        cmd_name = args[0]
        param_args = args[1:]
        params = {}

        if not param_args: # No params
            pass
        elif param_args[0].startswith('{') and param_args[-1].endswith('}'): # Likely JSON
            json_params_str = " ".join(param_args)
            try:
                params = json.loads(json_params_str)
                if not isinstance(params, dict):
                    logger.error("JSON params must be a valid JSON object (e.g., {\"key\": \"value\"}).")
                    return
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON parameters: {e}")
                return
        else: # key=value pairs
            for p_arg in param_args:
                if '=' not in p_arg:
                    logger.error(f"Invalid parameter format: {p_arg}. Expected key=value or a single JSON string.")
                    return
                key, value_str = p_arg.split('=', 1)
                # Attempt to convert value to int, float, or leave as str
                try:
                    if '.' in value_str: params[key] = float(value_str)
                    else: params[key] = int(value_str)
                except ValueError:
                    # Handle common boolean/null strings
                    if value_str.lower() == 'true': params[key] = True
                    elif value_str.lower() == 'false': params[key] = False
                    elif value_str.lower() == 'null' or value_str.lower() == 'none': params[key] = None
                    else: params[key] = value_str # Keep as string if not easily convertible
            logger.info(f"Parsed rawcmd params: {params}")

        await self._execute_simple_command(f"raw command {cmd_name}", cmd_name, params)


    async def handle_help_command(self, args: List[str]):
        print("\nAvailable Commands:")
        # ... (keep help text from original) ...
        print("  connect                       - Disconnect current and attempt to reconnect to the mower.")
        print("  status                        - Display summarized mower status.")
        print("  raw_status                    - Display full raw MowingDevice data.")
        print("  maps (or plans)               - List available tasks/plans and mapped areas.")
        print("  sync_maps                     - Attempt to refresh map and plan data from the mower.")
        print("  mow_areas <hashes> [opts...]  - Mow specified areas. Type 'mow_areas' for detailed options.")
        print("  start <plan_id_or_name>       - Start a predefined task/plan by its ID or name.")
        print("  dock (or charge)              - Send mower to dock.")
        print("  undock (or leave_dock)        - Command mower to leave the dock.")
        print("  pause                         - Pause the current mowing task.")
        print("  resume                        - Resume a paused mowing task.")
        print("  stop (or cancel)              - Stop/cancel the current job.")
        print("  blade_height <mm>             - Set blade cutting height (e.g., blade_height 60).")
        print("  rawcmd <cmd_name> [params]    - Send a raw command. Type 'rawcmd' for examples.")
        print("  help                          - Show this help message.")
        print("  exit                          - Exit the CLI application.")
        print("----------------------------------------------------------------------------------\n")


    async def handle_exit_command(self, args: List[str]):
        logger.info("Exit command received. Shutting down...")
        self.cli_exit_event.set()

    async def handle_connect_command(self, args: List[str]):
        logger.info("Manual (re)connect requested.")
        
        # First, clean up existing connection if any
        if self.active_mower_device:
            logger.info(f"Disconnecting current device: {self.active_mower_device._cloud_device.deviceName}...")
            await self._app_shutdown_logic() # Perform full cleanup of current connection
            # Reset controller state for new connection
            self.active_mower_device = None
            self.continuous_reporting_started = False
            # self.cli_exit_event should NOT be reset here if we want the main loop to continue
            logger.info("Previous device instance and associated resources (MQTT, etc.) cleared.")
        
        # Now, attempt to connect again
        if await self.connect_and_initialize_mower():
            logger.info(f"Successfully reconnected to: {self.active_mower_device._cloud_device.deviceName}")
            # Restart periodic monitor if it was stopped or not started
            if self._periodic_status_task and (self._periodic_status_task.done() or self._periodic_status_task.cancelled()):
                logger.info("Restarting periodic status monitor after reconnect.")
                self._periodic_status_task = asyncio.create_task(self.periodic_status_monitor())
            elif not self._periodic_status_task : # If it was never started (e.g. initial connect failed)
                 self._periodic_status_task = asyncio.create_task(self.periodic_status_monitor())
        else:
            logger.error("Reconnect attempt failed. Check credentials and network. Try 'connect' again or 'exit'.")


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
        
        # Bind the controller's method to be the handler
        bound_handler = getattr(self.controller, handler_method_name)
        self._commands[name] = bound_handler
        
        logger.debug(f"Registered command '{name}' to MowerController.{handler_method_name}")
        
        for alias in (aliases or []):
            self._aliases[alias] = name
            logger.debug(f"Registered alias '{alias}' for command '{name}'")


    async def dispatch(self, command_str: str):
        if not command_str.strip():
            return
        
        parts = command_str.strip().split() # Don't lowercase command itself yet, params might be case-sensitive
        action_input = parts[0].lower() # Command name is case-insensitive
        arguments = parts[1:]

        # Allow basic commands even if not fully connected
        if not self.controller.active_mower_device and action_input not in ["exit", "help", "connect"]:
            logger.warning("Mower not connected. Available commands: connect, help, exit.")
            return

        actual_command_name = self._aliases.get(action_input, action_input)
        handler = self._commands.get(actual_command_name)

        if handler:
            try:
                await handler(arguments)
            except MowerCommandError as e: # Catch command-specific errors
                logger.error(f"Command '{actual_command_name}' failed: {e}")
            except Exception as e: # Catch unexpected errors from handler logic
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
    
    # Simple commands using _execute_simple_command via partial or direct call in handler
    # For these, we can create small lambdas IF the handler method name is different
    # or just call controller._execute_simple_command directly.
    # The current setup maps to MowerController methods, so the controller methods will call _execute_simple_command.
    registry.register("dock", "handle_dock_command", aliases=["charge"])
    registry.register("undock", "handle_undock_command", aliases=["leave_dock"])
    registry.register("pause", "handle_pause_command")
    registry.register("resume", "handle_resume_command")
    registry.register("stop", "handle_stop_command", aliases=["cancel"])
    
    registry.register("blade_height", "handle_blade_height_command")
    registry.register("rawcmd", "handle_raw_command")
    registry.register("help", "handle_help_command")
    registry.register("exit", "handle_exit_command")
    registry.register("connect", "handle_connect_command")

# Add simple command handlers to MowerController that call _execute_simple_command
MowerController.handle_dock_command = lambda self, args: self._execute_simple_command("dock", "return_to_dock")
MowerController.handle_undock_command = lambda self, args: self._execute_simple_command("undock", "leave_dock")
MowerController.handle_pause_command = lambda self, args: self._execute_simple_command("pause", "pause_execute_task")
MowerController.handle_resume_command = lambda self, args: self._execute_simple_command("resume", "resume_execute_task")
MowerController.handle_stop_command = lambda self, args: self._execute_simple_command("stop", "cancel_job")


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
            if controller.cli_exit_event.is_set(): # Check again after input, event might be set during await
                break
            await registry.dispatch(cmd_input)
        except (EOFError, KeyboardInterrupt):
            logger.info("Exiting due to EOF or Interrupt...")
            controller.cli_exit_event.set() # Ensure exit event is set
            break
        except RuntimeError as e:
            if "Event loop is closed" in str(e) and controller.cli_exit_event.is_set():
                logger.info("Input thread caught loop closure during shutdown.")
                break
            logger.error(f"Runtime error in CLI loop: {e}", exc_info=True)
            # Potentially break or try to recover depending on error
        await asyncio.sleep(0.1) # Small yield to allow other tasks
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


    # Suppress known benign JSONDecodeErrors from pymammotion background tasks
    if isinstance(exception, json.JSONDecodeError):
        # Check if it's from known pymammotion internal MQTT message handling
        # This is a bit fragile as it depends on internal naming.
        problematic_coroutines_substrings = [
            "_parse_mqtt_response", "plan_callback", "_update_nav_data",
            "read_plan", "handle_message" # General paho message handler
        ]
        if any(sub in coro_repr for sub in problematic_coroutines_substrings) or \
           (future and future._source_traceback and any("pymammotion" in frame.filename for frame in future._source_traceback)):
             logger.debug(f"Handled known internal PyMammotion JSONDecodeError "
                         f"(likely from background map/plan detail fetch via MQTT): {msg} | {coro_repr}")
             return

    logger.error(f"Caught unhandled asyncio task exception: {msg}")
    if exception:
        logger.error("Exception traceback:", exc_info=exception) # This will print the traceback
    if coro_repr:
        logger.error(f"  Originating {coro_repr}")
    
    # Decide if we need to shut down the application
    # For now, just log. If critical, could call controller.cli_exit_event.set()


# --- Main Application ---
async def main_application():
    config = Config.from_env_and_input()

    # Configure logging
    log_level_val = getattr(logging, config.log_level, logging.INFO)
    logging.basicConfig(level=log_level_val,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        stream=sys.stdout)
    logger.setLevel(log_level_val) # Ensure our main logger respects the level

    # Set levels for verbose third-party loggers
    logging.getLogger("pymammotion.mqtt.mammotion_mqtt").setLevel(logging.WARNING)
    logging.getLogger("paho.mqtt.client").setLevel(logging.WARNING)
    logging.getLogger("linkkit").setLevel(logging.INFO) # Or WARNING
    logging.getLogger("asyncio").setLevel(logging.INFO) # Or WARNING

    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # The MowerController's __aenter__ handles initial connection and starting periodic monitor
    # and __aexit__ handles cleanup.
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
            main_task.cancel() # This should trigger cleanup in MowerController via finally/context exit
    except asyncio.CancelledError:
        logger.info("Main application task was cancelled.")
    except Exception as e_outer:
        logger.critical(f"Unhandled exception in main execution block: {e_outer}", exc_info=True)
    finally:
        logger.info("Main execution block finished or interrupted. Running final cleanup...")
        
        # Ensure main_task is awaited if it was cancelled or finished
        if main_task and not main_task.done():
            logger.info("Main task not done, cancelling it now explicitly.")
            main_task.cancel()
        if main_task:
            try:
                # This await is crucial for the __aexit__ of MowerController to run if main_task was cancelled.
                loop.run_until_complete(main_task) 
            except asyncio.CancelledError:
                logger.info("Main task acknowledged cancellation during final cleanup.")
            except Exception as e_final_main:
                logger.error(f"Exception from main_task during final completion: {e_final_main}", exc_info=True)

        # Additional cleanup for any other tasks that might still be around
        # (MowerController should handle its own tasks, but this is a safeguard)
        tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop)]
        if tasks:
            logger.info(f"Cancelling {len(tasks)} outstanding asyncio tasks during final shutdown...")
            for task in tasks: task.cancel()
            try:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                logger.info("Outstanding tasks processed.")
            except Exception as e_gather:
                 logger.error(f"Error gathering cancelled tasks: {e_gather}")


        if hasattr(loop, "shutdown_asyncgens"): # Python 3.6+
            logger.info("Shutting down async generators...")
            loop.run_until_complete(loop.shutdown_asyncgens())

        logger.info("Closing event loop...")
        loop.close()
        logger.info("Event loop closed. Application finished.")
