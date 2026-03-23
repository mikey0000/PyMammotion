"""Live device test — login, list devices, fetch firmware version, sync map.

Uses the new architecture exclusively:
  MammotionHTTP  →  MammotionMQTT  →  DeviceHandle / DeviceMessageBroker  →  MapFetchSaga

Usage:
    MAMMOTION_EMAIL=... MAMMOTION_PASSWORD='...' uv run python scripts/live_device_test.py

Never hardcodes credentials. Read-only: no mowing, no settings changes.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
from typing import Any

from aiohttp import ClientSession

from pymammotion.const import MAMMOTION_DOMAIN
from pymammotion.data.mqtt.event import MammotionEventMessage
from pymammotion.http.http import MammotionHTTP
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.map_saga import MapFetchSaga
from pymammotion.mqtt.mammotion_mqtt import MammotionMQTT
from pymammotion.proto import LubaMsg
from pymammotion.utility.device_type import DeviceType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
for _noisy in ("pymammotion.aliyun", "paho", "aiomqtt"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

_log = logging.getLogger("live_test")


# ---------------------------------------------------------------------------
# Message bridge: raw MQTT JSON → LubaMsg → DeviceMessageBroker
# ---------------------------------------------------------------------------


def _decode_protobuf_event(topic: str, raw_json: bytes, iot_id: str) -> LubaMsg | None:
    """Decode a Mammotion MQTT JSON payload into a LubaMsg, or return None."""
    if not topic.endswith("/thing/event/device_protobuf_msg_event/post"):
        return None
    try:
        payload = json.loads(raw_json)
        # Normalise: MammotionMQTT enriches the JSON with iot_id/product_key
        event = MammotionEventMessage.from_dict(payload)
        content_b64: str = event.params.value.content  # type: ignore[union-attr]
        binary_data = base64.b64decode(content_b64)
        return LubaMsg().parse(binary_data)
    except Exception:  # noqa: BLE001
        _log.debug("Could not decode protobuf from topic %s", topic, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# HTTP phase
# ---------------------------------------------------------------------------


async def _http_checks(http: MammotionHTTP) -> tuple[list[Any], list[Any]]:
    """Run HTTP-only queries and return (records, ota_list)."""
    device_page_resp = await http.get_user_device_page()
    records = device_page_resp.data.records if device_page_resp.data else []
    _log.info("Found %d device(s):", len(records))
    for rec in records:
        _log.info("  • %s  iot_id=%s  product_key=%s", rec.device_name, rec.iot_id, rec.product_key)

    if not records:
        return [], []

    iot_ids = [rec.iot_id for rec in records]
    ota_resp = await http.get_device_ota_firmware(iot_ids)
    ota_list = ota_resp.data or []
    for ota in ota_list:
        latest = ota.product_version_info_vo.release_version if ota.product_version_info_vo else "(none)"
        _log.info(
            "  • iot_id=%-36s  current=%s  latest=%s  upgradeable=%s",
            ota.device_id,
            ota.current_version,
            latest,
            ota.upgradeable,
        )

    return records, ota_list


# ---------------------------------------------------------------------------
# MQTT + map phase
# ---------------------------------------------------------------------------


async def _mqtt_map_sync(http: MammotionHTTP, records: list[Any]) -> None:
    """Connect via Mammotion direct MQTT and run MapFetchSaga for the first mower."""
    _log.info("=== MQTT / map sync phase ===")

    if not http.mqtt_credentials:
        _log.info("Fetching MQTT credentials …")
        await http.get_mqtt_credentials()

    mqtt_creds = http.mqtt_credentials
    if mqtt_creds is None:
        _log.error("Could not obtain MQTT credentials — aborting map sync")
        return

    # Pick the first mower-type device
    mower_records = [r for r in records if r.device_name.startswith(("Luba", "Yuka", "Spino"))]
    if not mower_records:
        mower_records = records
    if not mower_records:
        _log.warning("No devices — cannot run map sync")
        return

    target = mower_records[0]
    device_name: str = target.device_name
    iot_id: str = target.iot_id
    _log.info("Target device: %s (iot_id=%s)", device_name, iot_id)

    # Build broker and command infrastructure
    broker = DeviceMessageBroker()
    command_builder = MammotionCommand(device_name=device_name, user_account=0)

    mqtt = MammotionMQTT(
        mqtt_connection=mqtt_creds,
        records=records,
        mammotion_http=http,
    )

    connected_event = asyncio.Event()

    async def _on_connected() -> None:
        _log.info("MQTT connected")
        connected_event.set()

    async def _on_message(topic: str, raw_json: bytes, msg_iot_id: str) -> None:
        if msg_iot_id != iot_id:
            return
        luba_msg = _decode_protobuf_event(topic, raw_json, msg_iot_id)
        if luba_msg is not None:
            _log.debug("Decoded LubaMsg from topic %s", topic)
            await broker.on_message(luba_msg)

    mqtt.on_connected = _on_connected
    mqtt.on_message = _on_message

    mqtt.connect_async()

    _log.info("Waiting for MQTT connection (up to 15 s) …")
    try:
        await asyncio.wait_for(connected_event.wait(), timeout=15.0)
    except TimeoutError:
        _log.error("MQTT did not connect within 15 s")
        mqtt.disconnect()
        return

    _log.info("MQTT connected — running MapFetchSaga …")

    async def _send_command(cmd: bytes) -> None:
        await mqtt.send_cloud_command(iot_id, cmd)

    is_luba1 = DeviceType.is_luba1(device_name)
    saga = MapFetchSaga(
        device_id=iot_id,
        device_name=device_name,
        is_luba1=is_luba1,
        command_builder=command_builder,
        send_command=_send_command,
    )

    try:
        await saga.execute(broker)
    except Exception:  # noqa: BLE001
        _log.exception("MapFetchSaga failed")
    finally:
        mqtt.disconnect()
        await broker.close()

    if saga.result is not None:
        hl = saga.result
        _log.info("Map sync complete:")
        _log.info("  area_name entries : %d", len(hl.area_name))
        _log.info("  root hash IDs     : %d", len(hl.hashlist))
        if hl.area_name:
            _log.info("  Area names: %s", [a.name for a in hl.area_name])
    else:
        _log.warning("MapFetchSaga did not produce a result")


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
        http = MammotionHTTP(session=session)

        _log.info("Logging in as %s …", email)
        await http.login_v2(email, password)
        _log.info("Login OK — access token acquired")

        records, _ota_list = await _http_checks(http)

        if records:
            await _mqtt_map_sync(http, records)


if __name__ == "__main__":
    # aiomqtt (via paho-mqtt) needs SelectorEventLoop on Windows — ProactorEventLoop
    # does not implement add_reader/add_writer which paho uses for socket I/O.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
