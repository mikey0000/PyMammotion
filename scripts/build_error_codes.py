"""Regenerate ``pymammotion/data/error_codes.csv`` from an account's error-code export.

The source is the ``/user-server/v1/code/record/export-data`` CSV that
``MammotionHTTP.get_all_error_codes`` fetches — 469 codes and 26 languages at the
time of writing, exactly the columns :class:`ErrorInfo` declares.

The app's paged ``code/page-lan`` endpoint was checked against this export on
2026-09-09 and returns the identical 469-code set, so it is not a second source of
codes either — only of richer per-record metadata.

The APK's ``assets/servicecode.csv`` was evaluated as a second source and rejected:
its 368 codes are a strict subset of the export's, its 14 language columns are a
subset of the export's 26, and it fills **zero** cells the export leaves empty.  Pass
``--apk`` anyway to have it diffed against the export — it reports codes the APK has
that the export lacks (none so far) and codes whose text disagrees (8 at the time of
writing, where the APK carries older phrasing and the export carries what the app
renders today).  Keep it as a cross-check, not as an input.

Usage::

    uv run python scripts/build_error_codes.py \
        --export <endpoint.csv | config_entry-mammotion-*.json> \
        [--apk <path to assets/servicecode.csv>]

``--export`` accepts either the raw CSV or a Home Assistant diagnostics JSON, whose
``data.<device>.errors.error_codes`` map is that CSV already parsed.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import fields
import io
import json
import pathlib
import sys

from pymammotion.http.model.http import ErrorInfo

COLUMNS = [field.name for field in fields(ErrorInfo)]
OUTPUT = pathlib.Path(__file__).parents[1] / "pymammotion" / "data" / "error_codes.csv"


def _read_csv(path: pathlib.Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig") as handle:
        return {row["code"]: row for row in csv.DictReader(handle)}


def _read_export(path: pathlib.Path) -> dict[str, dict[str, str]]:
    """Accept a raw CSV export or a HA diagnostics dump containing one."""
    if path.suffix.lower() != ".json":
        return _read_csv(path)
    diagnostics = json.loads(path.read_text())
    for device in diagnostics.get("data", {}).values():
        codes = device.get("errors", {}).get("error_codes") if isinstance(device, dict) else None
        if codes:
            return codes
    raise SystemExit(f"no errors.error_codes found in {path}")


def _sort_key(code: str) -> tuple[int, str]:
    return (int(code), "") if code.lstrip("-").isdigit() else (0, code)


def cross_check(export: dict[str, dict[str, str]], apk: dict[str, dict[str, str]]) -> None:
    """Report what the APK asset would add or contradict, without using it as a source."""
    apk_only = sorted(set(apk) - set(export), key=_sort_key)
    shared = set(apk) & set(export)
    filled = sum(
        1
        for code in shared
        for column in set(apk[code]) & set(export[code])
        if not (export[code].get(column) or "").strip() and (apk[code].get(column) or "").strip()
    )
    conflicts = [
        code
        for code in sorted(shared, key=_sort_key)
        if (apk[code].get("en_implication") or "").strip() != (export[code].get("en_implication") or "").strip()
    ]
    print(f"  apk: {len(apk)} codes, {len(apk_only)} not in the export, {filled} cells it could fill")
    print(f"  apk: {len(conflicts)} codes whose en_implication disagrees (export wins): {conflicts}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export", type=pathlib.Path, required=True, help="export-data CSV or HA diagnostics JSON")
    parser.add_argument("--apk", type=pathlib.Path, help="the APK's assets/servicecode.csv, for cross-checking only")
    parser.add_argument("--output", type=pathlib.Path, default=OUTPUT)
    args = parser.parse_args()

    export = _read_export(args.export)
    if unknown := set(COLUMNS) - set(next(iter(export.values()))):
        print(f"warning: the export is missing columns ErrorInfo declares: {sorted(unknown)}", file=sys.stderr)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for code in sorted(export, key=_sort_key):
        writer.writerow({column: (export[code].get(column) or "").strip() for column in COLUMNS})
    args.output.write_text(buffer.getvalue(), encoding="utf-8")

    print(f"wrote {len(export)} codes to {args.output}")
    if args.apk:
        cross_check(export, _read_csv(args.apk))
    return 0


if __name__ == "__main__":
    sys.exit(main())
