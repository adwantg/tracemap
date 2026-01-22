"""
Rendering engine for traceroute visualization.

Provides:
- ASCII world map rendering (basic)
- Braille/Unicode block rendering (high-resolution)
- Rich table output for hop information
- Color-coded RTT/loss indicators

Author: gadwant
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich import box

from .models import Hop, TraceRun

# ============================================================================
# World Map Data
# ============================================================================

# Coarse continent outline points (lon, lat) for basic ASCII map
CONTINENT_DOTS = [
    # North America
    (-130, 55), (-125, 60), (-120, 65), (-100, 70), (-80, 70), (-60, 65),
    (-120, 60), (-110, 55), (-100, 50), (-90, 45), (-80, 40), (-75, 35),
    (-80, 30), (-90, 30), (-100, 30), (-105, 25), (-110, 30), (-115, 32),
    (-120, 35), (-125, 40), (-125, 48),
    # Central America & Caribbean
    (-90, 20), (-85, 15), (-80, 10), (-75, 10),
    # South America
    (-80, 10), (-75, 5), (-80, 0), (-75, -5), (-70, -10), (-65, -15),
    (-60, -20), (-55, -25), (-50, -25), (-45, -20), (-40, -15), (-35, -10),
    (-35, -5), (-50, 0), (-55, 5), (-60, 5), (-65, 0), (-70, -5),
    (-75, -35), (-72, -45), (-75, -52),
    # Europe
    (-10, 60), (-5, 58), (0, 55), (5, 52), (10, 55), (15, 55), (20, 55),
    (25, 55), (30, 55), (25, 60), (20, 65), (10, 70), (25, 70), (30, 68),
    (-5, 50), (0, 48), (5, 45), (10, 45), (15, 42), (10, 40), (5, 38),
    (0, 40), (-5, 43), (-10, 43),
    # Africa
    (-15, 30), (-5, 35), (10, 35), (20, 32), (30, 30), (35, 25), (40, 15),
    (50, 10), (45, 0), (40, -5), (35, -15), (30, -25), (25, -33), (20, -35),
    (15, -30), (10, -5), (5, 5), (0, 5), (-5, 5), (-10, 5), (-15, 10),
    (-15, 20),
    # Asia
    (35, 35), (40, 40), (45, 45), (50, 50), (60, 55), (70, 55), (80, 55),
    (90, 50), (100, 50), (110, 45), (120, 45), (130, 45), (140, 45), (145, 50),
    (150, 55), (160, 60), (170, 65), (180, 65),
    (70, 30), (75, 25), (80, 20), (85, 25), (90, 25), (95, 20), (100, 15),
    (105, 10), (110, 5), (115, 5), (120, 10), (125, 15), (130, 25), (135, 35),
    # Southeast Asia / Indonesia
    (100, 5), (105, 0), (110, -5), (115, -8), (120, -8), (130, -5), (140, -5),
    # Australia
    (115, -20), (120, -18), (130, -15), (140, -15), (150, -20), (153, -25),
    (150, -35), (145, -38), (140, -35), (135, -32), (130, -30), (125, -25),
    (120, -20),
    # New Zealand
    (170, -35), (175, -40), (178, -45),
]


# ============================================================================
# Color Configuration
# ============================================================================

class RTTLevel(Enum):
    """RTT level for color coding."""
    LOW = "low"      # < 50ms - green
    MED = "med"      # 50-150ms - yellow
    HIGH = "high"    # > 150ms - red
    TIMEOUT = "timeout"


def get_rtt_level(rtt_ms: Optional[float]) -> RTTLevel:
    """Determine RTT level for color coding."""
    if rtt_ms is None:
        return RTTLevel.TIMEOUT
    if rtt_ms < 50:
        return RTTLevel.LOW
    if rtt_ms < 150:
        return RTTLevel.MED
    return RTTLevel.HIGH


RTT_COLORS = {
    RTTLevel.LOW: "green",
    RTTLevel.MED: "yellow",
    RTTLevel.HIGH: "red",
    RTTLevel.TIMEOUT: "dim",
}

LOSS_COLORS = {
    0: "green",
    1: "yellow",   # 1-33%
    2: "red",      # > 33%
}


def get_loss_color(loss_pct: float) -> str:
    """Get color for packet loss percentage."""
    if loss_pct == 0:
        return LOSS_COLORS[0]
    if loss_pct <= 33:
        return LOSS_COLORS[1]
    return LOSS_COLORS[2]


# ============================================================================
# Map Configuration
# ============================================================================

@dataclass
class MapConfig:
    """Configuration for map rendering."""
    width: int = 120
    height: int = 32
    lat_min: float = -70
    lat_max: float = 70
    lon_min: float = -180
    lon_max: float = 180
    use_braille: bool = False  # Use braille characters for higher resolution
    show_legend: bool = True
    path_char: str = "•"
    land_char: str = "·"
    background_char: str = " "  # Empty/background character
    marker_style: str = "number"  # "number", "letter", "dot"


@dataclass
class BrailleMapConfig(MapConfig):
    """Configuration for braille-based map rendering."""
    use_braille: bool = True
    # Braille gives 2x4 subpixel resolution per character
    # Effective resolution: width*2 x height*4

    @property
    def effective_width(self) -> int:
        return self.width * 2

    @property
    def effective_height(self) -> int:
        return self.height * 4


# ============================================================================
# Projection and Geometry
# ============================================================================

def _project(lat: float, lon: float, cfg: MapConfig) -> Tuple[int, int]:
    """Equirectangular projection into grid coordinates (x, y)."""
    x = int((lon - cfg.lon_min) / (cfg.lon_max - cfg.lon_min) * (cfg.width - 1))
    # y: top=0 is lat_max
    y = int((cfg.lat_max - lat) / (cfg.lat_max - cfg.lat_min) * (cfg.height - 1))
    x = max(0, min(cfg.width - 1, x))
    y = max(0, min(cfg.height - 1, y))
    return x, y


def _project_braille(lat: float, lon: float, cfg: BrailleMapConfig) -> Tuple[int, int]:
    """Project to braille subpixel coordinates."""
    x = int((lon - cfg.lon_min) / (cfg.lon_max - cfg.lon_min) * (cfg.effective_width - 1))
    y = int((cfg.lat_max - lat) / (cfg.lat_max - cfg.lat_min) * (cfg.effective_height - 1))
    x = max(0, min(cfg.effective_width - 1, x))
    y = max(0, min(cfg.effective_height - 1, y))
    return x, y


def _bresenham(a: Tuple[int, int], b: Tuple[int, int]) -> List[Tuple[int, int]]:
    """Bresenham's line algorithm for drawing lines between points."""
    x0, y0 = a
    x1, y1 = b
    points = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return points


