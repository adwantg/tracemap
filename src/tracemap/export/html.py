"""
HTML export with interactive Leaflet.js map.

Generates a self-contained HTML file with:
- Interactive map using Leaflet.js and OpenStreetMap tiles
- Hop markers with popups showing detailed information
- Polyline paths between hops
- Color-coded markers based on RTT/loss
- Legend and summary panel

Author: gadwant
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..models import TraceRun


def _get_marker_color(hop) -> str:
    """Get marker color based on RTT and loss."""
    if hop.is_timeout:
        return "#9E9E9E"  # Grey for timeout
    if hop.loss_pct > 50:
        return "#F44336"  # Red for high loss
    if hop.rtt_avg_ms is None:
        return "#9E9E9E"
    if hop.rtt_avg_ms < 50:
        return "#4CAF50"  # Green for low RTT
    if hop.rtt_avg_ms < 150:
        return "#FFC107"  # Yellow/amber for medium
    return "#F44336"  # Red for high RTT


def _get_path_color(hop_from, hop_to) -> str:
    """Get path color based on target hop's RTT."""
    if hop_to.is_timeout:
        return "#BDBDBD"
    if hop_to.rtt_avg_ms is None:
        return "#2196F3"
    if hop_to.rtt_avg_ms < 50:
        return "#4CAF50"
    if hop_to.rtt_avg_ms < 150:
        return "#FFC107"
    return "#F44336"


