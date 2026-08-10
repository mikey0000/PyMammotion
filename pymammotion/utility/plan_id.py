"""Helpers for generating mower task identifiers and copy-name slots.

The mower's ``NavPlanJobSet.plan_id`` is a 21-character string composed of a
13-digit millisecond timestamp followed by 8 random digits (0–8). This
mirrors the APK's ``BaseUtil.get21Random()`` (``utils/BaseUtil.java:256-262``).

``make_copy_name`` mirrors the APK's ``getCopyTaskName`` — when the user
copies a plan it picks the first unused ``"Copy-N"`` slot (1..1000) so
multiple copies don't collide. The base label is parameterised so other
device kinds (Spino) can reuse it with a localised prefix later.
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

_RANDOM_DIGITS = 8
"""Number of trailing random digits appended to the timestamp."""

_COPY_SLOT_LIMIT = 1000
"""Maximum copy slot the APK probes before giving up (see getCopyTaskName)."""


def new_mower_plan_id(*, now_ms: int | None = None) -> str:
    """Generate a fresh 21-character mower ``plan_id``.

    The format matches the APK exactly: 13-digit millisecond timestamp +
    8 random digits in the range 0–8 (inclusive). The narrow 0–8 random
    range is what ``BaseUtil.get21Random`` produces — we replicate it so
    captured wire traffic is indistinguishable from app traffic.

    ``now_ms`` overrides the timestamp for deterministic testing.
    """
    ts = now_ms if now_ms is not None else int(time.time() * 1000)
    suffix = "".join(str(random.randint(0, 8)) for _ in range(_RANDOM_DIGITS))  # noqa: S311
    return f"{ts}{suffix}"


def make_copy_name(existing_names: Iterable[str], *, base: str = "Copy") -> str:
    """Return the first ``"{base}-N"`` name not already in *existing_names*.

    Walks ``N = 1, 2, …, 1000`` (matching the APK's upper bound) and stops
    at the first slot not present in ``existing_names``. If all 1000 slots
    are taken the final candidate is returned anyway — the same fallback
    the APK uses.
    """
    taken = set(existing_names)
    for n in range(1, _COPY_SLOT_LIMIT + 1):
        candidate = f"{base}-{n}"
        if candidate not in taken:
            return candidate
    return f"{base}-{_COPY_SLOT_LIMIT}"
