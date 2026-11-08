"""Tests for BluFi Wi-Fi provisioning: payload parsers and the provisioner against a fake BluFi device."""

from __future__ import annotations

import asyncio

import pytest

from pymammotion.bluetooth import blufi_wifi
from pymammotion.bluetooth.blufi_wifi import (
    FRAME_LEN,
    BlufiCtrl,
    BlufiData,
    BlufiError,
    BlufiWifiProvisioner,
    BlufiWifiStatus,
    StaConnectionStatus,
    WifiNetwork,
    WifiOpMode,
    parse_wifi_list,
    parse_wifi_status,
)
from tests.unit.bluetooth._fakes import BLUFI_VERSION, FakeBlufiBleClient, FakeBlufiDevice

TIMEOUT = 5.0
OLD_SSID = "IOT"
NEW_SSID = "Home Network"
PASSWORD = "correct-horse-battery-staple-and-then-some"  # noqa: S105 - test credential, long enough to fragment


@pytest.fixture(autouse=True)
def _no_frame_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(blufi_wifi, "FRAME_GAP_S", 0)


def _client(**overrides: object) -> FakeBlufiBleClient:
    options: dict[str, object] = {
        "current_ssid": OLD_SSID,
        "networks": [(NEW_SSID, -52), (OLD_SSID, -40)],
        "connect_reports": [StaConnectionStatus.FAILED, StaConnectionStatus.CONNECTED],
    }
    options.update(overrides)
    return FakeBlufiBleClient(FakeBlufiDevice(**options))  # type: ignore[arg-type]


def _status(ssid: str | None, status: StaConnectionStatus = StaConnectionStatus.CONNECTED) -> BlufiWifiStatus:
    return BlufiWifiStatus(op_mode=WifiOpMode.STA, sta_status=status, softap_connections=0, sta_ssid=ssid)


def test_parse_wifi_status_reads_header_and_station_fields() -> None:
    data = bytes([1, 0, 0, BlufiData.STA_WIFI_BSSID, 6]) + bytes.fromhex("da21f97c3f12")
    data += bytes([BlufiData.STA_WIFI_SSID, 3]) + b"IOT"

    assert parse_wifi_status(data) == BlufiWifiStatus(
        op_mode=WifiOpMode.STA,
        sta_status=StaConnectionStatus.CONNECTED,
        softap_connections=0,
        sta_ssid="IOT",
        sta_bssid="da:21:f9:7c:3f:12",
    )


def test_parse_wifi_status_maps_unknown_station_state_to_unknown() -> None:
    assert parse_wifi_status(bytes([1, 9, 0])).sta_status is StaConnectionStatus.UNKNOWN


def test_parse_wifi_status_rejects_a_truncated_header() -> None:
    with pytest.raises(BlufiError, match="too short"):
        parse_wifi_status(bytes([1, 0]))


def test_parse_wifi_status_drops_a_truncated_field() -> None:
    data = bytes([1, 0, 0, BlufiData.STA_WIFI_SSID, 9]) + b"IOT"

    assert parse_wifi_status(data).sta_ssid is None


def test_parse_wifi_list_reads_signed_rssi_entries() -> None:
    data = bytes([4, 0xCC]) + b"abc" + bytes([2, 0xD8]) + b"z"

    assert parse_wifi_list(data) == [WifiNetwork(ssid="abc", rssi=-52), WifiNetwork(ssid="z", rssi=-40)]


@pytest.mark.parametrize("tail", [bytes([9, 0xCC]) + b"ab", bytes([0, 0xCC]) + b"ab"])
def test_parse_wifi_list_stops_at_a_truncated_or_empty_entry(tail: bytes) -> None:
    assert parse_wifi_list(bytes([2, 0xCC]) + b"a" + tail) == [WifiNetwork(ssid="a", rssi=-52)]


def test_connected_to_requires_the_named_network() -> None:
    assert not _status(OLD_SSID).connected_to(NEW_SSID)


def test_connected_to_accepts_a_report_that_names_no_network() -> None:
    assert _status(None).connected_to(NEW_SSID)


def test_connected_to_is_false_while_connecting() -> None:
    assert not _status(NEW_SSID, StaConnectionStatus.CONNECTING).connected_to(NEW_SSID)


