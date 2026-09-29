"""The work-report page models: one record per job, newest first.

The server fills these per firmware and per job type, so a field may be absent,
``null`` or a type the app's Gson would coerce; none of that may fail the parse.
"""

from __future__ import annotations

import pytest

from pymammotion.http.model.work_report import WorkReportPage, WorkReportRecord, WorkReportResult, WorkReportType
from tests.unit.http._helpers import make_work_report_wire


def test_a_record_reads_the_wire_names() -> None:
    record = WorkReportRecord.from_dict(make_work_report_wire())

    assert record.work_id == "1727600000123"
    assert record.work_type == WorkReportType.SINGLE
    assert record.work_result == WorkReportResult.INTERRUPTED
    assert record.continue_work is True, "the bean's int 0/1 is the server's can-resume flag"
    assert (record.work_area_res, record.work_time_res) == (120.5, 1800)


def test_a_record_with_nulls_and_missing_fields_takes_the_defaults() -> None:
    """Gson leaves a null field at its Java default; mashumaro would otherwise reject ``None`` for an int."""
    record = WorkReportRecord.from_dict(
        {"workId": None, "workType": None, "continueWork": None, "workAreaRes": None, "workTimeRes": None}
    )

    assert record.work_id == ""
    assert record.continue_work is False
    assert (record.work_type, record.work_result) == (0, 0)
    assert (record.work_area_res, record.work_time_res) == (0.0, 0)


def test_a_record_ignores_fields_it_does_not_model() -> None:
    record = WorkReportRecord.from_dict(make_work_report_wire(someNewField={"x": 1}, originWorkId="42"))

    assert record.origin_work_id == "42"


def test_origin_work_id_defaults_to_the_beans_zero_when_absent_or_null() -> None:
    """``RecordsDTO`` initialises ``originWorkId = "0"``, and Gson keeps that default for a null."""
    absent = make_work_report_wire()
    absent.pop("originWorkId", None)

    assert WorkReportRecord.from_dict(absent).origin_work_id == "0"
    assert WorkReportRecord.from_dict(make_work_report_wire(originWorkId=None)).origin_work_id == "0"


def test_a_numeric_work_id_is_read_as_a_string() -> None:
    """Gson coerces a JSON number into the bean's String field, so the server may send either."""
    assert WorkReportRecord.from_dict(make_work_report_wire(workId=1727600000123)).work_id == "1727600000123"


def test_an_unknown_work_type_still_parses() -> None:
    assert WorkReportRecord.from_dict(make_work_report_wire(workType=9)).work_type == 9


@pytest.mark.parametrize(
    ("continue_work", "work_type", "expected"),
    [
        (1, 1, True),
        (1, 2, True),
        (1, 4, True),
        (1, 3, False),
        (0, 1, False),
    ],
    ids=["single", "plan", "resumed", "dropmow-never", "server-says-no"],
)
def test_can_resume_follows_the_app_button_rule(continue_work: int, work_type: int, expected: bool) -> None:
    """Literal wire ints (1 single, 2 plan, 3 DropMow, 4 resume), so renumbering the enum cannot hide a change."""
    record = WorkReportRecord.from_dict(make_work_report_wire(continueWork=continue_work, workType=work_type))

    assert record.can_resume is expected


def test_the_report_enums_carry_the_apps_numbers() -> None:
    """Values as the app's React Native report screen defines them (2.3.18.21 bundle, near byte 1320948)."""
    assert [m.value for m in WorkReportType] == [1, 2, 3, 4]
    assert [m.value for m in WorkReportResult] == [0, 1, 2, 3, 4, 5]


def test_resume_work_id_parses_the_string_the_way_the_app_does() -> None:
    assert WorkReportRecord.from_dict(make_work_report_wire(workId="1727600000123")).resume_work_id == 1727600000123


def test_resume_work_id_is_zero_for_an_empty_work_id() -> None:
    """Both app paths send 0 when ``workId`` is empty rather than skip the command."""
    assert WorkReportRecord.from_dict(make_work_report_wire(workId="")).resume_work_id == 0


def test_a_page_reads_records_and_counters() -> None:
    records = [make_work_report_wire(), make_work_report_wire(workId="1")]
    page = WorkReportPage.from_dict({"records": records, "total": 7, "size": 2, "current": 1, "pages": 4})

    assert [r.work_id for r in page.records] == ["1727600000123", "1"]
    assert (page.total, page.pages) == (7, 4)


def test_a_page_with_null_records_is_empty() -> None:
    assert WorkReportPage.from_dict({"records": None, "total": None}).records == []
