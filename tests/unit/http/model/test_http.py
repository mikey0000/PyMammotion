"""``/code/page-lan`` records and their conversion to the export-data row shape."""

from __future__ import annotations

from pymammotion.http.model.http import ErrorCodeRecord

# One record as the endpoint sends it, trimmed to the fields the conversion reads.
_WIRE = {
    "code": "2401",
    "description": "雷达变压器异常",
    "level": "1",
    "module": "20",
    "handleList": [
        {"language": "en", "implication": "LiDAR sensor anomaly ", "solution": " Contact support", "buttonName": ""},
        {"language": "DE", "implication": "LiDAR-Sensor-Anomalie", "solution": ""},
        {"language": "xx", "implication": "no such column", "solution": ""},
    ],
}


def test_a_record_becomes_an_export_row_with_one_column_pair_per_language() -> None:
    info = ErrorCodeRecord.from_dict(_WIRE).to_error_info()

    assert (info.code, info.level, info.description) == ("2401", "1", "雷达变压器异常")
    assert (info.en_implication, info.en_solution) == ("LiDAR sensor anomaly", "Contact support")
    assert info.de_implication == "LiDAR-Sensor-Anomalie", "the language tag is case-insensitive"
    assert info.fr_implication == "", "a language the record lacks stays blank"


def test_a_numbered_module_is_given_the_export_name() -> None:
    assert ErrorCodeRecord.from_dict(_WIRE).to_error_info().module == "sensor"


def test_an_unmapped_module_number_is_kept_rather_than_dropped() -> None:
    assert ErrorCodeRecord.from_dict(_WIRE | {"module": "99"}).to_error_info().module == "99"


def test_the_no_text_placeholder_is_read_as_blank() -> None:
    """page-lan sends ``"- -"`` for a code with no solution; merged as text, it filled 38 cells."""
    wire = _WIRE | {"handleList": [{"language": "en", "implication": "Request succeeded", "solution": "- -"}]}

    assert ErrorCodeRecord.from_dict(wire).to_error_info().en_solution == ""
