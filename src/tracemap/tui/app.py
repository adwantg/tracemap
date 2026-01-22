"""
Main Textual TUI application for tracemap.

Provides an interactive terminal interface with:
- World map panel with hop visualization
- Hop table with RTT, loss, ASN information  
- Summary panel with alerts and statistics
- Keyboard navigation and real-time updates

Author: gadwant
"""
from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, Static

from ..models import Hop, TraceRun
from ..render import render_static, MapConfig


class MapPanel(Static):
    """World map panel showing hop locations and paths."""

    trace: reactive[Optional[TraceRun]] = reactive(None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.border_title = "World Map"

    def watch_trace(self, trace: Optional[TraceRun]) -> None:
        """Update map when trace changes."""
        if trace:
            map_text = render_static(trace, MapConfig(width=100, height=24))
            self.update(map_text)
        else:
            self.update("Waiting for trace data...")


class SummaryPanel(Static):
    """Summary panel showing trace metadata and alerts."""

    trace: reactive[Optional[TraceRun]] = reactive(None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.border_title = "Summary"

    def watch_trace(self, trace: Optional[TraceRun]) -> None:
        """Update summary when trace changes."""
        if not trace:
            self.update("No trace data")
            return

        lines = []
        lines.append(f"[bold]Target:[/bold] {trace.meta.host}")
        if trace.meta.resolved_ip:
            lines.append(f"[bold]Resolved:[/bold] {trace.meta.resolved_ip}")
        lines.append(f"[bold]Protocol:[/bold] {trace.meta.protocol.upper()}")
        lines.append("")
        lines.append(f"[cyan]Total Hops:[/cyan] {trace.total_hops}")
        lines.append(f"[green]Responded:[/green] {trace.responded_hops}")
        lines.append(f"[yellow]Timeouts:[/yellow] {trace.timeout_hops}")
        lines.append(f"[red]Avg Loss:[/red] {trace.avg_loss_pct:.1f}%")

        # Alerts
        alerts = trace.get_detour_alerts()
        if alerts:
            lines.append("")
            lines.append("[bold red]⚠️ Alerts:[/bold red]")
            for alert in alerts[:3]:
                lines.append(f"  • {alert}")

        self.update("\n".join(lines))


class HopTable(DataTable):
    """Table showing hop details with color-coded RTT/loss."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cursor_type = "row"
        self.zebra_stripes = True

    def setup_columns(self, show_asn: bool = True) -> None:
        """Set up table columns."""
        self.clear(columns=True)
        self.add_column("#", width=3)
        self.add_column("IP", width=16)
        self.add_column("Hostname", width=22)
        self.add_column("Avg RTT", width=10)
        self.add_column("Min/Max", width=14)
        self.add_column("Loss", width=6)
        if show_asn:
            self.add_column("ASN", width=18)
        self.add_column("Location", width=20)

    def update_hops(self, hops: list[Hop], show_asn: bool = True) -> None:
        """Update table with hop data."""
        self.clear()
        self.setup_columns(show_asn)

        for hop in hops:
            # Color based on RTT
            rtt_style = "green"
            if hop.rtt_avg_ms is not None:
                if hop.rtt_avg_ms >= 150:
                    rtt_style = "red"
                elif hop.rtt_avg_ms >= 50:
                    rtt_style = "yellow"
            elif hop.is_timeout:
                rtt_style = "dim"

            # Color based on loss
            loss_style = "green"
            if hop.loss_pct > 33:
                loss_style = "red"
            elif hop.loss_pct > 0:
                loss_style = "yellow"

            # Format values
            avg_rtt = f"{hop.rtt_avg_ms:.1f} ms" if hop.rtt_avg_ms else "-"
            min_max = ""
            if hop.rtt_min_ms and hop.rtt_max_ms:
                min_max = f"{hop.rtt_min_ms:.1f}/{hop.rtt_max_ms:.1f}"

            row = [
                str(hop.hop),
                hop.display_ip,
                hop.hostname or "",
                f"[{rtt_style}]{avg_rtt}[/]",
                min_max,
                f"[{loss_style}]{hop.loss_pct:.0f}%[/]",
            ]

            if show_asn:
                row.append(hop.display_asn[:18] if hop.display_asn else "")

            row.append(hop.display_geo[:20] if hop.display_geo else "")

            self.add_row(*row)


class TraceMapApp(App):
    """Main tracemap TUI application."""

    TITLE = "Tracemap TUI"
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 2fr 1fr;
        grid-rows: 2fr 1fr;
    }

    #map-panel {
        column-span: 1;
        row-span: 1;
        border: round #444;
        background: $surface;
        padding: 0 1;
    }

    #hop-table-container {
        column-span: 1;
        row-span: 2;
        border: round #444;
        background: $surface;
    }

    #summary-panel {
        column-span: 1;
        row-span: 1;
        border: round #444;
        background: $surface;
        padding: 1;
    }

    HopTable {
        height: 100%;
    }

    MapPanel {
        height: 100%;
        overflow: auto;
    }

    SummaryPanel {
        height: 100%;
        overflow: auto;
    }

    .rtt-low { color: $success; }
    .rtt-med { color: $warning; }
    .rtt-high { color: $error; }
    .timeout { color: $text-muted; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("e", "export", "Export HTML"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("enter", "show_details", "Details"),
    ]

    trace: reactive[Optional[TraceRun]] = reactive(None)

    def __init__(self, trace: Optional[TraceRun] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_trace = trace

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()

        yield MapPanel(id="map-panel")
        yield Container(HopTable(id="hop-table"), id="hop-table-container")
        yield SummaryPanel(id="summary-panel")

        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        # Set border titles
        self.query_one("#hop-table-container").border_title = "Hop Details"

        if self._initial_trace:
            self.trace = self._initial_trace

    def watch_trace(self, trace: Optional[TraceRun]) -> None:
        """Update all panels when trace changes."""
        if not trace:
            return

        # Update map
        map_panel = self.query_one(MapPanel)
        map_panel.trace = trace

        # Update summary
        summary_panel = self.query_one(SummaryPanel)
        summary_panel.trace = trace

        # Update hop table
        hop_table = self.query_one(HopTable)
        hop_table.update_hops(trace.hops)

    def action_refresh(self) -> None:
        """Refresh the display."""
        if self.trace:
            self.watch_trace(self.trace)

    def action_export(self) -> None:
        """Export trace to HTML."""
        if not self.trace:
            self.notify("No trace to export", severity="warning")
            return

        try:
            from pathlib import Path
            from ..export.html import export_html

            output_path = Path(".tracemap/trace.html")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            export_html(self.trace, output_path)
            self.notify(f"Exported to {output_path}", severity="information")
        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error")

    def action_show_details(self) -> None:
        """Show details for selected hop."""
        hop_table = self.query_one(HopTable)
        if hop_table.cursor_row is not None and self.trace:
            idx = hop_table.cursor_row
            if 0 <= idx < len(self.trace.hops):
                hop = self.trace.hops[idx]
                self._show_hop_details(hop)

    def _show_hop_details(self, hop: Hop) -> None:
        """Display hop details notification."""
        lines = [
            f"Hop {hop.hop}: {hop.display_ip}",
        ]
        if hop.hostname:
            lines.append(f"Hostname: {hop.hostname}")
        if hop.rtt_avg_ms:
            lines.append(f"RTT: {hop.rtt_avg_ms:.1f}ms (min: {hop.rtt_min_ms:.1f}, max: {hop.rtt_max_ms:.1f})")
        if hop.jitter_ms:
            lines.append(f"Jitter: {hop.jitter_ms:.2f}ms")
        lines.append(f"Loss: {hop.loss_pct:.0f}%")
        if hop.display_geo:
            lines.append(f"Location: {hop.display_geo}")
        if hop.display_asn:
            lines.append(f"ASN: {hop.display_asn}")

        self.notify("\n".join(lines), title=f"Hop {hop.hop} Details", timeout=10)

    def update_trace(self, trace: TraceRun) -> None:
        """Update the trace data (for live updates)."""
        self.trace = trace


def run_tui(trace: Optional[TraceRun] = None) -> None:
    """Run the TUI application."""
    app = TraceMapApp(trace=trace)
    app.run()


if __name__ == "__main__":
    # Demo with sample data
    run_tui()
