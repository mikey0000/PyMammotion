"""Move a mower onto another Wi-Fi network over BLE with BluFi provisioning.

    WIFI_SSID=... WIFI_PASSWORD=... uv run python examples/blufi_set_wifi.py BLE_ADDRESS [--scan-only] [--force]

Credentials are read from the environment so they stay out of argv and shell history. They cross BLE
unencrypted, as the Mammotion app sends them. The mower's scan must list the SSID before anything is changed,
unless --force is given (hidden networks). Firmware may not report the result; check the router for the new lease.
"""

import argparse
import asyncio
import logging
import os
from pathlib import Path
import sys

from bleak import BleakClient, BleakScanner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymammotion.bluetooth.blufi_wifi import BlufiWifiProvisioner

SCAN_TIMEOUT_S = 20.0
CONNECT_TIMEOUT_S = 30.0

_LOGGER = logging.getLogger("blufi_set_wifi")


async def main(address: str, ssid: str | None, password: str | None, scan_only: bool, force: bool) -> int:
    """Connect over BLE, report the scan, then provision the station unless scanning only."""
    device = await BleakScanner.find_device_by_address(address, timeout=SCAN_TIMEOUT_S)
    if device is None:
        _LOGGER.error("No BLE device %s in range", address)
        return 2
    async with BleakClient(device, timeout=CONNECT_TIMEOUT_S) as client, BlufiWifiProvisioner(client) as provisioner:
        _LOGGER.info("BluFi version %s.%s", *await provisioner.get_version())
        networks = await provisioner.scan()
        for network in sorted(networks, key=lambda n: n.rssi, reverse=True):
            _LOGGER.info("  %4d dBm  %r", network.rssi, network.ssid)
        if scan_only:
            return 0
        if ssid is None or password is None:
            _LOGGER.error("Set WIFI_SSID and WIFI_PASSWORD")
            return 2
        if not force and all(network.ssid != ssid for network in networks):
            _LOGGER.error("The mower cannot see %r; nothing was changed", ssid)
            return 1
        status = await provisioner.connect_station(ssid, password)
        if status is None:
            _LOGGER.info("Credentials sent; the mower pushed no status. Check the router for its new lease.")
            return 0
        _LOGGER.info("Mower reported: %s", status)
        return 0 if status.connected_to(ssid) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("address", help="mower BLE address")
    parser.add_argument("--scan-only", action="store_true", help="report the scan, change nothing")
    parser.add_argument("--force", action="store_true", help="connect even if the scan does not list the SSID")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    sys.exit(
        asyncio.run(
            main(args.address, os.environ.get("WIFI_SSID"), os.environ.get("WIFI_PASSWORD"), args.scan_only, args.force)
        )
    )
