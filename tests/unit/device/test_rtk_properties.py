"""RTK base-station property pushes: the Mammotion flat path must mirror the Aliyun path."""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

from pymammotion.data.model.device import RTKBaseStationDevice
from pymammotion.data.mqtt.properties import Item, Items, MammotionPropertiesMessage
from pymammotion.device.state_reducer import RTKStateReducer


def _flat(params: dict) -> MammotionPropertiesMessage:
    return MammotionPropertiesMessage.from_json(
        json.dumps(
            {"id": "1", "version": "1.0", "sys": {"ack": 1}, "method": "thing.event.property.post", "params": params}
        )
    )


def _aliyun(**items: object) -> SimpleNamespace:
    """Aliyun ThingPropertiesMessage needs ~25 envelope fields; only ``params.items`` is read here."""
    return SimpleNamespace(
        params=SimpleNamespace(
            items=Items(**{k: Item(time=0, value=v) for k, v in items.items()}),
        )
    )


def _rtk(product_key: str = "") -> RTKBaseStationDevice:
    return RTKBaseStationDevice(name="RTK-Test", product_key=product_key)


def test_flat_coordinate_sets_position() -> None:
    updated = RTKStateReducer().apply_mammotion_properties(_rtk(), _flat({"coordinate": {"lat": 0.5, "lon": 0.2}}))

    assert (updated.lat, updated.lon) == (0.5, 0.2)


def test_flat_coordinate_zero_component_is_left_unset() -> None:
    device = _rtk()
    device.lat, device.lon = 0.5, 0.2

    updated = RTKStateReducer().apply_mammotion_properties(device, _flat({"coordinate": {"lat": 0.0, "lon": 0.3}}))

    assert (updated.lat, updated.lon) == (0.5, 0.3)


def test_flat_coordinate_applies_the_a1nc68bgzzx_shift_on_both_paths() -> None:
    reducer = RTKStateReducer()
    raw = -7.0  # out of range: the 436° low latitude that product reports

    flat = reducer.apply_mammotion_properties(_rtk("a1Nc68bGZzX"), _flat({"coordinate": {"lat": raw, "lon": raw}}))
    aliyun = reducer.apply_properties(_rtk("a1Nc68bGZzX"), _aliyun(coordinate=json.dumps({"lat": raw, "lon": raw})))

    assert flat.lat == aliyun.lat == raw + math.radians(436)
    assert flat.lon == aliyun.lon == raw + math.radians(436)


def test_flat_network_info_matches_aliyun() -> None:
    reducer = RTKStateReducer()
    net = {"wifi_rssi": -61, "wifi_sta_mac": "aa:bb:cc:dd:ee:01", "bt_mac": "aa:bb:cc:dd:ee:02"}

    flat = reducer.apply_mammotion_properties(_rtk(), _flat({"networkInfo": net}))
    aliyun = reducer.apply_properties(_rtk(), _aliyun(networkInfo=json.dumps(net)))

    for device in (flat, aliyun):
        assert (device.wifi_rssi, device.wifi_mac, device.bt_mac) == (-61, net["wifi_sta_mac"], net["bt_mac"])


def test_flat_version_info_fills_module_firmwares_and_copies_before_writing() -> None:
    reducer = RTKStateReducer()
    current = _rtk()
    info = {
        "devVer": "2.1.0.9",
        "whole": 1,
        "fwInfo": [
            {"t": "101", "c": "mc", "v": "1.1"},
            {"t": "102", "c": "rtk", "v": "2.2"},
            {"t": "103", "c": "lora", "v": "3.3"},
            {"t": "999", "c": "x", "v": ""},
        ],
    }

    updated = reducer.apply_mammotion_properties(current, _flat({"deviceVersionInfo": info, "loraGeneralConfig": "L1"}))

    assert updated.device_version == "2.1.0.9"
    assert updated.device_firmwares.device_version == "2.1.0.9"
    assert (
        updated.device_firmwares.main_controller,
        updated.device_firmwares.rtk_version,
        updated.device_firmwares.lora_version,
    ) == ("1.1", "2.2", "3.3")
    assert updated.lora_version == "L1"
    # The previous snapshot's nested model must be untouched (identity-based diff).
    assert current.device_firmwares.main_controller == ""


def test_aliyun_version_info_still_fills_module_firmwares() -> None:
    info = {"devVer": "2.1.0.9", "fwInfo": [{"t": "102", "v": "2.2"}]}

    updated = RTKStateReducer().apply_properties(_rtk(), _aliyun(deviceVersionInfo=json.dumps(info)))

    assert updated.device_version == "2.1.0.9"
    assert updated.device_firmwares.rtk_version == "2.2"


def test_flat_ota_progress_drives_update_check_and_installs_version() -> None:
    reducer = RTKStateReducer()

    running = reducer.apply_mammotion_properties(_rtk(), _flat({"otaProgress": {"progress": 40, "result": 2}}))
    assert running.update_check.isupgrading is True
    assert running.update_check.progress == 40
    assert running.has_live_ota_push()

    done = reducer.apply_mammotion_properties(
        running, _flat({"otaProgress": {"progress": 99, "result": 0, "version": "2.2.0.1"}})
    )
    assert done.update_check.isupgrading is False
    assert done.update_check.progress == 100
    assert done.device_version == "2.2.0.1"


def test_aliyun_ota_progress_uses_the_same_result_codes() -> None:
    ota = {"result": 1, "otaId": "o1", "progress": 55, "message": "", "version": "2.2.0.1", "properties": ""}

    failed = RTKStateReducer().apply_properties(_rtk(), _aliyun(otaProgress=ota))

    assert failed.update_check.isupgrading is False
    assert failed.update_check.progress == 55
    assert failed.device_version == ""
