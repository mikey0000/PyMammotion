"""Builders shared by the ``pymammotion.http`` unit tests."""

from __future__ import annotations


def make_work_report_wire(**overrides: object) -> dict:
    """One work-report record as ``device-server/v1/device/work-report/page`` sends it (``RecordsDTO``)."""
    wire: dict = {
        "id": "rep-1",
        "deviceName": "Luba-VSLKJX",
        "workId": "1727600000123",
        "workType": 1,
        "workResult": 4,
        "continueWork": 1,
        "workAreaRes": 120.5,
        "workTimeRes": 1800,
        "workArea": 300.0,
        "workTimeUsed": 2400,
        "startWorkTime": 1727600000,
    }
    wire.update(overrides)
    return wire


def make_work_report_page_body(*records: dict) -> dict:
    """A successful work-report page envelope carrying *records*."""
    return {"code": 0, "msg": "success", "data": {"records": list(records), "total": len(records), "current": 1}}
