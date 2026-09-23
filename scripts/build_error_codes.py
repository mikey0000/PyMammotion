"""Regenerate ``pymammotion/data/error_codes.csv`` from the cloud's error-code sources.

Two inputs, merged:

* ``--export``: the ``/user-server/v1/code/record/export-data`` CSV that
  ``MammotionHTTP.get_all_error_codes`` fetches — the columns :class:`ErrorInfo`
  declares, every language.  It wins wherever it has text.
* ``--page-lan``: a dump of ``MammotionHTTP.get_all_error_codes_paged`` (a JSON
  object keyed by code, or a list of records).  It adds the codes the export lacks
  and fills cells the export leaves blank; it never overwrites export text.

The two overlap only partly — on 2026-09-10 ``page-lan`` had 176 codes the export
lacked and the export 221 ``page-lan`` lacked — so neither alone is the table.

``--apk`` diffs the APK's ``assets/servicecode.csv`` against the result as a
cross-check only; it has never added a code or a cell.

Usage::

    uv run python scripts/build_error_codes.py \
        --export <endpoint.csv | config_entry-mammotion-*.json | pymammotion/data/error_codes.csv> \
        [--page-lan examples/dev_output/error_codes_live.json] \
        [--apk <path to assets/servicecode.csv>]

``--export`` accepts the raw CSV, the bundled CSV itself (to fold a new
``page-lan`` dump into it), or a Home Assistant diagnostics JSON whose
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

from pymammotion.http.model.http import ErrorCodeRecord, ErrorInfo

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


def _read_page_lan(path: pathlib.Path) -> dict[str, dict[str, str]]:
    """Read a page-lan dump and return its records as export-shaped rows."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = raw.values() if isinstance(raw, dict) else raw
    rows = (ErrorCodeRecord.from_dict(record).to_error_info() for record in records)
    return {row.code: {column: getattr(row, column) for column in COLUMNS} for row in rows}


def merge(export: dict[str, dict[str, str]], page_lan: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Add page-lan codes the export lacks and fill its blank cells, never overwriting export text."""
    merged = {code: dict(row) for code, row in export.items()}
    for code, row in page_lan.items():
        target = merged.setdefault(code, dict.fromkeys(COLUMNS, ""))
        for column, value in row.items():
            if value.strip() and not (target.get(column) or "").strip():
                target[column] = value
    return merged


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
    parser.add_argument("--page-lan", type=pathlib.Path, help="get_all_error_codes_paged dump (JSON)")
    parser.add_argument("--apk", type=pathlib.Path, help="the APK's assets/servicecode.csv, for cross-checking only")
    parser.add_argument("--output", type=pathlib.Path, default=OUTPUT)
    args = parser.parse_args()

    export = _read_export(args.export)
    if args.page_lan:
        page_lan = _read_page_lan(args.page_lan)
        added = len(set(page_lan) - set(export))
        export = merge(export, page_lan)
        print(f"  page-lan: {len(page_lan)} codes, {added} not in the export")
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
