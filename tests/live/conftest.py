"""Session-scoped fixtures for live-device integration tests.

These tests require a real Mammotion account and (for the BLE-parametrised
variants) a local Bluetooth adapter that can see the mower.  They are
gated behind the ``live`` pytest marker and skip silently when the env
vars below are not set, so a regular ``uv run pytest tests/`` run picks
them up only when explicitly requested.

Env vars:
    MAMMOTION_EMAIL           required for any live test
    MAMMOTION_PASSWORD        required for any live test
    MAMMOTION_DEVICE_NAME     optional; otherwise the first mower from the account is used
    MAMMOTION_BLE_ADDRESS     optional; required only for ``prefer_ble=True`` parametrisations
    MAMMOTION_BLE_SCAN_TIMEOUT optional float (default 10.0) — BleakScanner timeout
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator

import pytest

from pymammotion.client import MammotionClient
from pymammotion.transport.base import TransportType

_logger = logging.getLogger(__name__)


def _pick_first_mower(client: MammotionClient) -> str | None:
    """Return the device_name of the first registered mower (Luba/Yuka/Spino), or None."""
    devices = list(client.device_registry.all_devices)
    mowers = [d for d in devices if d.device_name.startswith(("Luba", "Yuka", "Spino"))]
    if mowers:
        return mowers[0].device_name
    if devices:
        return devices[0].device_name
    return None


async def _try_attach_ble(client: MammotionClient, device_name: str, ble_address: str, timeout: float) -> bool:
    """Best-effort BLE attach.  Returns True if the BLE transport is registered."""
    try:
        from bleak import BleakScanner  # noqa: PLC0415 - optional dep at module import time
    except ImportError:
        _logger.warning("bleak not installed; skipping BLE attach")
        return False

    ble_dev = await BleakScanner.find_device_by_address(ble_address, timeout=timeout)
    if ble_dev is None:
        _logger.warning("BLE device %s not found within %.1fs", ble_address, timeout)
        return False
    await client.add_ble_to_device(device_name, ble_dev)
    # The handle has registered the BLE transport; connection may take a moment.
    handle = client.device_registry.get_by_name(device_name)
    if handle is None:
        return False
    for _ in range(20):  # up to ~10s for BLE to come up
        if handle.is_transport_connected(TransportType.BLE):
            return True
        await asyncio.sleep(0.5)
    return handle.is_transport_connected(TransportType.BLE)


@pytest.fixture(scope="session")
async def live_client() -> AsyncIterator[tuple[MammotionClient, str]]:
    """Log in once, attach BLE if configured, hold the connection for the session."""
    email = os.environ.get("MAMMOTION_EMAIL", "").strip()
    password = os.environ.get("MAMMOTION_PASSWORD", "").strip()
    if not email or not password:
        pytest.skip("MAMMOTION_EMAIL / MAMMOTION_PASSWORD not set")

    client = MammotionClient()
    try:
        await client.login_and_initiate_cloud(email, password)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"cloud login failed: {exc}")

    device_name = os.environ.get("MAMMOTION_DEVICE_NAME", "").strip() or _pick_first_mower(client)
    if not device_name:
        await client.stop()
        pytest.skip("no devices on the Mammotion account")

    ble_address = os.environ.get("MAMMOTION_BLE_ADDRESS", "").strip()
    if ble_address:
        scan_timeout = float(os.environ.get("MAMMOTION_BLE_SCAN_TIMEOUT", "10.0"))
        attached = await _try_attach_ble(client, device_name, ble_address, scan_timeout)
        if not attached:
            _logger.warning("BLE attach unsuccessful; ble-parametrised tests will skip")

    try:
        yield client, device_name
    finally:
        with contextlib.suppress(Exception):
            await client.stop()


@pytest.fixture(params=[False, True], ids=["mqtt", "ble"])
def prefer_ble(
    request: pytest.FixtureRequest,
    live_client: tuple[MammotionClient, str],
) -> bool:
    """Parametrise each live test over MQTT (False) and BLE (True) transports.

    Skips the BLE variant when no BLE transport is registered/connected on
    the device — keeps the test matrix clean on hosts without a BLE adapter.
    """
    client, device_name = live_client
    handle = client.device_registry.get_by_name(device_name)
    if handle is None:
        pytest.skip(f"device '{device_name}' not registered")
    if request.param and not handle.is_transport_connected(TransportType.BLE):
        pytest.skip("BLE not available for this test host")
    client.set_prefer_ble(handle.device_id, prefer_ble=request.param)
    return request.param
