"""Change a mower's Wi-Fi network over BLE with BluFi provisioning, as the Mammotion app's network settings do.

Frames are sent unencrypted: the app never runs BluFi security negotiation, and mower firmware ignores it. The
app wraps the SSID and password in an extra envelope only after its optional ECDH pairing, which this skips.
Firmware 6.0.0 answers version and scan requests but not GET_WIFI_STATUS, so confirm a switch from the network.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import IntEnum
import logging
from typing import TYPE_CHECKING, Self

from pymammotion.bluetooth.ble_message import BleMessage
from pymammotion.bluetooth.const import UUID_NOTIFICATION_CHARACTERISTIC
from pymammotion.utility.enum_base import UnknownTolerantIntEnum

if TYPE_CHECKING:
    from types import TracebackType

    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

_LOGGER = logging.getLogger(__name__)

PACKAGE_CTRL = 0
PACKAGE_DATA = 1

#: The app's frame size when no MTU is negotiated: 4-byte header plus 16 data bytes.
FRAME_LEN = 20
FRAME_HEADER_LEN = 4
FRAME_GAP_S = 0.01


class BlufiCtrl(IntEnum):
    """BluFi control-frame subtypes."""

    ACK = 0
    SET_SEC_MODE = 1
    SET_OP_MODE = 2
    CONNECT_WIFI = 3
    DISCONNECT_WIFI = 4
    GET_WIFI_STATUS = 5
    DEAUTHENTICATE = 6
    GET_VERSION = 7
    CLOSE_CONNECTION = 8
    GET_WIFI_LIST = 9


class BlufiData(IntEnum):
    """BluFi data-frame subtypes."""

    NEG = 0
    STA_WIFI_BSSID = 1
    STA_WIFI_SSID = 2
    STA_WIFI_PASSWORD = 3
    WIFI_CONNECTION_STATE = 15
    VERSION = 16
    WIFI_LIST = 17
    ERROR = 18
    CUSTOM_DATA = 19


class WifiOpMode(IntEnum):
    """BluFi Wi-Fi operating modes."""

    NULL = 0
    STA = 1
    SOFTAP = 2
    STA_SOFTAP = 3


class StaConnectionStatus(UnknownTolerantIntEnum):
    """Station connection state in a BluFi Wi-Fi status report."""

    CONNECTED = 0
    FAILED = 1
    CONNECTING = 2
    CONNECTED_NO_IP = 3
    UNKNOWN = 255


class BlufiError(Exception):
    """The device rejected a BluFi request or never answered it."""


@dataclass(frozen=True)
class WifiNetwork:
    """One access point from the device's Wi-Fi scan."""

    ssid: str
    rssi: int


@dataclass(frozen=True)
class BlufiWifiStatus:
    """A BluFi Wi-Fi status report."""

    op_mode: int
    sta_status: StaConnectionStatus
    softap_connections: int
    sta_ssid: str | None = None
    sta_bssid: str | None = None

    def connected_to(self, ssid: str) -> bool:
        """Return whether the station has an IP on *ssid* (or on an unnamed network if the report omits it)."""
        return self.sta_status is StaConnectionStatus.CONNECTED and self.sta_ssid in (None, ssid)


def parse_wifi_status(data: bytes) -> BlufiWifiStatus:
    """Parse a WIFI_CONNECTION_STATE payload: op mode, station status, softAP count, then tag/length/value fields."""
    if len(data) < 3:
        raise BlufiError(f"Wi-Fi status too short: {data.hex()}")
    fields: dict[int, bytes] = {}
    offset = 3
    while offset + 2 <= len(data):
        tag, length = data[offset], data[offset + 1]
        value = data[offset + 2 : offset + 2 + length]
        if len(value) != length:
            break
        fields[tag] = value
        offset += 2 + length
    ssid = fields.get(BlufiData.STA_WIFI_SSID)
    bssid = fields.get(BlufiData.STA_WIFI_BSSID)
    return BlufiWifiStatus(
        op_mode=data[0],
        sta_status=StaConnectionStatus(data[1]),
        softap_connections=data[2],
        sta_ssid=ssid.decode(errors="replace") if ssid is not None else None,
        sta_bssid=bssid.hex(":") if bssid is not None else None,
    )


