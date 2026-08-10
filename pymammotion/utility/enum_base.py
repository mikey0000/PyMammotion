"""Base IntEnum that tolerates unknown wire values instead of raising."""

from __future__ import annotations

from enum import IntEnum
import logging

_logger = logging.getLogger(__name__)

# Dedupe key: (class name, offending value).  Keeps a persistent unknown value
# from re-logging on every frame — we log it once and move on.
_logged_unknown: set[tuple[str, object]] = set()


class UnknownTolerantIntEnum(IntEnum):
    """An ``IntEnum`` that resolves unrecognised values to its ``UNKNOWN`` member.

    Subclasses MUST define an ``UNKNOWN`` member (a real member or an alias of an
    existing sentinel).  ``EnumType(x)`` for an unmodelled ``x`` logs once per
    ``(class, value)`` and returns ``UNKNOWN`` instead of raising ``ValueError`` —
    so incoming device frames carrying newer/unexpected values never crash message
    processing or entities that display them.
    """

    @classmethod
    def _missing_(cls, value: object) -> UnknownTolerantIntEnum:
        """Return ``UNKNOWN`` for an unrecognised *value*, logging it once."""
        key = (cls.__name__, value)
        if key not in _logged_unknown:
            _logged_unknown.add(key)
            _logger.error("%s: unknown value %r — falling back to UNKNOWN", cls.__name__, value)
        # Subclasses must define an ``UNKNOWN`` member; look it up by name (the base
        # itself has no members, so this only ever runs on a concrete subclass).
        return cls["UNKNOWN"]
