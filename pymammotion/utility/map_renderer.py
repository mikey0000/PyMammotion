"""Backwards-compatible re-export of :mod:`pymammotion.render.map_renderer`.

A 450-line PIL renderer that fetches OSM tiles and caches them on disk is not a
leaf helper, so it moved to the ``render`` package; this path survives for
out-of-tree callers.  See ``pymammotion/render/map_renderer.py``.
"""

from __future__ import annotations

from pymammotion.render.map_renderer import (
    OSM_USER_AGENT,
    GeoBounds,
    placeholder_png,
    render_map_png,
    set_osm_user_agent,
)

__all__ = [
    "OSM_USER_AGENT",
    "GeoBounds",
    "placeholder_png",
    "render_map_png",
    "set_osm_user_agent",
]
