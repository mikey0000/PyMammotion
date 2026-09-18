"""Backwards-compatible re-export of :mod:`pymammotion.data.model.svg`.

These modules operate on ``data.model`` types, so they now live there; this path
survives because the Home Assistant integration imports from it.  New code should
import from the new location.

The upward import below is the inversion this move was meant to remove — it
cannot go while this path must keep working.  Deleting this shim needs a
coordinated change: update the integration's imports, release, then drop it.
"""

from __future__ import annotations

from pymammotion.data.model.svg import (
    _SVG_CHUNK_SIZE,
    area_centroid,
    build_svg_ack,
    build_svg_delete,
    build_svg_for_area,
    build_svg_update,
    chunk_svg_messages,
)

__all__ = [
    "_SVG_CHUNK_SIZE",
    "area_centroid",
    "build_svg_ack",
    "build_svg_delete",
    "build_svg_for_area",
    "build_svg_update",
    "chunk_svg_messages",
]
