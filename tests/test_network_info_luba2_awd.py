"""Regression test for the Luba 2 AWD 3000 ``networkInfo`` property parse failure.

The Luba 2 AWD 3000 reports a ``networkInfo`` payload that omits several
device-class-dependent fields the model previously marked as *required*
(``wifi_available``, ``iccid``, ``sim_source``, ``mnet_reg``, ``mnet_rsrp``,
``mnet_snr``, ``mnet_enable``, ``wt_sec``, and the three nested traffic blocks
``bTra`` / ``bwTra`` / ``mTra``). A single missing required field made
``mashumaro`` raise ``MissingField``; the exception is caught at DEBUG in
``MowerStateReducer`` / ``RTKStateReducer`` so the device stayed available but
WiFi RSSI, IP, LTE signal, mileage, work_time, and battery_cycles never surfaced
in Home Assistant.

The payload below is a real, PII-redacted capture from a Luba 2 AWD 3000
(see https://github.com/mikey0000/Mammotion-HA/issues/751).
"""

import json

from pymammotion.data.mqtt.mammotion_properties import NetworkInfo

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
