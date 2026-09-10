"""The bundled error-code table and the lookup the device's reported codes need."""

from __future__ import annotations

from dataclasses import fields

import pytest

from pymammotion.data.error_codes import (
    LANGUAGES,
    bundled_error_codes,
    describe,
    get_error_info,
    normalise_code,
    solution,
)
from pymammotion.http.model.http import ErrorInfo


def test_the_bundled_table_parses_into_the_model() -> None:
    table = bundled_error_codes()
    assert len(table) > 400, f"the shipped table looks truncated: {len(table)} codes"
    assert all(isinstance(info, ErrorInfo) for info in table.values())


def test_every_row_is_keyed_by_its_own_code() -> None:
    """A row keyed by anything but its code makes every lookup silently wrong."""
    mismatched = [key for key, info in bundled_error_codes().items() if key != info.code]
    assert not mismatched, f"rows keyed by something other than their code: {mismatched[:5]}"


def test_languages_are_derived_from_the_model() -> None:
    declared = {field.name.removesuffix("_implication") for field in fields(ErrorInfo) if "_implication" in field.name}
    assert set(LANGUAGES) == declared


def test_english_is_complete() -> None:
    """``describe`` falls back to English, so a gap there leaves a code unreadable."""
    missing = [code for code, info in bundled_error_codes().items() if not info.en_implication.strip()]
    assert not missing, f"codes with no English text: {missing[:5]}"


@pytest.mark.parametrize(("reported", "expected"), [(-1005, "1005"), (1005, "1005"), ("-1005", "1005"), (0, "0")])
def test_a_reported_code_normalises_to_its_table_key(reported: int | str, expected: str) -> None:
    """The device reports faults negative; the table keys them positive."""
    assert normalise_code(reported) == expected


def test_a_negative_reported_code_resolves() -> None:
    """The whole point of the sign handling: -1005 is what a mower actually sends."""
    info = get_error_info(-1005)
    assert info is not None
    assert info.code == "1005"
    assert "battery" in info.en_implication.lower()


def test_an_unknown_code_resolves_to_nothing_rather_than_raising() -> None:
    # 11133 was reported by a real Yuka and is in neither the export nor the APK asset.
    assert get_error_info(-11133) is None
    assert describe(-11133) == "Unknown error -11133"
    assert solution(-11133) == ""


def test_a_fetched_table_takes_precedence_over_the_bundle() -> None:
    """A host that refreshed from the account endpoint must not be overridden by us."""
    fresher = {"1005": ErrorInfo(**{field.name: "fetched" for field in fields(ErrorInfo)})}
    assert describe(-1005, extra=fresher) == "fetched"
    assert describe(-1004, extra=fresher) == "Tilt sensor activated", "an unrelated code still uses the bundle"


def test_a_language_the_table_lacks_falls_back_to_english() -> None:
    """``ja`` is declared by the model but empty in the export, so it must fall back."""
    assert describe(-1005, "ja") == describe(-1005, "en")


def test_a_language_the_table_has_is_used() -> None:
    german = describe(-1005, "de")
    assert german and german != describe(-1005, "en")


def test_describe_is_never_empty() -> None:
    """A caller rendering an error needs something to show for every code."""
    blank = [code for code in bundled_error_codes() if not describe(code).strip()]
    assert not blank, f"codes that describe() renders as empty: {blank[:5]}"


def test_solution_is_empty_when_the_code_has_no_remedy() -> None:
    assert solution(0) == ""


def test_a_code_whose_every_field_is_blank_still_renders() -> None:
    """The last-resort branch: known code, no text in any language and no description.

    Unreachable through the shipped table (English is complete there), so it needs an
    injected entry — otherwise the fallback is dead code nobody would notice breaking.
    """
    blank = {"9999": ErrorInfo(**{field.name: "" for field in fields(ErrorInfo)})}

    assert describe(9999, extra=blank) == "Unknown error 9999"
    assert solution(9999, extra=blank) == ""


def test_a_non_numeric_code_does_not_raise() -> None:
    """``normalise_code`` is handed whatever a caller has; it must not explode on junk."""
    assert normalise_code("not-a-code") == "not-a-code"
    assert get_error_info("not-a-code") is None
