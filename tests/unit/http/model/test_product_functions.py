"""The function set ``product-version-function/list`` publishes for one product key and firmware.

The app decodes every field as a nullable string (``Functions`` in
``config/functions/data/remote/model``), so the model has to survive nulls,
numeric ids and keys it has never seen rather than lose the whole list.
"""

from __future__ import annotations

from pymammotion.http.model.product_functions import ProductFunctionsData

_WIRE = {
    "productKey": "a1BmXWlsdbA",
    "productVersion": "1.12.3.10",
    "functions": [
        {"id": "11", "parentId": "1", "functionName": "Remote drive", "functionCode": "002.002", "remark": None},
        {"id": "12", "parentId": "1", "functionName": "Video encryption", "functionCode": "001.006.001"},
        {"id": "13", "parentId": None, "functionName": "no code yet", "functionCode": None},
    ],
}


def test_the_camelcase_wire_keys_map_to_snake_case_fields() -> None:
    data = ProductFunctionsData.from_dict(_WIRE)

    assert data.product_key == "a1BmXWlsdbA"
    assert data.product_version == "1.12.3.10"
    assert data.functions[0].function_name == "Remote drive"
    assert data.functions[0].parent_id == "1"


def test_codes_skips_rows_without_a_code() -> None:
    """The app compares ``functionCode`` for equality, so a null code can never match anything."""
    assert ProductFunctionsData.from_dict(_WIRE).codes() == ["002.002", "001.006.001"]


def test_a_numeric_id_and_unknown_keys_do_not_break_it() -> None:
    wire = {**_WIRE, "brandNew": 1, "functions": [{"id": 7, "functionCode": "003.001", "sortNo": 3}]}

    assert ProductFunctionsData.from_dict(wire).codes() == ["003.001"]


def test_a_null_function_list_reads_as_empty() -> None:
    """``functions`` is nullable in the app model; a firmware with no rows publishes none."""
    assert ProductFunctionsData.from_dict({"productKey": "pk", "functions": None}).codes() == []
