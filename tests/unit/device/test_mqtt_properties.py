"""MQTT ``thing.event.property.post`` parsing regressions.

Payload shapes vary by device and firmware — WiFi-only mowers omit the whole
cellular block, Spinos post model-only or firmware-only params, and the Yuka
Mini 2 omits several fields older devices always sent.  Each group here pins a
real payload that once raised MissingField and got dropped.
"""

from __future__ import annotations

import json
from pathlib import Path

from pymammotion.data.mqtt.mammotion_properties import DeviceProperties, NetworkInfo
from pymammotion.data.mqtt.properties import MammotionPropertiesMessage

# ===========================================================================
# Regression test for the Luba 2 AWD 3000 ``networkInfo`` property parse failure.
# ===========================================================================

LUBA2_AWD_NETWORK_INFO = json.dumps(
    {
        "ssid": "REDACTED",
        "ip": "192.168.1.1",
        "wifi_sta_mac": "aa:bb:cc:dd:ee:01",
        "wifi_rssi": -44,
        "bt_mac": "aa:bb:cc:dd:ee:02",
        "mnet_model": "L716-EU",
        "imei": "000000000000000",
        "fw_ver": "17016.1000.00.38.02.17",
        "sim": "Ready",
        "imsi": "000000000000000",
        "mnet_rssi": -73,
        "signal": 3,
        "mnet_link": 1,
        "mnet_option": "REDACTED",
        "mnet_ip": "10.0.0.1",
        "used_net": 1,
        "hub_reset": 0,
        "mnet_dis": 0,
        "airplane_times": 0,
        "lsusb_num": 7,
        "mnet_rx": "181.47MB",
        "mnet_tx": "177.76MB",
        "mnet_uniot": 0,
        "mnet_un_getiot": 1,
        "apn_num": 1,
        "apn_info": "REDACTED",
        "apn_cid": 1,
        "ssh_flag": "0",
        "mileage": "272.64 km",
        "work_time": "324 h 3 min 42 s",
        "bat_cycles": "120 times",
    }
)


def test_luba2_awd_network_info_parses() -> None:
    """A Luba 2 AWD 3000 networkInfo payload decodes instead of being dropped."""
    ni = NetworkInfo.from_json(LUBA2_AWD_NETWORK_INFO)

    assert ni.wifi_rssi == -44
    assert ni.mnet_rssi == -73
    assert ni.mnet_model == "L716-EU"
    assert ni.mileage == "272.64 km"
    assert ni.work_time == "324 h 3 min 42 s"
    assert ni.bat_cycles == "120 times"

    assert ni.wifi_available == 0
    assert ni.iccid == ""
    assert ni.sim_source == ""
    assert ni.mnet_reg == ""
    assert ni.mnet_rsrp == ""
    assert ni.mnet_snr == ""
    assert ni.mnet_enable == 0
    assert ni.wt_sec == 0
    assert ni.b_tra is None
    assert ni.bw_tra is None
    assert ni.m_tra is None


def test_wifi_only_network_info_omitting_cellular_fields_parses() -> None:
    """A WiFi-only mower (e.g. Yuka mini) omits the whole cellular block — it must still parse.

    Regression for a real Yuka-MNTXVHBE property post that raised
    MissingField "mnet_model" and got dropped, so the device never updated state.
    """
    wifi_only = json.dumps(
        {
            "ssid": "IOT",
            "ip": "192.168.20.45",
            "wifi_sta_mac": "14:5d:34:31:db:f6",
            "wifi_rssi": -56,
            "wifi_available": 1,
            "bt_mac": "14:5d:34:31:db:f7",
            "mnet_enable": 0,
            "apn_num": 0,
            "apn_info": "",
            "apn_cid": 0,
            "used_net": 1,
            "hub_reset": 0,
            "mnet_dis": 0,
            "airplane_times": 0,
            "lsusb_num": 4,
            "mnet_rx": 0,  # WiFi-only devices send an int here, not the cellular "181.47MB" string
            "mnet_tx": 0,
            "mnet_uniot": 0,
            "mnet_un_getiot": 0,
            "ssh_flag": "0",
            "mileage": "254960",
            "work_time": "6 h 42 min 37 s",
            "wt_sec": 24157,
            "bat_cycles": "0",
        }
    )

    ni = NetworkInfo.from_json(wifi_only)

    # WiFi fields present; cellular fields defaulted rather than raising MissingField.
    assert ni.wifi_rssi == -56
    assert ni.ssid == "IOT"
    assert ni.mnet_model == ""
    assert ni.imei == ""
    assert ni.sim == ""
    assert ni.mnet_rssi == 0
    assert ni.mnet_rx == "0"  # int coerced to str
    assert ni.work_time == "6 h 42 min 37 s"


# ===========================================================================
# Regression tests for partial ``thing.event.property.post`` payloads.
# ===========================================================================

SPINO_MODEL_ONLY = json.dumps(
    {
        "id": "14846",
        "version": "1.0",
        "sys": {"ack": 1},
        "params": {"intMod": "SPINO E1", "extMod": "SPINO E1"},
        "method": "thing.event.property.post",
    }
)

SPINO_FW_ONLY = json.dumps(
    {
        "id": "14848",
        "version": "1.0",
        "sys": {"ack": 1},
        "params": {
            "deviceVersion": "1.15.2.1039",
            "deviceVersionInfo": json.dumps(
                {
                    "devVer": "1.15.2.1039",
                    "whole": 1,
                    "fwInfo": [
                        {"t": "63", "c": "63-PAWG4", "v": "1.2.0.275"},
                        {"t": "65", "c": "65-PACG4", "v": "1.2.0.279"},
                    ],
                }
            ),
        },
        "method": "thing.event.property.post",
    }
)


