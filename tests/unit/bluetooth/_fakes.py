"""Hand-written BLE fakes for the bluetooth package: a BluFi device and a GATT client wired to it."""

from __future__ import annotations

from collections.abc import Callable

from pymammotion.bluetooth.ble_message import BleMessage
from pymammotion.bluetooth.blufi_wifi import (
    FRAME_LEN,
    PACKAGE_CTRL,
    PACKAGE_DATA,
    BlufiCtrl,
    BlufiData,
    StaConnectionStatus,
    WifiOpMode,
)

NotifyCallback = Callable[[object, bytearray], None]

BLUFI_VERSION = (1, 2)


class FakeBlufiDevice:
    """The device side of plain BluFi Wi-Fi provisioning, built on the library's own frame parser.

    ``connect_reports`` are the station states pushed, in order, about the new network after CONNECT_WIFI
    (empty for firmware that pushes none). ``stale_report_first`` first pushes the old network as still
    connected. ``error_on`` answers that control subtype with an ERROR frame. Like mower firmware 6.0.0, it
    never answers GET_WIFI_STATUS.
    """

    def __init__(
        self,
        *,
        current_ssid: str,
        networks: list[tuple[str, int]],
        connect_reports: list[StaConnectionStatus],
        stale_report_first: bool = False,
        error_on: BlufiCtrl | None = None,
    ) -> None:
        self.framing = BleMessage(None)  # type: ignore[arg-type]
        self.networks = networks
        self.connect_reports = connect_reports
        self.stale_report_first = stale_report_first
        self.error_on = error_on
        self.sta_ssid = current_ssid
        self.op_mode = WifiOpMode.STA
        self.received_ssid: str | None = None
        self.received_password: str | None = None
        self.connect_requested = False

    def receive(self, frame: bytes) -> list[bytes]:
        """Consume one written frame and return the frames the device notifies back."""
        if self.framing.parseNotification(frame) != 0:
            return []
        notification = self.framing.notification
        package, subtype, data = notification.getPkgType(), notification.getSubType(), notification.getDataArray()
        self.framing.clear_notification()
        if package == PACKAGE_CTRL and subtype == self.error_on:
            return [self._frame(BlufiData.ERROR, bytes([3]))]
        if package == PACKAGE_DATA:
            if subtype == BlufiData.STA_WIFI_SSID:
                self.received_ssid = data.decode()
            elif subtype == BlufiData.STA_WIFI_PASSWORD:
                self.received_password = data.decode()
            return []
        return self._on_ctrl(subtype, data)

    def _on_ctrl(self, subtype: int, data: bytes) -> list[bytes]:
        if subtype == BlufiCtrl.GET_VERSION:
            return [self._frame(BlufiData.VERSION, bytes(BLUFI_VERSION))]
        if subtype == BlufiCtrl.SET_OP_MODE:
            self.op_mode = WifiOpMode(data[0])
        elif subtype == BlufiCtrl.GET_WIFI_LIST:
            entries = b"".join(bytes([len(ssid) + 1, rssi & 0xFF]) + ssid.encode() for ssid, rssi in self.networks)
            return [self._frame(BlufiData.WIFI_LIST, entries)]
        elif subtype == BlufiCtrl.CONNECT_WIFI:
            self.connect_requested = True
            frames = [self._status_frame(StaConnectionStatus.CONNECTED)] if self.stale_report_first else []
            self.sta_ssid = self.received_ssid or self.sta_ssid
            frames += [self._status_frame(report) for report in self.connect_reports]
            return frames
        return []

    def _status_frame(self, status: StaConnectionStatus) -> bytes:
        ssid = self.sta_ssid.encode()
        payload = bytes([self.op_mode, status, 0, BlufiData.STA_WIFI_SSID, len(ssid)]) + ssid
        return self._frame(BlufiData.WIFI_CONNECTION_STATE, payload)

    def _frame(self, subtype: BlufiData, data: bytes) -> bytes:
        sequence = self.framing.generate_send_sequence()
        return self.framing.getPostBytes(
            self.framing.getTypeValue(PACKAGE_DATA, subtype), False, False, False, False, sequence, data
        )


class FakeBlufiBleClient:
    """GATT client wired to a FakeBlufiDevice: writes reach the device, its replies arrive as notifications.

    Rejects any write longer than the app's BluFi frame, as a link without a negotiated MTU would.
    """

    def __init__(self, device: FakeBlufiDevice) -> None:
        self.device = device
        self.writes: list[bytes] = []
        self.is_connected = True
        self._notify: NotifyCallback | None = None

    async def start_notify(self, _uuid: str, callback: NotifyCallback) -> None:
        self._notify = callback

    async def stop_notify(self, _uuid: str) -> None:
        if not self.is_connected:
            raise RuntimeError("stop_notify on a disconnected client")  # as bleak does
        self._notify = None

    async def write_gatt_char(self, uuid: str, data: bytes, _response: bool = True) -> None:
        assert len(data) <= FRAME_LEN, f"{len(data)}-byte write exceeds the {FRAME_LEN}-byte BluFi frame"
        assert self._notify is not None, "write before start_notify"
        self.writes.append(bytes(data))
        for reply in self.device.receive(bytes(data)):
            self._notify(uuid, bytearray(reply))
