"""Wire layout of the ``dev_net.proto`` fields and enum values added from app 2.3.20.30.

Wi-Fi scan/connect, identity, IoT-state and BLE-pairing exchanges (``DevNet`` fields 31-41) and the
BLE-encryption report.  Frames are hand-encoded from explicit tags, with a distinct value in every
field, so a renumbered or swapped field fails here.
"""

from __future__ import annotations

import betterproto2
import pytest

from pymammotion.proto import (
    BandMode,
    BleEncryptStatus,
    BlePairAction,
    BlePairStatus,
    DevNet,
    DrvWificonnectReq,
    DrvWifiList,
    WifiConnectResult,
    WifiConnectVersion,
    WifiIotStatusReport,
    WifilistVersion,
    WifiMode,
    WifiScanVersion,
)

#: int32 -60 on the wire: ten-byte two's-complement varint (not zig-zag).
_MINUS_60 = b"\xc4\xff\xff\xff\xff\xff\xff\xff\xff\x01"


def _dev_net(tag: bytes, body: bytes) -> tuple[str, object]:
    return betterproto2.which_one_of(DevNet().parse(tag + bytes([len(body)]) + body), "NetSubType")


@pytest.mark.parametrize(
    ("tag", "field"),
    [
        # (n << 3) | 2 for n = 31..41: 250 -> 0xFA 0x01, then 258, 266, ... 330 -> 0x82..0xCA, 0x02.
        (b"\xfa\x01", "toapp_allListUpload"),
        (b"\x82\x02", "todev_wificonnect"),
        (b"\x8a\x02", "toapp_wificonnect"),
        (b"\x92\x02", "todev_wifiscan"),
        (b"\x9a\x02", "toapp_wifiscan"),
        (b"\xa2\x02", "toapp_get_identity_req"),
        (b"\xaa\x02", "todev_get_identity_rsp"),
        (b"\xb2\x02", "todev_get_iot_state_req"),
        (b"\xba\x02", "toapp_get_iot_state_rsp"),
        (b"\xc2\x02", "todev_ble_pair_req"),
        (b"\xca\x02", "toapp_ble_pair_rsp"),
    ],
    ids=lambda value: value if isinstance(value, str) else value.hex(),
)
def test_dev_net_reads_the_new_oneof_fields_31_to_41(tag: bytes, field: str) -> None:
    name, _ = betterproto2.which_one_of(DevNet().parse(tag + b"\x00"), "NetSubType")

    assert name == field


@pytest.mark.parametrize(
    ("enum", "names"),
    [
        (
            WifiConnectResult,
            [
                "CONNECT_SUCCESS",
                "FAIL_PASSWORD",
                "FAIL_SSID",
                "FAIL_CONNECT_CANCELLED",
                "FAIL_CONNECT_WRONG_KEY",
                "FAIL_CONNECT_MAX_CONN",
                "FAIL_BLACK_LIST",
                "FAIL_CONNECT_FAIL",
                "FAIL_NOT_FIND_AP",
                "FAIL_WIFI_MODE_FAIL",
                "FAIL_UNKNOWN",
            ],
        ),
        (BandMode, ["FEQ_UNKNOWN_", "FEQ_2_4G", "FEQ_5G", "FEQ_2_4G_AND_5G"]),
        (WifiMode, ["NULL", "STA", "AP", "APSTA"]),
        (BlePairAction, ["UNKNOWN_ACTION", "REQUEST_PAIR", "DELETE_BOND", "QUERY_PAIR_STATUS"]),
        (
            BlePairStatus,
            [
                "UNKNOWN_STATUS",
                "NOT_PAIRED",
                "ALREADY_PAIRED",
                "PAIRING_STARTED",
                "PAIRING_IN_PROGRESS",
                "PAIR_SUCCESS",
                "PAIR_FAILED",
                "DELETE_BOND_SUCCESS",
                "DELETE_BOND_FAILED",
                "PAIR_SUCCESS_IOTONLINE",
            ],
        ),
        (WifilistVersion, ["VERSION_UNSPECIFIED", "VERSION_1"]),
        (WifiConnectVersion, ["CONNECT_VERSION_Default"]),
        (WifiScanVersion, ["SCAN_VERSION_Default"]),
    ],
    ids=lambda value: value.__name__ if isinstance(value, type) else "",
)
def test_new_enums_number_their_members_as_the_app_does(enum: type[betterproto2.Enum], names: list[str]) -> None:
    """Every one of these app enums is numbered 0..n-1 in declaration order."""
    assert [(member.name, member.value) for member in enum] == [(name, value) for value, name in enumerate(names)]


def test_ble_encrypt_status_uses_the_apps_magic_values() -> None:
    assert [(m.name, m.value) for m in BleEncryptStatus] == [
        ("BLE_S_UNKNOWN", 0),
        ("BLE_S_ENCRYPT", 42189),
        ("BLE_S_UNENCRYPT", 15730),
    ]


