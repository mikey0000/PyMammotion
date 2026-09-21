r"""Dump the per-model work-setting capability schema for an account's devices.

The app asks ``product/param/version/search`` which job settings a model and
firmware actually expose — whether to show ride-boundary distance at all, what
to default it to, whether the value is forced, the bounds of the control.
``WorkingSettingManage`` in the APK switches on the ``code`` of each row ("15"
is ride edge, "21" start progress, and so on).

The library never calls this endpoint: the answers change with firmware
releases, not with the clock, so paying a per-device round trip on every setup
buys nothing.  Run this occasionally instead, commit the JSON, and fold any
change into the static capability helpers by hand.

Usage::

    MAMMOTION_EMAIL=... MAMMOTION_PASSWORD='...' \\
        uv run python scripts/dump_product_params.py [-o out.json] [--raw]

With ``--product-key`` and ``--device-version`` it queries one model directly
and needs no devices on the account.  ``--diff <old.json>`` reports what changed
against a previous dump, which is the point of keeping them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any

from aiohttp import ClientSession

from pymammotion.client import MammotionClient
from pymammotion.http.model.product_params import ProductParamData

_log = logging.getLogger("dump_product_params")

# The codes WorkingSettingManage switches on, for a readable dump.  Anything not
# listed still appears, by its bare code.
KNOWN_CODES = {
    "3": "channel_width (path spacing)",
    "4": "blade_height",
    "15": "ride_boundary_distance",
    "21": "start_progress",
}


def _annotate(summary: dict[str, Any]) -> dict[str, Any]:
    """Label the codes we have identified, leaving the rest as they came."""
    return {f"{code} ({KNOWN_CODES[code]})" if code in KNOWN_CODES else code: value for code, value in summary.items()}


async def _dump_one(
    client: MammotionClient, product_key: str, device_version: str, *, raw: bool
) -> dict[str, Any] | None:
    http = client.mammotion_http
    if http is None:
        _log.error("no HTTP session — login did not complete")
        return None
    params: ProductParamData | None = await http.get_product_params(product_key, device_version)
    if params is None:
        _log.warning("no parameters returned for %s @ %s", product_key, device_version)
        return None
    return params.to_dict() if raw else _annotate(params.to_summary())


async def _collect(args: argparse.Namespace) -> dict[str, Any]:
    email = os.environ.get("MAMMOTION_EMAIL", "")
    password = os.environ.get("MAMMOTION_PASSWORD", "")
    if not email or not password:
        _log.error("Set MAMMOTION_EMAIL and MAMMOTION_PASSWORD")
        raise SystemExit(2)

    out: dict[str, Any] = {}
    async with ClientSession() as session:
        client = MammotionClient()
        try:
            await client.login_and_initiate_cloud(email, password, session)

            if args.product_key:
                key = f"{args.product_key}@{args.device_version}"
                out[key] = await _dump_one(client, args.product_key, args.device_version, raw=args.raw)
                return out

            devices = list(client.aliyun_device_list()) + list(client.mammotion_device_list())
            for record in devices:
                product_key = record.product_key or ""
                name = record.device_name or product_key
                state = client.get_device_by_name(name)
                firmware = getattr(getattr(state, "device_firmwares", None), "device_version", "") or ""
                if not product_key:
                    _log.info("skipping %s — no product key", name)
                    continue
                _log.info("querying %s (%s @ %s)", name, product_key, firmware or "unknown firmware")
                out[f"{name} [{product_key}@{firmware}]"] = await _dump_one(client, product_key, firmware, raw=args.raw)
        finally:
            await client.stop()
    return out


def _diff(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Report what a new dump says that the previous one did not."""
    lines: list[str] = []
    for key in sorted(set(old) | set(new)):
        if key not in old:
            lines.append(f"+ {key}: new")
            continue
        if key not in new:
            lines.append(f"- {key}: gone")
            continue
        before, after = old[key] or {}, new[key] or {}
        for code in sorted(set(before) | set(after)):
            if before.get(code) != after.get(code):
                lines.append(f"~ {key} / {code}:\n    was {before.get(code)}\n    now {after.get(code)}")
    return lines


def main() -> None:
    """Fetch the schema for the account's devices and print or write it."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--out", type=Path, help="write the dump here instead of stdout")
    parser.add_argument("--raw", action="store_true", help="dump the response verbatim, not the summary")
    parser.add_argument("--product-key", help="query one model instead of the account's devices")
    parser.add_argument("--device-version", default="", help="firmware to query with --product-key")
    parser.add_argument("--diff", type=Path, help="compare against a previous dump and print the changes")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = asyncio.run(_collect(args))
    rendered = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False)

    if args.out:
        args.out.write_text(rendered + "\n")
        _log.info("wrote %s", args.out)
    else:
        print(rendered)

    if args.diff:
        changes = _diff(json.loads(args.diff.read_text()), result)
        print("\n".join(changes) if changes else "no changes against " + str(args.diff), file=sys.stderr)


if __name__ == "__main__":
    main()