def _great_circle_points(
    lat1: float, lon1: float, lat2: float, lon2: float, num_points: int = 20
) -> List[Tuple[float, float]]:
    """
    Generate points along a great circle arc between two coordinates.

    This produces curved paths on the map that better represent actual flight/data paths.
    """
    points = []

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Angular distance
    d = 2 * math.asin(math.sqrt(
        (math.sin((lat2_rad - lat1_rad) / 2)) ** 2 +
        math.cos(lat1_rad) * math.cos(lat2_rad) *
        (math.sin((lon2_rad - lon1_rad) / 2)) ** 2
    ))

    if d < 0.001:  # Very short distance, just straight line
        return [(lat1, lon1), (lat2, lon2)]

    for i in range(num_points + 1):
        f = i / num_points

        a = math.sin((1 - f) * d) / math.sin(d)
        b = math.sin(f * d) / math.sin(d)

        x = a * math.cos(lat1_rad) * math.cos(lon1_rad) + b * math.cos(lat2_rad) * math.cos(lon2_rad)
        y = a * math.cos(lat1_rad) * math.sin(lon1_rad) + b * math.cos(lat2_rad) * math.sin(lon2_rad)
        z = a * math.sin(lat1_rad) + b * math.sin(lat2_rad)

        lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
        lon = math.degrees(math.atan2(y, x))

        points.append((lat, lon))

    return points