def _hop_to_geojson(trace: TraceRun) -> Dict[str, Any]:
    """Convert trace hops to GeoJSON format."""
    features = []

    # Add hop markers
    for hop in trace.hops:
        if not hop.geo:
            continue

        properties = {
            "hop": hop.hop,
            "ip": hop.display_ip,
            "hostname": hop.hostname or "",
            "rtt_avg": f"{hop.rtt_avg_ms:.1f} ms" if hop.rtt_avg_ms else "-",
            "rtt_min": f"{hop.rtt_min_ms:.1f} ms" if hop.rtt_min_ms else "-",
            "rtt_max": f"{hop.rtt_max_ms:.1f} ms" if hop.rtt_max_ms else "-",
            "loss": f"{hop.loss_pct:.0f}%",
            "geo": hop.display_geo,
            "asn": hop.display_asn,
            "color": _get_marker_color(hop),
            "is_timeout": hop.is_timeout,
        }

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [hop.geo.lon, hop.geo.lat],
                },
                "properties": properties,
            }
        )

    # Add path lines
    geo_hops = [h for h in trace.hops if h.geo]
    for i in range(1, len(geo_hops)):
        prev = geo_hops[i - 1]
        curr = geo_hops[i]

        if prev.geo and curr.geo:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [prev.geo.lon, prev.geo.lat],
                            [curr.geo.lon, curr.geo.lat],
                        ],
                    },
                    "properties": {
                        "from_hop": prev.hop,
                        "to_hop": curr.hop,
                        "color": _get_path_color(prev, curr),
                        "is_timeout": curr.is_timeout,
                    },
                }
            )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Traceroute Map - {host}</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        #map {{ height: 100vh; width: 100%; }}
        .info-panel {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(255, 255, 255, 0.95);
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            z-index: 1000;
            max-width: 300px;
            font-size: 13px;
        }}
        .info-panel h3 {{
            margin-bottom: 10px;
            color: #333;
            font-size: 16px;
        }}
        .info-panel .stat {{
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            border-bottom: 1px solid #eee;
        }}
        .info-panel .stat:last-child {{ border-bottom: none; }}
        .info-panel .label {{ color: #666; }}
        .info-panel .value {{ font-weight: 500; color: #333; }}
        .legend {{
            position: absolute;
            bottom: 30px;
            left: 10px;
            background: rgba(255, 255, 255, 0.95);
            padding: 10px 15px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            z-index: 1000;
            font-size: 12px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 3px 0;
        }}
        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
        .popup-content {{ font-size: 13px; line-height: 1.5; }}
        .popup-content strong {{ color: #333; }}
        .popup-content .hop-num {{
            display: inline-block;
            background: #2196F3;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: bold;
            margin-bottom: 5px;
        }}
    </style>
</head>
<body>
    <div id="map"></div>

    <div class="info-panel">
        <h3>🗺️ Traceroute Map</h3>
        <div class="stat">
            <span class="label">Target:</span>
            <span class="value">{host}</span>
        </div>
        <div class="stat">
            <span class="label">Total Hops:</span>
            <span class="value">{total_hops}</span>
        </div>
        <div class="stat">
            <span class="label">Responded:</span>
            <span class="value">{responded_hops}</span>
        </div>
        <div class="stat">
            <span class="label">Timeouts:</span>
            <span class="value">{timeout_hops}</span>
        </div>
        <div class="stat">
            <span class="label">Avg Loss:</span>
            <span class="value">{avg_loss:.1f}%</span>
        </div>
        <div class="stat">
            <span class="label">Protocol:</span>
            <span class="value">{protocol}</span>
        </div>
    </div>

    <div class="legend">
        <div class="legend-item">
            <div class="legend-dot" style="background: #4CAF50;"></div>
            <span>RTT &lt; 50ms</span>
        </div>
        <div class="legend-item">
            <div class="legend-dot" style="background: #FFC107;"></div>
            <span>RTT 50-150ms</span>
        </div>
        <div class="legend-item">
            <div class="legend-dot" style="background: #F44336;"></div>
            <span>RTT &gt; 150ms / High Loss</span>
        </div>
        <div class="legend-item">
            <div class="legend-dot" style="background: #9E9E9E;"></div>
            <span>Timeout</span>
        </div>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const traceData = {geojson};

        // Initialize map
        const map = L.map('map').setView([30, 0], 2);

        // Add tile layer
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }}).addTo(map);

        // Track points for bounds
        const points = [];

        // Add GeoJSON features
        traceData.features.forEach(feature => {{
            if (feature.geometry.type === 'Point') {{
                const coords = feature.geometry.coordinates;
                const props = feature.properties;

                points.push([coords[1], coords[0]]);

                // Create marker
                const marker = L.circleMarker([coords[1], coords[0]], {{
                    radius: 8,
                    fillColor: props.color,
                    color: '#fff',
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.9
                }});

                // Create popup content
                let popupHtml = `
                    <div class="popup-content">
                        <span class="hop-num">Hop ${{props.hop}}</span>
                        <br><strong>IP:</strong> ${{props.ip}}
                `;

                if (props.hostname) {{
                    popupHtml += `<br><strong>Hostname:</strong> ${{props.hostname}}`;
                }}

                popupHtml += `
                    <br><strong>RTT:</strong> ${{props.rtt_avg}} (min: ${{props.rtt_min}}, max: ${{props.rtt_max}})
                    <br><strong>Loss:</strong> ${{props.loss}}
                `;

                if (props.geo) {{
                    popupHtml += `<br><strong>Location:</strong> ${{props.geo}}`;
                }}

                if (props.asn) {{
                    popupHtml += `<br><strong>ASN:</strong> ${{props.asn}}`;
                }}

                popupHtml += '</div>';

                marker.bindPopup(popupHtml);
                marker.addTo(map);

                // Add hop number label
                const label = L.divIcon({{
                    className: 'hop-label',
                    html: `<div style="background: #333; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; font-weight: bold;">${{props.hop}}</div>`,
                    iconSize: [20, 16],
                    iconAnchor: [10, -8]
                }});
                L.marker([coords[1], coords[0]], {{ icon: label }}).addTo(map);

            }} else if (feature.geometry.type === 'LineString') {{
                const coords = feature.geometry.coordinates.map(c => [c[1], c[0]]);
                const props = feature.properties;

                L.polyline(coords, {{
                    color: props.color,
                    weight: 3,
                    opacity: props.is_timeout ? 0.4 : 0.8,
                    dashArray: props.is_timeout ? '5, 10' : null
                }}).addTo(map);
            }}
        }});

        // Fit bounds to show all points
        if (points.length > 0) {{
            map.fitBounds(points, {{ padding: [50, 50] }});
        }}
    </script>
</body>
</html>
"""


def export_html(trace: TraceRun, output_path: Path) -> None:
    """
    Export trace to interactive HTML with Leaflet.js map.

    Args:
        trace: The trace to export
        output_path: Path to write HTML file
    """
    geojson = _hop_to_geojson(trace)

    html = HTML_TEMPLATE.format(
        host=trace.meta.host,
        total_hops=trace.total_hops,
        responded_hops=trace.responded_hops,
        timeout_hops=trace.timeout_hops,
        avg_loss=trace.avg_loss_pct,
        protocol=trace.meta.protocol.upper(),
        geojson=json.dumps(geojson),
    )

    output_path.write_text(html, encoding="utf-8")
