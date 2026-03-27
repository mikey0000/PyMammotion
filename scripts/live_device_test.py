"""Live device test — login, list devices, fetch firmware version, sync map.

Uses MammotionClient.login_and_initiate_cloud() to handle authentication and
MQTT transport setup for both pre-2025 (Aliyun) and post-2025 (Mammotion) devices.

Usage:
    MAMMOTION_EMAIL=... MAMMOTION_PASSWORD='...' uv run python scripts/live_device_test.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import betterproto2
from aiohttp import ClientSession

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.exceptions import DeviceOfflineException
from pymammotion.client import MammotionClient
from pymammotion.const import MAMMOTION_DOMAIN
from pymammotion.data.model import GenerateRouteInformation, hash_list
from pymammotion.data.model.device_config import OperationSettings, create_path_order
from pymammotion.data.model.hash_list import HashList
from pymammotion.device.handle import DeviceHandle
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.map_saga import MapFetchSaga
from pymammotion.messaging.mow_path_saga import MowPathSaga
from pymammotion.proto import LubaMsg
from pymammotion.utility.device_type import DeviceType

# ---------------------------------------------------------------------------
# Logging — console + file
# ---------------------------------------------------------------------------

_LOG_FILE = Path(__file__).parent / "mqtt_log.txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_FILE, mode="w", encoding="utf-8"),
    ],
)
for _noisy in ("pymammotion.aliyun", "paho", "aiomqtt"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

_log = logging.getLogger("live_test")
_PROTO_DEBUG = os.environ.get("PROTO_DEBUG", "").lower() in ("1", "true", "yes")

_log.info("Logging MQTT traffic to %s", _LOG_FILE)


# ---------------------------------------------------------------------------
# Outgoing command logging
# ---------------------------------------------------------------------------


def _make_send_command(
    raw_send: Callable[[bytes], Awaitable[None]],
    iot_id: str,
) -> Callable[[bytes], Awaitable[None]]:
    """Wrap a send callable to log the decoded LubaMsg before each send."""

    async def _send(cmd: bytes) -> None:
        try:
            decoded = LubaMsg().parse(cmd)
            _log.info("→ SEND  iot_id=%s  %s", iot_id, decoded)
        except Exception:  # noqa: BLE001
            _log.info("→ SEND  iot_id=%s  (%d bytes, could not decode)", iot_id, len(cmd))
        await raw_send(cmd)

    return _send


# ---------------------------------------------------------------------------
# Global incoming message logger
# ---------------------------------------------------------------------------


def _make_message_logger(iot_id: str) -> Callable[[object], Awaitable[None]]:
    """Return an async handler that logs every unsolicited incoming message."""

    async def _log_message(msg: object) -> None:
        try:
            _log.info("← RECV  iot_id=%s  %s", iot_id, msg)
            # Dig into nav sub-messages for extra detail
            sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")  # type: ignore[arg-type]
            if sub_name == "nav":
                leaf_name, leaf_val = betterproto2.which_one_of(sub_val, "SubNavMsg")
                _log.info(
                    "← NAV   iot_id=%s  leaf=%s  val=%s",
                    iot_id,
                    leaf_name,
                    leaf_val,
                )
        except Exception:  # noqa: BLE001
            pass

    return _log_message


# ---------------------------------------------------------------------------
# Shared map saga runner
# ---------------------------------------------------------------------------


async def _run_map_saga(
    broker: DeviceMessageBroker,
    command_builder: MammotionCommand,
    device_name: str,
    iot_id: str,
    send_command: Callable[[bytes], Awaitable[None]],
) -> HashList | None:
    _log.info("Sending ble sync before map fetch …")
    await send_command(command_builder.send_todev_ble_sync(3))

    is_luba1 = DeviceType.is_luba1(device_name)
    saga = MapFetchSaga(
        device_id=iot_id,
        device_name=device_name,
        is_luba1=is_luba1,
        command_builder=command_builder,
        send_command=send_command,
    )
    try:
        await saga.execute(broker)
    except DeviceOfflineException:
        raise
    except Exception:  # noqa: BLE001
        _log.exception("MapFetchSaga failed")

    if saga.result is not None:
        hl = saga.result
        _log.info("Map sync complete:")
        _log.info("  area_name entries : %d", len(hl.area_name))
        _log.info("  root hash IDs     : %d", len(hl.hashlist))
        _log.info("  areas fetched     : %d", len(hl.area))
        _log.info("  obstacles fetched : %d", len(hl.obstacle))
        _log.info("  paths fetched     : %d", len(hl.path))
        _log.info("  svg fetched       : %d", len(hl.svg))
        _log.info("  missing hashes    : %d", len(hl.missing_hashlist(0)))
        if hl.area_name:
            _log.info("  Area names: %s", [a.name for a in hl.area_name])
        _log.info("  Area hashes: %s", list(hl.area.keys()))
    else:
        _log.warning("MapFetchSaga did not produce a result")

    return saga.result


async def _run_mow_path_saga(
    broker: DeviceMessageBroker,
    command_builder: MammotionCommand,
    device_name: str,
    send_command: Callable[[bytes], Awaitable[None]],
    map_result: HashList,
) -> None:
    all_zone_hashs = list(map_result.area.keys())
    if not all_zone_hashs:
        _log.warning("MowPathSaga: no area hashes available — skipping")
        # return

    # Use up to 2 zones
    # zone_hashs = all_zone_hashs[:2]
    zone_hashs = []
    _log.info("MowPathSaga: using %d of %d zone(s): %s", len(zone_hashs), len(all_zone_hashs), zone_hashs)

    # Build operation settings for the Yuka — channel_width within 8-14 range
    op = OperationSettings(
        is_mow=True,
        is_dump=True,
        is_edge=False,
        channel_width=12,          # Yuka path_spacing: min=8 max=14
        speed=0.3,
        job_mode=4,
        border_mode=0,
        obstacle_laps=1,
        mowing_laps=1,
        ultra_wave=2,
        channel_mode=0,
        toward=0,
        toward_mode=0,
        toward_included_angle=90,
        blade_height=0,
        start_progress=0,
        collect_grass_frequency=10,
    )
    path_order = create_path_order(op, device_name)
    _log.info(
        "path_order bytes: %s  (hex: %s)",
        list(path_order.encode("latin-1")),
        path_order.encode("latin-1").hex(),
    )

    route_info = GenerateRouteInformation(
        one_hashs=[],
        job_mode=op.job_mode,
        speed=op.speed,
        ultra_wave=op.ultra_wave,
        channel_mode=op.channel_mode,
        channel_width=op.channel_width,
        blade_height=op.blade_height,
        toward=op.toward,
        toward_included_angle=op.toward_included_angle,
        toward_mode=op.toward_mode,
        edge_mode=op.mowing_laps,  # edge_mode = border laps count
        path_order=path_order,
    )
    _log.info("GenerateRouteInformation: %s", route_info)

    # Subscribe to ALL incoming nav messages during the saga for analysis
    nav_events: list[tuple[float, str, object]] = []

    async def _capture_nav(msg: object) -> None:
        try:
            sub_name, sub_val = betterproto2.which_one_of(msg, "LubaSubMsg")  # type: ignore[arg-type]
            if sub_name == "nav":
                leaf_name, leaf_val = betterproto2.which_one_of(sub_val, "SubNavMsg")
                nav_events.append((time.time(), leaf_name, leaf_val))
                _log.info(
                    "← NAV_CAPTURE  leaf=%s  val=%s",
                    leaf_name,
                    leaf_val,
                )
        except Exception:  # noqa: BLE001
            pass

    # with broker.subscribe_unsolicited(_capture_nav):
    saga = MowPathSaga(
        command_builder=command_builder,
        send_command=send_command,
        zone_hashs=zone_hashs,
        route_info=route_info,
        skip_planning=True,
    )
    try:
        await saga.execute(broker)
    except Exception:  # noqa: BLE001
        _log.exception("MowPathSaga failed")
        _log.info("Nav events captured before failure: %d", len(nav_events))
        for ts, name, val in nav_events:
            _log.info("  t+%.3f  %-30s  %s", ts - nav_events[0][0], name, val)
        return

    total_frames = sum(len(frames) for frames in saga.result.values())
    _log.info("MowPathSaga complete:")
    _log.info("  transactions : %d", len(saga.result))
    _log.info("  total frames : %d", total_frames)
    for tx_id, frames in saga.result.items():
        _log.info("  tx=%d  frames=%s", tx_id, sorted(frames.keys()))

    # ------------------------------------------------------------------
    # Decode path/area order from cover_path_upload frames
    # ------------------------------------------------------------------
    _log.info("=== PATH / AREA ORDER ANALYSIS ===")
    for tx_id, frames in saga.result.items():
        _log.info("Transaction %d:", tx_id)
        for frame_num in sorted(frames.keys()):
            mow_path = frames[frame_num]
            _log.info(
                "  frame %d/%d  area=%d  total_paths=%d  valid_paths=%d  data_hash=%d  reserved=%s",
                mow_path.current_frame,
                mow_path.total_frame,
                mow_path.area,
                mow_path.total_path_num,
                mow_path.valid_path_num,
                mow_path.data_hash,
                mow_path.reserved,
            )
            for i, pkt in enumerate(mow_path.path_packets):
                _log.info(
                    "    packet[%d]  zone_hash=%d  path_hash=%d  type=%d  cur=%d  total=%d",
                    i,
                    pkt.zone_hash,
                    pkt.path_hash,
                    pkt.path_type,
                    pkt.path_cur,
                    pkt.path_total,
                )

    # Summarise nav events captured during the saga
    _log.info("=== NAV EVENTS DURING SAGA (%d total) ===", len(nav_events))
    if nav_events:
        t0 = nav_events[0][0]
        for ts, name, val in nav_events:
            _log.info("  t+%.3f  %-35s  %s", ts - t0, name, val)


def _ordered_mower_candidates[T: DeviceHandle](devices: list[T], name_attr: str) -> list[T]:
    """Return devices reordered so known mower prefixes come first."""
    mowers = [d for d in devices if getattr(d, name_attr, "").startswith(("Luba", "Yuka", "Spino"))]
    others = [d for d in devices if d not in mowers]
    return mowers + others


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    email = os.environ.get("MAMMOTION_EMAIL", "")
    password = os.environ.get("MAMMOTION_PASSWORD", "")
    if not email or not password:
        _log.error("Set MAMMOTION_EMAIL and MAMMOTION_PASSWORD environment variables")
        sys.exit(1)

    async with ClientSession(MAMMOTION_DOMAIN) as session:
        client = MammotionClient()

        _log.info("Logging in as %s …", email)
        await client.login_and_initiate_cloud(email, password, session)
        _log.info("Login and MQTT connection established")

        devices = list(client.device_registry.all_devices)
        if not devices:
            _log.warning("No devices found — nothing to do")
            return

        _log.info("Found %d device(s):", len(devices))
        for handle in devices:
            _log.info("  • %s  iot_id=%s", handle.device_name, handle.iot_id)

        # Grab the cloud client for Aliyun HTTP-based command sending
        cloud_client: CloudIOTGateway | None = client._cloud_client  # noqa: SLF001

        # Wait for the Aliyun MQTT transport to connect (it's a background task)
        aliyun_transport = client._aliyun_transport  # noqa: SLF001
        if aliyun_transport is not None:
            _log.info("Waiting for Aliyun MQTT transport to connect …")
            for _ in range(30):
                if aliyun_transport.is_connected:
                    break
                await asyncio.sleep(0.5)
            if aliyun_transport.is_connected:
                _log.info("Aliyun MQTT transport connected")
            else:
                _log.warning("Aliyun MQTT transport did not connect in time — responses may not arrive")

        candidates = _ordered_mower_candidates(devices, "device_name")
        for i, handle in enumerate(candidates):
            device_name: str = handle.device_name
            iot_id: str = handle.iot_id
            _log.info("Trying device %d/%d: %s  iot_id=%s", i + 1, len(candidates), device_name, iot_id)

            command_builder = MammotionCommand(device_name=device_name, user_account=0)

            # Aliyun devices: send commands via HTTP API; Mammotion devices: via MQTT transport
            if cloud_client is not None and iot_id in client._iot_id_to_device_id:  # noqa: SLF001
                async def _send_command(  # noqa: RUF029
                    cmd: bytes,
                    _cloud: CloudIOTGateway = cloud_client,
                    _iot_id: str = iot_id,
                ) -> None:
                    await _cloud.send_cloud_command(_iot_id, cmd)
            else:
                async def _send_command(cmd: bytes, _handle: DeviceHandle = handle) -> None:  # type: ignore[misc]
                    await _handle.active_transport().send(cmd, iot_id=_handle.iot_id)  # noqa: SLF001

            _send_command = _make_send_command(_send_command, iot_id)

            # Attach a persistent global logger for all incoming nav messages
            msg_logger = _make_message_logger(iot_id)
            handle.broker.subscribe_unsolicited(msg_logger)  # intentionally not context-managed (runs for lifetime)

            try:
                await _run_mow_path_saga(handle.broker, command_builder, device_name, _send_command, HashList())
                break  # success
            except DeviceOfflineException:
                _log.warning("Device %s is offline, trying next …", device_name)
                if i == len(candidates) - 1:
                    _log.error("All devices are offline")


if __name__ == "__main__":
    # aiomqtt (via paho-mqtt) needs SelectorEventLoop on Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
