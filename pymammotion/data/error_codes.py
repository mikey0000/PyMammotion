"""The bundled error-code table and the lookup the device's codes need.

Why bundle at all: a mower reports a bare integer, and turning that into text used
to require an authenticated round trip, so a host that had not fetched (or could
not fetch) the table showed the user a number.  The table changes rarely — the two
APK builds we have ship byte-identical copies — so it travels with the library and
the network becomes an optional refresh rather than a prerequisite.

Provenance (see ``scripts/build_error_codes.py``): the account endpoint's
``code/record/export-data`` CSV, verbatim.  Two other candidate sources were checked
against it and neither adds a code:

* the APK's ``assets/servicecode.csv`` — 368 codes, 14 language columns, both strict
  subsets, and it fills no cell the export leaves empty (both APK builds we have
  ship byte-identical copies);
* the app's own paged ``code/page-lan`` endpoint — run against a live account on
  2026-09-09 it returned **exactly this same set of 469 codes**.  It is still the
  richer *record* source (display hints, product keys, nested translations — see
  ``MammotionHTTP.get_all_error_codes_paged``), but not a richer code list.

So this table is complete with respect to what the cloud publishes.  Codes a device
reports that are absent here are firmware-side and documented nowhere upstream:
``5004`` (an undocumented sibling of ``5001``, the only other 4-digit 5xxx code, a
LoRa fault) and ``11133`` have both been seen from a Yuka and appear in neither
endpoint nor the APK.

The device reports a fault as a **negative** code (``-1005``) while the table keys
it positively (``1005``), which is why :func:`get_error_info` normalises through
``abs()`` — without that, every live fault misses.
"""

from __future__ import annotations

import csv
from dataclasses import fields
from functools import lru_cache
from importlib import resources
import logging
from typing import TYPE_CHECKING

from pymammotion.http.model.http import ErrorInfo

if TYPE_CHECKING:
    from collections.abc import Mapping

_LOGGER = logging.getLogger(__name__)

#: Languages the table carries, derived from the model so the two cannot drift.
#: Coverage varies by code and language — ``en`` and ``zh`` are complete, the rest
#: are not, which is what the fallback in :func:`describe` is for.
LANGUAGES = tuple(
    field.name.removesuffix("_implication") for field in fields(ErrorInfo) if field.name.endswith("_implication")
)

_DATA_FILE = "error_codes.csv"


@lru_cache(maxsize=1)
def bundled_error_codes() -> Mapping[str, ErrorInfo]:
    """Every bundled code, keyed by its positive string form.

    Parsed once on first use and cached; the file is ~470 rows, so this costs a few
    milliseconds and only for callers that actually resolve a code.
    """
    known = {field.name for field in fields(ErrorInfo)}
    text = resources.files("pymammotion.data").joinpath(_DATA_FILE).read_text(encoding="utf-8")
    table: dict[str, ErrorInfo] = {}
    for row in csv.DictReader(text.splitlines()):
        # Tolerate a column the model has not caught up with rather than failing the
        # whole load; a missing one is a real mismatch and should raise.
        table[row["code"]] = ErrorInfo(**{key: value for key, value in row.items() if key in known})
    return table


def normalise_code(code: int | str) -> str:
    """Return the table key for a code as the device reports it.

    Faults arrive negative and the table is keyed positive, so the sign is dropped.
    """
    try:
        return str(abs(int(code)))
    except (TypeError, ValueError):
        return str(code).strip().lstrip("-")


def get_error_info(code: int | str, *, extra: Mapping[str, ErrorInfo] | None = None) -> ErrorInfo | None:
    """Look up one code, or ``None`` when neither source knows it.

    *extra* is consulted first, so a host that fetched a fresher table (via
    ``MammotionHTTP.get_all_error_codes``) keeps that precedence over the bundle
    without having to merge the two itself.
    """
    key = normalise_code(code)
    if extra and (found := extra.get(key)):
        return found
    return bundled_error_codes().get(key)


def describe(code: int | str, language: str = "en", *, extra: Mapping[str, ErrorInfo] | None = None) -> str:
    """Human-readable text for a code, falling back through language then code.

    Returns the requested language's implication, else English (the only complete
    non-Chinese column), else a bare ``"Unknown error <code>"`` — a caller
    rendering an error should never be handed an empty string.
    """
    info = get_error_info(code, extra=extra)
    if info is None:
        return f"Unknown error {code}"
    for candidate in (language.lower(), "en"):
        if candidate in LANGUAGES and (text := getattr(info, f"{candidate}_implication", "").strip()):
            return text
    return info.description.strip() or f"Unknown error {code}"


def solution(code: int | str, language: str = "en", *, extra: Mapping[str, ErrorInfo] | None = None) -> str:
    """Remedy text for a code, or an empty string — most codes carry no solution."""
    info = get_error_info(code, extra=extra)
    if info is None:
        return ""
    for candidate in (language.lower(), "en"):
        if candidate in LANGUAGES and (text := getattr(info, f"{candidate}_solution", "").strip()):
            return text
    return ""
