"""Interactive console for PyMammotion that publishes data to local MQTT server

Description:
    Based on PyMammotion/examples/dev_console.py

    Connects to mammotion servers to act as a gateway between cloud and a local mqtt server
    publishes all parameters to local mqtt server on change.

    Parameters published under {base_topic}/devices/{device_id}/...../..../.....

    JSON objects are published under:
        {base_topic}/devices/paths_json
        {base_topic}/devices/areas_json
        {base_topic}/devices/plans_json
        {base_topic}/devices/mowpath_json
        {base_topic}/devices/error_list_json
        {base_topic}/error_info/{language_code}_json

    Accepts commands on there topics:
        {base_topic}/devices/{device_id}/publish_all                        publishes all topics for device.
        {base_topic}/devices/{device_id}/clear_states                       clears state for areas, paths, plans and error_list

        {base_topic}/devices/{device_id}/send                               raw command, payload with details
        {base_topic}/devices/{device_id}/send_and_wait                      raw command, payload with details
        {base_topic}/devices/{device_id}/sync_map                           DevConsole Function, same as sync_areas
        {base_topic}/devices/{device_id}/fetch_rtk                          DevConsole Function, device_id must be rtk station

        {base_topic}/devices/{device_id}/start_report_stream                PyMammotion internal
        {base_topic}/devices/{device_id}/ensure_fresh_state                 PyMammotion internal
        {base_topic}/devices/{device_id}/request_report_snapshot            PyMammotion internal
        {base_topic}/devices/{device_id}/request_reports                    PyMammotion internal

        Sagas:
        {base_topic}/devices/{device_id}/sync_areas                         areas_json / map.area (Mow areas)
                                                                            paths_json / map.path (Paths channels/tunnels)
        {base_topic}/devices/{device_id}/sync_plans                         plans_json / map.plan (Tasks)
        {base_topic}/devices/{device_id}/sync_mowpath                       mowpath_json / map.current_mow_path (Waypoints)
        
        Streaming:
        {base_topic}/devices/{device_id}/get_stream_subscription            response on {base_topic}/devices/{device_id}/stream_subscription_json
        {base_topic}/devices/{device_id}/start_stream                       command to device to start streaming (required on older devices only)
        {base_topic}/devices/{device_id}/stop_stream                        command to device to stop streaming (be nice)
        
        Helpers:
        {base_topic}/devices/{device_id}/req_state_and_location             Updates sys_status and location.device
        {base_topic}/devices/{device_id}/req_errors                         Updates errors including errors_json
        {base_topic}/devices/{device_id}/req_dock_location                  Updates location.RTK and location.dock
        

        Other Functions:
        {base_topic}/devices/global/setup_all_mower_watchers                PyMammotion internal
        {base_topic}/devices/global/get_error_info                          publishes to {base_topic}/error_info/{language_code}/{error_code}) 
                                                                            and {base_topic}/error_info/{language_code}_json
        {base_topic}/devices/global/kill                                    payload must be 'kill'
        
    Command response JSON is published to {base_topic}/devices/{device_name}/{command}/response_json

    Sample 'send_and_wait' command:
        {
            cmd:"single_schedule",
            expected_field:"todev_planjob_set",
            kwargs: {
                plan_id: plan_id_number_here
            }
        }

    Sample 'send' command:
        {
            cmd:"pause_execute_task"
        }
    

Usage:
    create .env file in same folder as this file (or work directory where you launch from.):
    adjust content:
        EXTERNAL_MQTT_HOST=mqtt_host_here
        EXTERNAL_MQTT_PORT=1883
        EXTERNAL_MQTT_USER=username_here
        EXTERNAL_MQTT_PASS=password_here
        EXTERNAL_MQTT_TOPIC=m2m
        EMAIL=your@email.com
        PASSWORD=password_here
        MAMMOTION2MQTT_HA_VERSION="0.5.45"
        MAMMOTION2MQTT_PUBLISH_STATE=false
Flags:
    -l / --listen          Connect and receive messages without sending any outbound polls.
                           Useful for passive observation or debugging device-initiated traffic.
    --ble-address MAC      BLE-only mode: connect over Bluetooth to the mower at MAC.
                           Skips cloud login / MQTT entirely; transport runs its own
                           BleakScanner.find_device_by_address lookup.
    --device-name NAME     Friendly device name to register under (BLE-only mode).
                           Defaults to "Luba-BLE-<MAC suffix>".
Aditional Required packages:
    pymammotion and the file "pymammotion/examples/dev_console.py" in the same folder as this.
    ipython
    rich
    aiomqtt
    pyjwt # not jwt
    shapely
    python-dotenv


Output files (written to examples/mammotion2mqtt_output/):
    state_{device_name}.json        If enabled. Full device state (mower or RTK), updated on every
                                    incoming state change.
    mammotion_dev.log               If enabled. Full DEBUG log.

Available in the IPython REPL if running with attached terminal:
    mammotion                       MammotionClient singleton (cloud connection active)
    devices                         list[DeviceHandle]
    send(name, cmd, **kwargs)       Queue a command and block until complete
    send_and_wait(name, cmd, field) Send and block until the response arrives
    fetch_rtk(name)                 Fetch LoRa version for an RTK base station
    dump(name)                      Force-write state_{name}.json right now
    listen(on=True)                 Stop/resume MQTT polling on all devices
    console                         DevConsole instance
    loop                            The main asyncio event loop
    publish_all                     Publish all parameters to MQTT for all devices. Even if the value has not changed.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any
from importlib.metadata import version

import aiomqtt
import IPython  # noqa: F401 — re-exported for REPL namespace
from rich.logging import RichHandler

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from dev_console import DevConsole, _bootstrap_ble_only, _bootstrap_ble_via_proxy, _load_credentials, _rich_console, _save_credentials
from dotenv import load_dotenv

from pymammotion.client import MammotionClient
from pymammotion.transport.base import TransportType

from pymammotion.http.model.http import ErrorInfo

_LOGGER = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Config — populated by _load_env_config() at startup
# ──────────────────────────────────────────────────────────────────────────────

always_update_dump_files = False
write_log_to_file = False
publish_full_state = False
mammotion_client_ha_version = "0.5.44"


def _load_env_config() -> None:
    """Load .env file and apply environment-driven config flags (call once at startup)."""
    global always_update_dump_files, write_log_to_file, publish_full_state, mammotion_client_ha_version

    load_dotenv()

    def _getenv_lower(var: str) -> str:
        return os.getenv(var, "").lower()

    for var in [
        "EXTERNAL_MQTT_HOST", "EXTERNAL_MQTT_PORT", "EXTERNAL_MQTT_USER", "EXTERNAL_MQTT_PASS",
        "EXTERNAL_MQTT_TOPIC", "EMAIL", "PASSWORD","MAMMOTION2MQTT_HA_VERSION","ALIYUN_APP_KEY","ALIYUN_APP_SECRET","MAMMOTION_OAUTH2_CLIENT_ID","MAMMOTION_OUATH2_CLIENT_SECRET",
    ]:
        if os.getenv(var):
            if "pass" in var.lower():
                print(f"Environment variable {var} is set to 'XXXXXXX' (Password)")
            else:
                print(f"Environment variable {var} is set to '{os.getenv(var)}'")
        else:
            print(f"Environment variable {var} is not set")

    if _getenv_lower("MAMMOTION2MQTT_WRITE_FILES") == "true":
        print("always_update_dump_files")
        always_update_dump_files = True
        print("write_log_to_file")
        write_log_to_file = True
    if _getenv_lower("MAMMOTION2MQTT_PUBLISH_STATE") == "true":
        print("publish_full_state")
        publish_full_state = True
    if _getenv_lower("MAMMOTION2MQTT_HA_VERSION"):
        mammotion_client_ha_version = os.getenv("MAMMOTION2MQTT_HA_VERSION",mammotion_client_ha_version)


# ──────────────────────────────────────────────────────────────────────────────
# Output directory
# ──────────────────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path(__file__).parent / "mammotion2mqtt_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def _setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    rich = RichHandler(
        console=_rich_console,
        rich_tracebacks=True,
        show_time=True,
        show_path=False,
        markup=True,
    )
    rich.setLevel(logging.INFO)
    root.addHandler(rich)

    if write_log_to_file:
        # File handler — everything at DEBUG
        fh = logging.FileHandler(OUTPUT_DIR / "mammotion_dev.log", mode="a", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s  %(message)s"))
        root.addHandler(fh)

    # Show our own activity on console; suppress chatty third-party transport
    for module in (
        "pymammotion.transport",
        "pymammotion.client",
        "pymammotion.device",
        "pymammotion.messaging",
        "pymammotion.aliyun",
        "pymammotion.http",
    ):
        logging.getLogger(module).setLevel(logging.DEBUG)
    for noisy in ("aiomqtt", "aiohttp", "asyncio", "bleak"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ──────────────────────────────────────────────────────────────────────────────
# External MQTT Publisher
# ──────────────────────────────────────────────────────────────────────────────


class ExternalMQTTPublisher:
    """Publishes device state to an external MQTT broker and subscribes to commands."""

    def __init__(
            self,
            host: str,
            port: int = 1883,
            username: str | None = None,
            password: str | None = None,
            base_topic: str = "mammotion",
    ) -> None:
        """Initialize the external MQTT publisher."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.base_topic = base_topic
        self.client: aiomqtt.Client | None = None
        self.connected = False
        self._context_manager = None
        self.dev_console: DevConsole | None = None
        self._listener_task: asyncio.Task | None = None
        self._previous_state: dict[str, dict[str, Any]] = {}
        self._previous_complex_state: dict[str, dict[str, str]] = {}

    async def connect(self) -> None:
        """Connect to the external MQTT broker."""
        self._will = aiomqtt.Will(
            topic=f"{self.base_topic}/mammotion2mqtt/status", payload="offline", retain=True
        )
        try:
            self.client = aiomqtt.Client(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                will=self._will,
            )
            self._context_manager = self.client.__aenter__()
            await self._context_manager
            self.connected = True
            await self.client.publish(
                f"{self.base_topic}/mammotion2mqtt/status", payload="online", retain=True
            )
            await self.client.publish(
                f"{self.base_topic}/mammotion2mqtt/account_email",
                payload=os.getenv("EMAIL", "").lower(),
                retain=True,
            )
            await self.client.publish(
                f"{self.base_topic}/mammotion2mqtt/pymammotion_version",
                 payload=version('PyMammotion'), 
                 retain=True)
            await self.client.publish(
                f"{self.base_topic}/mammotion2mqtt/homeassistant_version",
                 payload=mammotion_client_ha_version, 
                 retain=True)

            _LOGGER.info(
                "Connected to external MQTT broker [bold]%s:%d[/bold]",
                self.host,
                self.port,
            )
            try:
                self._listener_task = asyncio.create_task(self._listen_for_commands())
                _LOGGER.info("Command listener task created")
            except Exception as e:
                _LOGGER.error("Failed to create command listener task: %s", e, exc_info=True)
        except Exception as e:
            _LOGGER.error("Failed to connect to external MQTT broker: %s", e, exc_info=True)
            self.connected = False
            self.client = None

    async def disconnect(self) -> None:
        """Disconnect from the external MQTT broker."""
        if self._listener_task is not None:
            await self.client.publish(f"{self.base_topic}/mammotion2mqtt/status", payload="exited", retain=True)
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self.client is not None:
            try:
                await self.client.__aexit__(None, None, None)
                self.connected = False
                _LOGGER.info("Disconnected from external MQTT broker")
            except Exception as e:
                _LOGGER.error("Error disconnecting from MQTT: %s", e)
            finally:
                self.client = None

    async def publish(self, topic: str, payload: str | dict, retain: bool = False, qos: int = 2) -> None:
        """Publish a message to the external MQTT broker."""
        if not self.connected or self.client is None:
            _LOGGER.warning("MQTT not connected, skipping publish to %s", topic)
            return

        if isinstance(payload, dict):
            payload = json.dumps(payload)

        try:
            await self.client.publish(topic, payload, qos, retain=retain)
        except Exception as e:
            _LOGGER.warning("Failed to publish to %s: %s", topic, e)

    async def _listen_for_commands(self) -> None:
        """Subscribe to command topics and process incoming commands."""
        if not self.client:
            _LOGGER.error("MQTT client not initialized")
            return

        try:
            await self.client.subscribe(f"{self.base_topic}/devices/+/publish_all")
            await self.client.subscribe(f"{self.base_topic}/devices/+/clear_state")
            await self.client.subscribe(f"{self.base_topic}/devices/+/send")
            await self.client.subscribe(f"{self.base_topic}/devices/+/send_and_wait")

            await self.client.subscribe(f"{self.base_topic}/devices/+/sync_map")
            await self.client.subscribe(f"{self.base_topic}/devices/+/fetch_rtk")

            await self.client.subscribe(f"{self.base_topic}/devices/+/sync_areas")
            await self.client.subscribe(f"{self.base_topic}/devices/+/sync_plans")
            await self.client.subscribe(f"{self.base_topic}/devices/+/sync_mowpath")
            
            await self.client.subscribe(f"{self.base_topic}/devices/+/get_stream_subscription")
            await self.client.subscribe(f"{self.base_topic}/devices/+/start_stream")
            await self.client.subscribe(f"{self.base_topic}/devices/+/stop_stream")

            await self.client.subscribe(f"{self.base_topic}/devices/+/req_state_and_location")
            await self.client.subscribe(f"{self.base_topic}/devices/+/req_errors")
            await self.client.subscribe(f"{self.base_topic}/devices/+/req_dock_location")

            await self.client.subscribe(f"{self.base_topic}/devices/+/start_report_stream")
            await self.client.subscribe(f"{self.base_topic}/devices/+/ensure_fresh_state")
            await self.client.subscribe(f"{self.base_topic}/devices/+/request_report_snapshot")
            await self.client.subscribe(f"{self.base_topic}/devices/+/request_reports")

            
            
            await self.client.subscribe(f"{self.base_topic}/devices/global/setup_all_mower_watchers")
            await self.client.subscribe(f"{self.base_topic}/devices/global/get_error_info")
            await self.client.subscribe(f"{self.base_topic}/devices/global/kill")

            _LOGGER.info("Subscribed to command topics under [bold]%s/devices/+[/bold]", self.base_topic)

            async for message in self.client.messages:
                try:
                    await self._handle_command(message)
                except Exception as e:
                    _LOGGER.error("Error handling command message: %s", e, exc_info=True)

        except asyncio.CancelledError:
            _LOGGER.info("Command listener cancelled")
        except Exception as e:
            _LOGGER.error("Error in command listener: %s", e, exc_info=True)

    async def _handle_command(self, message: Any) -> None:
        """Handle an incoming MQTT command message."""
        try:
            topic = str(message.topic)
            payload = message.payload.decode() if isinstance(message.payload, bytes) else message.payload

            parts = topic.split("/")
            if len(parts) < 4:
                _LOGGER.warning("Invalid command topic format: %s", topic)
                return

            device_name = parts[2]
            command = parts[3]

            cmd_data: dict[str, Any] = {}
            if payload:
                try:
                    cmd_data = json.loads(payload)
                except json.JSONDecodeError:
                    _LOGGER.warning("Invalid JSON in command payload: %s", payload)
                    #return

            _LOGGER.info(
                "[bold yellow]→ MQTT Command[/bold yellow]  [cyan]%s[/cyan]  [green]%s[/green]",
                device_name,
                command,
            )

            if not self.dev_console:
                _LOGGER.error("DevConsole not set up for command execution")
                return

            if command == "send":
                await self._execute_send(device_name, cmd_data)
            elif command == "send_and_wait":
                await self._execute_send_and_wait(device_name, cmd_data)
            elif command == "sync_map":
                await self.dev_console.sync_map(device_name)
            elif command == "fetch_rtk":
                await self.dev_console.fetch_rtk(device_name)
                #await self._execute_fetch_rtk(device_name, cmd_data)

            elif command == "publish_all":
                await self._execute_publish_all(device_name, cmd_data)
            elif command == "clear_state":
                # Clear complex object cache (plans / areas / paths / mowpath)
                self._previous_complex_state.pop(device_name, None)
                
            elif command == "sync_areas":
                await self._execute_sync_areas(device_name, cmd_data)
            elif command == "sync_plans":
                await self._execute_sync_plans(device_name, cmd_data)    
            elif command == "sync_mowpath":
                await self._execute_sync_mowpath(device_name, cmd_data)
            elif command == "get_stream_subscription":
                await self._execute_get_stream_subscription(device_name,cmd_data)  
            elif command == "start_stream":
                await self._execute_start_stream(device_name,cmd_data)    
            elif command == "stop_stream":
                await self._execute_stop_stream(device_name,cmd_data)    
            elif command == "request_report_snapshot":
                """Fire a one-shot count=1 report, skipped if the BLE stream is already active.

                Use after state-changing commands or on state-change watchers to get a fresh
                snapshot without fighting an in-progress BLE continuous feed.
                Used by HA after state-changing commands and in the sys_status watcher.
                Safe to call at any time; skips silently if BLE is already streaming fresher data.
                """
                handle = self.dev_console.mammotion.device_registry.get_by_name(device_name)
                if handle:
                    await handle.request_report_snapshot()
            elif command == "ensure_fresh_state":
                """Fire a one-shot snapshot if the last inbound report is older than ``max_age_s`` seconds.

                Intended for use at the top of user-action handlers (start/dock/pause/cancel)
                to avoid acting on stale state after a long idle period.  Fire-and-forget:
                the response arrives asynchronously.
                """

                await self.dev_console.mammotion.ensure_fresh_state(device_name)
                
            elif command == "start_report_stream":
                """Start a transient report window lasting ``duration_ms`` ms.

                If the device is actively mowing or returning (ACTIVE mode), starts a
                continuous (count=0) stream and arms a stop timer.  In any other mode
                (docked, idle) a single one-shot count=1 poll is issued instead — there
                is no point holding a continuous stream for a stationary device.

                For the continuous path:
                * Repeated calls within the window reset the timer without re-sending
                RPT_START (prevents cloud quota spam on frequent callers like a dashboard).
                * If the BLE polling loop already holds a continuous stream the RPT_START
                is skipped (data already flowing) but the timer is still armed.
                * The stop callback skips RPT_STOP if BLE is still streaming so the BLE
                polling loop is never interrupted mid-run.
                """
                handle = self.dev_console.mammotion.device_registry.get_by_name(device_name)
                if handle:
                    await handle.start_report_stream()

            elif command == "request_reports":
                """Enqueue a one-shot "request_iot_sys(count=count)" data refresh."""
                handle = self.dev_console.mammotion.device_registry.get_by_name(device_name)
                if handle:
                    await handle.request_reports()

                    
            elif command == "setup_all_mower_watchers":
                """Set up state-change watchers for all registered mower devices.

                Skips RTK base stations and swimming-pool (Spino/S1/E1) devices.
                """
                self.dev_console.mammotion.setup_all_mower_watchers()
                
            elif command == "req_state_and_location":
                await self._execute_send(device_name, { "cmd": "get_report_cfg"})
            elif command == "req_errors":
                await self._execute_send(device_name, {"cmd": "allpowerfull_rw","kwargs": {"rw_id": 5,"rw": 1,"context": 2}})
                await self._execute_send(device_name, {"cmd": "allpowerfull_rw","kwargs": {"rw_id": 5,"rw": 1,"context": 3}})
            elif command == "req_dock_location":
                # send_and_Wait
                await self._execute_send(device_name, {"cmd":"read_write_device","expected_field":"bidire_comm_cmd","kwargs": {"rw_id":5,"rw":1,"context":1,}})
            


            elif command == "get_error_info":
                await self._execute_get_error_info(cmd_data)
            elif command == "kill":
                if payload == "kill":
                    _LOGGER.warning("Killing app in 3 seconds. App might restart if running in a container")
                    await self.client.publish(f"{self.base_topic}/mammotion2mqtt/status", payload="kill", retain=True)
                    await asyncio.sleep(3)
                    self._listener_task.cancel()
                    #sys.exit(0)
                    os._exit(0) # hard exit
            else:
                _LOGGER.warning("Unknown command: %s", command)

        except Exception as e:
            _LOGGER.error("Error handling command: %s", e, exc_info=True)

    def _flatten_dict(self, d: dict, parent_key: str = "", sep: str = "/") -> dict[str, Any]:
        """Flatten a nested dictionary for MQTT topic publishing."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k

            if isinstance(v, (list, tuple)):
                items.append((new_key, json.dumps(v)))
            elif isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            elif isinstance(v, (str, int, float, bool, type(None))):
                items.append((new_key, v))
            else:
                try:
                    items.append((new_key, str(v)))
                except Exception:
                    pass

        return dict(items)
    
    async def _publish_if_changed_json(
        self,
        device_name: str,
        source_obj: Any,
        attr_path: list[str],
        topic_suffix: str,
    ) -> None:
        """
        Extract a nested attribute, detect changes, and publish full JSON if changed.

        Example:
            attr_path = ["map", "plan"]
            topic_suffix = "plans"
        """
        #_LOGGER.warning("DEBUG: Checking %s for %s", ".".join(attr_path), device_name)
        try:
            # Traverse attribute path safely
            current = source_obj
            for attr in attr_path:
                if not hasattr(current, attr):
                    return
                current = getattr(current, attr)

            if current is None:
                return

            # Convert to JSON-safe dict
            
            data_dict = self._to_jsonable(current)
            data_str = json.dumps(data_dict, sort_keys=True)

            # if hasattr(current, "to_json"):
            #     data_dict = json.loads(current.to_json())
            # else:
            #     data_dict = json.loads(json.dumps(current, default=str))

            data_str = json.dumps(data_dict, sort_keys=True)

            # Init device cache
            if device_name not in self._previous_complex_state:
                self._previous_complex_state[device_name] = {}

            key = ".".join(attr_path)
            prev = self._previous_complex_state[device_name].get(key)

            if prev != data_str:
                topic = f"{self.base_topic}/devices/{device_name}/{topic_suffix}"

                await self.publish(
                    topic,
                    payload=data_str,
                    retain=True,
                    qos=2,
                )

                self._previous_complex_state[device_name][key] = data_str

                _LOGGER.info(
                    "Published updated %s for %s",
                    key,
                    device_name,
                )

        except Exception as e:
            _LOGGER.warning(
                "Failed processing %s for %s: %s",
                ".".join(attr_path),
                device_name,
                e,
            )

    
    def _to_jsonable(self, obj: Any, seen: set[int] | None = None) -> Any:
        """Recursively convert any object into JSON-safe structure."""
        if seen is None:
            seen = set()

        # Prevent recursion loops
        obj_id = id(obj)
        if obj_id in seen:
            return "<recursion>"
        seen.add(obj_id)

        # Primitive types
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj

        # Dict
        if isinstance(obj, dict):
            return {
                str(k): self._to_jsonable(v, seen)
                for k, v in obj.items()
            }

        # List / tuple / set
        if isinstance(obj, (list, tuple, set)):
            return [self._to_jsonable(x, seen) for x in obj]

        # If object has to_json method
        if hasattr(obj, "to_json"):
            try:
                return json.loads(obj.to_json())
            except Exception:
                pass

        # If object has __dict__ → expand it
        if hasattr(obj, "__dict__"):
            try:
                return {
                    key: self._to_jsonable(value, seen)
                    for key, value in vars(obj).items()
                    if not key.startswith("_")
                }
            except Exception:
                pass

        # Fallback
        return str(obj)



    async def _extract_device_parameters(self, handle: Any) -> dict[str, Any]:
        """Extract all relevant parameters from a device handle."""
        snapshot = handle.snapshot
        device_state = snapshot.device_state if hasattr(snapshot, "device_state") else None

        parameters: dict[str, Any] = {
            "device_name": handle.device_name,
            "device_id": handle.device_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        mqtt_transport = handle._transports.get(TransportType.CLOUD_ALIYUN) or handle._transports.get(  # noqa: SLF001
            TransportType.CLOUD_MAMMOTION
        )
        parameters["mqtt_connected"] = mqtt_transport is not None and mqtt_transport.is_connected

        if device_state is not None:
            try:
                state_dict: dict[str, Any] = {}
                for field_name in dir(device_state):
                    if not field_name.startswith("_"):
                        try:
                            value = getattr(device_state, field_name)
                            if not callable(value) and not hasattr(value, "__dict__"):
                                state_dict[field_name] = value
                        except Exception:
                            pass
                parameters["state"] = state_dict
            except Exception as e:
                _LOGGER.warning("Error extracting device state: %s", e)

        try:
            parameters["raw_snapshot"] = json.loads(handle.snapshot.raw.to_json())
        except Exception:
            pass

        return parameters

    async def _publish_device_to_external_mqtt(self, device_name: str) -> None:
        """Publish a single device's current state to the external MQTT broker."""
        if not self.connected or not self.dev_console:
            return

        handle = self.dev_console.mammotion.device_registry.get_by_name(device_name)
        if handle is None:
            return

        try:
            parameters = await self._extract_device_parameters(handle)

            
            # --- COMPLEX OBJECT CHANGE DETECTION ---
            await self._publish_if_changed_json(
                device_name,
                handle.snapshot.raw,
                ["map", "plan"],
                "plans_json"
            )

            await self._publish_if_changed_json(
                device_name,
                handle.snapshot.raw,
                ["map", "area"],
                "areas_json"
            )

            await self._publish_if_changed_json(
                device_name,
                handle.snapshot.raw,
                ["map", "path"],
                "paths_json"
            )

            await self._publish_if_changed_json(
                device_name,
                handle.snapshot.raw,
                ["map", "current_mow_path"],
                "mowpath_json"
            )
            await self._publish_if_changed_json(
                device_name,
                handle.snapshot.raw,
                ["errors"],
                "error_list_json"
            )


            state_topic = f"{self.base_topic}/devices/{device_name}/state"
            if publish_full_state:
                await self.publish(state_topic, parameters, retain=True, qos=2)

            flat_params = self._flatten_dict(parameters)

            if device_name not in self._previous_state:
                self._previous_state[device_name] = {}

            previous = self._previous_state[device_name]

            for key, value in flat_params.items():
                if key in ("state", "raw_snapshot"):
                    continue

                value_str = str(value)

                if key not in previous or previous[key] != value_str:
                    field_topic = f"{self.base_topic}/devices/{device_name}/{key}"
                    await self.publish(field_topic, value_str, retain=False, qos=2)
                    previous[key] = value_str
                    _LOGGER.debug(
                        "Published changed parameter for %s: %s = %s", device_name, key, value_str
                    )

            _LOGGER.debug("Published device %s to external MQTT with change detection", device_name)
        except Exception as e:
            _LOGGER.error("Error publishing device %s to external MQTT: %s", device_name, e)

    async def _execute_publish_all(self, device_name: str, cmd_data: dict) -> None:  # noqa: ARG002
        """Force publish all parameters for a device."""
        if not self.dev_console:
            return

        await self._send_response(device_name, "publish_all", "sending")
        
        try:
            #if device_name in self._previous_state:
            #    del self._previous_state[device_name]
            
            # Clear flat state cache
            self._previous_state.pop(device_name, None)

            # Clear complex object cache (plans / areas / paths)
            self._previous_complex_state.pop(device_name, None)

            await self._publish_device_to_external_mqtt(device_name)
            await self._send_response(device_name, "publish_all", "success")
            _LOGGER.info("✓ publish_all executed: %s", device_name)
        except Exception as e:
            await self._send_response(device_name, "publish_all", "error", error=str(e))
            _LOGGER.error("✗ publish_all failed: %s", e)

    async def _execute_get_error_info(self, cmd_data: dict) -> None:
        try:
            language_code = cmd_data.get("language_code", "en")

            all_sessions = self.dev_console.mammotion.account_registry.all_sessions
            if not all_sessions:
                _LOGGER.warning("No account sessions available")
                return
            
            acct_session = all_sessions[0]
            error_codes: dict[str, ErrorInfo] = await acct_session.cloud_client.mammotion_http.get_all_error_codes()
            
            # Build individual error info entries
            for error_info in error_codes.values():
                error_payload: dict[str, Any] = {
                    "code": error_info.code,
                    "implication": getattr(error_info, f"{language_code}_implication", "N/A"),
                    "solution": getattr(error_info, f"{language_code}_solution", "N/A")
                }
                await self.publish(
                    f"{self.base_topic}/error_info/{language_code}/{error_info.code}",
                    payload=error_payload,
                    retain=True,
                )
            
            # Publish full error_codes dict as JSON
            full_error_dict: dict[str, dict[str, Any]] = {}
            for code, error_info in error_codes.items():
                full_error_dict[code] = {
                    "code": error_info.code,
                    "implication": getattr(error_info, f"{language_code}_implication", "N/A"),
                    "solution": getattr(error_info, f"{language_code}_solution", "N/A")
                }
            
            await self.publish(
                f"{self.base_topic}/error_info/{language_code}_json",
                payload=full_error_dict,
                retain=True,
            )
            
            _LOGGER.info("✓ get_error_info executed for language: %s (%d errors)", language_code, len(error_codes))
        except Exception as e:
            _LOGGER.error("✗ get_error_info failed: %s", e, exc_info=True)

    async def _execute_get_stream_subscription(self, device_name: str, cmd_data:dict) -> None:
        #device_id = cmd_data.get("device_id")
        iot_id : str | None = None
        device_id = ""

        for handle in self.dev_console.mammotion.device_registry.all_devices:
            if handle.device_name == device_name: #if handle.device_id == device_id:
                iot_id = handle.iot_id
                device_id = handle.device_id
                break

        if iot_id == None:
            _LOGGER.warning("Unable to find device: %s", device_name)
            await self._send_response(device_name, "get_stream_subscription", "error", error="Device not found")
            return

        all_sessions = self.dev_console.mammotion.account_registry.all_sessions
        if not all_sessions:
            _LOGGER.warning("No account sessions available")
            return
        
        acct_session = all_sessions[0]

        
        res = await acct_session.cloud_client.mammotion_http.get_stream_subscription(iot_id,False)
        #res = await cloud_client.mammotion_http.get_stream_subscription(_devices_list[0].iot_id)
        print(res)
        pars_dict = {
            "appid": res.data.appid,
            "channelName" : res.data.channelName,
            "token": res.data.token,
            "uid": res.data.uid,
            "license": res.data.license,
            "availableTime": res.data.availableTime
        }
        await self.publish(
            f"{self.base_topic}/devices/{device_id}/stream_subscription_json",
            payload=pars_dict,
            retain=True,
        )

    

    async def _execute_start_stream(self, device_name: str, cmd_data:dict) -> None:

        handle = self.dev_console.mammotion.device_registry.get_by_name(device_name)
        if handle is None:
            await self._send_response(device_name, "start_stream", "error", error="Device not found")
            return

        
        await self.dev_console.mammotion._send_agora_join_over_mqtt(handle)


    async def _execute_stop_stream(self, device_name: str, cmd_data:dict) -> None:    
        handle = self.dev_console.mammotion.device_registry.get_by_name(device_name)
        if handle is None:
            await self._send_response(device_name, "stop_stream", "error", error="Device not found")
            return
        
        """Fire the Agora join-channel command over MQTT only, without waiting for an ack."""
        command_bytes = handle.commands.device_agora_join_channel_with_position(enter_state=0)
        mqtt_transport = handle._transports.get(TransportType.CLOUD_ALIYUN) or handle._transports.get(  # noqa: SLF001
            TransportType.CLOUD_MAMMOTION
        )
        #for transport_type in (TransportType.CLOUD_ALIYUN, TransportType.CLOUD_MAMMOTION):
        #    mqtt_transport = handle.get_transport(transport_type)
        if mqtt_transport is not None and mqtt_transport.is_connected:
            await handle._send_marked(mqtt_transport, command_bytes)
            #break
            

    async def _execute_send(self, device_name: str, cmd_data: dict) -> None:
        """Execute send command."""
        if not self.dev_console:
            return

        cmd = cmd_data.get("cmd")
        kwargs = cmd_data.get("kwargs", {})
        
        await self._send_response(device_name, "send", "sending", cmd=cmd)
        
        if not cmd:
            _LOGGER.warning("send: missing 'cmd' field")
            await self._send_response(device_name, "send", "missing 'cmd' field", cmd=cmd)
            return

        try:
            await self.dev_console.mammotion.send_command_with_args(device_name, cmd, **kwargs)
            await self._send_response(device_name, "send", "success", cmd=cmd)
            _LOGGER.info("✓ send executed: %s %s", device_name, cmd)
        except Exception as e:
            await self._send_response(device_name, "send", "error", cmd=cmd, error=str(e))
            _LOGGER.error("✗ send failed: %s", e)

    async def _execute_send_and_wait(self, device_name: str, cmd_data: dict) -> None:
        """Execute send_and_wait command."""
        if not self.dev_console:
            return

        cmd = cmd_data.get("cmd")
        expected_field = cmd_data.get("expected_field")
        kwargs = cmd_data.get("kwargs", {})
        send_timeout = cmd_data.get("send_timeout", 1.0)

        await self._send_response(
            device_name, "send_and_wait", "sending",
            cmd=cmd, expected_field=expected_field
        )
        
        if not cmd or not expected_field:
            _LOGGER.warning("send_and_wait: missing 'cmd' or 'expected_field'")
            await self._send_response(
                device_name, "send_and_wait", "missing 'cmd' or 'expected_field'",
                cmd=cmd, expected_field=expected_field
            )
            return

        try:
            result = await self.dev_console.mammotion.send_command_and_wait(
                device_name, cmd, expected_field, send_timeout=send_timeout, **kwargs
            )
            await self._send_response(
                device_name, "send_and_wait", "success",
                cmd=cmd, expected_field=expected_field, result=str(result)
            )
            _LOGGER.info("✓ send_and_wait executed: %s %s → %s", device_name, cmd, expected_field)
        except Exception as e:
            await self._send_response(
                device_name, "send_and_wait", "error",
                cmd=cmd, expected_field=expected_field, error=str(e)
            )
            _LOGGER.error("✗ send_and_wait failed: %s", e)
    async def _execute_sync_mowpath(self, device_name: str, cmd_data: dict) -> None:
        """Execute sync_mowpath command."""
        if not self.dev_console:
            return

        timeout = cmd_data.get("timeout", 120.0)
        
        await self._send_response(device_name, "sync_mowpath", "sending", timeout=timeout)
        
        try:
            await self.dev_console.mammotion.check_and_get_mow_path(device_name)
            await self._send_response(device_name, "sync_mowpath", "success", timeout=timeout)
            _LOGGER.info("✓ sync_mowpath enqueued: %s", device_name)
        except Exception as e:
            await self._send_response(device_name, "sync_mowpath", "error", error=str(e))
            _LOGGER.error("✗ sync_mowpath failed: %s", e)
    async def _execute_sync_areas(self, device_name: str, cmd_data: dict) -> None:
        """Execute sync_areas command."""
        if not self.dev_console:
            return

        timeout = cmd_data.get("timeout", 120.0)
        
        await self._send_response(device_name, "sync_areas", "sending", timeout=timeout)
        
        try:
            #self.dev_console.sync_map(device_name,timeout=timeout) # use implementation in dev_console
            await self.dev_console.mammotion.start_map_sync(device_name)
            await self._send_response(device_name, "sync_areas", "success", timeout=timeout)
            _LOGGER.info("✓ sync_areas enqueued: %s", device_name)
        except Exception as e:
            await self._send_response(device_name, "sync_areas", "error", error=str(e))
            _LOGGER.error("✗ sync_areas failed: %s", e)
    async def _execute_sync_plans(self, device_name: str, cmd_data: dict) -> None:
        """Execute sync_plans command."""
        if not self.dev_console:
            return

        timeout = cmd_data.get("timeout", 120.0)
        
        await self._send_response(device_name, "sync_plans", "sending", timeout=timeout)
        
        try:
            await self.dev_console.mammotion.start_plan_sync(device_name)
            await self._send_response(device_name, "sync_plans", "success", timeout=timeout)
            _LOGGER.info("✓ sync_plans enqueued: %s", device_name)
        except Exception as e:
            await self._send_response(device_name, "sync_plans", "error", error=str(e))
            _LOGGER.error("✗ sync_plans failed: %s", e)
    # async def _execute_fetch_rtk(self, device_name: str, cmd_data: dict) -> None:  # noqa: ARG002
    #     """Execute fetch_rtk command."""
    #     if not self.dev_console:
    #         return

    #     await self._send_response(device_name, "fetch_rtk", "sending")
        
    #     try:
    #         #self.dev_console.fetch_rtk(device_name) # use implementation in dev_console
    #         await self.dev_console.mammotion.fetch_rtk_lora_info(device_name)
    #         await self._send_response(device_name, "fetch_rtk", "success")
    #         _LOGGER.info("✓ fetch_rtk executed: %s", device_name)
    #     except Exception as e:
    #         await self._send_response(device_name, "fetch_rtk", "error", error=str(e))
    #         _LOGGER.error("✗ fetch_rtk failed: %s", e)

    async def _send_response(
        self,
        device_name: str,
        command: str,
        status: str,
        **extra_fields
    ) -> None:
        """Send a response message for a command."""
        response: dict[str, Any] = {
            "status": status,
            "device": device_name,
            "command": command,
            "timestamp": datetime.now(UTC).isoformat(),
            **extra_fields,
        }
        
        # Use command-specific topic, fall back to generic "send" topic
        topic_suffix = command if command in ["sync_map", "send_and_wait", "fetch_rtk","send"] else "mammotion_to_mqtt"
        topic = f"{self.base_topic}/devices/{device_name}/{topic_suffix}/response_json"
        
        await self.publish(topic, response, retain=False)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