def test_wifi_iot_status_reads_the_ble_encryption_report_from_field_5() -> None:
    # ble_encrypt: (5 << 3) | 2 = 0x2A; status 42189 = 0xA4CD -> varint 0xCD 0xC9 0x02.
    report = WifiIotStatusReport().parse(b"\x2a\x04\x08\xcd\xc9\x02")

    assert report.ble_encrypt is not None
    assert report.ble_encrypt.ble_encrypt_status is BleEncryptStatus.BLE_S_ENCRYPT


def test_wifi_list_request_carries_its_version_on_field_2() -> None:
    assert bytes(DrvWifiList(version=WifilistVersion.VERSION_1)) == b"\x10\x01"


def test_all_list_upload_reads_repeated_wifi_list_entries() -> None:
    # toapp_allListUpload (31): wifilist (field 1) = DrvListUpload{sum=2, current=1, status=3, Memssid="m", rssi=-60}.
    entry = b"\x08\x02\x10\x01\x18\x03\x22\x01m" + b"\x28" + _MINUS_60
    _, upload = _dev_net(b"\xfa\x01", b"\x0a" + bytes([len(entry)]) + entry)

    (only,) = upload.wifilist
    assert (only.sum, only.current, only.status, only.memssid, only.rssi) == (2, 1, 3, "m", -60)


def test_wifi_connect_request_encodes_fields_1_to_6_in_order() -> None:
    request = DrvWificonnectReq(bizid=3, wifimode=WifiMode.AP, wifi_ssid="s", has_password=1, wifi_password="p")

    # version (field 1) is the single default value, so it is not emitted.
    assert bytes(request) == b"\x10\x03" + b"\x18\x02" + b"\x22\x01s" + b"\x28\x01" + b"\x32\x01p"


def test_wifi_connect_reply_reads_bizid_and_connect_state() -> None:
    # toapp_wificonnect (33): bizid=7, connect_state=FAIL_SSID (2).
    _, reply = _dev_net(b"\x8a\x02", b"\x08\x07\x10\x02")

    assert (reply.bizid, reply.connect_state) == (7, WifiConnectResult.FAIL_SSID)


def test_wifi_scan_request_reads_bizid() -> None:
    # todev_wifiscan (34): version default (omitted), bizid=9 on field 2.
    _, request = _dev_net(b"\x92\x02", b"\x10\x09")

    assert (request.version, request.bizid) == (WifiScanVersion.SCAN_VERSION_Default, 9)


def test_wifi_scan_reply_reads_bizid_and_every_network_field() -> None:
    # toapp_wifiscan (35): bizid=4; wifilist (field 2) = WiFilist{has_password=1, band_mode=5G, ssid="n", rssi=-60}.
    network = b"\x08\x01\x10\x02\x1a\x01n" + b"\x20" + _MINUS_60
    _, reply = _dev_net(b"\x9a\x02", b"\x08\x04" + b"\x12" + bytes([len(network)]) + network)

    (only,) = reply.wifilist
    assert reply.bizid == 4
    assert (only.has_password, only.band_mode, only.ssid, only.rssi) == (1, BandMode.FEQ_5G, "n", -60)


def test_identity_request_reads_req_id_and_device_name() -> None:
    # toapp_get_identity_req (36): req_id=3, device_name="d".
    _, request = _dev_net(b"\xa2\x02", b"\x08\x03\x12\x01d")

    assert (request.req_id, request.device_name) == (3, "d")


def test_identity_response_reads_every_field() -> None:
    # todev_get_identity_rsp (37): req_id=3, result=5, identity_data="i", decryption_key="k".
    _, response = _dev_net(b"\xaa\x02", b"\x08\x03\x10\x05\x1a\x01i\x22\x01k")

    assert (response.req_id, response.result, response.identity_data, response.decryption_key) == (3, 5, "i", "k")


def test_iot_state_request_reads_req_id() -> None:
    _, request = _dev_net(b"\xb2\x02", b"\x08\x06")  # todev_get_iot_state_req (38): req_id=6.

    assert request.req_id == 6


def test_iot_state_response_reads_every_field() -> None:
    # toapp_get_iot_state_rsp (39): req_id=6, result=2, has_ever_connected=true.
    _, response = _dev_net(b"\xba\x02", b"\x08\x06\x10\x02\x18\x01")

    assert (response.req_id, response.result, response.has_ever_connected) == (6, 2, True)


def test_ble_pair_request_reads_req_id_and_action() -> None:
    # todev_ble_pair_req (40): req_id=8, action=DELETE_BOND (2).
    _, request = _dev_net(b"\xc2\x02", b"\x08\x08\x10\x02")

    assert (request.req_id, request.action) == (8, BlePairAction.DELETE_BOND)


def test_ble_pair_response_reads_req_id_status_and_device_name() -> None:
    # toapp_ble_pair_rsp (41): req_id=8, status=PAIR_SUCCESS_IOTONLINE (9), device_name="d".
    _, response = _dev_net(b"\xca\x02", b"\x08\x08\x10\x09\x1a\x01d")

    assert (response.req_id, response.status, response.device_name) == (8, BlePairStatus.PAIR_SUCCESS_IOTONLINE, "d")
