"""Interactive development console for PyMammotion.

Usage:
    EMAIL=your@email.com PASSWORD=yourpass uv run python examples/dev_console.py
    EMAIL=your@email.com PASSWORD=yourpass uv run python examples/dev_console.py --listen
    uv run python examples/dev_console.py --ble-address AA:BB:CC:DD:EE:FF
    uv run python examples/dev_console.py --esphome-proxy esp32-proxy.local --ble-address AA:BB:CC:DD:EE:FF

Flags:
    -l / --listen           Connect and receive messages without sending any outbound polls.
                            Useful for passive observation or debugging device-initiated traffic.
    --ble-address MAC       BLE-only mode: connect over Bluetooth to the mower at MAC.
                            Skips cloud login / MQTT entirely; transport runs its own
                            BleakScanner.find_device_by_address lookup.
    --device-name NAME      Friendly device name to register under (BLE-only mode).
                            Defaults to "Luba-BLE-<MAC suffix>".
    --esphome-proxy HOST    Route the BLE connection through an ESPHome bluetooth proxy
                            at HOST (e.g. esp32-bluetooth-proxy.local).  Requires
                            --ble-address.  Needs the 'extras' deps:
                                uv sync --group extras
    --esphome-password PASS Password for the ESPHome proxy (default: empty).

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
    listen(on=True)                 Stop/resume MQTT polling on all devices
    console                         DevConsole instance
    loop                            The main asyncio event loop
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Protocol

import IPython
from rich.console import Console
from rich.logging import RichHandler

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymammotion.account.registry import BLE_ONLY_ACCOUNT
from pymammotion.client import MammotionClient
from pymammotion.messaging.broker import _LUBA_SUB_GROUP
from pymammotion.transport.base import Subscription, TransportType


class ExternalMQTT(Protocol):
    """Protocol for optional external MQTT publishers (see mammotion_to_mqtt.py)."""

    connected: bool
    dev_console: Any

    async def _publish_device_to_external_mqtt(self, device_name: str) -> None: ...


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
        external_mqtt: ExternalMQTT | None = None,
        *,
        output_dir: Path | None = None,
        always_dump: bool = True,
    ) -> None:
        self.mammotion = mammotion
        self.loop = main_loop
        self.external_mqtt = external_mqtt
        self._output_dir = output_dir or OUTPUT_DIR
        self.always_dump = always_dump
        if external_mqtt is not None:
            external_mqtt.dev_console = self
        # Strong references to all callbacks and subscriptions — must outlive the connection
        self._notification_cbs: dict[str, tuple[Callable[..., Awaitable[None]], Subscription]] = {}
        self._sent_cbs: dict[str, tuple[Callable[..., Awaitable[None]], Subscription]] = {}

    # ── File helpers ──────────────────────────────────────────────────────────

    def _state_path(self, name: str) -> Path:
        return self._output_dir / f"state_{name.replace('/', '_')}.json"

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
            path.write_text(handle.snapshot.raw.to_json(), encoding="utf-8")
            _LOGGER.debug("State written → %s", path)
        except Exception:
            _LOGGER.exception("dump: failed to write state for %s", name)
            _LOGGER.debug("dump: raw snapshot for %s: %r", name, handle.snapshot.raw)

    # ── Callback factory ──────────────────────────────────────────────────────

    @staticmethod
    def _describe_luba_msg(msg: Any) -> str:
        """Return ``"group.sub_name"`` (e.g. ``"nav.toapp_gethash_ack"``) for a LubaMsg.

        Falls back to the top-level group name when no leaf can be extracted, or
        ``"(empty)"`` if the message has no recognizable sub-group.
        """
        import betterproto2

        try:
            sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")
        except Exception:  # noqa: BLE001
            return "(message)"
        if not sub_name:
            return "(empty)"
        leaf_group = _LUBA_SUB_GROUP.get(sub_name)
        if leaf_group and sub_val is not None:
            try:
                leaf_name, _ = betterproto2.which_one_of(sub_val, leaf_group)
                if leaf_name:
                    return f"{sub_name}.{leaf_name}"
            except Exception:  # noqa: BLE001, S110
                pass
        return sub_name

    def _make_notification_cb(self, device_name: str) -> Callable[[Any], Awaitable[None]]:
        """Return an async callback for broker.subscribe_unsolicited.

        Called with a LubaMsg on every unsolicited incoming message.
        """

        async def _on_message(msg: Any) -> None:
            if self.always_dump:
                self.dump(device_name)
            if self.external_mqtt is not None and self.external_mqtt.connected:
                await self.external_mqtt._publish_device_to_external_mqtt(device_name)
            _LOGGER.info(
                "[bold cyan]← %s[/bold cyan]  [green]%s[/green]",
                device_name,
                self._describe_luba_msg(msg),
            )

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

    def _make_sent_cb(self, device_name: str) -> Callable[[bytes], Awaitable[None]]:
        """Return an async callback for handle.subscribe_sent.

        Called with the raw command bytes of every outbound payload.
        """
        from pymammotion.proto import LubaMsg

        async def _on_sent(payload: bytes) -> None:
            try:
                msg = LubaMsg().parse(payload)
                _LOGGER.info(
                    "[bold yellow]→ %s[/bold yellow]  [magenta]%s[/magenta]",
                    device_name,
                    self._describe_luba_msg(msg),
                )
            except Exception:  # noqa: BLE001
                _LOGGER.info(
                    "[bold yellow]→ %s[/bold yellow]  [magenta](%d bytes)[/magenta]",
                    device_name,
                    len(payload),
                )

        return _on_sent

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
        sent_cb = self._make_sent_cb(device_name)
        sent_sub = handle.subscribe_sent(sent_cb)
        self._sent_cbs[device_name] = (sent_cb, sent_sub)
        _LOGGER.info("Hooked broker + sent callbacks for [bold]%s[/bold]", device_name)

    def hook_all_devices(self) -> None:

        for handle in self.mammotion.device_registry.all_devices:
            self.hook_device(handle.device_name)

    # ── RTK device wiring ─────────────────────────────────────────────────────

    def _make_rtk_state_cb(self, device_name: str) -> Callable[[Any], Awaitable[None]]:
        """Return an async callback for state_changed_bus on an RTK base station."""
        from pymammotion.state.device_state import DeviceSnapshot

        async def _on_state_changed(snapshot: DeviceSnapshot) -> None:
            if self.always_dump:
                self.dump(device_name)
            if self.external_mqtt is not None and self.external_mqtt.connected:
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
        sent_cb = self._make_sent_cb(device_name)
        sent_sub = handle.subscribe_sent(sent_cb)
        self._sent_cbs[device_name] = (sent_cb, sent_sub)
        _LOGGER.info("Hooked state-change + sent callbacks for RTK [bold]%s[/bold]", device_name)

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

    def debug(self, on: bool = True) -> None:
        """Toggle DEBUG logging on the terminal (file always logs DEBUG).

        Example:
            debug()        # enable DEBUG on terminal
            debug(False)   # revert to INFO on terminal

        """
        level = logging.DEBUG if on else logging.INFO
        for handler in logging.getLogger().handlers:
            if isinstance(handler, RichHandler):
                handler.setLevel(level)
        state = "ON" if on else "OFF"
        _LOGGER.info("Terminal debug logging: [bold]%s[/bold]", state)

    def listen(self, on: bool = True) -> None:
        """Toggle listen-only mode — stop or resume the MQTT poll loop on all devices.

        In listen-only mode the handle still receives and processes every incoming
        message; it just never sends outbound polls.  Useful for passive observation.

        Example:
            listen()        # disable polling (listen only)
            listen(False)   # re-enable polling

        """
        for handle in self.mammotion.device_registry.all_devices:
            if on:
                asyncio.run_coroutine_threadsafe(handle.stop_polling(), self.loop).result(timeout=5)
            else:
                asyncio.run_coroutine_threadsafe(handle.start(), self.loop).result(timeout=5)
        state = "ON (polling stopped)" if on else "OFF (polling resumed)"
        _LOGGER.info("Listen-only mode: [bold]%s[/bold]", state)

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

    async def start_all_devices(self) -> None:
        """Call handle.start() on every registered device."""
        for handle in self.mammotion.device_registry.all_devices:
            _LOGGER.info("Starting [bold]%s[/bold]", handle.device_name)
            await handle.start()

    async def write_errors_to_file(self) -> None:
        """Fetch error codes from each cloud account and write them to disk."""
        for acct_session in self.mammotion.account_registry.all_sessions:
            if acct_session.cloud_client is None:
                continue
            error_codes = await acct_session.cloud_client.mammotion_http.get_all_error_codes()
            path = self._state_path("out__error_codes")
            with open(path, "w") as f:
                json.dump(error_codes, f, indent=2, default=str)
            _LOGGER.debug("Error codes written → %s", path)

    async def publish_all_devices_to_external_mqtt(self) -> None:
        """Publish the current state of all devices to the external MQTT broker."""
        if self.external_mqtt is None or not self.external_mqtt.connected:
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
# Main
# ──────────────────────────────────────────────────────────────────────────────


async def _bootstrap_ble_only(
    mammotion: MammotionClient,
    ble_address: str,
    device_name: str | None,
) -> None:
    """Register a single BLE-only device by MAC and open the GATT connection.

    Skips cloud login entirely.  Uses ``add_ble_only_device(ble_address=...)``
    so the transport runs its own one-shot ``BleakScanner.find_device_by_address``
    when ``connect()`` is called.  No HTTP, no MQTT.
    """
    from pymammotion.data.model.device import MowingDevice

    ble_address = ble_address.upper()
    if device_name is None:
        device_name = f"Luba-BLE-{ble_address.replace(':', '')[-6:]}"

    _LOGGER.info(
        "[bold yellow]BLE-only mode[/bold yellow] — registering [bold]%s[/bold] at %s",
        device_name,
        ble_address,
    )
    handle = await mammotion.add_ble_only_device(
        device_id=device_name,
        device_name=device_name,
        initial_device=MowingDevice(name=device_name),
        ble_address=ble_address,
    )
    await handle.start()

    _LOGGER.info("Scanning + connecting to BLE device %s …", ble_address)
    transport = handle.get_transport(TransportType.BLE)
    if transport is None:
        msg = f"BLE transport missing on handle for {device_name}"
        raise RuntimeError(msg)
    await transport.connect()
    _LOGGER.info("BLE connected.")


async def _bootstrap_ble_via_proxy(
    mammotion: MammotionClient,
    proxy_host: str,
    proxy_password: str,
    ble_address: str,
    device_name: str | None,
    *,
    discovery_timeout: float = 30.0,
) -> None:
    """Connect to the mower via an ESPHome BLE proxy and reuse our BLETransport.

    Bridges aioesphomeapi → bleak-esphome → bleak so the mower's GATT
    connection is routed through the proxy device, while everything downstream
    (BLETransport, BleMessage codec, ble_activity_loop, ble_polling_loop)
    runs unchanged — bleak-esphome installs an ``ESPHomeClient`` shim that
    bleak_retry_connector.establish_connection picks up automatically.

    Steps:
      1. Spin up a minimal habluetooth ``BluetoothManager`` (we never call
         ``_discover_service_info``; the no-op subclass just satisfies the ABC).
      2. Open an aioesphomeapi connection to the proxy and fetch its DeviceInfo.
      3. ``connect_scanner`` builds an ESPHomeScanner, sets up the GATT shim,
         and subscribes to the proxy's BLE advertisement stream.
      4. Register the scanner with the manager and wait up to
         *discovery_timeout* seconds for an advertisement matching
         *ble_address* — that gives us a real ``BLEDevice`` whose backend is
         the ESPHome proxy.
      5. Hand the BLEDevice to ``add_ble_only_device(ble_device=..., self_managed_scanning=False)``
         and call ``transport.connect()`` exactly like the local-bleak path.

    Lazy-imports the optional deps; raises with a clear install hint if missing.
    """
    try:
        from aioesphomeapi import APIClient
        from bleak_esphome import connect_scanner
        from bluetooth_adapters import get_adapters
        from habluetooth import BluetoothManager, set_manager
    except ImportError as exc:
        msg = (
            "ESPHome BLE-proxy mode requires the 'extras' dependency group:\n"
            "    uv sync --group extras\n"
            "(or pip install aioesphomeapi bleak-esphome habluetooth bluetooth-adapters)"
        )
        raise RuntimeError(msg) from exc

    from pymammotion.data.model.device import MowingDevice

    ble_address = ble_address.upper()
    if device_name is None:
        device_name = f"Luba-BLE-{ble_address.replace(':', '')[-6:]}"

    # Step 1: minimal habluetooth manager.  We're not consuming discovery callbacks
    # (no HA, no integrations subscribing) so _discover_service_info is a no-op.
    class _NoOpManager(BluetoothManager):  # type: ignore[misc, no-any-unimported]
        def _discover_service_info(self, service_info: object) -> None:  # noqa: ARG002
            return

    adapters = get_adapters()
    manager = _NoOpManager(adapters, slot_manager=None)
    set_manager(manager)
    await manager.async_setup()

    # Step 2: open the proxy connection.
    _LOGGER.info(
        "[bold yellow]ESPHome proxy mode[/bold yellow] — connecting to proxy at [bold]%s[/bold]",
        proxy_host,
    )
    api = APIClient(address=proxy_host, port=6053, password=proxy_password)
    await api.connect(login=True)
    device_info = await api.device_info()
    _LOGGER.info(
        "Proxy connected: name=%s mac=%s bt_proxy_features=%s",
        device_info.name,
        device_info.bluetooth_mac_address or device_info.mac_address,
        device_info.bluetooth_proxy_feature_flags_compat(api.api_version),
    )

    # Step 3: build the scanner.
    client_data = connect_scanner(api, device_info, available=True)
    scanner = client_data.scanner
    if scanner is None:
        msg = f"connect_scanner returned no scanner for proxy {proxy_host}"
        raise RuntimeError(msg)
    await scanner.async_setup()

    # Step 4: register and wait for an advertisement matching our target.
    unregister = manager.async_register_scanner(scanner)
    _LOGGER.info(
        "Scanner registered (connectable=%s) — waiting up to %.0fs for %s …",
        scanner.connectable,
        discovery_timeout,
        ble_address,
    )

    deadline = asyncio.get_running_loop().time() + discovery_timeout
    ble_device = None
    while asyncio.get_running_loop().time() < deadline:
        # The scanner accumulates devices as the proxy streams advertisements;
        # poll its discovered set rather than wiring a callback we'd just unwind.
        for dev, _adv in scanner.discovered_devices_and_advertisement_data.values():
            if dev.address.upper() == ble_address:
                ble_device = dev
                break
        if ble_device is not None:
            break
        await asyncio.sleep(0.5)

    if ble_device is None:
        unregister()
        await api.disconnect()
        msg = (
            f"BLE device {ble_address} did not appear in advertisements from proxy "
            f"{proxy_host} within {discovery_timeout:.0f}s"
        )
        raise RuntimeError(msg)

    _LOGGER.info("Discovered %s via proxy — registering handle and connecting GATT", ble_address)

    # Step 5: hand the BLEDevice to the existing BLE-only path.  self_managed_scanning=False
    # because the proxy + scanner own discovery, not bleak directly.
    handle = await mammotion.add_ble_only_device(
        device_id=device_name,
        device_name=device_name,
        initial_device=MowingDevice(name=device_name),
        ble_device=ble_device,
        self_managed_scanning=False,
    )
    await handle.start()

    transport = handle.get_transport(TransportType.BLE)
    if transport is None:
        msg = f"BLE transport missing on handle for {device_name}"
        raise RuntimeError(msg)
    await transport.connect()
    _LOGGER.info("BLE connected via ESPHome proxy.")


async def _main(args: argparse.Namespace) -> None:
    _setup_logging()

    mammotion = MammotionClient("0.5.27")
    main_loop = asyncio.get_running_loop()
    dev = DevConsole(mammotion, main_loop)

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
        await mammotion.login_and_initiate_cloud(email, password)
        _LOGGER.info("Login complete — waiting for MQTT …")

        await asyncio.sleep(3)

    dev.hook_all_devices()
    dev.hook_all_rtk_devices()

    if args.listen:
        for handle in mammotion.device_registry.all_devices:
            await handle.stop_polling()
        _LOGGER.info("[bold yellow]Listen-only mode[/bold yellow] — MQTT polling disabled on all devices")

    if not args.ble_address and not args.esphome_proxy:
        # log_mqtt_credentials walks AccountSession.cloud_client / mammotion_http,
        # both of which are None in any BLE-only mode.
        dev.log_mqtt_credentials()
    dev.dump_all()

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
        "debug": dev.debug,
        "listen": dev.listen,
        "console": dev,
        "loop": main_loop,
        "asyncio": asyncio,
    }

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
        f"  [cyan]loop[/cyan]                                                — main asyncio event loop\n"
        f"\n  Output → [dim]{OUTPUT_DIR}[/dim]\n"
    )

    def _start_repl() -> None:
        IPython.embed(user_ns=namespace, using="asyncio")

    # Run IPython in a thread so the main loop stays alive for MQTT
    await asyncio.to_thread(_start_repl)

    _LOGGER.info("REPL exited — shutting down.")
    await mammotion.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PyMammotion interactive dev console")
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
    except KeyboardInterrupt:
        pass