def test_partial_property_post_model_fields_only() -> None:
    """A property/post carrying only ``intMod`` / ``extMod`` decodes successfully."""
    msg = MammotionPropertiesMessage.from_json(SPINO_MODEL_ONLY)
    p = msg.params

    assert p.int_mod == "SPINO E1"
    assert p.ext_mod == "SPINO E1"

    # Absent fields decode as None (numeric) / "" (string) rather than raising;
    # None lets consumers distinguish "not reported" from a genuine 0.
    assert p.device_state is None
    assert p.battery_percentage is None
    assert p.device_version == ""
    assert p.network_info is None
    assert p.coordinate is None
    assert p.device_other_info is None
    assert p.device_version_info is None
    assert p.check_data is None


def test_partial_property_post_firmware_only() -> None:
    """A property/post carrying only ``deviceVersion`` / ``deviceVersionInfo`` decodes successfully."""
    msg = MammotionPropertiesMessage.from_json(SPINO_FW_ONLY)
    p = msg.params

    assert p.device_version == "1.15.2.1039"
    assert p.device_version_info is not None
    assert p.device_version_info.dev_ver == "1.15.2.1039"
    assert [fw.c for fw in p.device_version_info.fw_info] == ["63-PAWG4", "65-PACG4"]

    # Everything else defaults / is None.
    assert p.battery_percentage is None
    assert p.network_info is None
    assert p.coordinate is None


def test_device_properties_accepts_empty_params() -> None:
    """A property/post with no params at all still decodes (every field optional)."""
    p = DeviceProperties.from_dict({})
    assert p.device_state is None
    assert p.network_info is None


# ===========================================================================
# Regression test for the Yuka Mini 2 ``thing.event.property.post`` parse failure.
# ===========================================================================

# tests/unit/device/ → repo tests/ is parents[2].
FIXTURE = Path(__file__).parents[2] / "fixtures" / "yuka_mini2_property_post.json"


def test_yuka_mini2_property_post_parses() -> None:
    """The full property message decodes instead of being dropped on a missing field."""
    raw = FIXTURE.read_bytes()
    msg = MammotionPropertiesMessage.from_json(raw)
    p = msg.params

    # Core status that HA depends on — the data that was being thrown away.
    assert p.battery_percentage == 31
    assert p.device_state == 13
    assert p.knife_height == 60
    assert "YUKA mini 2" in p.ext_mod
    assert p.device_version == "2.3.23.19"

    # Fields this device class does not report must default, not raise.
    assert p.left_motor_version == ""
    assert p.right_motor_version == ""
    assert p.rtk_version == ""
    assert p.bms_version == ""
    assert p.network_info.ip == ""
    assert p.network_info.apn_num == 0
    assert p.device_other_info.tilt_degree == ""

    # Fields the device *does* report still populate (incl. the previously typo'd alias).
    assert p.network_info.wifi_rssi == -65
    assert p.device_other_info.iot_con_fail_min == "0"
    assert [fw.c for fw in p.device_version_info.fw_info][:2] == [
        "202-MNWheelfG4BT",
        "201-MNWheelfG4",
    ]


def test_missing_optional_fields_does_not_raise() -> None:
    """Stripping every now-optional key must still yield a usable message."""
    obj = json.loads(FIXTURE.read_bytes())
    for key in ("leftMotorVersion", "rightMotorVersion", "rtkVersion", "bmsVersion"):
        obj["params"].pop(key, None)  # already absent for this device, asserted explicit
    msg = MammotionPropertiesMessage.from_json(json.dumps(obj))
    assert msg.params.battery_percentage == 31

# ===========================================================================
# ``otaProgress`` on the Mammotion flat property post — the app reads this object
# (MQTTService.messageArrived) and it was silently dropped here for lack of a field.
# ===========================================================================

OTA_PROGRESS_POST = json.dumps(
    {
        "id": "20991",
        "version": "1.0",
        "sys": {"ack": 1},
        "params": {
            "otaProgress": {
                "otaId": "ota-42",
                "version": "1.16.0.1101",
                "progress": 37,
                "result": 2,
                "message": "",
                "properties": "",
            }
        },
        "method": "thing.event.property.post",
    }
)


def test_ota_progress_object_is_parsed() -> None:
    p = MammotionPropertiesMessage.from_json(OTA_PROGRESS_POST).params

    assert p.ota_progress is not None
    assert p.ota_progress.ota_id == "ota-42"
    assert p.ota_progress.version == "1.16.0.1101"
    assert p.ota_progress.progress == 37
    assert p.ota_progress.result == 2


def test_ota_progress_accepts_json_string_and_partial_object() -> None:
    """Some firmware sends nested objects as JSON strings, and fields may be missing."""
    raw = json.dumps(
        {
            "id": "1",
            "version": "1.0",
            "sys": {"ack": 1},
            "params": {"otaProgress": json.dumps({"progress": 100, "result": 0})},
            "method": "thing.event.property.post",
        }
    )
    p = MammotionPropertiesMessage.from_json(raw).params

    assert p.ota_progress is not None
    assert (p.ota_progress.progress, p.ota_progress.result, p.ota_progress.version) == (100, 0, "")


def test_post_without_ota_progress_leaves_field_none() -> None:
    assert MammotionPropertiesMessage.from_json(SPINO_MODEL_ONLY).params.ota_progress is None