# ============================================================================
# Braille Rendering
# ============================================================================

# Braille character encoding
# Each braille character is a 2x4 dot matrix
# Dots are numbered:
#   1 4
#   2 5
#   3 6
#   7 8
# Unicode offset: 0x2800
BRAILLE_BASE = 0x2800


def _dots_to_braille(dots: List[Tuple[int, int]]) -> str:
    """
    Convert a list of dot positions to a braille character.

    Dot positions are (x, y) where x is 0-1 and y is 0-3.
    """
    bits = 0
    for x, y in dots:
        if x == 0:
            if y == 0:
                bits |= 0x01  # dot 1
            elif y == 1:
                bits |= 0x02  # dot 2
            elif y == 2:
                bits |= 0x04  # dot 3
            elif y == 3:
                bits |= 0x40  # dot 7
        else:  # x == 1
            if y == 0:
                bits |= 0x08  # dot 4
            elif y == 1:
                bits |= 0x10  # dot 5
            elif y == 2:
                bits |= 0x20  # dot 6
            elif y == 3:
                bits |= 0x80  # dot 8

    return chr(BRAILLE_BASE + bits)


class BrailleCanvas:
    """Canvas for braille rendering with subpixel resolution."""

    def __init__(self, width: int, height: int):
        """
        Initialize canvas.

        Args:
            width: Character width
            height: Character height

        The effective resolution is width*2 x height*4 subpixels.
        """
        self.width = width
        self.height = height
        # Subpixel grid
        self._dots: set[Tuple[int, int]] = set()

    def set_dot(self, x: int, y: int) -> None:
        """Set a subpixel dot."""
        if 0 <= x < self.width * 2 and 0 <= y < self.height * 4:
            self._dots.add((x, y))

    def draw_line(self, x0: int, y0: int, x1: int, y1: int) -> None:
        """Draw a line between two subpixel coordinates."""
        for x, y in _bresenham((x0, y0), (x1, y1)):
            self.set_dot(x, y)

    def render(self) -> List[str]:
        """Render the canvas to a list of strings."""
        lines = []
        for cy in range(self.height):
            row = []
            for cx in range(self.width):
                # Get dots in this character cell
                dots = []
                for dx in range(2):
                    for dy in range(4):
                        sx = cx * 2 + dx
                        sy = cy * 4 + dy
                        if (sx, sy) in self._dots:
                            dots.append((dx, dy))

                if dots:
                    row.append(_dots_to_braille(dots))
                else:
                    row.append(" ")

            lines.append("".join(row))

        return lines


# ============================================================================
# ASCII Map Rendering
# ============================================================================

def _empty_grid(cfg: MapConfig) -> List[List[str]]:
    """Create an empty character grid."""
    return [[" " for _ in range(cfg.width)] for _ in range(cfg.height)]


def _draw_background(grid: List[List[str]], cfg: MapConfig) -> None:
    """Draw continent outlines on the grid."""
    for lon, lat in CONTINENT_DOTS:
        x, y = _project(lat, lon, cfg)
        if grid[y][x] == " ":
            grid[y][x] = cfg.land_char


