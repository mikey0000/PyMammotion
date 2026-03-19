"""Interactive development console for PyMammotion.

Usage:
    EMAIL=your@email.com PASSWORD=yourpass uv run python tests/dev_console.py

Output files (written to tests/dev_output/):
    state_{device_name}.json        Full MowingDevice state, updated on every
                                    incoming protobuf message.
    raw_msgs_{device_name}.jsonl    Newline-delimited JSON; one record per
                                    incoming LubaMsg sub-message.
    mammotion_dev.log               Full DEBUG log.

Available in the IPython REPL:
    mammotion                       Mammotion singleton (cloud connection active)
    devices                         dict[name, MammotionMowerDeviceManager]
    send(name, cmd, **kwargs)       Queue a command and block until complete
    dump(name)                      Force-write state_{name}.json right now
    console                         DevConsole instance
    loop                            The main asyncio event loop
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import Callable, Awaitable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import IPython
from rich.console import Console
from rich.logging import RichHandler

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymammotion.mammotion.devices.mammotion import Mammotion
from pymammotion.mqtt.aliyun_mqtt import AliyunMQTT
from pymammotion.mqtt.mammotion_mqtt import MammotionMQTT

# ──────────────────────────────────────────────────────────────────────────────
# Output directory
# ──────────────────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path(__file__).parent / "dev_output"
OUTPUT_DIR.mkdir(exist_ok=True)

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
    logging.getLogger("pymammotion.mqtt").setLevel(logging.DEBUG)
    logging.getLogger("pymammotion.mammotion").setLevel(logging.DEBUG)
    logging.getLogger("pymammotion.aliyun").setLevel(logging.DEBUG)
    for noisy in ("aiomqtt", "aiohttp", "asyncio", "bleak"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ──────────────────────────────────────────────────────────────────────────────
# DevConsole — holds all strong references so weakref callbacks aren't collected
# ──────────────────────────────────────────────────────────────────────────────


class DevConsole:
    """Wires per-device callbacks and provides REPL helpers."""

    def __init__(self, mammotion: Mammotion, main_loop: asyncio.AbstractEventLoop) -> None:
        self.mammotion = mammotion
        self.loop = main_loop
        # Strong references to all callbacks — must outlive the connection
        self._notification_cbs: dict[str, Callable[..., Awaitable[None]]] = {}
        self._ready_cbs: list[Callable[..., Awaitable[None]]] = []

    # ── File helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _state_path(name: str) -> Path:
        return OUTPUT_DIR / f"state_{name.replace('/', '_')}.json"

    @staticmethod
    def _raw_path(name: str) -> Path:
        return OUTPUT_DIR / f"raw_msgs_{name.replace('/', '_')}.jsonl"

    def dump(self, name: str) -> None:
        """Write the current MowingDevice JSON state for *name* to disk."""
        device_mgr = self.mammotion.device_manager.devices.get(name)
        if device_mgr is None:
            _LOGGER.warning("dump: device %r not found. Available: %s", name, list(self.mammotion.device_manager.devices))
            return
        try:
            path = self._state_path(name)
            path.write_text(device_mgr.state.to_json(), encoding="utf-8")
            _LOGGER.debug("State written → %s", path)
        except Exception:
            _LOGGER.exception("dump: failed to write state for %s", name)

    def _append_raw(self, name: str, msg_type: str, msg_dict: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": msg_type,
            "data": msg_dict,
        }
        with self._raw_path(name).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    # ── Callback factory ──────────────────────────────────────────────────────

    def _make_notification_cb(self, device_name: str) -> Callable[..., Awaitable[None]]:
        """Return an async callback for MowerStateManager.cloud_on_notification_callback.

        Called with (sub_msg_name, sub_msg_object) after every LubaMsg.
        """

        async def _on_notification(res: tuple[str, Any]) -> None:
            self.dump(device_name)

            if isinstance(res, (tuple, list)) and len(res) == 2:
                msg_type, msg_obj = res
                try:
                    raw: dict[str, Any] = msg_obj.to_dict() if msg_obj is not None else {}
                except Exception:
                    raw = {}
                self._append_raw(device_name, str(msg_type), raw)
                _LOGGER.info(
                    "[bold cyan]← %s[/bold cyan]  [green]%s[/green]",
                    device_name,
                    msg_type,
                )

        return _on_notification

    # ── Credential logging ────────────────────────────────────────────────────

    def log_mqtt_credentials(self) -> None:
        """Log all MQTT-related credentials for every active cloud connection.

        Written at DEBUG to the log file and printed to the terminal so you
        can verify token values / expiry without digging through debug logs.
        """
        import time

        _rich_console.rule("[bold yellow]MQTT Credentials[/bold yellow]")

        for key, mqtt_cloud in self.mammotion.mqtt_list.items():
            cloud_client = mqtt_cloud.cloud_client
            http = cloud_client.mammotion_http
            client = mqtt_cloud._mqtt_client

            _rich_console.print(f"\n[bold white]── {key} ──[/bold white]")

            # ── HTTP / JWT layer ─────────────────────────────────────────────
            _rich_console.print("[bold]HTTP access token[/bold]")
            expires_in = http.expires_in
            remaining = max(0, int(expires_in - time.time()))
            _rich_console.print(f"  access_token  : {http.login_info.access_token}")
            _rich_console.print(f"  expires_at    : {datetime.fromtimestamp(expires_in, tz=timezone.utc).isoformat()}"
                                f"  ([cyan]{remaining // 3600}h {(remaining % 3600) // 60}m[/cyan] remaining)")
            _rich_console.print(f"  refresh_token : {http.login_info.refresh_token}")

            # ── MammotionMQTT JWT credentials ────────────────────────────────
            if isinstance(client, MammotionMQTT) and http.mqtt_credentials is not None:
                creds = http.mqtt_credentials
                _rich_console.print("\n[bold]MammotionMQTT (JWT)[/bold]")
                _rich_console.print(f"  host          : {creds.host}")
                _rich_console.print(f"  username      : {creds.username}")
                _rich_console.print(f"  client_id     : {creds.client_id}")
                _rich_console.print(f"  jwt           : {creds.jwt}")

            # ── AliyunMQTT credentials ───────────────────────────────────────
            if isinstance(client, AliyunMQTT):
                _rich_console.print("\n[bold]AliyunMQTT (HMAC + iotToken)[/bold]")
                _rich_console.print(f"  host          : {client._mqtt_host}")
                _rich_console.print(f"  username      : {client._mqtt_username}")
                _rich_console.print(f"  product_key   : {client._product_key}")
                _rich_console.print(f"  device_name   : {client._device_name}")
                _rich_console.print(f"  device_secret : {client._device_secret}")

                session = cloud_client.session_by_authcode_response
                if session is not None and session.data is not None:
                    issued = cloud_client._iot_token_issued_at
                    ion_exp = max(0, int(issued + session.data.iotTokenExpire - time.time()))
                    ref_exp = max(0, int(issued + session.data.refreshTokenExpire - time.time()))
                    _rich_console.print(f"\n[bold]  Aliyun session[/bold]")
                    _rich_console.print(f"    iotToken          : {session.data.iotToken}")
                    _rich_console.print(f"    iotTokenExpire    : {session.data.iotTokenExpire}s total"
                                        f"  ([cyan]{ion_exp // 3600}h {(ion_exp % 3600) // 60}m[/cyan] remaining)")
                    _rich_console.print(f"    refreshToken      : {session.data.refreshToken}")
                    _rich_console.print(f"    refreshTokenExpire: {session.data.refreshTokenExpire}s total"
                                        f"  ([cyan]{ref_exp // 3600}h {(ref_exp % 3600) // 60}m[/cyan] remaining)")
                    _rich_console.print(f"    issued_at         : {datetime.fromtimestamp(issued, tz=timezone.utc).isoformat()}")

            # Mirror everything to the DEBUG log file too
            _LOGGER.debug("=== credentials for %s ===", key)
            _LOGGER.debug("HTTP access_token=%s", http.login_info.access_token)
            _LOGGER.debug("HTTP refresh_token=%s", http.login_info.refresh_token)
            _LOGGER.debug("HTTP expires_at=%s remaining=%ds", http.expires_in, remaining)
            if isinstance(client, MammotionMQTT) and http.mqtt_credentials is not None:
                creds = http.mqtt_credentials
                _LOGGER.debug("MammotionMQTT host=%s username=%s client_id=%s jwt=%s",
                               creds.host, creds.username, creds.client_id, creds.jwt)
            if isinstance(client, AliyunMQTT):
                _LOGGER.debug("AliyunMQTT host=%s username=%s product_key=%s device_name=%s device_secret=%s",
                               client._mqtt_host, client._mqtt_username, client._product_key,
                               client._device_name, client._device_secret)
                session = cloud_client.session_by_authcode_response
                if session is not None and session.data is not None:
                    _LOGGER.debug("Aliyun iotToken=%s iotTokenExpire=%ds refreshToken=%s refreshTokenExpire=%ds",
                                   session.data.iotToken, session.data.iotTokenExpire,
                                   session.data.refreshToken, session.data.refreshTokenExpire)

        _rich_console.rule()

    # ── Device wiring ─────────────────────────────────────────────────────────

    def hook_device(self, device_name: str) -> None:
        """Attach the notification callback to a device (idempotent)."""
        if device_name in self._notification_cbs:
            return  # already hooked
        device_mgr = self.mammotion.device_manager.devices.get(device_name)
        if device_mgr is None or device_mgr.cloud is None:
            return
        cb = self._make_notification_cb(device_name)
        self._notification_cbs[device_name] = cb  # keep strong reference
        device_mgr.cloud.set_notification_callback(cb)
        _LOGGER.info("Hooked notification callback for [bold]%s[/bold]", device_name)

    def hook_all_devices(self) -> None:
        for name in list(self.mammotion.device_manager.devices):
            self.hook_device(name)

    def register_ready_hooks(self) -> None:
        """Subscribe on_ready_event on all MammotionCloud instances so we
        re-hook devices whenever the MQTT session (re-)establishes."""
        for mqtt_cloud in self.mammotion.mqtt_list.values():

            async def _on_ready(_self: DevConsole = self) -> None:
                _self.hook_all_devices()

            # Keep strong ref so weakref in DataEvent doesn't collect it
            self._ready_cbs.append(_on_ready)
            mqtt_cloud.on_ready_event.add_subscribers(_on_ready)

    # ── REPL helpers ──────────────────────────────────────────────────────────

    def send(self, name: str, cmd: str, **kwargs: Any) -> None:
        """Queue a command on a device and block until complete (30 s timeout).

        Example:
            send("Luba-VS563L6H", "send_todev_ble_sync", sync_type=3)
        """
        device_mgr = self.mammotion.device_manager.devices.get(name)
        if device_mgr is None:
            print(f"Device {name!r} not found.\nAvailable: {list(self.mammotion.device_manager.devices)}")
            return
        if device_mgr.cloud is None:
            print(f"Device {name!r} has no active cloud connection.")
            return
        try:
            fut = asyncio.run_coroutine_threadsafe(device_mgr.cloud.command(cmd, **kwargs), self.loop)
            fut.result(timeout=30)
            print(f"✓  {cmd!r} → {name!r}")
        except TimeoutError:
            print(f"✗  Timed out waiting for {name!r}")
        except Exception as exc:
            print(f"✗  Error: {exc}")

    def dump_all(self) -> None:
        """Force-write state JSON for every connected device."""
        for name in self.mammotion.device_manager.devices:
            self.dump(name)
            print(f"Written → {self._state_path(name)}")

    def status(self) -> None:
        """Print a summary of connected devices and MQTT health."""
        dm = self.mammotion.device_manager
        print(f"\n{'Device':<30}  {'MQTT':>6}  State file")
        print("-" * 70)
        for name, mgr in dm.devices.items():
            mqtt_ok = "✓" if mgr.cloud and mgr.cloud.mqtt.is_connected() else "✗"
            path = self._state_path(name)
            size = f"{path.stat().st_size:,} B" if path.exists() else "—"
            print(f"  {name:<28}  {mqtt_ok:>6}  {size}")
        print()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


async def _main() -> None:
    _setup_logging()

    email = os.environ.get("EMAIL") or input("Mammotion email: ").strip()
    password = os.environ.get("PASSWORD") or input("Mammotion password: ").strip()

    mammotion = Mammotion()
    main_loop = asyncio.get_running_loop()
    dev = DevConsole(mammotion, main_loop)

    _LOGGER.info("Logging in as [bold]%s[/bold] …", email)
    await mammotion.login_and_initiate_cloud(email, password)
    _LOGGER.info("Login complete — waiting for MQTT …")

    await asyncio.sleep(3)

    dev.register_ready_hooks()
    dev.hook_all_devices()
    dev.log_mqtt_credentials()
    dev.dump_all()

    _LOGGER.info(
        "Connected. Devices: [bold]%s[/bold]",
        ", ".join(mammotion.device_manager.devices) or "(none yet)",
    )
    _LOGGER.info("Output directory: [bold]%s[/bold]", OUTPUT_DIR)

    # ── REPL namespace ────────────────────────────────────────────────────────
    namespace = {
        "mammotion": mammotion,
        "devices": mammotion.device_manager.devices,
        "send": dev.send,
        "dump": dev.dump,
        "dump_all": dev.dump_all,
        "status": dev.status,
        "creds": dev.log_mqtt_credentials,
        "console": dev,
        "loop": main_loop,
        "asyncio": asyncio,
    }

    _rich_console.print(
        "\n[bold green][PyMammotion dev console][/bold green]\n"
        f"  [cyan]devices[/cyan]  = {list(mammotion.device_manager.devices)}\n\n"
        "  [cyan]send(name, cmd, **kwargs)[/cyan]  — queue a command (blocking)\n"
        "  [cyan]dump(name)[/cyan]                 — write state_{name}.json\n"
        "  [cyan]dump_all()[/cyan]                 — write state JSON for all devices\n"
        "  [cyan]status()[/cyan]                   — show connection status\n"
        "  [cyan]creds()[/cyan]                    — print all MQTT credentials\n"
        f"  [cyan]loop[/cyan]                       — main asyncio event loop\n"
        f"\n  Output → [dim]{OUTPUT_DIR}[/dim]\n"
    )

    def _start_repl() -> None:
        IPython.embed(user_ns=namespace, using="asyncio")

    # Run IPython in a thread so the main loop stays alive for MQTT
    await asyncio.to_thread(_start_repl)

    _LOGGER.info("REPL exited — shutting down.")
    await mammotion.stop()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
