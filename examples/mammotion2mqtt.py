"""Interactive development console for PyMammotion.

Usage:
    create .env file in same folder as this file:
    adjust content:
    EXTERNAL_MQTT_HOST=mqtt_host_here
    EXTERNAL_MQTT_PORT=1883
    EXTERNAL_MQTT_USER=username_here
    EXTERNAL_MQTT_PASS=password_here
    EXTERNAL_MQTT_TOPIC=m2m
    EMAIL=svefro.your@email.com
    PASSWORD=password_here

Output files (written to examples/dev_output/):
    state_{device_name}.json        Full device state (mower or RTK), updated on every
                                    incoming state change.
    mammotion_dev.log               Full DEBUG log.

Available in the IPython REPL:
    mammotion                       MammotionClient singleton (cloud connection active)
    devices                         list[DeviceHandle]
    send(name, cmd, **kwargs)       Queue a command and block until complete
    send_and_wait(name, cmd, field) Send and block until the response arrives
    fetch_rtk(name)                 Fetch LoRa version for an RTK base station
    dump(name)                      Force-write state_{name}.json right now
    console                         DevConsole instance
    loop                            The main asyncio event loop
"""





from __future__ import annotations

import sys
# Insert the local path at the very beginning (index 0) to give it highest priority
#sys.path.insert(0, "/mnt/SveFroOneDriveOffice/Programming/Python/sf_mammotion/new_app/PyMammotion")

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any

import IPython
from rich.console import Console
from rich.logging import RichHandler

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymammotion.account.registry import BLE_ONLY_ACCOUNT
from pymammotion.client import MammotionClient
from pymammotion.transport.base import Subscription, TransportType

from dotenv import load_dotenv

# Load the .env file into the environment
load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Output directory
# ──────────────────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path(__file__).parent / "dev_output"
OUTPUT_DIR.mkdir(exist_ok=True)

CREDENTIALS_FILE = Path(__file__).parent / "dev_credentials.json"


def _load_credentials() -> tuple[str, str]:
    """Load saved email/password from dev_credentials.json, if present."""
    if CREDENTIALS_FILE.exists():
        try:
            data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
            return data.get("email", ""), data.get("password", "")
        except Exception:
            pass
    return "", ""


