"""Generate live map GeoJSON for the first available device.

Logs in, runs a full map sync, and writes the resulting
``generated_geojson`` to ``examples/dev_output/map_{device}.geojson``.

Usage:
    EMAIL=... PASSWORD=... ./.venv/Scripts/python.exe scripts/generate_live_map_geojson.py

Env var names match ``examples/dev_console.py`` — run that first if you want
an interactive session with the same login.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
)
for noisy in ("pymammotion.aliyun", "paho", "aiomqtt", "pymammotion.mqtt"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

log = logging.getLogger("geojson_test")

OUTPUT_DIR = Path(__file__).parent.parent / "examples" / "dev_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def _pick_mower(devices: list[DeviceHandle]) -> DeviceHandle | None:
    mowers = [d for d in devices if d.device_name.startswith(("Luba", "Yuka", "Spino"))]
    return mowers[0] if mowers else (devices[0] if devices else None)


async def _login_with_retry(client: MammotionClient, email: str, password: str, attempts: int = 3) -> None:
    delay = 2.0
    for attempt in range(1, attempts + 1):
        try:
            await client.login_and_initiate_cloud(email, password)
            return
        except Exception as exc:
            log.warning("Login attempt %d/%d failed: %s", attempt, attempts, exc)
            if attempt == attempts:
                raise
            await asyncio.sleep(delay)
            delay *= 2


async def _wait_for_map_sync(handle: DeviceHandle, timeout: float = 180.0) -> bool:
    """Poll handle.has_queued_commands until the map saga completes or we time out."""
    import time as _time
    deadline = _time.monotonic() + timeout
    await asyncio.sleep(1.0)  # give enqueue_saga time to flip is_saga_active
    while handle.has_queued_commands():
        if _time.monotonic() > deadline:
            return False
        await asyncio.sleep(1.0)
    return True


async def main() -> int:
    email = os.environ.get("EMAIL") or os.environ.get("MAMMOTION_EMAIL", "")
    password = os.environ.get("PASSWORD") or os.environ.get("MAMMOTION_PASSWORD", "")
    if not email or not password:
        log.error("Set EMAIL and PASSWORD env vars")
        return 2

    client = MammotionClient()
    log.info("Logging in as %s …", email)
    await _login_with_retry(client, email, password)

    # Let MQTT settle — dev_console.py does this too.
    await asyncio.sleep(3)

    devices = list(client.device_registry.all_devices)
    log.info("Found %d device(s):", len(devices))
    for d in devices:
        log.info("  • %s  iot_id=%s", d.device_name, d.iot_id)

    handle = _pick_mower(devices)
    if handle is None:
        log.error("No devices on this account")
        await client.stop()
        return 1
    log.info("Using device: %s", handle.device_name)

    # start_map_sync enqueues MapFetchSaga and wires _on_map_complete which
    # calls device.map.generate_geojson itself — same path dev_console.py's
    # sync_map() uses.
    log.info("Enqueuing MapFetchSaga …")
    await client.start_map_sync(handle.device_name)
    completed = await _wait_for_map_sync(handle, timeout=240.0)
    if not completed:
        log.error("Map sync did not finish within the timeout")
        await client.stop()
        return 1
    log.info("Map sync complete")

    device = client.get_device_by_name(handle.device_name)
    if device is None:
        log.error("Device vanished from registry after sync")
        await client.stop()
        return 1

    if not device.map.generated_geojson and device.location.RTK.latitude != 0:
        device.map.generate_geojson(device.location.RTK, device.location.dock)

    geo = device.map.generated_geojson or {"type": "FeatureCollection", "features": []}
    out_path = OUTPUT_DIR / f"map_{handle.device_name}.geojson"
    out_path.write_text(json.dumps(geo, indent=2), encoding="utf-8")
    log.info("Wrote %s", out_path)

    await client.stop()
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
