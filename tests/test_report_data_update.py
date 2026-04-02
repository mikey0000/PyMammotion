"""Tests that ReportData.update() only mutates fields present in the proto message."""
from __future__ import annotations

from pymammotion.data.model.report_info import (
    ConnectData,
    DeviceData,
    Maintain,
    RTKData,
    ReportData,
    VisionInfo,
    WorkData,
)
from pymammotion.proto import ReportInfoData, RptConnectStatus, RptDevStatus, RptMaintain, RptRtk, RptWork, VioToAppInfoMsg


def _make_report_data_with_values() -> ReportData:
    rd = ReportData()
    rd.connect = ConnectData(wifi_rssi=-60, iot_con_status=1)
    rd.dev = DeviceData(sys_status=5, battery_val=50)
    rd.rtk = RTKData(status=3, gps_stars=10)
    rd.maintenance = Maintain(mileage=100000, work_time=9999)
    rd.vision_info = VisionInfo(x=1.0, y=2.0)
    rd.work = WorkData(area=1234, progress=5678)
    return rd


def test_partial_update_only_touches_present_fields() -> None:
    """When ReportInfoData contains only dev+rtk, other fields must stay unchanged."""
    rd = _make_report_data_with_values()

    msg = ReportInfoData(
        dev=RptDevStatus(sys_status=13, battery_val=82),
        rtk=RptRtk(status=4, gps_stars=25),
    )

    rd.update(msg)

    # Updated fields
    assert rd.dev.sys_status == 13
    assert rd.dev.battery_val == 82
    assert rd.rtk.status == 4
    assert rd.rtk.gps_stars == 25

    # Unchanged fields — must retain their original values
    assert rd.connect.wifi_rssi == -60
    assert rd.connect.iot_con_status == 1
    assert rd.maintenance.mileage == 100000
    assert rd.maintenance.work_time == 9999
    assert rd.vision_info.x == 1.0
    assert rd.vision_info.y == 2.0
    assert rd.work.area == 1234
    assert rd.work.progress == 5678


def test_connect_only_update() -> None:
    """Only connect present — all other fields stay unchanged."""
    rd = _make_report_data_with_values()

    msg = ReportInfoData(connect=RptConnectStatus(wifi_rssi=-53, iot_con_status=1))
    rd.update(msg)

    assert rd.connect.wifi_rssi == -53
    # dev still has original value
    assert rd.dev.sys_status == 5


def test_work_only_update() -> None:
    """Only work present — all other fields stay unchanged."""
    rd = _make_report_data_with_values()

    msg = ReportInfoData(work=RptWork(area=99999, progress=11111))
    rd.update(msg)

    assert rd.work.area == 99999
    assert rd.work.progress == 11111
    assert rd.dev.sys_status == 5
    assert rd.connect.wifi_rssi == -60


def test_full_update_touches_all_present_fields() -> None:
    """When all sub-messages are present, all fields are updated."""
    rd = _make_report_data_with_values()

    msg = ReportInfoData(
        connect=RptConnectStatus(wifi_rssi=-40),
        dev=RptDevStatus(sys_status=0, battery_val=100),
        rtk=RptRtk(status=2, gps_stars=15),
        maintain=RptMaintain(mileage=500000, work_time=123456),
        vio_to_app_info=VioToAppInfoMsg(x=3.0, y=4.0),
        work=RptWork(area=8888, progress=7777),
    )
    rd.update(msg)

    assert rd.connect.wifi_rssi == -40
    assert rd.dev.sys_status == 0
    assert rd.dev.battery_val == 100
    assert rd.rtk.status == 2
    assert rd.rtk.gps_stars == 15
    assert rd.maintenance.mileage == 500000
    assert rd.maintenance.work_time == 123456
    assert rd.vision_info.x == 3.0
    assert rd.vision_info.y == 4.0
    assert rd.work.area == 8888
    assert rd.work.progress == 7777


def test_empty_message_leaves_everything_unchanged() -> None:
    """An empty ReportInfoData must not modify any existing field."""
    rd = _make_report_data_with_values()

    rd.update(ReportInfoData())

    assert rd.dev.sys_status == 5
    assert rd.dev.battery_val == 50
    assert rd.connect.wifi_rssi == -60
    assert rd.rtk.status == 3
    assert rd.maintenance.mileage == 100000
    assert rd.vision_info.x == 1.0
    assert rd.work.area == 1234