def _draw_path(grid: List[List[str]], hops: List[Hop], cfg: MapConfig, use_great_circle: bool = True) -> None:
    """Draw path lines between hops."""
    pts: List[Tuple[int, int]] = []
    geo_hops = [h for h in hops if h.geo]

    for h in geo_hops:
        if h.geo:
            pts.append(_project(h.geo.lat, h.geo.lon, cfg))

    if use_great_circle and len(geo_hops) >= 2:
        # Draw great circle arcs
        for i in range(1, len(geo_hops)):
            prev_hop = geo_hops[i - 1]
            curr_hop = geo_hops[i]

            if prev_hop.geo and curr_hop.geo:
                arc_points = _great_circle_points(
                    prev_hop.geo.lat, prev_hop.geo.lon,
                    curr_hop.geo.lat, curr_hop.geo.lon,
                    num_points=15
                )

                for j in range(1, len(arc_points)):
                    ax, ay = _project(arc_points[j-1][0], arc_points[j-1][1], cfg)
                    bx, by = _project(arc_points[j][0], arc_points[j][1], cfg)

                    for x, y in _bresenham((ax, ay), (bx, by)):
                        if grid[y][x] == " " or grid[y][x] == cfg.land_char:
                            grid[y][x] = cfg.path_char
    else:
        # Simple straight lines
        for i in range(1, len(pts)):
            for x, y in _bresenham(pts[i - 1], pts[i]):
                if grid[y][x] == " " or grid[y][x] == cfg.land_char:
                    grid[y][x] = cfg.path_char


def _draw_markers(grid: List[List[str]], hops: List[Hop], cfg: MapConfig) -> None:
    """
    Draw hop markers on the grid.
    
    Handles overlapping markers by showing the first hop number
    and marking clusters with a special indicator.
    """
    # Track which grid positions have hops
    hop_positions: Dict[Tuple[int, int], List[int]] = {}
    
    # Collect all hop positions
    for h in hops:
        if not h.geo:
            continue
        
        x, y = _project(h.geo.lat, h.geo.lon, cfg)
        pos = (x, y)
        
        if pos not in hop_positions:
            hop_positions[pos] = []
        hop_positions[pos].append(h.hop)
    
    # Draw markers
    for (x, y), hop_nums in hop_positions.items():
        if cfg.marker_style == "number":
            if len(hop_nums) == 1:
                # Single hop - show its number
                mark = str(hop_nums[0] % 10)
            else:
                # Multiple hops - show first with cluster indicator
                # e.g., "3+" means hops 3,4,5... at same location
                mark = f"{hop_nums[0]%10}+"
                # If it won't fit, just show the marker
                if x + 1 < cfg.width and grid[y][x + 1] == cfg.background_char:
                    grid[y][x + 1] = "+"
                mark = str(hop_nums[0] % 10)
        elif cfg.marker_style == "letter":
            mark = chr(ord('A') + (hop_nums[0] - 1) % 26)
            if len(hop_nums) > 1:
                # Add + for clusters
                if x + 1 < cfg.width and grid[y][x + 1] == cfg.background_char:
                    grid[y][x + 1] = "+"
        else:
            mark = "●"
        
        grid[y][x] = mark


def render_static(trace: TraceRun, cfg: Optional[MapConfig] = None) -> str:
    """
    Render a trace as a static ASCII/Unicode map.

    Args:
        trace: The trace to render
        cfg: Map configuration

    Returns:
        String representation of the map
    """
    cfg = cfg or MapConfig()

    grid = _empty_grid(cfg)
    _draw_background(grid, cfg)
    _draw_path(grid, trace.hops, cfg)
    _draw_markers(grid, trace.hops, cfg)

    lines = ["".join(row) for row in grid]

    # Header
    header = f"tracemap: {trace.meta.host}"
    if trace.meta.resolved_ip:
        header += f" ({trace.meta.resolved_ip})"
    header += f"  hops={trace.total_hops}  responded={trace.responded_hops}"

    output = [header]

    if cfg.show_legend:
        legend = f"legend: {cfg.land_char} land  {cfg.path_char} path  0-9 hop markers  + clustered hops"
        output.append(legend)

    output.append("")
    output.extend(lines)

    # Alerts
    alerts = trace.get_detour_alerts()
    if alerts:
        output.append("")
        for alert in alerts[:3]:  # Show max 3 alerts
            output.append(f"⚠️  {alert}")

    return "\n".join(output)


