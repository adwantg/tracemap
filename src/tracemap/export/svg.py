"""
SVG export for traceroute visualization.

Generates a static SVG image with:
- World map outline
- Hop markers with numbers
- Path lines between hops (curved great-circle approximation)
- Legend and metadata

Author: gadwant
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Tuple

from ..models import Hop, TraceRun

# Simple world map outline for SVG (more detailed than ASCII version)
# Points are (lon, lat) pairs forming continent outlines
WORLD_OUTLINE = [
    # North America
    [
        (-168, 65),
        (-140, 70),
        (-120, 68),
        (-100, 70),
        (-80, 72),
        (-60, 65),
        (-80, 45),
        (-70, 42),
        (-75, 35),
        (-80, 32),
        (-82, 28),
        (-88, 28),
        (-97, 26),
        (-104, 30),
        (-117, 32),
        (-122, 37),
        (-125, 42),
        (-124, 48),
        (-130, 55),
        (-168, 65),
    ],
    # South America
    [
        (-82, 8),
        (-75, 5),
        (-70, 2),
        (-50, -2),
        (-35, -8),
        (-40, -22),
        (-55, -25),
        (-58, -38),
        (-68, -50),
        (-75, -52),
        (-70, -45),
        (-72, -35),
        (-70, -18),
        (-82, 8),
    ],
    # Europe
    [
        (-10, 60),
        (0, 50),
        (10, 55),
        (25, 60),
        (30, 70),
        (40, 68),
        (35, 60),
        (28, 45),
        (25, 38),
        (10, 38),
        (0, 45),
        (-10, 45),
        (-10, 60),
    ],
    # Africa
    [
        (-18, 28),
        (-12, 15),
        (-18, 8),
        (-5, 5),
        (10, 4),
        (15, -15),
        (35, -20),
        (28, -35),
        (20, -35),
        (12, -5),
        (42, 12),
        (52, 28),
        (35, 32),
        (10, 35),
        (-5, 35),
        (-18, 28),
    ],
    # Asia
    [
        (25, 38),
        (35, 35),
        (60, 42),
        (75, 35),
        (90, 22),
        (104, 22),
        (108, 12),
        (120, 22),
        (130, 35),
        (145, 45),
        (155, 60),
        (170, 68),
        (180, 68),
        (180, 70),
        (100, 78),
        (70, 75),
        (50, 65),
        (40, 55),
        (25, 38),
    ],
    # Australia
    [
        (113, -22),
        (125, -15),
        (145, -15),
        (153, -28),
        (150, -38),
        (140, -38),
        (130, -32),
        (118, -35),
        (113, -22),
    ],
]


def _project_equirectangular(
    lat: float, lon: float, width: int, height: int, padding: int = 40
) -> Tuple[float, float]:
    """Project lat/lon to SVG coordinates."""
    # Map bounds
    lon_min, lon_max = -180, 180
    lat_min, lat_max = -70, 85

    x = padding + (lon - lon_min) / (lon_max - lon_min) * (width - 2 * padding)
    y = padding + (lat_max - lat) / (lat_max - lat_min) * (height - 2 * padding)

    return x, y


def _great_circle_points(
    lat1: float, lon1: float, lat2: float, lon2: float, num_points: int = 20
) -> List[Tuple[float, float]]:
    """Generate points along a great circle arc."""
    points = []

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Angular distance
    d = 2 * math.asin(
        math.sqrt(
            (math.sin((lat2_rad - lat1_rad) / 2)) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * (math.sin((lon2_rad - lon1_rad) / 2)) ** 2
        )
    )

    if d < 0.001:
        return [(lat1, lon1), (lat2, lon2)]

    for i in range(num_points + 1):
        f = i / num_points

        a = math.sin((1 - f) * d) / math.sin(d)
        b = math.sin(f * d) / math.sin(d)

        x = a * math.cos(lat1_rad) * math.cos(lon1_rad) + b * math.cos(lat2_rad) * math.cos(
            lon2_rad
        )
        y = a * math.cos(lat1_rad) * math.sin(lon1_rad) + b * math.cos(lat2_rad) * math.sin(
            lon2_rad
        )
        z = a * math.sin(lat1_rad) + b * math.sin(lat2_rad)

        lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
        lon = math.degrees(math.atan2(y, x))

        points.append((lat, lon))

    return points


def _get_marker_color(hop: Hop) -> str:
    """Get marker color based on RTT and loss."""
    if hop.is_timeout:
        return "#9E9E9E"
    if hop.loss_pct > 50:
        return "#F44336"
    if hop.rtt_avg_ms is None:
        return "#9E9E9E"
    if hop.rtt_avg_ms < 50:
        return "#4CAF50"
    if hop.rtt_avg_ms < 150:
        return "#FFC107"
    return "#F44336"


def generate_svg(
    trace: TraceRun,
    width: int = 1200,
    height: int = 600,
) -> str:
    """
    Generate SVG content for a trace.

    Args:
        trace: The trace to visualize
        width: SVG width in pixels
        height: SVG height in pixels

    Returns:
        SVG content as string
    """
    padding = 40
    svg_parts = []

    # SVG header
    svg_parts.append(f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
  <defs>
    <style>
      .land {{ fill: none; stroke: #BDBDBD; stroke-width: 1; }}
      .path-line {{ fill: none; stroke-width: 2.5; stroke-linecap: round; }}
      .hop-marker {{ stroke: #fff; stroke-width: 2; }}
      .hop-label {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 10px; font-weight: bold; fill: #fff; text-anchor: middle; dominant-baseline: central; }}
      .title {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 16px; font-weight: bold; fill: #333; }}
      .subtitle {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 12px; fill: #666; }}
      .legend-text {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 10px; fill: #666; }}
    </style>
  </defs>

  <!-- Background -->
  <rect width="{width}" height="{height}" fill="#FAFAFA"/>
''')

    # Draw world outline
    svg_parts.append("  <!-- World outline -->")
    for continent in WORLD_OUTLINE:
        points = []
        for lon, lat in continent:
            x, y = _project_equirectangular(lat, lon, width, height, padding)
            points.append(f"{x:.1f},{y:.1f}")

        if points:
            svg_parts.append(f'  <polyline class="land" points="{" ".join(points)}"/>')

    # Draw path lines
    geo_hops = [h for h in trace.hops if h.geo]
    svg_parts.append("  <!-- Path lines -->")

    for i in range(1, len(geo_hops)):
        prev = geo_hops[i - 1]
        curr = geo_hops[i]

        if prev.geo and curr.geo:
            color = _get_marker_color(curr)
            opacity = "0.4" if curr.is_timeout else "0.7"
            dash = 'stroke-dasharray="5,5"' if curr.is_timeout else ""

            # Generate great circle arc
            arc_points = _great_circle_points(
                prev.geo.lat, prev.geo.lon, curr.geo.lat, curr.geo.lon, num_points=15
            )

            svg_points = []
            for lat, lon in arc_points:
                x, y = _project_equirectangular(lat, lon, width, height, padding)
                svg_points.append(f"{x:.1f},{y:.1f}")

            svg_parts.append(
                f'  <polyline class="path-line" stroke="{color}" opacity="{opacity}" {dash} '
                f'points="{" ".join(svg_points)}"/>'
            )

    # Draw hop markers
    svg_parts.append("  <!-- Hop markers -->")

    for hop in trace.hops:
        if not hop.geo:
            continue

        x, y = _project_equirectangular(hop.geo.lat, hop.geo.lon, width, height, padding)
        color = _get_marker_color(hop)

        # Tooltip
        tooltip_parts = [f"Hop {hop.hop}: {hop.display_ip}"]
        if hop.rtt_avg_ms:
            tooltip_parts.append(f"RTT: {hop.rtt_avg_ms:.1f}ms")
        if hop.loss_pct > 0:
            tooltip_parts.append(f"Loss: {hop.loss_pct:.0f}%")
        if hop.display_geo:
            tooltip_parts.append(hop.display_geo)
        tooltip = " | ".join(tooltip_parts)

        svg_parts.append(f'''  <g>
    <title>{tooltip}</title>
    <circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="{color}" class="hop-marker"/>
    <text x="{x:.1f}" y="{y:.1f}" class="hop-label">{hop.hop}</text>
  </g>''')

    # Title and metadata
    svg_parts.append(f'''
  <!-- Title and legend -->
  <text x="{padding}" y="25" class="title">Traceroute: {trace.meta.host}</text>
  <text x="{padding}" y="42" class="subtitle">Hops: {trace.total_hops} | Responded: {trace.responded_hops} | Timeouts: {trace.timeout_hops} | Avg Loss: {trace.avg_loss_pct:.1f}%</text>
''')

    # Legend
    legend_x = width - 150
    legend_y = height - 80
    svg_parts.append(f'''  <!-- Legend -->
  <rect x="{legend_x - 10}" y="{legend_y - 15}" width="140" height="75" fill="#fff" stroke="#E0E0E0" rx="4"/>
  <circle cx="{legend_x}" cy="{legend_y}" r="5" fill="#4CAF50"/>
  <text x="{legend_x + 15}" y="{legend_y + 4}" class="legend-text">RTT &lt; 50ms</text>
  <circle cx="{legend_x}" cy="{legend_y + 18}" r="5" fill="#FFC107"/>
  <text x="{legend_x + 15}" y="{legend_y + 22}" class="legend-text">RTT 50-150ms</text>
  <circle cx="{legend_x}" cy="{legend_y + 36}" r="5" fill="#F44336"/>
  <text x="{legend_x + 15}" y="{legend_y + 40}" class="legend-text">RTT &gt; 150ms</text>
  <circle cx="{legend_x}" cy="{legend_y + 54}" r="5" fill="#9E9E9E"/>
  <text x="{legend_x + 15}" y="{legend_y + 58}" class="legend-text">Timeout</text>
''')

    # Close SVG
    svg_parts.append("</svg>")

    return "\n".join(svg_parts)


def export_svg(trace: TraceRun, output_path: Path, **kwargs) -> None:
    """
    Export trace to static SVG.

    Args:
        trace: The trace to export
        output_path: Path to write SVG file
        **kwargs: Additional arguments passed to generate_svg
    """
    svg_content = generate_svg(trace, **kwargs)
    output_path.write_text(svg_content, encoding="utf-8")
