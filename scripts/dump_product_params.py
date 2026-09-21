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

from pymammotion.http.http import MammotionHTTP
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
    http: MammotionHTTP, product_key: str, device_version: str, int_mod: str, *, raw: bool
) -> dict[str, Any] | None:
    params: ProductParamData | None = await http.get_product_params(product_key, device_version, int_mod)
    if params is None or not params.detail_vos:
        return None
    return params.to_dict() if raw else _annotate(params.to_summary())


async def _firmware_by_name(http: MammotionHTTP, iot_ids: list[str]) -> dict[str, str]:
    """Map device name to running firmware; the endpoint rejects a blank version."""
    if not iot_ids:
        return {}
    try:
        ota = await http.get_device_ota_firmware(iot_ids)
    except Exception:  # noqa: BLE001
        _log.warning("could not read firmware versions", exc_info=True)
        return {}
    return {c.device_name: c.current_version or "" for c in (ota.data or []) if c.device_name}


async def _sweep(
    http: MammotionHTTP,
    product_key: str,
    models: list[Any],
    version: str,
    *,
    raw: bool,
) -> dict[str, Any]:
    """Query every internal model under one product key.

    The schema is keyed by ``intMod``, and a device does not report which of its
    product's models it is over HTTP, so the whole set is dumped and identical
    answers collapsed — that is what makes the result usable as a static table.
    """
    by_model: dict[str, Any] = {}
    for model in models:
        if not model.int_mod:
            continue
        result = await _dump_one(http, product_key, version, model.int_mod, raw=raw)
        if result is None:
            continue
        label = f"{model.int_mod} ({model.ext_mod})" if model.ext_mod else model.int_mod
        by_model[label] = result
    return by_model


async def _collect(args: argparse.Namespace) -> dict[str, Any]:
    email = os.environ.get("MAMMOTION_EMAIL", "")
    password = os.environ.get("MAMMOTION_PASSWORD", "")
    if not email or not password:
        _log.error("Set MAMMOTION_EMAIL and MAMMOTION_PASSWORD")
        raise SystemExit(2)

    out: dict[str, Any] = {}
    async with ClientSession() as session:
        # HTTP only: this is an account-level lookup, so there is no reason to
        # bring up MQTT and the device transports for it.
        http = MammotionHTTP(session=session)
        login = await http.login_v2(email, password)
        if login.code != 0:
            _log.error("login failed: %s", login.msg)
            raise SystemExit(1)

        if args.product_key:
            if not args.int_mod or not args.device_version:
                _log.error("--product-key needs --int-mod and --device-version; both are rejected blank")
                raise SystemExit(2)
            key = f"{args.product_key}@{args.device_version}"
            out[key] = {
                args.int_mod: await _dump_one(http, args.product_key, args.device_version, args.int_mod, raw=args.raw)
            }
            return out

        products = {p.product_key: p for p in ((await http.get_product_list()).data or [])}

        if args.all_products:
            if not args.device_version:
                _log.error("--all-products needs --device-version; the endpoint rejects a blank one")
                raise SystemExit(2)
            for product_key, product in products.items():
                _log.info("querying %s (%d models)", product_key, len(product.models or []))
                found = await _sweep(http, product_key, product.models or [], args.device_version, raw=args.raw)
                if found:
                    out[product_key] = found
            return out

        page = await http.get_user_device_page()
        records = (page.data.records if page.data else []) or []
        firmware = await _firmware_by_name(http, [r.iot_id for r in records if r.iot_id])

        for record in records:
            product_key = record.product_key or ""
            name = record.device_name or product_key
            if not product_key:
                _log.info("skipping %s — no product key", name)
                continue
            version = args.device_version or firmware.get(name, "")
            if not version:
                _log.warning("skipping %s — no firmware version and none given", name)
                continue
            product = products.get(product_key)
            models = product.models if product else []
            _log.info("querying %s (%s @ %s, %d models)", name, product_key, version, len(models or []))
            found = await _sweep(http, product_key, models or [], version, raw=args.raw)
            if found:
                out[f"{name} [{product_key}@{version}]"] = found
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
    parser.add_argument("--int-mod", help="internal model id, required with --product-key")
    parser.add_argument("--device-version", default="", help="firmware to query for; never blank")
    parser.add_argument(
        "--all-products", action="store_true", help="sweep every product and model, not just this account's"
    )
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
