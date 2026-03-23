"""Live device test — login, list devices, fetch firmware version, sync map.

Detects device generation from HTTP responses and picks the correct MQTT path:
  - Pre-2025 devices (get_user_device_list)  →  CloudIOTGateway + AliyunMQTT
  - Post-2025 devices (get_user_device_page) →  MammotionMQTT

Usage:
    MAMMOTION_EMAIL=... MAMMOTION_PASSWORD='...' uv run python scripts/live_device_test.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
from collections.abc import Awaitable, Callable

from aiohttp import ClientSession

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.exceptions import DeviceOfflineException
from pymammotion.const import MAMMOTION_DOMAIN
from pymammotion.data.model import GenerateRouteInformation
from pymammotion.data.model.hash_list import HashList
from pymammotion.data.mqtt.event import DeviceProtobufMsgEventParams, MammotionEventMessage, ThingEventMessage
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import DeviceInfo, DeviceRecord, DeviceRecords
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.map_saga import MapFetchSaga
from pymammotion.messaging.mow_path_saga import MowPathSaga
from pymammotion.mqtt import AliyunMQTT, MammotionMQTT
from pymammotion.proto import LubaMsg
from pymammotion.utility.device_type import DeviceType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
for _noisy in ("pymammotion.aliyun", "paho", "aiomqtt"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

_log = logging.getLogger("live_test")
_PROTO_DEBUG = os.environ.get("PROTO_DEBUG", "").lower() in ("1", "true", "yes")


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
# Message bridge: raw MQTT JSON → LubaMsg → DeviceMessageBroker
# ---------------------------------------------------------------------------


def _decode_protobuf_event(topic: str, raw_json: bytes) -> LubaMsg | None:
    """Decode a Mammotion MQTT JSON payload into a LubaMsg, or return None.

    Handles both paths:
      MammotionMQTT: topic ends with /thing/event/device_protobuf_msg_event/post
      AliyunMQTT:    topic contains thing/events or _thing/event/notify
    """
    is_mammotion_event = topic.endswith("/thing/event/device_protobuf_msg_event/post")
    is_aliyun_event = "thing/events" in topic or "_thing/event/notify" in topic
    if not (is_mammotion_event or is_aliyun_event):
        return None
    try:
        payload = json.loads(raw_json)
        if is_aliyun_event:
            # Aliyun thing/events: use ThingEventMessage which handles the identifier dispatch
            event = ThingEventMessage.from_dicts(payload)
            if not isinstance(event.params, DeviceProtobufMsgEventParams):
                return None
            content_b64: str = event.params.value.content
        else:
            # MammotionMQTT device_protobuf_msg_event/post: different envelope format
            mm_event = MammotionEventMessage.from_dict(payload)
            content_b64 = mm_event.params.value.content  # type: ignore[union-attr]
        binary_data = base64.b64decode(content_b64)
        luba_msg = LubaMsg().parse(binary_data)
        if _PROTO_DEBUG:
            _log.info("PROTO  topic=%s  %s", topic, luba_msg)
        return luba_msg
    except Exception:  # noqa: BLE001
        _log.debug("Could not decode protobuf from topic %s", topic, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# HTTP phase
# ---------------------------------------------------------------------------


async def _http_checks(http: MammotionHTTP) -> tuple[list[DeviceInfo], list[DeviceRecord]]:
    """Query device lists and return (aliyun_devices, mammotion_devices).

    Aliyun devices come from get_user_device_list (pre-2025).
    Mammotion devices come from get_user_device_page (post-2025).
    """
    device_list_resp = await http.get_user_device_list()
    device_infos: list[DeviceInfo] = device_list_resp.data or []

    device_page_resp = await http.get_user_device_page()
    device_records_page: DeviceRecords | None = device_page_resp.data
    device_records: list[DeviceRecord] = device_records_page.records if device_records_page else []

    if device_infos:
        _log.info("Found %d pre-2025 device(s) (→ Aliyun MQTT):", len(device_infos))
        for d in device_infos:
            _log.info("  • %-30s  iot_id=%s  type=%s", d.device_name, d.iot_id, d.device_type)

    if device_records:
        _log.info("Found %d post-2025 device(s) (→ Mammotion MQTT):", len(device_records))
        for r in device_records:
            _log.info("  • %-30s  iot_id=%s", r.device_name, r.iot_id)

    all_iot_ids = [d.iot_id for d in device_infos] + [r.iot_id for r in device_records]
    if all_iot_ids:
        ota_resp = await http.get_device_ota_firmware(all_iot_ids)
        for ota in ota_resp.data or []:
            latest = ota.product_version_info_vo.release_version if ota.product_version_info_vo else "(none)"
            _log.info(
                "  OTA %-36s  current=%-12s  latest=%-12s  upgradeable=%s",
                ota.device_id,
                ota.current_version,
                latest,
                ota.upgradeable,
            )

    return device_infos, device_records


# ---------------------------------------------------------------------------
# Aliyun auth flow
# ---------------------------------------------------------------------------


async def _setup_aliyun(http: MammotionHTTP) -> CloudIOTGateway:
    """Run the full Aliyun CloudIOTGateway authentication sequence."""
    _log.info("Running Aliyun auth flow …")
    await http.refresh_authorization_code()

    cloud_client = CloudIOTGateway(mammotion_http=http)
    country_code = http.login_info.userInformation.domainAbbreviation
    _log.info("Country code: %s", country_code)

    await cloud_client.get_region(country_code)
    await cloud_client.connect()
    await cloud_client.login_by_oauth(country_code)
    await cloud_client.aep_handle()
    await cloud_client.session_by_auth_code()

    _log.info(
        "Aliyun auth complete — product_key=%s  device_name=%s",
        cloud_client._aep_response.data.productKey,
        cloud_client._aep_response.data.deviceName,
    )
    return cloud_client


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
    else:
        _log.warning("MapFetchSaga did not produce a result")

    return saga.result


async def _run_mow_path_saga(
    broker: DeviceMessageBroker,
    command_builder: MammotionCommand,
    send_command: Callable[[bytes], Awaitable[None]],
    map_result: HashList,
) -> None:
    zone_hashs = list(map_result.area.keys())
    if not zone_hashs:
        _log.warning("MowPathSaga: no area hashes available — skipping")
        return

    _log.info("MowPathSaga: requesting mow path for %d zone(s): %s", len(zone_hashs), zone_hashs)
    route_info = GenerateRouteInformation(one_hashs=zone_hashs)
    saga = MowPathSaga(
        command_builder=command_builder,
        send_command=send_command,
        zone_hashs=zone_hashs,
        route_info=route_info,
    )
    try:
        await saga.execute(broker)
    except Exception:  # noqa: BLE001
        _log.exception("MowPathSaga failed")
        return

    total_frames = sum(len(frames) for frames in saga.result.values())
    _log.info("MowPathSaga complete:")
    _log.info("  transactions : %d", len(saga.result))
    _log.info("  total frames : %d", total_frames)
    for tx_id, frames in saga.result.items():
        _log.info("  tx=%d  frames=%s", tx_id, sorted(frames.keys()))


def _ordered_mower_candidates[T](devices: list[T], name_attr: str) -> list[T]:
    """Return devices reordered so known mower prefixes come first."""
    mowers = [d for d in devices if getattr(d, name_attr, "").startswith(("Luba", "Yuka", "Spino"))]
    others = [d for d in devices if d not in mowers]
    return mowers + others


# ---------------------------------------------------------------------------
# Aliyun MQTT path
# ---------------------------------------------------------------------------


async def _mqtt_map_sync_aliyun(http: MammotionHTTP, device_infos: list[DeviceInfo]) -> None:
    """Connect via AliyunMQTT (pre-2025 devices) and run MapFetchSaga.

    On DeviceOfflineException, automatically tries the next device.
    """
    _log.info("=== Aliyun MQTT phase ===")

    cloud_client = await _setup_aliyun(http)

    mqtt = AliyunMQTT(
        region_id=cloud_client._region_response.data.regionId,
        product_key=cloud_client._aep_response.data.productKey,
        device_name=cloud_client._aep_response.data.deviceName,
        device_secret=cloud_client._aep_response.data.deviceSecret,
        iot_token=cloud_client._session_by_authcode_response.data.iotToken,
        client_id=cloud_client._client_id,
        cloud_client=cloud_client,
    )

    # active_iot_id[0] is updated per attempt so the shared callback filters correctly
    active_iot_id: list[str] = [""]
    active_broker: list[DeviceMessageBroker] = [DeviceMessageBroker()]

    connected_event = asyncio.Event()

    async def _on_connected() -> None:
        topics = mqtt._subscription_topics()
        _log.info("Aliyun MQTT connected — subscribed to %d topics:", len(topics))
        for t in topics:
            _log.info("  sub: %s", t)
        connected_event.set()

    async def _on_message(topic: str, raw_json: bytes, msg_iot_id: str) -> None:
        _log.info("← RECV  topic=%s  iot_id=%s  payload=%s", topic, msg_iot_id, raw_json)
        if msg_iot_id != active_iot_id[0]:
            return
        luba_msg = _decode_protobuf_event(topic, raw_json)
        if luba_msg is not None:
            _log.info("← DECODED  %s", luba_msg)
            await active_broker[0].on_message(luba_msg)

    mqtt.on_connected = _on_connected
    mqtt.on_message = _on_message
    mqtt.connect_async()

    _log.info("Waiting for Aliyun MQTT connection (up to 20 s) …")
    try:
        await asyncio.wait_for(connected_event.wait(), timeout=20.0)
    except TimeoutError:
        _log.error("Aliyun MQTT did not connect within 20 s")
        mqtt.disconnect()
        await active_broker[0].close()
        return

    candidates = _ordered_mower_candidates(device_infos, "device_name")
    try:
        for i, target in enumerate(candidates):
            device_name: str = target.device_name
            iot_id: str = target.iot_id
            _log.info("Trying device %d/%d: %s  iot_id=%s", i + 1, len(candidates), device_name, iot_id)

            active_iot_id[0] = iot_id
            broker = DeviceMessageBroker()
            active_broker[0] = broker
            command_builder = MammotionCommand(device_name=device_name, user_account=0)

            async def _send_command(cmd: bytes, _iot_id: str = iot_id) -> None:
                await mqtt.send_cloud_command(_iot_id, cmd)

            _send_command = _make_send_command(_send_command, iot_id)

            try:
                map_result = await _run_map_saga(broker, command_builder, device_name, iot_id, _send_command)
                if map_result is not None:
                    await _run_mow_path_saga(broker, command_builder, _send_command, map_result)
                break  # success
            except DeviceOfflineException:
                _log.warning("Device %s is offline, trying next …", device_name)
                await broker.close()
                if i == len(candidates) - 1:
                    _log.error("All devices are offline")
    finally:
        mqtt.disconnect()
        await active_broker[0].close()


# ---------------------------------------------------------------------------
# Mammotion MQTT path
# ---------------------------------------------------------------------------


async def _mqtt_map_sync_mammotion(http: MammotionHTTP, device_records: list[DeviceRecord]) -> None:
    """Connect via MammotionMQTT (post-2025 devices) and run MapFetchSaga.

    On DeviceOfflineException, automatically tries the next device.
    """
    _log.info("=== Mammotion MQTT phase ===")

    if not http.mqtt_credentials:
        _log.info("Fetching MQTT credentials …")
        await http.get_mqtt_credentials()

    mqtt_creds = http.mqtt_credentials
    if mqtt_creds is None:
        _log.error("Could not obtain MQTT credentials — aborting")
        return

    mqtt = MammotionMQTT(
        mqtt_connection=mqtt_creds,
        records=device_records,
        mammotion_http=http,
    )

    active_iot_id: list[str] = [""]
    active_broker: list[DeviceMessageBroker] = [DeviceMessageBroker()]

    connected_event = asyncio.Event()

    async def _on_connected() -> None:
        all_topics = [
            t
            for rec in device_records
            for t in mqtt._topics_for(rec.product_key, rec.device_name)
        ]
        _log.info("Mammotion MQTT connected — subscribed to %d topics:", len(all_topics))
        for t in all_topics:
            _log.info("  sub: %s", t)
        connected_event.set()

    async def _on_message(topic: str, raw_json: bytes, msg_iot_id: str) -> None:
        _log.info("← RECV  topic=%s  iot_id=%s  payload=%s", topic, msg_iot_id, raw_json[:200])
        if msg_iot_id != active_iot_id[0]:
            return
        luba_msg = _decode_protobuf_event(topic, raw_json)
        if luba_msg is not None:
            _log.info("← DECODED  %s", luba_msg)
            await active_broker[0].on_message(luba_msg)

    mqtt.on_connected = _on_connected
    mqtt.on_message = _on_message
    mqtt.connect_async()

    _log.info("Waiting for Mammotion MQTT connection (up to 15 s) …")
    try:
        await asyncio.wait_for(connected_event.wait(), timeout=15.0)
    except TimeoutError:
        _log.error("Mammotion MQTT did not connect within 15 s")
        mqtt.disconnect()
        await active_broker[0].close()
        return

    candidates = _ordered_mower_candidates(device_records, "device_name")
    try:
        for i, target in enumerate(candidates):
            device_name: str = target.device_name
            iot_id: str = target.iot_id
            _log.info("Trying device %d/%d: %s  iot_id=%s", i + 1, len(candidates), device_name, iot_id)

            active_iot_id[0] = iot_id
            broker = DeviceMessageBroker()
            active_broker[0] = broker
            command_builder = MammotionCommand(device_name=device_name, user_account=0)

            async def _send_command(cmd: bytes, _iot_id: str = iot_id) -> None:
                await mqtt.send_cloud_command(_iot_id, cmd)

            _send_command = _make_send_command(_send_command, iot_id)

            try:
                map_result = await _run_map_saga(broker, command_builder, device_name, iot_id, _send_command)
                if map_result is not None:
                    await _run_mow_path_saga(broker, command_builder, _send_command, map_result)
                break  # success
            except DeviceOfflineException:
                _log.warning("Device %s is offline, trying next …", device_name)
                await broker.close()
                if i == len(candidates) - 1:
                    _log.error("All devices are offline")
    finally:
        mqtt.disconnect()
        await active_broker[0].close()


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

        device_infos, device_records = await _http_checks(http)

        if not device_infos and not device_records:
            _log.warning("No devices found — nothing to do")
            return

        if device_infos:
            # Pre-2025 devices go through the Aliyun cloud gateway
            await _mqtt_map_sync_aliyun(http, device_infos)
        else:
            # Post-2025 devices use the direct Mammotion MQTT path
            await _mqtt_map_sync_mammotion(http, device_records)


if __name__ == "__main__":
    # aiomqtt (via paho-mqtt) needs SelectorEventLoop on Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
