#!/usr/bin/env python3
"""Inject encoded credentials into pymammotion/const.py before building.

Usage:
    python scripts/update_credentials.py \
        --app-key KEY --app-secret SECRET \
        --oauth2-client-id CLIENT_ID --oauth2-client-secret CLIENT_SECRET

The script replaces the sentinel block in const.py with an obfuscated form.
Run with empty strings (or --reset) to reset to the source (no-credentials) state.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

_K = (109, 97, 109, 109, 111, 116, 105, 111, 110, 95, 97, 112, 112)

_SENTINEL_RE = re.compile(
    r"# --- credentials:.*?# --- end credentials ---",
    re.DOTALL,
)

_BLANK_BLOCK = """\
# --- credentials: injected at build time via scripts/update_credentials.py — do not edit ---
APP_KEY: str = ""
APP_SECRET: str = ""
MAMMOTION_OAUTH2_CLIENT_ID: str = ""
MAMMOTION_OAUTH2_CLIENT_SECRET: str = ""
# --- end credentials ---"""

_ENCODED_BLOCK = """\
# --- credentials: injected at build time via scripts/update_credentials.py — do not edit ---
def _r(d: tuple[int, ...]) -> str:
    _k = (109, 97, 109, 109, 111, 116, 105, 111, 110, 95, 97, 112, 112)
    return bytes(v ^ _k[i % len(_k)] for i, v in enumerate(d)).decode()

APP_KEY = _r({key!r})
APP_SECRET = _r({secret!r})
MAMMOTION_OAUTH2_CLIENT_ID = _r({oauth2_client_id!r})
MAMMOTION_OAUTH2_CLIENT_SECRET = _r({oauth2_client_secret!r})
# --- end credentials ---"""


def _encode(value: str) -> tuple[int, ...]:
    return tuple(b ^ _K[i % len(_K)] for i, b in enumerate(value.encode()))


def _decode(d: tuple[int, ...]) -> str:
    return bytes(v ^ _K[i % len(_K)] for i, v in enumerate(d)).decode()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject encoded credentials into const.py")
    parser.add_argument("--app-key", required=True, metavar="KEY")
    parser.add_argument("--app-secret", required=True, metavar="SECRET")
    parser.add_argument("--oauth2-client-id", default="", metavar="CLIENT_ID")
    parser.add_argument("--oauth2-client-secret", default="", metavar="CLIENT_SECRET")
    parser.add_argument("--reset", action="store_true", help="Reset to blank (source) state")
    args = parser.parse_args()

    const_path = Path(__file__).parent.parent / "pymammotion" / "const.py"
    content = const_path.read_text()

    if not _SENTINEL_RE.search(content):
        raise SystemExit(f"Sentinel block not found in {const_path}")

    if args.reset or (not args.app_key and not args.app_secret):
        replacement = _BLANK_BLOCK
    else:
        enc_key = _encode(args.app_key)
        enc_secret = _encode(args.app_secret)
        enc_oauth2_id = _encode(args.oauth2_client_id)
        enc_oauth2_secret = _encode(args.oauth2_client_secret)
        assert _decode(enc_key) == args.app_key, "Round-trip check failed for --app-key"
        assert _decode(enc_secret) == args.app_secret, "Round-trip check failed for --app-secret"
        assert _decode(enc_oauth2_id) == args.oauth2_client_id, "Round-trip check failed for --oauth2-client-id"
        assert _decode(enc_oauth2_secret) == args.oauth2_client_secret, "Round-trip check failed for --oauth2-client-secret"
        replacement = _ENCODED_BLOCK.format(
            key=enc_key,
            secret=enc_secret,
            oauth2_client_id=enc_oauth2_id,
            oauth2_client_secret=enc_oauth2_secret,
        )

    content = _SENTINEL_RE.sub(replacement, content)
    const_path.write_text(content)
    print(f"Updated {const_path}")


if __name__ == "__main__":
    main()