async def _main(args: argparse.Namespace) -> None:
    _load_env_config()
    _setup_logging()

    mammotion = MammotionClient(mammotion_client_ha_version)
    main_loop = asyncio.get_running_loop()

    # Connect external MQTT before cloud login so we can publish failures
    external_mqtt: ExternalMQTTPublisher | None = None
    mqtt_host = os.environ.get("EXTERNAL_MQTT_HOST")
    if mqtt_host:
        mqtt_port = int(os.environ.get("EXTERNAL_MQTT_PORT", "1883"))
        mqtt_user = os.environ.get("EXTERNAL_MQTT_USER")
        mqtt_pass = os.environ.get("EXTERNAL_MQTT_PASS")
        mqtt_topic = os.environ.get("EXTERNAL_MQTT_TOPIC", "mammotion")
        external_mqtt = ExternalMQTTPublisher(
            host=mqtt_host,
            port=mqtt_port,
            username=mqtt_user,
            password=mqtt_pass,
            base_topic=mqtt_topic,
        )
        _LOGGER.info("Connecting to external MQTT Broker [bold]%s[/bold] …", mqtt_host)
        await external_mqtt.connect()

    dev = DevConsole(
        mammotion,
        main_loop,
        external_mqtt,
        output_dir=OUTPUT_DIR,
        always_dump=always_update_dump_files,
    )

    if args.esphome_proxy:
        if not args.ble_address:
            msg = "--esphome-proxy requires --ble-address (the mower's BLE MAC)"
            raise SystemExit(msg)
        # ESPHome BLE-proxy path: bridge to bleak via bleak-esphome and reuse
        # the standard BLE-only flow.
        await _bootstrap_ble_via_proxy(
            mammotion,
            proxy_host=args.esphome_proxy,
            proxy_password=args.esphome_password or "",
            ble_address=args.ble_address,
            device_name=args.device_name,
        )
    elif args.ble_address:
        # BLE-only path: skip cloud login entirely, connect over Bluetooth.
        await _bootstrap_ble_only(mammotion, args.ble_address, args.device_name)
    else:
        saved_email, saved_password = _load_credentials()
        email = os.environ.get("EMAIL") or input(f"Mammotion email [{saved_email}]: ").strip() or saved_email
        password = (
            os.environ.get("PASSWORD")
            or input(f"Mammotion password [{'*' * len(saved_password) if saved_password else ''}]: ").strip()
            or saved_password
        )
        _save_credentials(email, password)

        _LOGGER.info("Logging in as [bold]%s[/bold] …", email)
        try:
            await mammotion.login_and_initiate_cloud(email, password)
            _LOGGER.info("Login complete — waiting for MQTT …")
        except Exception as e:
            print("Failed to start: " + str(e))
            if external_mqtt:
                await external_mqtt.publish(
                    f"{external_mqtt.base_topic}/mammotion2mqtt/mammotion_status",
                    payload="Failed to start: " + str(e),
                    retain=True,
                )
            await asyncio.sleep(3)
            print("Exiting due to error.")
            sys.exit(1)

        await asyncio.sleep(3)

    dev.hook_all_devices()
    dev.hook_all_rtk_devices()
    await dev.start_all_devices()

    if args.listen:
        for handle in mammotion.device_registry.all_devices:
            await handle.stop_polling()
        _LOGGER.info("[bold yellow]Listen-only mode[/bold yellow] — MQTT polling disabled on all devices")

    if not args.ble_address and not args.esphome_proxy:
        # log_mqtt_credentials walks AccountSession.cloud_client / mammotion_http,
        # both of which are None in any BLE-only mode.
        dev.log_mqtt_credentials()
    if always_update_dump_files:
        dev.dump_all()

    if external_mqtt:
        await dev.publish_all_devices_to_external_mqtt()

    device_names = [h.device_name for h in mammotion.device_registry.all_devices]
    _LOGGER.info(
        "Connected. Devices: [bold]%s[/bold]",
        ", ".join(device_names) or "(none yet)",
    )
    _LOGGER.info("Output directory: [bold]%s[/bold]", OUTPUT_DIR)

    if external_mqtt:
        await external_mqtt.publish(
            f"{external_mqtt.base_topic}/mammotion2mqtt/account_email",
            payload=os.getenv("EMAIL", "").lower(),
            retain=True,
        )
        await external_mqtt.publish(
            f"{external_mqtt.base_topic}/mammotion2mqtt/mammotion_status",
            payload="ready",
            retain=True,
        )

    # ── REPL namespace ────────────────────────────────────────────────────────
    namespace = {
        "mammotion": mammotion,
        "devices": mammotion.device_registry.all_devices,
        "send": dev.send,
        "send_and_wait": dev.send_and_wait,
        "sync_map": dev.sync_map,
        "fetch_rtk": dev.fetch_rtk,
        "dump": dev.dump,
        "dump_all": dev.dump_all,
        "status": dev.status,
        "creds": dev.log_mqtt_credentials,
        "debug": dev.debug,
        "listen": dev.listen,
        "publish_all": dev.sync_external_mqtt,
        "console": dev,
        "loop": main_loop,
        "asyncio": asyncio,
    }

    mqtt_note = (
        "  [cyan]publish_all()[/cyan]                                      "
        "— publish all parameters to external MQTT\n"
        if external_mqtt
        else ""
    )
    listen_note = "  [bold yellow]⚡ Listen-only mode — polling disabled[/bold yellow]\n\n" if args.listen else ""
    _rich_console.print(
        "\n[bold green][PyMammotion dev console][/bold green]\n"
        f"  [cyan]devices[/cyan]  = {device_names}\n\n"
        f"{listen_note}"
        "  [cyan]send(name, cmd, **kwargs)[/cyan]                           — queue a command (blocking)\n"
        "  [cyan]send_and_wait(name, cmd, expected_field, **kwargs)[/cyan]  — send and block for response\n"
        "  [cyan]sync_map(name)[/cyan]                                      — run a full MapFetchSaga (blocking)\n"
        "  [cyan]fetch_rtk(name)[/cyan]                                     — fetch LoRa version for an RTK base station\n"
        "  [cyan]dump(name)[/cyan]                                          — write state_{name}.json\n"
        "  [cyan]dump_all()[/cyan]                                          — write state JSON for all devices\n"
        "  [cyan]status()[/cyan]                                            — show connection status\n"
        "  [cyan]creds()[/cyan]                                             — print all MQTT credentials\n"
        "  [cyan]debug(on=True)[/cyan]                                      — toggle DEBUG logging on terminal\n"
        "  [cyan]listen(on=True)[/cyan]                                     — stop/resume MQTT polling on all devices\n"
        f"{mqtt_note}"
        f"  [cyan]loop[/cyan]                                               — main asyncio event loop\n"
        f"\n  Output → [dim]{OUTPUT_DIR}[/dim]\n"
    )



    def _run_idle_loop():
        import time
        import datetime
        counter = 0

        while True:
            print("Alive. DateTime: " + str(datetime.datetime.now()))

            time.sleep(60)

    def _start_repl() -> None:
        import IPython as _IPython
        _IPython.embed(user_ns=namespace, using="asyncio")

    if sys.stdout.isatty():
        print("Terminal attached, starting REPL")
        # Run IPython in a thread so the main loop stays alive for MQTT
        await asyncio.to_thread(_start_repl)
    else:
        print("Running without terminal attached, like in docker, printing DateTime every minute")
        await asyncio.to_thread(_run_idle_loop)

    _LOGGER.info("REPL exited — shutting down.")
    if external_mqtt:
        await external_mqtt.disconnect()
    await mammotion.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PyMammotion interactive dev console with MQTT bridge")
    parser.add_argument(
        "-l", "--listen",
        action="store_true",
        help="listen-only mode: connect and receive messages without sending any polls",
    )
    parser.add_argument(
        "--ble-address",
        metavar="MAC",
        default=None,
        help="BLE-only mode: connect to the mower at this MAC address. Skips cloud login / MQTT.",
    )
    parser.add_argument(
        "--device-name",
        metavar="NAME",
        default=None,
        help="Friendly device name (BLE-only mode).  Defaults to Luba-BLE-<MAC suffix>.",
    )
    parser.add_argument(
        "--esphome-proxy",
        metavar="HOST",
        default=None,
        help=(
            "Connect via an ESPHome BLE proxy at HOST (e.g. esp32-bluetooth-proxy.local). "
            "Requires --ble-address.  Skips cloud login.  Needs the 'extras' deps "
            "(uv sync --group extras)."
        ),
    )
    parser.add_argument(
        "--esphome-password",
        metavar="PASS",
        default=None,
        help="API password for the ESPHome proxy (default: empty).",
    )
    _args = parser.parse_args()
    try:
        asyncio.run(_main(_args))
    except SystemExit:
        print("System exit")
    except KeyboardInterrupt:
        pass
