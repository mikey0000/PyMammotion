"""The per-model work-setting schema, and the round trip a host depends on.

A host persists this and reads it back, so ``from_dict(to_dict(x))`` has to
return what went in.  It did not: the model writes field names and reads
aliases, and the mismatch produced an empty list rather than an error.
"""

from __future__ import annotations

from pymammotion.http.model.product_params import ProductParam, ProductParamData

# One row as the endpoint actually sends it.
_WIRE = {
    "detailVos": [
        {"code": "3", "name": "刀盘高度", "isShow": 1, "uiType": "cutHeighSlider",
         "min": "25", "max": "70", "step": "1", "dataType": 1},
        {"code": "15", "name": "骑边距离", "isShow": 0, "uiType": "sliderStepPage",
         "defaultValue": "0", "dataType": 2},
        {"code": "12", "name": "绕障策略", "isShow": 1, "range": ["1", "10", "11", "12"]},
    ],
    "productKey": "uY54W5rM8YH",
    "intMod": "113",
    "version": "2.3.30.39",
}


def test_it_reads_the_wire_format() -> None:
    """The endpoint's own key names, which is what a fetch hands us."""
    data = ProductParamData.from_dict(_WIRE)

    assert data.product_key == "uY54W5rM8YH"
    assert data.int_mod == "113"
    assert set(data.by_code()) == {"3", "12", "15"}


def test_bounds_come_through() -> None:
    """These are what the integration otherwise hard-codes."""
    blade = ProductParamData.from_dict(_WIRE).by_code()["3"]

    assert (blade.min, blade.max, blade.step) == ("25", "70", "1")
    assert blade.shown is True


def test_a_hidden_row_is_reported_hidden() -> None:
    """Ride-boundary distance is isShow 0 on every model served today."""
    assert ProductParamData.from_dict(_WIRE).by_code()["15"].shown is False


def test_an_enumerated_row_keeps_its_range() -> None:
    """The bypass strategies the hardware accepts, including one we do not model."""
    assert ProductParamData.from_dict(_WIRE).by_code()["12"].range == ["1", "10", "11", "12"]


def test_it_round_trips_through_to_dict() -> None:
    """A host stores this; reading it back must not silently yield nothing."""
    original = ProductParamData.from_dict(_WIRE)

    restored = ProductParamData.from_dict(original.to_dict())

    assert set(restored.by_code()) == {"3", "12", "15"}
    assert restored.by_code()["3"].min == "25"
    assert restored.by_code()["15"].shown is False
    assert restored.product_key == "uY54W5rM8YH"


def test_an_unknown_key_does_not_break_it() -> None:
    """The schema gains fields between app releases."""
    data = ProductParamData.from_dict({**_WIRE, "somethingNew": 1, "detailVos": [{"code": "3", "brandNew": "x"}]})

    assert set(data.by_code()) == {"3"}


def test_the_summary_is_flat_and_sorted() -> None:
    """What the dump script writes out for diffing between runs."""
    summary = ProductParamData.from_dict(_WIRE).to_summary()

    assert list(summary) == ["3", "12", "15"]
    assert summary["3"]["min"] == "25"
    assert summary["15"]["shown"] is False


def test_an_empty_answer_is_still_valid() -> None:
    """Nine of one product key's models return no rows at all."""
    data = ProductParamData.from_dict({"productKey": "k", "detailVos": []})

    assert data.detail_vos == []
    assert data.by_code() == {}


def test_a_row_defaults_to_hidden() -> None:
    """Absent isShow must not read as shown."""
    assert ProductParam(code="99").shown is False
