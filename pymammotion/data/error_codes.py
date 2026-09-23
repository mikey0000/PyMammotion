"""The bundled error-code table and the lookup the device's codes need.

Why bundle at all: a mower reports a bare integer, and turning that into text used
to require an authenticated round trip, so a host that had not fetched (or could
not fetch) the table showed the user a number.  The table changes rarely — the two
APK builds we have ship byte-identical copies — so it travels with the library and
the network becomes an optional refresh rather than a prerequisite.

Provenance (see ``scripts/build_error_codes.py``): the account endpoint's
``code/record/export-data`` CSV, plus every code the app's ``code/page-lan``
endpoint adds.  The two sources overlap only partly — on 2026-09-10 ``page-lan``
returned 176 codes the export lacks (English only), and the export 221 that
``page-lan`` does not.  The export wins where both have a code, because it carries
every language.  The APK's ``assets/servicecode.csv`` adds nothing to either.

An account's export is not complete either: on some accounts it lists every code
but fills text for fewer than half, so :func:`set_fetched_error_codes` overlays a
fetched row on the bundled one instead of replacing it.

Codes a device reports that appear in no source are firmware-side and documented
nowhere upstream: ``5004``, ``11133`` and ``11134`` have all been seen from mowers.

The device reports a fault as a **negative** code (``-1005``) while the table keys
it positively (``1005``), which is why :func:`get_error_info` normalises through
``abs()`` — without that, every live fault misses.
"""

from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass, fields, replace
from functools import lru_cache
from importlib import resources
import logging
import time
from typing import TYPE_CHECKING, Any

from mashumaro.exceptions import InvalidFieldValue, MissingField

from pymammotion.http.model.http import ErrorCodeRecord, ErrorInfo
from pymammotion.transport.base import is_transient_network_error

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pymammotion.http.http import MammotionHTTP

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


#: A table fetched from an account, shared by every device in the process.  The
#: table is the same ~470 rows for every device on an account, so one copy is
#: kept here rather than one per device: held per device it was serialised into
#: each device's persisted state and into every diagnostics dump, several times
#: over, for data the library already bundles.
_fetched: dict[str, ErrorInfo] = {}


def set_fetched_error_codes(table: Mapping[str, ErrorInfo] | None) -> None:
    """Install the account-fetched table for every lookup in this process.

    Each fetched row is laid over its bundled row, so a cell the account's export
    leaves blank keeps the bundled text.  Passing ``None`` or an empty mapping clears
    it and falls back to the bundle.
    """
    _fetched.clear()
    if table:
        bundle = bundled_error_codes()
        _fetched.update({code: _overlay(bundle.get(code), info) for code, info in table.items()})
    else:
        _refresh.reset()


def _overlay(base: ErrorInfo | None, fresh: ErrorInfo) -> ErrorInfo:
    """Return *base* with every non-blank field of *fresh* written over it."""
    if base is None:
        return fresh
    return replace(base, **{f.name: value for f in fields(ErrorInfo) if (value := getattr(fresh, f.name)).strip()})


def table_from_records(records: Mapping[str, ErrorCodeRecord]) -> dict[str, ErrorInfo]:
    """Return ``code/page-lan`` records as a table :func:`set_fetched_error_codes` accepts."""
    return {code: record.to_error_info() for code, record in records.items()}


def fetched_error_codes() -> Mapping[str, ErrorInfo]:
    """Return the account-fetched table, empty when nothing has been fetched."""
    return _fetched


def normalise_code(code: int | str) -> str:
    """Return the table key for a code as the device reports it.

    Faults arrive negative and the table is keyed positive, so the sign is dropped.
    """
    try:
        return str(abs(int(code)))
    except (TypeError, ValueError):
        return str(code).strip().lstrip("-")


#: Home Assistant language tags whose table column is named differently.
_LANGUAGE_ALIASES = {"nb": "no", "nn": "no"}


def table_language(language: str) -> str:
    """Return the table's column prefix for a BCP 47 tag such as ``en-GB`` or ``zh-Hans``."""
    base = language.lower().replace("_", "-").split("-", 1)[0]
    return _LANGUAGE_ALIASES.get(base, base)


def get_error_info(code: int | str, *, extra: Mapping[str, ErrorInfo] | None = None) -> ErrorInfo | None:
    """Look up one code, or ``None`` when neither source knows it.

    *extra* is consulted first, then the process-wide table a host installed
    with :func:`set_fetched_error_codes`, then the bundle — so a fresher table
    takes precedence without any caller having to merge the two itself.
    """
    key = normalise_code(code)
    if extra and (found := extra.get(key)):
        return found
    if found := _fetched.get(key):
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
    for candidate in (table_language(language), "en"):
        if candidate in LANGUAGES and (text := getattr(info, f"{candidate}_implication", "").strip()):
            return text
    return info.description.strip() or f"Unknown error {code}"


