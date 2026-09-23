"""The bundled error-code table and the lookup the device's reported codes need."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import fields, replace
from typing import Any
from unittest.mock import create_autospec

from aiohttp import ClientConnectionError
import pytest

from pymammotion.data import error_codes
from pymammotion.data.error_codes import (
    LANGUAGES,
    bundled_error_codes,
    describe,
    get_error_info,
    normalise_code,
    refresh_error_codes,
    set_fetched_error_codes,
    solution,
    table_from_records,
    table_language,
)
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import ErrorCodeRecord, ErrorInfo, Response
from pymammotion.transport.base import ReLoginRequiredError


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


@pytest.fixture
def clear_fetched_table() -> Iterator[None]:
    """The fetched table is process-wide; clearing it also resets ``refresh_error_codes``'s progress."""
    yield
    set_fetched_error_codes(None)


def test_the_bundle_carries_codes_only_page_lan_publishes() -> None:
    """2401 is absent from every account export seen so far and present in ``page-lan``."""
    info = get_error_info(-2401)
    assert info is not None, "the page-lan-only codes were not folded into the bundle"
    assert info.en_implication == "LiDAR sensor anomaly"
    assert info.module == "sensor", "page-lan's numeric module 20 was not mapped to a name"


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


@pytest.mark.parametrize(
    ("tag", "column"), [("en-GB", "en"), ("zh-Hans", "zh"), ("pt_BR", "pt"), ("DE", "de"), ("nb", "no")]
)
def test_a_region_tagged_language_maps_to_its_table_column(tag: str, column: str) -> None:
    """Home Assistant hands over BCP 47 tags; the table is keyed by bare language."""
    assert table_language(tag) == column


def test_a_region_tagged_language_is_described_in_that_language() -> None:
    assert describe(-1005, "de-CH") == describe(-1005, "de") != describe(-1005, "en")
    assert solution(-1304, "de-CH") == solution(-1304, "de") != solution(-1304, "en")


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


@pytest.mark.regression
@pytest.mark.usefixtures("clear_fetched_table")
def test_a_fetched_row_with_blank_text_keeps_the_bundled_text() -> None:
    """Some accounts' export lists every code but fills text for fewer than half.

    A fetched row replaced its bundled row wholesale, so installing such an export
    turned 1304 ("Poor positioning status") into a record with no text at all, and
    Home Assistant's notification showed a bare "Code 1304".
    """
    bundled = bundled_error_codes()["1304"]
    blank_text = {name: "" for name in (f.name for f in fields(ErrorInfo)) if name.endswith(("_implication", "_solution"))}
    set_fetched_error_codes({"1304": replace(bundled, **blank_text)})

    info = get_error_info(-1304)

    assert info is not None
    assert info.en_implication == "Poor positioning status"
    assert info.de_solution == bundled.de_solution


@pytest.mark.usefixtures("clear_fetched_table")
def test_a_fetched_row_overrides_the_bundled_text_it_does_carry() -> None:
    bundled = bundled_error_codes()["1304"]
    only_english = {f.name: "" for f in fields(ErrorInfo)} | {"code": "1304", "en_implication": "fetched wording"}
    set_fetched_error_codes({"1304": ErrorInfo(**only_english)})

    info = get_error_info(1304)

    assert info is not None
    assert info.en_implication == "fetched wording"
    assert info.fr_implication == bundled.fr_implication


@pytest.mark.usefixtures("clear_fetched_table")
def test_a_fetched_code_the_bundle_lacks_is_used_as_is() -> None:
    fresh = ErrorInfo(**{field.name: "" for field in fields(ErrorInfo)} | {"code": "11134", "en_implication": "new"})
    set_fetched_error_codes({"11134": fresh})

    assert describe(-11134) == "new"


@pytest.mark.usefixtures("clear_fetched_table")
def test_a_page_lan_table_in_one_language_keeps_the_bundle_for_the_rest() -> None:
    """A table fetched in German fills German and must not erase the bundled English."""
    record = ErrorCodeRecord.from_dict(
        {"code": "1304", "handleList": [{"language": "de", "implication": "Neu", "solution": ""}]}
    )
    set_fetched_error_codes(table_from_records({"1304": record}))

    assert describe(-1304, "de") == "Neu"
    assert describe(-1304, "en") == "Poor positioning status"


def _german_record() -> ErrorCodeRecord:
    return ErrorCodeRecord.from_dict(
        {"code": "1304", "handleList": [{"language": "de", "implication": "Schlechte Ortung", "solution": ""}]}
    )


def _http(version: str = "v2", records: dict[str, ErrorCodeRecord] | None = None) -> Any:
    http = create_autospec(MammotionHTTP, instance=True)
    http.get_error_code_version.return_value = Response(code=0, msg="ok", data=version)
    http.get_all_error_codes_paged.return_value = {"1304": _german_record()} if records is None else records
    return http


def _cache(version: str, language: str, text: str = "Gespeichert") -> dict[str, Any]:
    row = dict.fromkeys((f.name for f in fields(ErrorInfo)), "") | {"code": "1304", "de_implication": text}
    return {"version": version, "language": language, "codes": {"1304": row}}


@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_fetches_a_new_version_in_the_requested_language() -> None:
    http = _http()

    cache = await refresh_error_codes(http, "de-CH")

    http.get_all_error_codes_paged.assert_awaited_once_with(language="de", require_complete=True)
    assert describe(-1304, "de") == "Schlechte Ortung"
    assert cache is not None
    assert (cache["version"], cache["language"]) == ("v2", "de")
    assert cache["codes"]["1304"]["de_implication"] == "Schlechte Ortung"