def _save_credentials(email: str, password: str) -> None:
    """Persist email/password to dev_credentials.json."""
    try:
        CREDENTIALS_FILE.write_text(
            json.dumps({"email": email, "password": password}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        _LOGGER.warning("Could not save credentials to %s", CREDENTIALS_FILE)

_rich_console = Console()
_LOGGER = logging.getLogger(__name__)


def _setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Rich handler — INFO+ to terminal
    rich = RichHandler(
        console=_rich_console,
        rich_tracebacks=True,
        show_time=True,
        show_path=False,
        markup=True,
    )
    rich.setLevel(logging.INFO)
    root.addHandler(rich)

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
# DevConsole — holds all strong references so weakref callbacks aren't collected
# ──────────────────────────────────────────────────────────────────────────────


class DevConsole:
    """Wires per-device callbacks and provides REPL helpers."""

    def __init__(
        self,
        mammotion: MammotionClient,
        main_loop: asyncio.AbstractEventLoop,
        external_mqtt_publisher: ExternalMQTTPublisher | None = None,
    ) -> None:
        """Initialize DevConsole with optional external MQTT publisher."""
        self.mammotion = mammotion
        self.loop = main_loop
        self.external_mqtt = external_mqtt_publisher
        if external_mqtt_publisher:
            external_mqtt_publisher.dev_console = self  # Register for command execution
        self._notification_cbs: dict[str, tuple[Callable[..., Awaitable[None]], Subscription]] = {}

    # ── File helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _state_path(name: str) -> Path:
        return OUTPUT_DIR / f"state_{name.replace('/', '_')}.json"

    def dump(self, name: str) -> None:
        """Write the current MowingDevice JSON state for *name* to disk."""
        handle = self.mammotion.device_registry.get_by_name(name)
        if handle is None:
            _LOGGER.warning(
                "dump: device %r not found. Available: %s",
                name,
                [h.device_name for h in self.mammotion.device_registry.all_devices],
            )
            return
        try:
            path = self._state_path(name)
            data = json.loads(handle.snapshot.raw.to_json())
            path.write_text(json.dumps(data, indent=4), encoding="utf-8")
            #path.write_text(handle.snapshot.raw.to_json(), encoding="utf-8")
            
            _LOGGER.debug("State written → %s", path)
        except Exception:
            _LOGGER.exception("dump: failed to write state for %s", name)
            _LOGGER.debug("dump: raw snapshot for %s: %r", name, handle.snapshot.raw)

    # ── Callback factory ──────────────────────────────────────────────────────

    def _make_notification_cb(self, device_name: str) -> Callable[[Any], Awaitable[None]]:
        """Return an async callback for broker.subscribe_unsolicited.

        Called with a LubaMsg on every unsolicited incoming message.
        """
        import betterproto2

        async def _on_message(msg: Any) -> None:
            self.dump(device_name)
            # Publish to external MQTT on state change
            if self.external_mqtt:
                await self.external_mqtt._publish_device_to_external_mqtt(device_name)
            try:
                sub_name, _ = betterproto2.which_one_of(msg, "LubaSubMsg")
                _LOGGER.info(
                    "[bold cyan]← %s[/bold cyan]  [green]%s[/green]",
                    device_name,
                    sub_name,
                )
            except Exception:
                _LOGGER.info("[bold cyan]← %s[/bold cyan]  [green](message)[/green]", device_name)

        return _on_message

    # ── Credential logging ────────────────────────────────────────────────────

    def log_mqtt_credentials(self) -> None:
        """Log all MQTT-related credentials for active cloud connections."""
        import time

        _rich_console.rule("[bold yellow]MQTT Credentials[/bold yellow]")

        for acct_session in self.mammotion.account_registry.all_sessions:
            if acct_session.account_id == BLE_ONLY_ACCOUNT:
                continue

            # Prefer the HTTP client embedded in the cloud gateway (Aliyun path).
            http = (
                acct_session.cloud_client.mammotion_http
                if acct_session.cloud_client is not None
                else acct_session.mammotion_http
            )

            _rich_console.print(f"\n[bold white]── Account: {acct_session.account_id} ──[/bold white]")

            # ── HTTP / JWT layer ─────────────────────────────────────────────────
            if http is not None and http.login_info is not None:
                _rich_console.print("[bold]HTTP access token[/bold]")
                expires_in = http.expires_in
                remaining = max(0, int(expires_in - time.time()))
                _rich_console.print(f"  access_token  : {http.login_info.access_token}")
                _rich_console.print(
                    f"  expires_at    : {datetime.fromtimestamp(expires_in, tz=UTC).isoformat()}"
                    f"  ([cyan]{remaining // 3600}h {(remaining % 3600) // 60}m[/cyan] remaining)"
                )
                _rich_console.print(f"  refresh_token : {http.login_info.refresh_token}")

                _LOGGER.debug("HTTP access_token=%s", http.login_info.access_token)
                _LOGGER.debug("HTTP refresh_token=%s", http.login_info.refresh_token)
                _LOGGER.debug("HTTP expires_at=%s remaining=%ds", http.expires_in, remaining)

                # ── MammotionMQTT JWT credentials ─────────────────────────────
                if http.mqtt_credentials is not None:
                    creds = http.mqtt_credentials
                    _rich_console.print("\n[bold]MammotionMQTT (JWT)[/bold]")
                    _rich_console.print(f"  host          : {creds.host}")
                    _rich_console.print(f"  username      : {creds.username}")
                    _rich_console.print(f"  client_id     : {creds.client_id}")
                    _rich_console.print(f"  jwt           : {creds.jwt}")
                    _LOGGER.debug(
                        "MammotionMQTT host=%s username=%s client_id=%s jwt=%s",
                        creds.host,
                        creds.username,
                        creds.client_id,
                        creds.jwt,
                    )

            # ── AliyunMQTT credentials ───────────────────────────────────────────
            aliyun = acct_session.aliyun_transport
            cloud_client = acct_session.cloud_client
            if aliyun is not None:
                cfg = aliyun._config  # noqa: SLF001
                _rich_console.print("\n[bold white]── AliyunMQTT ──[/bold white]")
                _rich_console.print("[bold]AliyunMQTT (HMAC + iotToken)[/bold]")
                _rich_console.print(f"  host          : {cfg.host}")
                _rich_console.print(f"  username      : {cfg.username}")
                _rich_console.print(f"  product_key   : {cfg.product_key}")
                _rich_console.print(f"  device_name   : {cfg.device_name}")
                _rich_console.print(f"  device_secret : {cfg.device_secret}")
                _LOGGER.debug(
                    "AliyunMQTT host=%s username=%s product_key=%s device_name=%s device_secret=%s",
                    cfg.host,
                    cfg.username,
                    cfg.product_key,
                    cfg.device_name,
                    cfg.device_secret,
                )

                if cloud_client is not None:
                    auth_resp = cloud_client.session_by_authcode_response
                    if auth_resp is not None and auth_resp.data is not None:
                        issued = cloud_client._iot_token_issued_at  # noqa: SLF001
                        ion_exp = max(0, int(issued + auth_resp.data.iotTokenExpire - time.time()))
                        ref_exp = max(0, int(issued + auth_resp.data.refreshTokenExpire - time.time()))
                        _rich_console.print("\n[bold]  Aliyun session[/bold]")
                        _rich_console.print(f"    iotToken          : {auth_resp.data.iotToken}")
                        _rich_console.print(
                            f"    iotTokenExpire    : {auth_resp.data.iotTokenExpire}s total"
                            f"  ([cyan]{ion_exp // 3600}h {(ion_exp % 3600) // 60}m[/cyan] remaining)"
                        )
                        _rich_console.print(f"    refreshToken      : {auth_resp.data.refreshToken}")
                        _rich_console.print(
                            f"    refreshTokenExpire: {auth_resp.data.refreshTokenExpire}s total"
                            f"  ([cyan]{ref_exp // 3600}h {(ref_exp % 3600) // 60}m[/cyan] remaining)"
                        )
                        _rich_console.print(
                            f"    issued_at         : {datetime.fromtimestamp(issued, tz=UTC).isoformat()}"
                        )
                        _LOGGER.debug(
                            "Aliyun iotToken=%s iotTokenExpire=%ds refreshToken=%s refreshTokenExpire=%ds",
                            auth_resp.data.iotToken,
                            auth_resp.data.iotTokenExpire,
                            auth_resp.data.refreshToken,
                            auth_resp.data.refreshTokenExpire,
                        )

        _rich_console.rule()

    # ── Device wiring ─────────────────────────────────────────────────────────

    def hook_device(self, device_name: str) -> None:
        """Attach the state-change callback to a device (idempotent)."""
        if device_name in self._notification_cbs:
            return  # already hooked
        handle = self.mammotion.device_registry.get_by_name(device_name)
        if handle is None:
            return
        cb = self._make_notification_cb(device_name)
        sub = handle.broker.subscribe_unsolicited(cb)
        self._notification_cbs[device_name] = (cb, sub)  # keep both alive
        _LOGGER.info("Hooked broker callback for [bold]%s[/bold]", device_name)

    def hook_all_devices(self) -> None:

        for handle in self.mammotion.device_registry.all_devices:
            self.hook_device(handle.device_name)

    # ── RTK device wiring ─────────────────────────────────────────────────────

    def _make_rtk_state_cb(self, device_name: str) -> Callable[[Any], Awaitable[None]]:
        """Return an async callback for state_changed_bus on an RTK base station."""
        from pymammotion.state.device_state import DeviceSnapshot

        async def _on_state_changed(snapshot: DeviceSnapshot) -> None:
            self.dump(device_name)
            # Publish to external MQTT on state change
            if self.external_mqtt:
                await self.external_mqtt._publish_device_to_external_mqtt(device_name)
            _LOGGER.info(
                "[bold magenta]← %s[/bold magenta]  [green]state updated[/green]",
                device_name,
            )

        return _on_state_changed

    def hook_rtk_device(self, device_name: str) -> None:
        """Attach a state-change callback to an RTK base station device (idempotent).

        RTK devices push most of their data via thing/properties events rather
        than protobuf broker messages, so this subscribes to state_changed_bus
        instead of the unsolicited broker.
        """
        if device_name in self._notification_cbs:
            return
        handle = self.mammotion.device_registry.get_by_name(device_name)
        if handle is None:
            return
        cb = self._make_rtk_state_cb(device_name)
        sub = handle.subscribe_state_changed(cb)
        self._notification_cbs[device_name] = (cb, sub)
        _LOGGER.info("Hooked state-change callback for RTK [bold]%s[/bold]", device_name)

    def hook_all_rtk_devices(self) -> None:
        """Attach state-change callbacks to every registered RTK base station."""
        from pymammotion.utility.device_type import DeviceType

        for handle in self.mammotion.device_registry.all_devices:
            if DeviceType.is_rtk(handle.device_name):
                self.hook_rtk_device(handle.device_name)

    def fetch_rtk(self, name: str) -> None:
        """Fetch LoRa version info for an RTK base station (blocking).

        Example:
            fetch_rtk("Luba-RTK-XXXXXX")

        """
        try:
            fut = asyncio.run_coroutine_threadsafe(
                self.mammotion.fetch_rtk_lora_info(name), self.loop
            )
            fut.result(timeout=15)
            print(f"✓  fetch_rtk_lora_info → {name!r}")
        except TimeoutError:
            print(f"✗  Timed out fetching RTK info for {name!r}")
        except Exception as exc:
            print(f"✗  Error: {exc}")

    # ── REPL helpers ──────────────────────────────────────────────────────────

    def send(self, name: str, cmd: str, **kwargs: Any) -> None:
        """Queue a command on a device and block until complete (30 s timeout).

        Example:
            send("Luba-VS563L6H", "send_todev_ble_sync", sync_type=3)

        """
        handle = self.mammotion.device_registry.get_by_name(name)
        if handle is None:
            print(
                f"Device {name!r} not found.\n"
                f"Available: {[h.device_name for h in self.mammotion.device_registry.all_devices]}"
            )
            return
        try:
            fut = asyncio.run_coroutine_threadsafe(
                self.mammotion.send_command_with_args(name, cmd, **kwargs), self.loop
            )
            fut.result(timeout=30)
            print(f"✓  {cmd!r} → {name!r}")
        except TimeoutError:
            print(f"✗  Timed out waiting for {name!r}")
        except Exception as exc:
            print(f"✗  Error: {exc}")

    def send_and_wait(
        self,
        name: str,
        cmd: str,
        expected_field: str,
        *,
        send_timeout: float = 1.0,
        timeout: float = 3.0,
        **kwargs: Any,
    ) -> Any:
        """Send a command and block until the matching protobuf response arrives.

        Uses broker.send_and_wait for request/response correlation via the
        protobuf oneof field name.  Returns the full LubaMsg response.

        Args:
            name:           Registered device name.
            cmd:            Method name on MammotionCommand (e.g. "get_report_cfg").
            expected_field: Protobuf oneof field name expected in the response
                            (e.g. "toapp_report_cfg").
            send_timeout:   Seconds the broker waits for the device to respond
                            per attempt (default 5 s).
            timeout:        Wall-clock seconds before this call gives up (default 30 s).
            **kwargs:       Arguments forwarded to the command builder.

        Example:
            resp = send_and_wait(
                "Luba-VS563L6H",
                "get_report_cfg",
                "toapp_report_cfg",
            )

        """
        handle = self.mammotion.device_registry.get_by_name(name)
        if handle is None:
            print(
                f"Device {name!r} not found.\n"
                f"Available: {[h.device_name for h in self.mammotion.device_registry.all_devices]}"
            )
            return None
        try:
            fut = asyncio.run_coroutine_threadsafe(
                self.mammotion.send_command_and_wait(
                    name,
                    cmd,
                    expected_field,
                    send_timeout=send_timeout,
                    **kwargs,
                ),
                self.loop,
            )
            result = fut.result(timeout=timeout)
            print(f"✓  {cmd!r} → {expected_field!r}  {result}")
            return result
        except TimeoutError:
            print(f"✗  Timed out waiting for {expected_field!r} from {name!r}")
            return None
        except Exception as exc:
            print(f"✗  Error: {exc}")
            return None

    def sync_map(self, name: str, *, timeout: float = 120.0) -> None:
        """Run a full MapFetchSaga for *name* and dump state on completion.

        Blocks until the saga finishes or *timeout* seconds elapse.

        Example:
            sync_map("Luba-VS563L6H")

        """
        handle = self.mammotion.device_registry.get_by_name(name)
        if handle is None:
            print(
                f"Device {name!r} not found.\n"
                f"Available: {[h.device_name for h in self.mammotion.device_registry.all_devices]}"
            )
            return
        try:
            fut = asyncio.run_coroutine_threadsafe(
                self.mammotion.start_map_sync(name), self.loop
            )
            fut.result(timeout=timeout)
            print(f"✓  map sync enqueued for {name!r} — watching for completion …")
        except TimeoutError:
            print(f"✗  Timed out enqueuing map sync for {name!r}")
        except Exception as exc:
            print(f"✗  Error: {exc}")

    def dump_all(self) -> None:
        """Force-write state JSON for every connected device."""
        for handle in self.mammotion.device_registry.all_devices:
            self.dump(handle.device_name)
            print(f"Written → {self._state_path(handle.device_name)}")

    def status(self) -> None:
        """Print a summary of connected devices and transport health."""
        print(f"\n{'Device':<30}  {'MQTT':>6}  State file")
        print("-" * 70)
        for handle in self.mammotion.device_registry.all_devices:
            mqtt_transport = handle._transports.get(TransportType.CLOUD_ALIYUN) or handle._transports.get(  # noqa: SLF001
                TransportType.CLOUD_MAMMOTION
            )
            mqtt_ok = "✓" if mqtt_transport is not None and mqtt_transport.is_connected else "✗"
            path = self._state_path(handle.device_name)
            size = f"{path.stat().st_size:,} B" if path.exists() else "—"
            print(f"  {handle.device_name:<28}  {mqtt_ok:>6}  {size}")
        print()

    # ── Extend DevConsole class with external MQTT methods ────────────────────

    

    

    def _make_notification_cb(self, device_name: str) -> Callable[[Any], Awaitable[None]]:
        """Return an async callback for broker.subscribe_unsolicited.

        Called with a LubaMsg on every unsolicited incoming message.
        """
        import betterproto2

        async def _on_message(msg: Any) -> None:
            self.dump(device_name)
            # Publish to external MQTT on state change
            if self.external_mqtt and self.external_mqtt.connected:
                await self.external_mqtt._publish_device_to_external_mqtt(device_name)
            try:
                sub_name, _ = betterproto2.which_one_of(msg, "LubaSubMsg")
                _LOGGER.info(
                    "[bold cyan]← %s[/bold cyan]  [green]%s[/green]",
                    device_name,
                    sub_name,
                )
            except Exception:
                _LOGGER.info("[bold cyan]← %s[/bold cyan]  [green](message)[/green]", device_name)

        return _on_message

    def _make_rtk_state_cb(self, device_name: str) -> Callable[[Any], Awaitable[None]]:
        """Return an async callback for state_changed_bus on an RTK base station."""
        from pymammotion.state.device_state import DeviceSnapshot

        async def _on_state_changed(snapshot: DeviceSnapshot) -> None:
            self.dump(device_name)
            # Publish to external MQTT on state change
            if self.external_mqtt and self.external_mqtt.connected:
                await self.external_mqtt._publish_device_to_external_mqtt(device_name)
            _LOGGER.info(
                "[bold magenta]← %s[/bold magenta]  [green]state updated[/green]",
                device_name,
            )

        return _on_state_changed

    async def publish_all_devices_to_external_mqtt(self) -> None:
        """Publish the current state of all devices to the external MQTT broker."""
        if not self.external_mqtt or not self.external_mqtt.connected:
            _LOGGER.warning("External MQTT not connected")
            return

        _LOGGER.info("Publishing all devices to external MQTT broker …")
        for handle in self.mammotion.device_registry.all_devices:
            await self.external_mqtt._publish_device_to_external_mqtt(handle.device_name)
        _LOGGER.info("All devices published to external MQTT broker")
        
    def sync_external_mqtt(self) -> None:
        """Synchronously publish all devices to external MQTT (REPL helper)."""
        try:
            fut = asyncio.run_coroutine_threadsafe(
                self.publish_all_devices_to_external_mqtt(), self.loop
            )
            fut.result(timeout=10)
            print("✓  All devices synced to external MQTT")
        except TimeoutError:
            print("✗  Timed out syncing to external MQTT")
        except Exception as exc:
            print(f"✗  Error: {exc}")




# ──────────────────────────────────────────────────────────────────────────────
# External MQTT Publisher
# ──────────────────────────────────────────────────────────────────────────────
import aiomqtt
#from aiomqtt import Client, Will

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
        
        

    async def connect(self) -> None:
        """Connect to the external MQTT broker."""
        
        self._will = aiomqtt.Will(topic=f"{self.base_topic}/mammotion2mqtt/mqtt_status", payload="offline", retain=True)
        try:
            self.client = aiomqtt.Client(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                will=self._will
            )

            self.client
            self._context_manager = self.client.__aenter__()
            await self._context_manager
            self.connected = True
            await self.client.publish(f"{self.base_topic}/mammotion2mqtt/mqtt_status", payload="online", retain=True)
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

    async def publish(self, topic: str, payload: str | dict, retain: bool = False) -> None:
        """Publish a message to the external MQTT broker."""
        if not self.connected or self.client is None:
            _LOGGER.warning("MQTT not connected, skipping publish to %s", topic)
            return

        if isinstance(payload, dict):
            payload = json.dumps(payload)

        try:
            await self.client.publish(topic, payload, retain=retain)
        except Exception as e:
            _LOGGER.warning("Failed to publish to %s: %s", topic, e)

    async def _listen_for_commands(self) -> None:
        """Subscribe to command topics and process incoming commands."""
        if not self.client:
            _LOGGER.error("MQTT client not initialized")
            return

        try:
            await self.client.subscribe(f"{self.base_topic}/devices/+/send")
            await self.client.subscribe(f"{self.base_topic}/devices/+/send_and_wait")
            await self.client.subscribe(f"{self.base_topic}/devices/+/sync_map")
            await self.client.subscribe(f"{self.base_topic}/devices/+/fetch_rtk")
            await self.client.subscribe(f"{self.base_topic}/devices/+/publish_all")

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

            cmd_data = {}
            if payload:
                try:
                    cmd_data = json.loads(payload)
                except json.JSONDecodeError:
                    _LOGGER.warning("Invalid JSON in command payload: %s", payload)
                    return

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
                await self._execute_sync_map(device_name, cmd_data)
            elif command == "fetch_rtk":
                await self._execute_fetch_rtk(device_name, cmd_data)
            elif command == "publish_all":
                await self._execute_publish_all(device_name, cmd_data)
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

    async def _extract_device_parameters(self, handle: Any) -> dict[str, Any]:
        """Extract all relevant parameters from a device handle."""
        snapshot = handle.snapshot
        device_state = snapshot.device_state if hasattr(snapshot, "device_state") else None

        parameters = {
            "device_name": handle.device_name,
            "device_id": handle.device_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        mqtt_transport = handle._transports.get(TransportType.CLOUD_ALIYUN) or handle._transports.get(
            TransportType.CLOUD_MAMMOTION
        )
        parameters["mqtt_connected"] = mqtt_transport is not None and mqtt_transport.is_connected

        if device_state is not None:
            try:
                state_dict = {}
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

            state_topic = f"{self.base_topic}/devices/{device_name}/state"
            await self.publish(state_topic, parameters, retain=True)

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
                    await self.publish(field_topic, value_str, retain=True)
                    previous[key] = value_str
                    _LOGGER.debug("Published changed parameter: %s = %s", key, value_str)

            _LOGGER.debug("Published device %s to external MQTT with change detection", device_name)
        except Exception as e:
            _LOGGER.error("Error publishing device %s to external MQTT: %s", device_name, e)

    async def _execute_publish_all(self, device_name: str, cmd_data: dict) -> None:
        """Force publish all parameters for a device."""
        if not self.dev_console:
            return

        try:
            if device_name in self._previous_state:
                del self._previous_state[device_name]

            await self._publish_device_to_external_mqtt(device_name)
            response = {
                "status": "success",
                "device": device_name,
                "command": "publish_all",
                "timestamp": datetime.now(UTC).isoformat(),
            }
            _LOGGER.info("✓ publish_all executed: %s", device_name)
        except Exception as e:
            response = {
                "status": "error",
                "device": device_name,
                "command": "publish_all",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            _LOGGER.error("✗ publish_all failed: %s", e)

        await self.publish(
            f"{self.base_topic}/devices/{device_name}/publish_all/response",
            response,
            retain=False,
        )

    async def _execute_send(self, device_name: str, cmd_data: dict) -> None:
        """Execute send command."""
        if not self.dev_console:
            return

        cmd = cmd_data.get("cmd")
        kwargs = cmd_data.get("kwargs", {})

        if not cmd:
            _LOGGER.warning("send: missing 'cmd' field")
            return

        try:
            await self.dev_console.mammotion.send_command_with_args(device_name, cmd, **kwargs)
            response = {
                "status": "success",
                "device": device_name,
                "command": "send",
                "cmd": cmd,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            _LOGGER.info("✓ send executed: %s %s", device_name, cmd)
        except Exception as e:
            response = {
                "status": "error",
                "device": device_name,
                "command": "send",
                "cmd": cmd,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            _LOGGER.error("✗ send failed: %s", e)

        await self.publish(
            f"{self.base_topic}/devices/{device_name}/send/response",
            response,
            retain=False,
        )

    async def _execute_send_and_wait(self, device_name: str, cmd_data: dict) -> None:
        """Execute send_and_wait command."""
        if not self.dev_console:
            return

        cmd = cmd_data.get("cmd")
        expected_field = cmd_data.get("expected_field")
        kwargs = cmd_data.get("kwargs", {})
        send_timeout = cmd_data.get("send_timeout", 1.0)
        timeout = cmd_data.get("timeout", 3.0)

        if not cmd or not expected_field:
            _LOGGER.warning("send_and_wait: missing 'cmd' or 'expected_field'")
            return

        try:
            result = await self.dev_console.mammotion.send_command_and_wait(
                device_name,
                cmd,
                expected_field,
                send_timeout=send_timeout,
                **kwargs,
            )
            response = {
                "status": "success",
                "device": device_name,
                "command": "send_and_wait",
                "cmd": cmd,
                "expected_field": expected_field,
                "result": str(result),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            _LOGGER.info("✓ send_and_wait executed: %s %s → %s", device_name, cmd, expected_field)
        except Exception as e:
            response = {
                "status": "error",
                "device": device_name,
                "command": "send_and_wait",
                "cmd": cmd,
                "expected_field": expected_field,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            _LOGGER.error("✗ send_and_wait failed: %s", e)

        await self.publish(
            f"{self.base_topic}/devices/{device_name}/send_and_wait/response",
            response,
            retain=False,
        )

    async def _execute_sync_map(self, device_name: str, cmd_data: dict) -> None:
        """Execute sync_map command."""
        if not self.dev_console:
            return

        timeout = cmd_data.get("timeout", 120.0)

        try:
            await self.dev_console.mammotion.start_map_sync(device_name)
            response = {
                "status": "success",
                "device": device_name,
                "command": "sync_map",
                "timeout": timeout,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            _LOGGER.info("✓ sync_map enqueued: %s", device_name)
        except Exception as e:
            response = {
                "status": "error",
                "device": device_name,
                "command": "sync_map",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            _LOGGER.error("✗ sync_map failed: %s", e)

        await self.publish(
            f"{self.base_topic}/devices/{device_name}/sync_map/response",
            response,
            retain=False,
        )

    async def _execute_fetch_rtk(self, device_name: str, cmd_data: dict) -> None:
        """Execute fetch_rtk command."""
        if not self.dev_console:
            return

        try:
            await self.dev_console.mammotion.fetch_rtk_lora_info(device_name)
            response = {
                "status": "success",
                "device": device_name,
                "command": "fetch_rtk",
                "timestamp": datetime.now(UTC).isoformat(),
            }
            _LOGGER.info("✓ fetch_rtk executed: %s", device_name)
        except Exception as e:
            response = {
                "status": "error",
                "device": device_name,
                "command": "fetch_rtk",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            _LOGGER.error("✗ fetch_rtk failed: %s", e)

        await self.publish(
            f"{self.base_topic}/devices/{device_name}/fetch_rtk/response",
            response,
            retain=False,
        )
# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


async def _main() -> None:
    _setup_logging()

    saved_email, saved_password = _load_credentials()
    email = os.environ.get("EMAIL") or input(f"Mammotion email [{saved_email}]: ").strip() or saved_email
    password = os.environ.get("PASSWORD") or input(f"Mammotion password [{'*' * len(saved_password) if saved_password else ''}]: ").strip() or saved_password
    _save_credentials(email, password)

    # Setup external MQTT (optional, can be configured via environment variables)
    external_mqtt = None
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

    mammotion = MammotionClient()
    main_loop = asyncio.get_running_loop()
    dev = DevConsole(mammotion, main_loop, external_mqtt)

    _LOGGER.info("Logging in as [bold]%s[/bold] …", email)
    await mammotion.login_and_initiate_cloud(email, password)
    _LOGGER.info("Login complete — waiting for MQTT …")

    await asyncio.sleep(3)

    dev.hook_all_devices()
    dev.hook_all_rtk_devices()
    dev.log_mqtt_credentials()
    dev.dump_all()

    # Publish initial state to external MQTT
    if external_mqtt:
        await dev.publish_all_devices_to_external_mqtt()

    # Fetch supplemental HTTP data for any RTK base stations
    from pymammotion.utility.device_type import DeviceType

    for handle in mammotion.device_registry.all_devices:
        if DeviceType.is_rtk(handle.device_name):
            _LOGGER.info("Fetching RTK LoRa info for [bold]%s[/bold] …", handle.device_name)
            await mammotion.fetch_rtk_lora_info(handle.device_name)

    device_names = [h.device_name for h in mammotion.device_registry.all_devices]
    _LOGGER.info(
        "Connected. Devices: [bold]%s[/bold]",
        ", ".join(device_names) or "(none yet)",
    )
    _LOGGER.info("Output directory: [bold]%s[/bold]", OUTPUT_DIR)

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
        "sync_mqtt": dev.sync_external_mqtt,  # NEW: sync to external MQTT
        "pub": dev.sync_external_mqtt,  # NEW: sync to external MQTT
        "console": dev,
        "loop": main_loop,
        "asyncio": asyncio,
    }

    mqtt_status = f"  [cyan]sync_mqtt() / pub()[/cyan]                              — sync all devices to external MQTT\n" if external_mqtt else ""

    _rich_console.print(
        "\n[bold green][PyMammotion dev console][/bold green]\n"
        f"  [cyan]devices[/cyan]  = {device_names}\n\n"
        "  [cyan]send(name, cmd, **kwargs)[/cyan]                           — queue a command (blocking)\n"
        "  [cyan]send_and_wait(name, cmd, expected_field, **kwargs)[/cyan]  — send and block for response\n"
        "  [cyan]sync_map(name)[/cyan]                                      — run a full MapFetchSaga (blocking)\n"
        "  [cyan]fetch_rtk(name)[/cyan]                                     — fetch LoRa version for an RTK base station\n"
        "  [cyan]dump(name)[/cyan]                                          — write state_{name}.json\n"
        "  [cyan]dump_all()[/cyan]                                          — write state JSON for all devices\n"
        "  [cyan]status()[/cyan]                                            — show connection status\n"
        "  [cyan]creds()[/cyan]                                             — print all MQTT credentials\n"
        f"{mqtt_status}"
        f"  [cyan]loop[/cyan]                                                — main asyncio event loop\n"
        f"\n  Output → [dim]{OUTPUT_DIR}[/dim]\n"
    )

    def _start_repl() -> None:
        IPython.embed(user_ns=namespace, using="asyncio")

    # Run IPython in a thread so the main loop stays alive for MQTT
    await asyncio.to_thread(_start_repl)

    _LOGGER.info("REPL exited — shutting down.")
    if external_mqtt:
        await external_mqtt.disconnect()
    await mammotion.stop()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
