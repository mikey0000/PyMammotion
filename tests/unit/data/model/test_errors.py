"""DeviceErrors: the padded code list the device sends, and resolving it to text."""

from __future__ import annotations

from dataclasses import fields

from pymammotion.data.error_codes import set_fetched_error_codes
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
    """The table is installed once for the process, not carried by each device."""
    fetched = {"1201": ErrorInfo(**{field.name: "from the account" for field in fields(ErrorInfo)})}
    set_fetched_error_codes(fetched)
    try:
        assert DeviceErrors(err_code_list=[-1201]).describe(-1201) == "from the account"
    finally:
        set_fetched_error_codes(None)


def test_every_device_sees_one_installed_table() -> None:
    """The point of the move: one copy serves every device on the account."""
    fetched = {"1201": ErrorInfo(**{field.name: "shared" for field in fields(ErrorInfo)})}
    set_fetched_error_codes(fetched)
    try:
        assert DeviceErrors(err_code_list=[-1201]).describe(-1201) == "shared"
        assert DeviceErrors(err_code_list=[-1201, -1005]).describe(-1201) == "shared"
    finally:
        set_fetched_error_codes(None)


def test_clearing_the_table_falls_back_to_the_bundle() -> None:
    """An account that signs out must not leave its table resolving codes."""
    set_fetched_error_codes({"1201": ErrorInfo(**{f.name: "gone" for f in fields(ErrorInfo)})})
    set_fetched_error_codes(None)
    assert DeviceErrors(err_code_list=[-1201]).describe(-1201) == "The robot is stuck"


def test_the_table_is_not_serialised_per_device() -> None:
    """It used to be a field, so every device persisted ~470 rows of it."""
    set_fetched_error_codes({"1201": ErrorInfo(**{f.name: "big" for f in fields(ErrorInfo)})})
    try:
        dumped = DeviceErrors(err_code_list=[-1201]).to_dict()
    finally:
        set_fetched_error_codes(None)
    assert set(dumped) == {"err_code_list", "err_code_list_time"}
    assert "big" not in str(dumped)


def test_an_unknown_code_still_renders() -> None:
    errors = DeviceErrors(err_code_list=[5004])
    assert errors.describe(5004) == "Unknown error 5004"
    assert errors.info(5004) is None


def test_it_round_trips_through_json() -> None:
    """HA persists this model, so the new members must not break serialisation.

    The code table is no longer among them, so what persists is just the two
    reported lists.
    """
    errors = DeviceErrors(err_code_list=[-1005], err_code_list_time=[123])

    restored = DeviceErrors.from_dict(errors.to_dict())

    assert restored.err_code_list == [-1005]
    assert restored.err_code_list_time == [123]


def test_a_cache_holding_the_old_table_still_loads() -> None:
    """Stores written before the move carry the field; it must be ignored, not fatal."""
    restored = DeviceErrors.from_dict(
        {"err_code_list": [-1005], "err_code_list_time": [1], "error_codes": {"1201": {"code": "1201"}}}
    )

    assert restored.err_code_list == [-1005]
    assert not hasattr(restored, "error_codes")


def test_a_cache_written_before_error_codes_existed_still_loads() -> None:
    """HA has stored blobs without the field; they must not fail to deserialise."""
    restored = DeviceErrors.from_dict({"err_code_list": [-1005], "err_code_list_time": [123]})

    assert restored.describe(-1005), "the bundle still answers when the cache had no table"
