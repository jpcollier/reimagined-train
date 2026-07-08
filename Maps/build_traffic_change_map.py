#!/usr/bin/env python3
"""Build a simple Leaflet map of 2024-to-2025 traffic changes."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "Maps" / "traffic_change_2024_2025.html"
SOURCES = [
    {
        "dataset": "ATR",
        "path": ROOT / "ATR" / "Analysis" / "atr_2024_2025_midweek_matches.csv",
        "change_col": "pct_change_2024_2025",
        "id_col": "segment_id_2024",
    },
    {
        "dataset": "VTMC",
        "path": ROOT / "VTMC" / "Analysis" / "vtmc_2024_2025_midweek_matches.csv",
        "change_col": "pct_change",
        "id_col": "node_id_2024",
    },
]


def as_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def marker_color(change: float) -> str:
    if change <= -10:
        return "#1f78b4"
    if change < 0:
        return "#6baed6"
    if change < 10:
        return "#fdae6b"
    return "#e31a1c"


def load_points() -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    for source in SOURCES:
        with source["path"].open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                lat = as_float(row.get("latitude", ""))
                lon = as_float(row.get("longitude", ""))
                change = as_float(row.get(source["change_col"], ""))
                vol_2024 = as_float(row.get("midweek_avg_daily_volume_2024", ""))
                vol_2025 = as_float(row.get("midweek_avg_daily_volume_2025", ""))
                if lat is None or lon is None or change is None:
                    continue
                points.append(
                    {
                        "dataset": source["dataset"],
                        "site_id": row.get(source["id_col"], ""),
                        "name": row.get("display_name", ""),
                        "lat": lat,
                        "lon": lon,
                        "change": change,
                        "color": marker_color(change),
                        "volume_2024": vol_2024,
                        "volume_2025": vol_2025,
                    }
                )
    return points


def build_html(points: list[dict[str, object]]) -> str:
    escaped_points = json.dumps(points, ensure_ascii=False)
    total = len(points)
    atr = sum(1 for p in points if p["dataset"] == "ATR")
    vtmc = sum(1 for p in points if p["dataset"] == "VTMC")
    changes = [float(p["change"]) for p in points]
    summary = (
        f"{total} matched locations ({atr} ATR, {vtmc} VTMC); "
        f"2024→2025 change range {min(changes):.1f}% to {max(changes):.1f}%."
    )
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>2024 to 2025 Traffic Change Map</title>
  <link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\">
  <style>
    body {{ margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; }}
    header {{ padding: 1rem 1.25rem; border-bottom: 1px solid #ddd; }}
    h1 {{ margin: 0 0 .25rem; font-size: 1.35rem; }}
    p {{ margin: .25rem 0; color: #444; }}
    #map {{ height: calc(100vh - 118px); min-height: 520px; }}
    .legend {{ background: white; padding: .75rem; border-radius: .5rem; box-shadow: 0 1px 6px #0003; line-height: 1.4; }}
    .swatch {{ display: inline-block; width: .85rem; height: .85rem; border-radius: 50%; margin-right: .35rem; vertical-align: -0.1rem; }}
    .leaflet-popup-content {{ min-width: 230px; }}
  </style>
</head>
<body>
  <header>
    <h1>2024 to 2025 Traffic Change: ATR and VTMC</h1>
    <p>{html.escape(summary)}</p>
    <p>Circle color shows percent change in midweek average daily volume. ATR sites are circles; VTMC sites are squares.</p>
  </header>
  <div id=\"map\"></div>
  <script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"></script>
  <script>
    const points = {escaped_points};
    const map = L.map('map');
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    const bounds = [];
    const layers = {{ ATR: L.layerGroup(), VTMC: L.layerGroup() }};

    function popup(point) {{
      const change = Number(point.change).toFixed(1);
      const volume2024 = point.volume_2024 == null ? 'n/a' : Math.round(point.volume_2024).toLocaleString();
      const volume2025 = point.volume_2025 == null ? 'n/a' : Math.round(point.volume_2025).toLocaleString();
      return `<strong>${{point.dataset}} ${{point.site_id}}</strong><br>${{point.name}}<br>` +
        `<b>Change:</b> ${{change}}%<br><b>2024 volume:</b> ${{volume2024}}<br><b>2025 volume:</b> ${{volume2025}}`;
    }}

    const overlapGroups = new Map();
    for (const point of points) {{
      const key = `${{point.dataset}}:${{point.lat.toFixed(6)}},${{point.lon.toFixed(6)}}`;
      if (!overlapGroups.has(key)) {{
        overlapGroups.set(key, []);
      }}
      overlapGroups.get(key).push(point);
    }}

    function offsetLatLng(point, index, total) {{
      const base = L.latLng(point.lat, point.lon);
      if (total < 2) {{
        return base;
      }}

      // Spread same-coordinate markers side-by-side on the screen so directional
      // pairs such as EB/WB counts can both be clicked without changing the data.
      const angle = total === 2 ? (index === 0 ? Math.PI : 0) : (2 * Math.PI * index) / total;
      const offsetMeters = 10;
      const earthRadiusMeters = 6378137;
      const latOffset = (Math.sin(angle) * offsetMeters / earthRadiusMeters) * (180 / Math.PI);
      const lonOffset = (Math.cos(angle) * offsetMeters / (earthRadiusMeters * Math.cos(base.lat * Math.PI / 180))) * (180 / Math.PI);
      return L.latLng(base.lat + latOffset, base.lng + lonOffset);
    }}

    for (const group of overlapGroups.values()) {{
      group.forEach((point, index) => {{
        const latlng = offsetLatLng(point, index, group.length);
        bounds.push([point.lat, point.lon]);
        const options = {{ radius: 7, color: '#333', weight: 1, fillColor: point.color, fillOpacity: 0.82 }};
        const marker = point.dataset === 'ATR'
          ? L.circleMarker(latlng, options)
          : L.marker(latlng, {{ icon: L.divIcon({{ className: '', html: `<span style="display:block;width:13px;height:13px;background:${{point.color}};border:1px solid #333;"></span>`, iconSize: [13, 13] }}) }});
        marker.bindPopup(popup(point));
        marker.addTo(layers[point.dataset]);
      }});
    }}

    layers.ATR.addTo(map);
    layers.VTMC.addTo(map);
    L.control.layers(null, layers, {{ collapsed: false }}).addTo(map);
    map.fitBounds(bounds, {{ padding: [30, 30] }});

    const legend = L.control({{ position: 'bottomright' }});
    legend.onAdd = function () {{
      const div = L.DomUtil.create('div', 'legend');
      div.innerHTML = '<strong>2024→2025 change</strong><br>' +
        '<span class=\"swatch\" style=\"background:#1f78b4\"></span>≤ -10%<br>' +
        '<span class=\"swatch\" style=\"background:#6baed6\"></span>-10% to 0%<br>' +
        '<span class=\"swatch\" style=\"background:#fdae6b\"></span>0% to 10%<br>' +
        '<span class=\"swatch\" style=\"background:#e31a1c\"></span>≥ 10%<br><hr>' +
        '○ ATR &nbsp; □ VTMC';
      return div;
    }};
    legend.addTo(map);
  </script>
</body>
</html>
"""


def main() -> None:
    points = load_points()
    if not points:
        raise SystemExit("No map points found")
    OUTPUT.write_text(build_html(points), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(points)} points")


if __name__ == "__main__":
    main()