async def test_get_version_returns_major_and_minor() -> None:
    async with BlufiWifiProvisioner(_client()) as provisioner:  # type: ignore[arg-type]
        assert await asyncio.wait_for(provisioner.get_version(), TIMEOUT) == BLUFI_VERSION


async def test_scan_returns_the_networks_the_device_sees() -> None:
    async with BlufiWifiProvisioner(_client()) as provisioner:  # type: ignore[arg-type]
        networks = await asyncio.wait_for(provisioner.scan(), TIMEOUT)

    assert networks == [WifiNetwork(ssid=NEW_SSID, rssi=-52), WifiNetwork(ssid=OLD_SSID, rssi=-40)]


async def test_scan_raises_when_the_device_reports_an_error() -> None:
    async with BlufiWifiProvisioner(_client(error_on=BlufiCtrl.GET_WIFI_LIST)) as provisioner:  # type: ignore[arg-type]
        with pytest.raises(BlufiError, match="error 3"):
            await asyncio.wait_for(provisioner.scan(), TIMEOUT)


async def test_connect_station_delivers_credentials_and_the_connect_request() -> None:
    client = _client()

    async with BlufiWifiProvisioner(client) as provisioner:  # type: ignore[arg-type]
        await asyncio.wait_for(provisioner.connect_station(NEW_SSID, PASSWORD), TIMEOUT)

    device = client.device
    assert (device.op_mode, device.received_ssid, device.received_password) == (WifiOpMode.STA, NEW_SSID, PASSWORD)
    assert device.connect_requested


async def test_connect_station_splits_credentials_into_app_sized_frames() -> None:
    """The fake rejects any write over FRAME_LEN, so a long password must arrive fragmented."""
    client = _client()

    async with BlufiWifiProvisioner(client) as provisioner:  # type: ignore[arg-type]
        await asyncio.wait_for(provisioner.connect_station(NEW_SSID, PASSWORD), TIMEOUT)

    assert len(PASSWORD) > FRAME_LEN
    assert client.device.received_password == PASSWORD
    assert max(len(write) for write in client.writes) <= FRAME_LEN


async def test_connect_station_returns_the_report_for_the_new_network() -> None:
    async with BlufiWifiProvisioner(_client()) as provisioner:  # type: ignore[arg-type]
        status = await asyncio.wait_for(provisioner.connect_station(NEW_SSID, PASSWORD), TIMEOUT)

    assert status == _status(NEW_SSID)


async def test_connect_station_skips_the_old_network_still_reported_connected() -> None:
    """The first report after CONNECT_WIFI can still describe the network being left."""
    client = _client(connect_reports=[StaConnectionStatus.CONNECTED], stale_report_first=True)

    async with BlufiWifiProvisioner(client) as provisioner:  # type: ignore[arg-type]
        status = await asyncio.wait_for(provisioner.connect_station(NEW_SSID, PASSWORD), TIMEOUT)

    assert status == _status(NEW_SSID)


async def test_connect_station_returns_the_last_report_when_the_network_never_comes_up() -> None:
    """The reports are queued during the writes, before any await suspends, so timeout=0 only ends the wait after them."""
    client = _client(connect_reports=[StaConnectionStatus.CONNECTING, StaConnectionStatus.FAILED])

    async with BlufiWifiProvisioner(client) as provisioner:  # type: ignore[arg-type]
        status = await asyncio.wait_for(provisioner.connect_station(NEW_SSID, PASSWORD, timeout=0), TIMEOUT)

    assert status == _status(NEW_SSID, StaConnectionStatus.FAILED)


async def test_connect_station_returns_none_when_the_device_pushes_no_report() -> None:
    """Mower firmware 6.0.0 pushes nothing; timeout=0 ends the wait at the first suspension."""
    async with BlufiWifiProvisioner(_client(connect_reports=[])) as provisioner:  # type: ignore[arg-type]
        status = await asyncio.wait_for(provisioner.connect_station(NEW_SSID, PASSWORD, timeout=0), TIMEOUT)

    assert status is None


async def test_exit_skips_unsubscribing_from_a_disconnected_client() -> None:
    """The fake's stop_notify raises when disconnected, as bleak does, so reaching the end means it was skipped."""
    client = _client()

    async with BlufiWifiProvisioner(client):  # type: ignore[arg-type]
        client.is_connected = False