def render_braille(trace: TraceRun, cfg: Optional[BrailleMapConfig] = None) -> str:
    """
    Render a trace using braille characters for higher resolution.

    Args:
        trace: The trace to render
        cfg: Braille map configuration

    Returns:
        String representation of the braille map
    """
    cfg = cfg or BrailleMapConfig()

    canvas = BrailleCanvas(cfg.width, cfg.height)

    # Draw continent outlines
    for lon, lat in CONTINENT_DOTS:
        x, y = _project_braille(lat, lon, cfg)
        canvas.set_dot(x, y)

    # Draw paths with great circle arcs
    geo_hops = [h for h in trace.hops if h.geo]

    for i in range(1, len(geo_hops)):
        prev_hop = geo_hops[i - 1]
        curr_hop = geo_hops[i]

        if prev_hop.geo and curr_hop.geo:
            arc_points = _great_circle_points(
                prev_hop.geo.lat, prev_hop.geo.lon,
                curr_hop.geo.lat, curr_hop.geo.lon,
                num_points=30
            )

            for j in range(1, len(arc_points)):
                ax, ay = _project_braille(arc_points[j-1][0], arc_points[j-1][1], cfg)
                bx, by = _project_braille(arc_points[j][0], arc_points[j][1], cfg)
                canvas.draw_line(ax, ay, bx, by)

    # Render
    lines = canvas.render()

    # Overlay hop markers (use regular characters)
    for h in trace.hops:
        if h.geo:
            x, y = _project(h.geo.lat, h.geo.lon, MapConfig(width=cfg.width, height=cfg.height))
            marker = str(h.hop % 10)
            if 0 <= y < len(lines) and 0 <= x < len(lines[y]):
                row = list(lines[y])
                row[x] = marker
                lines[y] = "".join(row)

    # Header
    header = f"tracemap: {trace.meta.host}  hops={trace.total_hops}"
    output = [header, ""] + lines

    return "\n".join(output)


# ============================================================================
# Rich Table Output
# ============================================================================

