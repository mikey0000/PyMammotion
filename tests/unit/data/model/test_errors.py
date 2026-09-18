"""DeviceErrors: the padded code list the device sends, and resolving it to text."""

from __future__ import annotations

from dataclasses import fields

from pymammotion.data.model.errors import DeviceErrors
from pymammotion.http.model.http import ErrorInfo


def test_active_codes_drops_the_padding() -> None:
    """The device always sends ten slots; the unused ones are 0, which means "success"."""
    errors = DeviceErrors(err_code_list=[-1005, 0, -2701, 0, 0, 0, 0, 0, 0, 0])
    assert errors.active_codes == [-1005, -2701]


def test_active_codes_is_empty_when_nothing_is_wrong() -> None:
    assert DeviceErrors(err_code_list=[0] * 10).active_codes == []


def test_a_reported_code_resolves_against_the_bundled_table() -> None:
    """No fetched table and no network — the whole reason the table is bundled."""
    errors = DeviceErrors(err_code_list=[-1201])
    assert errors.describe(-1201) == "The robot is stuck"
    assert errors.solution(-1201)
    assert (info := errors.info(-1201)) is not None and info.code == "1201"


def test_a_fetched_table_wins_over_the_bundle() -> None:
    fetched = {"1201": ErrorInfo(**{field.name: "from the account" for field in fields(ErrorInfo)})}
    errors = DeviceErrors(err_code_list=[-1201], error_codes=fetched)
    assert errors.describe(-1201) == "from the account"


def test_an_unknown_code_still_renders() -> None:
    errors = DeviceErrors(err_code_list=[5004])
    assert errors.describe(5004) == "Unknown error 5004"
    assert errors.info(5004) is None


def test_it_round_trips_through_json() -> None:
    """HA persists this model, so the new members must not break serialisation.

    Every field, including a populated ``error_codes`` — nested dataclasses through
    mashumaro are the part most likely to break, and the part a host actually stores.
    """
    fetched = {"1201": ErrorInfo(**{field.name: "stored" for field in fields(ErrorInfo)})}
    errors = DeviceErrors(err_code_list=[-1005], err_code_list_time=[123], error_codes=fetched)

    restored = DeviceErrors.from_dict(errors.to_dict())

    assert restored.err_code_list == [-1005]
    assert restored.err_code_list_time == [123]
    assert restored.error_codes["1201"].en_implication == "stored"
    assert restored.describe(-1201) == "stored", "a restored table must still resolve"


def test_a_cache_written_before_error_codes_existed_still_loads() -> None:
    """HA has stored blobs without the field; they must not fail to deserialise."""
    restored = DeviceErrors.from_dict({"err_code_list": [-1005], "err_code_list_time": [123]})

    assert restored.error_codes == {}
    assert restored.describe(-1005), "the bundle still answers when the cache had no table"