@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_returns_a_cache_that_round_trips() -> None:
    """What the host persists must reinstall the same table on the next start."""
    cache = await refresh_error_codes(_http(), "de")
    set_fetched_error_codes(None)

    await refresh_error_codes(None, "de", cache)

    assert describe(-1304, "de") == "Schlechte Ortung"


@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_skips_the_table_when_version_and_language_match() -> None:
    http = _http(version="v2")

    assert await refresh_error_codes(http, "de", _cache("v2", "de")) is None

    http.get_all_error_codes_paged.assert_not_awaited()
    assert describe(-1304, "de") == "Gespeichert"


@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_refetches_when_the_cache_has_no_codes() -> None:
    """A matching version is no reason to trust a cache that holds no table."""
    http = _http(version="v2")

    await refresh_error_codes(http, "de", _cache("v2", "de") | {"codes": {}})

    http.get_all_error_codes_paged.assert_awaited_once_with(language="de", require_complete=True)


@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_refetches_when_the_language_changed() -> None:
    """The app refetches on a UI language change even when the version is the same."""
    http = _http(version="v2")

    await refresh_error_codes(http, "de", _cache("v2", "en"))

    http.get_all_error_codes_paged.assert_awaited_once_with(language="de", require_complete=True)


@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_installs_the_cache_without_a_session() -> None:
    """BLE-only and offline hosts still resolve codes from the last fetch."""
    assert await refresh_error_codes(None, "de", _cache("v1", "de")) is None

    assert describe(-1304, "de") == "Gespeichert"


@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_checks_the_version_once_per_process() -> None:
    """Hosts call this on every poll; only the first call may reach the cloud."""
    http = _http()

    await refresh_error_codes(http, "de")
    await refresh_error_codes(http, "de")

    http.get_error_code_version.assert_awaited_once()


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """A settable monotonic clock for the retry wait: append a later time to move it."""
    now = [1000.0]
    monkeypatch.setattr(error_codes, "_monotonic", lambda: now[-1])
    return now


@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_retries_a_failed_version_check_after_the_wait(clock: list[float]) -> None:
    http = _http()
    http.get_error_code_version.side_effect = [Response(code=500, msg="down"), Response(code=0, msg="ok", data="v2")]

    await refresh_error_codes(http, "de")
    await refresh_error_codes(http, "de")
    assert http.get_error_code_version.await_count == 1, "a failing server was asked again before the wait"

    clock.append(clock[-1] + error_codes.RETRY_AFTER_FAILURE_SECONDS)
    await refresh_error_codes(http, "de")

    http.get_all_error_codes_paged.assert_awaited_once()


@pytest.mark.regression
@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_retries_a_fetch_that_failed_after_the_version_check(clock: list[float]) -> None:
    """The version check marked the refresh done before the table fetch ran.

    A page-lan walk that raised a network error, or came back empty, was then never
    retried for the rest of the process, although the docstring promised a retry.
    """
    http = _http()
    http.get_all_error_codes_paged.side_effect = [ClientConnectionError("reset"), {"1304": _german_record()}]

    await refresh_error_codes(http, "de")
    clock.append(clock[-1] + error_codes.RETRY_AFTER_FAILURE_SECONDS)
    cache = await refresh_error_codes(http, "de")

    assert cache is not None, "the failed fetch was never retried"
    assert describe(-1304, "de") == "Schlechte Ortung"


@pytest.mark.regression
@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_does_not_persist_an_incomplete_table() -> None:
    """A walk that lost a page returned the pages it had, and that was saved under the version.

    Every later start then found a matching version and non-empty codes and never
    fetched again, so the codes on the lost pages stayed unknown until Mammotion
    published a new version.
    """
    http = _http()
    http.get_all_error_codes_paged.return_value = {}

    await refresh_error_codes(http, "de")

    # The truncation itself is pinned in test_http_device_server; this pins that refresh asks for it.
    http.get_all_error_codes_paged.assert_awaited_once_with(language="de", require_complete=True)


@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_keeps_the_cache_through_a_network_error() -> None:
    http = _http()
    http.get_error_code_version.side_effect = ClientConnectionError("offline")

    assert await refresh_error_codes(http, "de", _cache("v1", "de")) is None

    assert describe(-1304, "de") == "Gespeichert"


@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_keeps_the_cache_when_the_fetch_comes_back_empty() -> None:
    http = _http(version="v2", records={})

    assert await refresh_error_codes(http, "de", _cache("v1", "de")) is None

    assert describe(-1304, "de") == "Gespeichert"


@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_propagates_a_rejected_login() -> None:
    """The host maps this to re-authentication; swallowing it would hide a dead login."""
    http = _http()
    http.get_error_code_version.side_effect = ReLoginRequiredError("account", "expired")

    with pytest.raises(ReLoginRequiredError):
        await refresh_error_codes(http, "de")


@pytest.mark.usefixtures("clear_fetched_table")
async def test_refresh_ignores_an_unreadable_cache_and_refetches() -> None:
    cache = _cache("v2", "de")
    cache["codes"]["1304"] = {"not": "an error row"}
    http = _http(version="v2")

    await refresh_error_codes(http, "de", cache)

    assert describe(-1304, "de") == "Schlechte Ortung"