def _hop_table(trace: TraceRun, show_asn: bool = True, max_consecutive_timeouts: int = 3) -> Table:
    """
    Render hop information as a Rich table.
    
    Stops displaying hops after max_consecutive_timeouts to avoid cluttering
    output with endless rows of asterisks (MTR-style behavior).
    
    Args:
        trace: The trace result
        show_asn: Whether to include ASN column
        max_consecutive_timeouts: Stop after this many consecutive timeout hops
    
    Returns:
        Rich Table with hop information
    """
    t = Table(show_header=True, header_style="bold", box=box.ROUNDED)

    t.add_column("#", justify="right", width=5)
    t.add_column("IP", width=17)
    t.add_column("Hostname", width=10)
    t.add_column("Avg RTT", justify="right", width=12)
    t.add_column("Min/Max", justify="right", width=14)
    t.add_column("Loss", justify="right", width=8)

    if show_asn:
        t.add_column("ASN", width=22)

    t.add_column("Geo", width=28)

    consecutive_timeouts = 0
    cutoff_hop = None
    last_real_hop = None

    for hop in trace.hops:
        # Track consecutive timeouts
        if hop.is_timeout:
            consecutive_timeouts += 1
        else:
            consecutive_timeouts = 0
            last_real_hop = hop.hop

        # Build row
        hop_num = str(hop.hop)
        ip_str = hop.ip or "*"
        hostname_str = hop.hostname or ""

        # RTT stats
        if hop.rtt_avg_ms is not None:
            avg_rtt = f"{hop.rtt_avg_ms:.1f} ms"
            min_max = f"{hop.rtt_min_ms:.1f}/{hop.rtt_max_ms:.1f}"
        else:
            avg_rtt = "-"
            min_max = ""

        # Loss
        loss_str = f"{hop.loss_pct:.0f}%"

        # Color based on RTT
        rtt_level = get_rtt_level(hop.rtt_avg_ms)
        rtt_color = RTT_COLORS.get(rtt_level, "white")

        # ASN info
        asn_str = ""
        if hop.geo and hop.geo.asn:
            asn_str = f"AS{hop.geo.asn}"
            if hop.geo.asn_org:
                # Wrap long org names
                org = hop.geo.asn_org
                if len(org) > 20:
                    org = org[:17] + "..."
                asn_str += f" ({org})"

        # Geo info
        geo_str = ""
        if hop.geo:
            parts = []
            if hop.geo.city:
                parts.append(hop.geo.city)
            if hop.geo.country:
                parts.append(hop.geo.country)
            geo_str = ", ".join(parts)

        # Build final row
        row = [
            hop_num,
            f"[{rtt_color}]{ip_str}[/{rtt_color}]",
            hostname_str,
            f"[{rtt_color}]{avg_rtt}[/{rtt_color}]",
            min_max,
            loss_str,
        ]

        if show_asn:
            row.append(asn_str)

        row.append(geo_str)

        t.add_row(*row)

        # Check if we should stop after this row
        if consecutive_timeouts >= max_consecutive_timeouts:
            cutoff_hop = hop.hop
            break

    # Add summary row if we cut off
    if cutoff_hop:
        remaining = trace.total_hops - cutoff_hop
        if remaining > 0:
            # Add empty row for spacing
            col_count = 8 if show_asn else 7
            t.add_row(*[""] * col_count)
            
            # Add summary message
            summary_text = f"[dim italic]({remaining} more timeout hops not shown - destination likely reached or firewalled)[/dim italic]"
            t.add_row(summary_text, *[""] * (col_count - 1))

    return t


def render_frame(trace: TraceRun) -> Panel:
    """
    Render a trace as a Rich Panel for live updating.

    Args:
        trace: The trace to render

    Returns:
        Rich Panel containing map and status
    """
    map_txt = Text(render_static(trace))
    table = _hop_table(trace, show_asn=True)

    # Summary
    summary_parts = [
        f"Host: {trace.meta.host}",
        f"Hops: {trace.total_hops}",
        f"Responded: {trace.responded_hops}",
        f"Timeouts: {trace.timeout_hops}",
    ]

    if trace.avg_loss_pct > 0:
        summary_parts.append(f"Avg Loss: {trace.avg_loss_pct:.1f}%")

    summary = " | ".join(summary_parts)

    content = Text.assemble(map_txt, "\n\n")

    return Panel.fit(
        content,
        title="Traceroute Map (live)",
        subtitle=summary,
    )


def render_full(trace: TraceRun, console: Optional[Console] = None) -> None:
    """
    Render a complete trace output with map and table.

    Args:
        trace: The trace to render
        console: Rich console (creates new if not provided)
    """
    console = console or Console()

    # Map
    console.print(Panel(render_static(trace), title="World Map"))

    # Hop table
    console.print()
    console.print(_hop_table(trace))

    # Alerts
    alerts = trace.get_detour_alerts()
    if alerts:
        console.print()
        for alert in alerts:
            console.print(f"[yellow]⚠️  {alert}[/yellow]")

    # Stats
    console.print()
    console.print(f"[dim]Total hops: {trace.total_hops} | "
                  f"Responded: {trace.responded_hops} | "
                  f"Timeouts: {trace.timeout_hops} | "
                  f"Avg Loss: {trace.avg_loss_pct:.1f}%[/dim]")


def render_live(*args, **kwargs):
    """Placeholder for live rendering (handled in trace.run_traceroute)."""
    raise NotImplementedError("Live rendering is handled by run_traceroute")