def solution(code: int | str, language: str = "en", *, extra: Mapping[str, ErrorInfo] | None = None) -> str:
    """Remedy text for a code, or an empty string — most codes carry no solution."""
    info = get_error_info(code, extra=extra)
    if info is None:
        return ""
    for candidate in (table_language(language), "en"):
        if candidate in LANGUAGES and (text := getattr(info, f"{candidate}_solution", "").strip()):
            return text
    return ""


@dataclass
class _RefreshState:
    """Per-process progress of :func:`refresh_error_codes`, shared like the table itself."""

    cache_installed: bool = False
    cache_usable: bool = False
    version_checked: bool = False
    retry_after: float = 0.0
    lock: asyncio.Lock | None = None
    loop: asyncio.AbstractEventLoop | None = None

    def reset(self) -> None:
        self.cache_installed = self.cache_usable = self.version_checked = False
        self.retry_after = 0.0

    def lock_for_this_loop(self) -> asyncio.Lock:
        """Return a lock bound to the running loop; a host that restarts its loop gets a new one."""
        loop = asyncio.get_running_loop()
        if self.lock is None or self.loop is not loop:
            self.lock, self.loop = asyncio.Lock(), loop
        return self.lock


_refresh = _RefreshState()

#: After a failed check or fetch, wait this long before asking again, so a server
#: that keeps failing costs one request an hour rather than one per poll.
RETRY_AFTER_FAILURE_SECONDS = 3600.0

#: The retry wait's clock; tests replace it rather than sleeping.
_monotonic = time.monotonic


async def refresh_error_codes(
    http: MammotionHTTP | None, language: str, cached: Mapping[str, Any] | None = None
) -> dict[str, Any] | None:
    """Keep the process-wide table current the way the Mammotion app does.

    *cached* (what an earlier call returned, as the host persisted it) is installed on
    the first call, so codes resolve offline.  Then, once per process, ``code/version``
    is checked and ``code/page-lan`` fetched in *language* only when the version or the
    language differs from *cached*.  Returns the new cache for the host to persist, or
    ``None`` when there is nothing new to save.

    Safe to call on every poll: once the table is confirmed current or fetched whole,
    it returns without touching the network.  A failed check or an incomplete fetch
    keeps the installed table and is retried after ``RETRY_AFTER_FAILURE_SECONDS``;
    authentication errors propagate.
    """
    async with _refresh.lock_for_this_loop():
        if not _refresh.cache_installed:
            _refresh.cache_usable = _install_cache(cached)
            _refresh.cache_installed = True
        if _refresh.version_checked or http is None or _monotonic() < _refresh.retry_after:
            return None
        try:
            fresh = await _fetch_if_stale(
                http, table_language(language), (cached or {}) if _refresh.cache_usable else {}
            )
        except Exception as err:
            if not is_transient_network_error(err):
                raise
            _LOGGER.debug("Error-code table not refreshed: %s", err)
            fresh = None
        if not _refresh.version_checked:
            _refresh.retry_after = _monotonic() + RETRY_AFTER_FAILURE_SECONDS
        return fresh


def _install_cache(cached: Mapping[str, Any] | None) -> bool:
    """Install *cached* and return whether it was readable."""
    if not cached:
        return False
    try:
        set_fetched_error_codes({code: ErrorInfo.from_dict(row) for code, row in cached.get("codes", {}).items()})
    except (InvalidFieldValue, MissingField, TypeError, AttributeError) as err:
        _LOGGER.debug("Ignoring an unreadable error-code cache: %s", err)
        return False
    return True


async def _fetch_if_stale(http: MammotionHTTP, language: str, cached: Mapping[str, Any]) -> dict[str, Any] | None:
    version = await http.get_error_code_version()
    if version.code != 0 or not version.data:
        _LOGGER.debug("Error-code version unavailable: %s %s", version.code, version.msg)
        return None
    if cached.get("version") == version.data and cached.get("language") == language and cached.get("codes"):
        _refresh.version_checked = True
        return None
    if not (records := await http.get_all_error_codes_paged(language=language, require_complete=True)):
        _LOGGER.debug("Error-code table %s incomplete or empty; keeping the installed one", version.data)
        return None
    table = table_from_records(records)
    set_fetched_error_codes(table)
    _refresh.version_checked = True
    _LOGGER.debug("Fetched %d error codes (version %s, %s)", len(table), version.data, language)
    return {
        "version": version.data,
        "language": language,
        "codes": {code: info.to_dict() for code, info in table.items()},
    }
