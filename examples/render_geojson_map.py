"""Render a generated GeoJSON map in a browser using Leaflet.

Builds a single self-contained HTML file that loads ArcGIS World Imagery
as the basemap (matching the Mammotion-HA wiki map page), inlines the
GeoJSON so there is no CORS / local-server hassle, and pipes each
feature's ``properties`` directly into ``L.geoJSON``'s ``style``
callback so the Leaflet Path options that ``generate_geojson.py``
emits (``color`` / ``fillColor`` / ``weight`` / ``dashArray`` / …)
render exactly as the library intended.

Usage
-----
    uv run python examples/render_geojson_map.py [GEOJSON] [-o OUTPUT] [--no-open]

Arguments (all optional):
    GEOJSON     Path to a GeoJSON FeatureCollection — defaults to the
                most recently modified ``examples/dev_output/map_*.geojson``
                (i.e. the last output of ``scripts/generate_live_map_geojson.py``).
    -o OUTPUT   Where to write the HTML (default: next to the GeoJSON).
    --no-open   Skip launching the browser — just write the file.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

# Matches how Home Assistant frontends reference the assets pack.
# For the standalone viewer we rewrite to the raw GitHub URL so the
# mower / dock / RTK icons actually load without the HA www mount.
_HA_ICON_PREFIX = "/local/community/ha-mammotion-assets/"
_GITHUB_ICON_PREFIX = "https://raw.githubusercontent.com/mikey0000/ha-mammotion-assets/main/"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Mammotion map — {title}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
        crossorigin="">
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
          integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
          crossorigin=""></script>
  <style>
    html, body {{ margin: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
    #map {{ height: 100%; width: 100%; background: #222; }}
    .info-panel {{
      position: absolute; top: 10px; left: 10px; z-index: 1000;
      background: rgba(255,255,255,0.92); padding: 8px 12px;
      border-radius: 6px; box-shadow: 0 2px 6px rgba(0,0,0,.3);
      max-width: 300px; font-size: 13px;
    }}
    .info-panel h3 {{ margin: 0 0 6px 0; font-size: 14px; }}
    .info-panel .count {{ display: inline-block; margin: 0 8px 2px 0; }}
    .leaflet-popup-content-wrapper {{ border-radius: 6px; }}
    .leaflet-popup-content b {{ font-size: 13px; }}
    .leaflet-popup-content small {{ color: #666; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="info-panel">
    <h3>{title}</h3>
    <div id="feature-counts"></div>
    <div style="margin-top:6px;color:#666;font-size:12px;">
      Click a feature for details. Basemap: Esri World Imagery.
    </div>
  </div>
  <script>
    const GEOJSON = {geojson_json};
    const HA_ICON_PREFIX = {ha_prefix_json};
    const GITHUB_ICON_PREFIX = {gh_prefix_json};

    const map = L.map('map', {{ maxZoom: 24, zoomSnap: 0.25 }});

    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
      {{
        maxZoom: 24,
        minZoom: 14,
        maxNativeZoom: 19,
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics',
      }},
    ).addTo(map);

    // Rewrite HA-local icon paths to the public asset repo so the viewer
    // works outside HA.
    function rewriteIconUrl(url) {{
      if (!url) return url;
      if (url.startsWith(HA_ICON_PREFIX)) {{
        return GITHUB_ICON_PREFIX + url.slice(HA_ICON_PREFIX.length);
      }}
      return url;
    }}

    const counts = {{}};

    const layer = L.geoJSON(GEOJSON, {{
      // Pipe properties straight into L.Path.setStyle — this is the
      // whole reason generate_geojson.py uses Leaflet key names.
      style: (feature) => feature.properties || {{}},
      pointToLayer: (feature, latlng) => {{
        const p = feature.properties || {{}};
        const iconUrl = rewriteIconUrl(p.iconUrl);
        if (iconUrl) {{
          return L.marker(latlng, {{
            icon: L.icon({{
              iconUrl: iconUrl,
              iconSize: p.iconSize || [30, 30],
              iconAnchor: p.iconAnchor || [15, 30],
            }}),
            title: p.Name || p.title || p.type_name || '',
          }});
        }}
        return L.circleMarker(latlng, p);
      }},
      onEachFeature: (feature, layer) => {{
        const p = feature.properties || {{}};
        const type = p.type_name || 'unknown';
        counts[type] = (counts[type] || 0) + 1;

        const name = p.Name || p.title || type;
        const desc = p.description || '';
        const meta = [];
        if (p.length) meta.push('length: ' + p.length.toFixed(1) + ' m');
        if (p.area) meta.push('area: ' + p.area.toFixed(1) + ' m&sup2;');
        const body =
          '<b>' + name + '</b><br>' +
          (desc ? desc + '<br>' : '') +
          '<small>' + type + (meta.length ? ' — ' + meta.join(', ') : '') + '</small>';
        layer.bindPopup(body);
        layer.bindTooltip(name, {{ direction: 'top', sticky: true }});
      }},
    }}).addTo(map);

    if (layer.getBounds().isValid()) {{
      map.fitBounds(layer.getBounds(), {{ padding: [30, 30] }});
    }} else {{
      map.setView([0, 0], 2);
    }}

    // Fill in the info-panel counts now that onEachFeature has run for every feature.
    const panel = document.getElementById('feature-counts');
    panel.innerHTML = Object.keys(counts)
      .sort()
      .map((k) => '<span class="count"><b>' + counts[k] + '</b> ' + k + '</span>')
      .join('');
  </script>
</body>
</html>
"""


def _find_latest_geojson() -> Path | None:
    """Return the most-recent ``map_*.geojson`` under ``examples/dev_output``."""
    dev_output = Path(__file__).parent / "dev_output"
    if not dev_output.exists():
        return None
    candidates = sorted(dev_output.glob("map_*.geojson"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def render(geojson_path: Path, output_path: Path) -> None:
    """Build the HTML file with *geojson_path* inlined and write to *output_path*."""
    with geojson_path.open(encoding="utf-8") as fh:
        geo = json.load(fh)

    feature_count = len(geo.get("features", []))
    title = geojson_path.stem + f" ({feature_count} features)"

    html = HTML_TEMPLATE.format(
        title=title,
        geojson_json=json.dumps(geo),
        ha_prefix_json=json.dumps(_HA_ICON_PREFIX),
        gh_prefix_json=json.dumps(_GITHUB_ICON_PREFIX),
    )
    output_path.write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "geojson",
        nargs="?",
        type=Path,
        help="Path to a GeoJSON file (default: latest examples/dev_output/map_*.geojson)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output HTML path (default: alongside the GeoJSON with .html suffix)",
    )
    parser.add_argument("--no-open", action="store_true", help="Do not launch a browser")
    args = parser.parse_args()

    geojson_path = args.geojson or _find_latest_geojson()
    if geojson_path is None:
        parser.error(
            "No GeoJSON specified and none found in examples/dev_output/. "
            "Run scripts/generate_live_map_geojson.py first or pass an explicit path."
        )
    if not geojson_path.exists():
        parser.error(f"GeoJSON not found: {geojson_path}")

    output_path = args.output or geojson_path.with_suffix(".html")
    render(geojson_path, output_path)
    print(f"Wrote {output_path}")

    if not args.no_open:
        webbrowser.open(output_path.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