def parse_wifi_list(data: bytes) -> list[WifiNetwork]:
    """Parse a WIFI_LIST payload: repeated ``[1 + len(ssid)][rssi][ssid]`` entries."""
    networks: list[WifiNetwork] = []
    offset = 0
    while offset < len(data) and (length := data[offset]) >= 1:
        entry = data[offset + 1 : offset + 1 + length]
        if len(entry) != length:
            break
        networks.append(
            WifiNetwork(ssid=entry[1:].decode(errors="replace"), rssi=int.from_bytes(entry[:1], signed=True))
        )
        offset += 1 + length
    return networks


class BlufiWifiProvisioner:
    """Provision a mower's Wi-Fi station over an already-connected BLE link.

    Use as an async context manager so the notify subscription is released. Owns the link's BluFi
    sequence numbers, so do not run another BluFi user (such as ``BLETransport``) on the same client.
    """

    def __init__(self, client: BleakClient, *, response_timeout: float = 10.0) -> None:
        self._client = client
        self._response_timeout = response_timeout
        self._message = BleMessage(client)
        self._message.max_data_len = FRAME_LEN - FRAME_HEADER_LEN
        self._frames: asyncio.Queue[tuple[int, int, bytes]] = asyncio.Queue()

    async def __aenter__(self) -> Self:
        """Subscribe to the BluFi notify characteristic."""
        await self._client.start_notify(UUID_NOTIFICATION_CHARACTERISTIC, self._on_notify)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the notify subscription."""
        if self._client.is_connected:
            await self._client.stop_notify(UUID_NOTIFICATION_CHARACTERISTIC)

    def _on_notify(self, _sender: BleakGATTCharacteristic | int, data: bytearray) -> None:
        if self._message.parseNotification(bytes(data)) != 0:
            return
        notification = self._message.notification
        self._frames.put_nowait((notification.getPkgType(), notification.getSubType(), notification.getDataArray()))
        self._message.clear_notification()

    async def _expect(self, subtype: BlufiData, timeout: float | None = None) -> bytes:
        """Return the next data frame of *subtype*; raises TimeoutError if none arrives."""
        async with asyncio.timeout(timeout if timeout is not None else self._response_timeout):
            while True:
                package, frame_subtype, data = await self._frames.get()
                if package == PACKAGE_DATA and frame_subtype == BlufiData.ERROR:
                    raise BlufiError(f"device reported BluFi error {data[0] if data else 255}")
                if package == PACKAGE_DATA and frame_subtype == subtype:
                    return data
                _LOGGER.debug("Ignoring BluFi frame package=%s subtype=%s", package, frame_subtype)

    async def _send(self, package: int, subtype: int, data: bytes | None = None) -> None:
        await self._message.post(False, False, False, self._message.getTypeValue(package, subtype), data)

    async def get_version(self) -> tuple[int, int]:
        """Return the device's BluFi protocol version as (major, minor)."""
        await self._send(PACKAGE_CTRL, BlufiCtrl.GET_VERSION)
        data = await self._expect(BlufiData.VERSION)
        if len(data) != 2:
            raise BlufiError(f"malformed BluFi version: {data.hex()}")
        return data[0], data[1]

    async def scan(self, timeout: float = 20.0) -> list[WifiNetwork]:
        """Ask the device to scan and return the access points it can see."""
        await self._send(PACKAGE_CTRL, BlufiCtrl.GET_WIFI_LIST)
        return parse_wifi_list(await self._expect(BlufiData.WIFI_LIST, timeout))

    async def connect_station(self, ssid: str, password: str, timeout: float = 30.0) -> BlufiWifiStatus | None:
        """Send station credentials and connect, the way the app's configure step does.

        Returns the first status report on *ssid*, else the last report the device pushed, or None when it
        pushed none before *timeout*. Reports about the network being left are skipped, not returned early.
        """
        await self._send(PACKAGE_CTRL, BlufiCtrl.SET_OP_MODE, bytes([WifiOpMode.STA]))
        await self._send(PACKAGE_DATA, BlufiData.STA_WIFI_SSID, ssid.encode())
        await asyncio.sleep(FRAME_GAP_S)
        await self._send(PACKAGE_DATA, BlufiData.STA_WIFI_PASSWORD, password.encode())
        await asyncio.sleep(FRAME_GAP_S)
        await self._send(PACKAGE_CTRL, BlufiCtrl.CONNECT_WIFI)

        last: BlufiWifiStatus | None = None
        try:
            async with asyncio.timeout(timeout):
                while True:
                    last = parse_wifi_status(await self._expect(BlufiData.WIFI_CONNECTION_STATE, timeout))
                    if last.connected_to(ssid):
                        return last
                    _LOGGER.debug("BluFi Wi-Fi status: %s", last)
        except TimeoutError:
            return last
