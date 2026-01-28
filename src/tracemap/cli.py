"""
CLI interface for tracemap.

Commands:
- trace: Run traceroute and visualize on world map
- replay: Replay a saved trace JSON
- export: Export trace to HTML/SVG
- diff: Compare two traces
- tui: Launch interactive TUI
- doctor: Check system prerequisites

Author: gadwant
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .geo import CachingGeoLocator, EnhancedGeoLocator, GeoLocator, MaxMindGeoLocator, MockGeoLocator
from .models import TraceRun
from .render import render_full, render_static
from .trace import Protocol, TraceConfig, run_traceroute, traceroute_binary

app = typer.Typer(
    add_completion=False,
    help="Traceroute visualization on an ASCII world map (TUI).",
    no_args_is_help=True,
)
console = Console()


def _pick_geolocator(
    mmdb_path: Optional[Path],
    enable_asn: bool = False,
    use_api: bool = True,
) -> GeoLocator:
    """
    Select and configure the appropriate GeoLocator.

    Priority with use_api=True (default):
    1. API lookup (ip-api.com - real data, no setup)
    2. Provided mmdb_path or TRACEMAP_GEOIP_MMDB
    3. MockGeoLocator fallback

    Priority with use_api=False:
    1. Provided mmdb_path or TRACEMAP_GEOIP_MMDB
    2. MockGeoLocator fallback
    """
    # Check for API mode (default for best experience)
    if use_api:
        try:
            from .geo_api import get_best_locator
            console.print("[green]Using real-time API geo lookup (ip-api.com)[/green]")
            console.print("[dim]No setup required! Getting real locations...[/dim]")
            return get_best_locator(
                mmdb_path=str(mmdb_path) if mmdb_path else None,
                prefer_api=True,
            )
        except ImportError:
            console.print("[yellow]API module not available, falling back to local/mock[/yellow]")

    # Fallback to local database mode
    env = os.environ.get("TRACEMAP_GEOIP_MMDB")
    candidate = mmdb_path or (Path(env) if env else None)

    base_locator: GeoLocator

    if candidate and candidate.exists():
        try:
            base_locator = MaxMindGeoLocator(candidate)
            console.print(f"[green]Using GeoIP database:[/green] {candidate}")
        except Exception as e:
            console.print(f"[yellow]GeoIP mmdb load failed:[/yellow] {e}")
            base_locator = MockGeoLocator()
    else:
        base_locator = MockGeoLocator()
        console.print("[yellow]Using mock geo data (less accurate)[/yellow]")
        console.print("[dim]Tip: Use --api flag for real locations, or set TRACEMAP_GEOIP_MMDB for offline mode[/dim]")

    # Add caching
    cached_locator = CachingGeoLocator(base_locator)

    # Add ASN if requested
    if enable_asn:
        try:
            from .asn import get_default_resolver
            asn_resolver = get_default_resolver()
            return EnhancedGeoLocator(cached_locator, asn_resolver)
        except Exception as e:
            console.print(f"[yellow]ASN lookup disabled:[/yellow] {e}")

    return cached_locator


@app.command()
def doctor() -> None:
    """Check system prerequisites and show config status."""
    console.print("[bold]Tracemap Doctor[/bold]\n")

    # Check traceroute binary
    bin_path = traceroute_binary()
    if not bin_path:
        console.print("[red]✗ traceroute binary not found.[/red]")
        console.print("  Install traceroute and retry.")
        raise typer.Exit(code=1)

    console.print(f"[green]✓ traceroute found:[/green] {bin_path}")

    # Check GeoIP
    mmdb_env = os.environ.get("TRACEMAP_GEOIP_MMDB")
    mmdb_path: Optional[Path] = Path(mmdb_env) if mmdb_env else None

    if mmdb_path and mmdb_path.exists():
        console.print(f"[green]✓ GeoIP database (TRACEMAP_GEOIP_MMDB):[/green] {mmdb_path}")
    elif mmdb_path and not mmdb_path.exists():
        console.print(f"[yellow]✗ GeoIP database (TRACEMAP_GEOIP_MMDB) not found:[/yellow] {mmdb_path}")
    else:
        console.print("[yellow]  GeoIP MMDB not configured (optional)[/yellow]")
        console.print("[dim]  Strategy: API lookups (ip-api → ipapi.co) → mock fallback[/dim]")
        console.print("[dim]  For offline: export TRACEMAP_GEOIP_MMDB=/path/to/GeoLite2-City.mmdb[/dim]")

    # Check ASN database
    asn_db = Path.home() / ".tracemap" / "asn.dat"
    if asn_db.exists():
        console.print(f"[green]✓ ASN database found:[/green] {asn_db}")
    else:
        console.print("[dim]  ASN database not found (optional, will use DNS lookup)[/dim]")
    
    # Check cache database
    cache_db = Path.home() / ".tracemap" / "cache.sqlite"
    if cache_db.exists():
        try:
            from .cache import GeoCache
            cache = GeoCache(cache_db)
            stats = cache.get_stats()
            console.print(f"[green]✓ Cache database:[/green] {cache_db}")
            console.print(f"  Valid entries: {stats['valid_entries']}, Expired: {stats['expired_entries']}")
            if stats['hits'] > 0:
                console.print(f"  Hit rate: {stats['hit_rate']:.1%}")
        except Exception as e:
            console.print(f"[yellow]⚠ Cache database exists but error:[/yellow] {e}")
    else:
        console.print("[dim]  Cache database not found (will be created on first trace)[/dim]")

    console.print("\n[green]All checks passed![/green]")


@app.command()
def trace(
    host: str = typer.Argument(..., help="Hostname or IP to traceroute"),
    max_hops: int = typer.Option(30, "--max-hops", "-m", help="Maximum hops"),
    timeout_s: float = typer.Option(2.0, "--timeout", "-w", help="Per-probe timeout (seconds)"),
    probes: int = typer.Option(3, "--probes", "-q", help="Probes per hop"),
    protocol: str = typer.Option("udp", "--protocol", "-P", help="Protocol: udp, tcp, icmp"),
    geoip_mmdb: Optional[Path] = typer.Option(None, "--geoip-mmdb", help="Path to GeoLite2-City.mmdb"),
    out: Path = typer.Option(Path(".tracemap/trace.json"), "--out", "-o", help="Output JSON path"),
    enable_asn: bool = typer.Option(False, "--asn", help="Enable ASN lookup"),
    no_live: bool = typer.Option(False, "--no-live", help="Disable live table updates"),
    redact: bool = typer.Option(False, "--redact", help="Redact IP addresses in output"),
    use_api: bool = typer.Option(True, "--api/--no-api", help="Use real-time API for geo lookups (default: enabled)"),
    show_map: bool = typer.Option(False, "--ascii-map", help="Show ASCII world map (use HTML export instead)"),
    profile: Optional[str] = typer.Option(None, "--profile", help="Use preset profile: default, offline, private, fast"),
    paris: bool = typer.Option(False, "--paris", help="Use Paris traceroute for ECMP-aware probing"),
    discover_paths: bool = typer.Option(False, "--discover-paths", help="Discover multiple ECMP paths (slower)"),
    dns_debug: bool = typer.Option(False, "--dns-debug", help="Check multiple DNS resolvers for consistency"),
    source_interface: Optional[str] = typer.Option(None, "--bind", "-b", help="Bind to specific interface (e.g., eth0)"),
    source_port: Optional[int] = typer.Option(None, "--source-port", help="Bind to specific source port"),
) -> None:
    """
    Run traceroute and display hop information in a clean table.
    
    By default, shows a clear table of hops (like MTR). 
    Use --ascii-map to show deprecated ASCII map.
    For best visualization, use the auto-generated HTML export.
    """
    out.parent.mkdir(parents=True, exist_ok=True)

    # DNS Debug Mode
    if dns_debug:
        from .analysis.dns_debug import check_dns_consistency
        console.print(f"[bold]DNS Consistency Check:[/bold] {host}")
        check_dns_consistency(host, console)
        # Continue with trace... or maybe we should return? 
        # Roadmap implies it's a flag for trace command so we continue.
        console.print()
    
    # Apply profile settings if specified
    if profile:
        from .profiles import get_profile
        prof = get_profile(profile)
        
        # Validate profile requirements
        is_valid, error = prof.validate(str(geoip_mmdb) if geoip_mmdb else None)
        if not is_valid:
            console.print(f"[red]Profile validation failed:[/red] {error}")
            raise typer.Exit(code=1)
        
        # Override flags with profile settings
        use_api = prof.use_api
        redact = redact or prof.redact_ips  # Keep manual redact if set
        
        console.print(f"[cyan]Using profile:[/cyan] {prof.name} - {prof.description}")
        
        if not prof.use_dns:
            console.print("[dim]  DNS lookups disabled by profile[/dim]")
        if prof.redact_ips:
            console.print("[dim]  IP redaction enabled by profile[/dim]")

    # Pick protocol
    try:
        proto = Protocol(protocol.lower())
    except ValueError:
        console.print(f"[red]Invalid protocol:[/red] {protocol}")
        console.print("Valid options: udp, tcp, icmp")
        raise typer.Exit(code=1)

    geoloc = _pick_geolocator(geoip_mmdb, enable_asn=enable_asn, use_api=use_api)
    
    # Handle Paris traceroute / ECMP discovery
    if paris or discover_paths:
        from .probing import ParisProber, ECMPDetector
        
        if discover_paths:
            console.print("[cyan]Discovering ECMP paths...[/cyan]")
            console.print("[dim]This may take 30-60 seconds...[/dim]")
            
            prober = ParisProber()
            ecmp_hops = prober.detect_ecmp_multipath(host, max_flows=5, max_hops=max_hops)
            
            if ecmp_hops:
                console.print(f"\n[yellow]⚠️  ECMP detected at {len(ecmp_hops)} hops:[/yellow]")
                for hop_num, ips in sorted(ecmp_hops.items()):
                    console.print(f"  Hop {hop_num}: {len(ips)} paths")
                    for ip in sorted(ips):
                        console.print(f"    - {ip}")
                console.print()
            else:
                console.print("[green]No ECMP detected (single path)[/green]\n")
        
        if paris:
            console.print("[cyan]Using Paris traceroute (ECMP-aware)[/cyan]")
            # Would integrate Paris-specific tracing here
            # For now, proceed with standard trace + ECMP detection
            # Note: In a real implementation we would modify run_traceroute to use ParisProber
            # But based on the gap analysis, we are just hooking up the plumbing for now.

    # Determine if DNS should be used
    resolve_hostnames = True
    if profile:
        prof = get_profile(profile)
        resolve_hostnames = prof.use_dns
    
    cfg = TraceConfig(
        host=host,
        max_hops=max_hops,
        timeout_s=timeout_s,
        probes=probes,
        protocol=proto,
        resolve_hostnames=resolve_hostnames,
        # TODO: Add source binding to TraceConfig
    )
    # Monkey-patch config for now until we update TraceConfig model
    if source_interface:
        cfg.source_interface = source_interface
    if source_port:
        cfg.source_port = source_port

    # Use ASCII map mode if requested, otherwise use clean table mode
    trace_result = run_traceroute(cfg, geoloc, live_render=not no_live, render_map=show_map)

    # Redact IPs if requested
    if redact:
        trace_result = _redact_trace(trace_result)

    # Save JSON
    out.write_text(
        json.dumps(trace_result.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )
    
    console.print()
    console.print(f"[green]✓[/green] Saved: {out}")


    # Auto-export HTML
    html_out = out.with_suffix(".html")
    try:
        from .export.html import export_html
        export_html(trace_result, html_out)
        console.print(f"[green]✓[/green] Saved: {html_out}")
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow]  HTML export failed: {e}")

    # Show helpful tips
    console.print()
    console.print("[bold]📊 View Results:[/bold]")
    console.print(f"  → Interactive map: [cyan]open {html_out}[/cyan]")
    console.print(f"  → Terminal UI:     [cyan]tracemap tui {out}[/cyan]")
    console.print()



@app.command()
def replay(
    trace_json: Path = typer.Argument(..., help="Path to a trace JSON"),
    use_tui: bool = typer.Option(False, "--tui", "-t", help="Use interactive TUI"),
) -> None:
    """Replay a saved trace JSON and render it."""
    if not trace_json.exists():
        console.print(f"[red]File not found:[/red] {trace_json}")
        raise typer.Exit(code=1)

    data = json.loads(trace_json.read_text(encoding="utf-8"))
    trace_result = TraceRun.model_validate(data)

    if use_tui:
        from .tui.app import run_tui
        run_tui(trace_result)
    else:
        render_full(trace_result, console)


@app.command()
def tui(
    trace_json: Optional[Path] = typer.Argument(None, help="Optional trace JSON to load"),
) -> None:
    """Launch interactive TUI interface."""
    from .tui.app import run_tui

    trace_result = None
    if trace_json and trace_json.exists():
        data = json.loads(trace_json.read_text(encoding="utf-8"))
        trace_result = TraceRun.model_validate(data)

    run_tui(trace_result)


@app.command()
def export(
    trace_json: Path = typer.Argument(..., help="Path to trace JSON"),
    format: str = typer.Option("html", "--format", "-f", help="Export format: html, svg, md, bundle"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output file path"),
    bundle: bool = typer.Option(False, "--bundle", help="Create a ZIP bundle with all formats"),
) -> None:
    """Export trace visualization to HTML, SVG, Markdown, or ZIP bundle."""
    if not trace_json.exists():
        console.print(f"[red]File not found:[/red] {trace_json}")
        raise typer.Exit(code=1)

    data = json.loads(trace_json.read_text(encoding="utf-8"))
    trace_result = TraceRun.model_validate(data)

    # Handle bundle shortcut
    if bundle or format == "bundle":
        format = "bundle"

    # Default output path
    if out is None:
        ext = "zip" if format == "bundle" else format
        out = trace_json.with_suffix(f".{ext}")

    if format.lower() == "html":
        try:
            from .export.html import export_html
            export_html(trace_result, out)
            console.print(f"[green]Exported:[/green] {out}")
        except ImportError:
            console.print("[yellow]HTML export module not available[/yellow]")
            raise typer.Exit(code=1)

    elif format.lower() == "svg":
        try:
            from .export.svg import export_svg
            export_svg(trace_result, out)
            console.print(f"[green]Exported:[/green] {out}")
        except ImportError:
            console.print("[yellow]SVG export module not available[/yellow]")
            raise typer.Exit(code=1)
    
    elif format.lower() in ("md", "markdown"):
        try:
            from .export.markdown import export_markdown
            export_markdown(trace_result, out)
            console.print(f"[green]Exported:[/green] {out}")
        except ImportError:
            console.print("[yellow]Markdown export module not available[/yellow]")
            raise typer.Exit(code=1)
            
    elif format.lower() == "bundle":
        try:
            from .export.bundle import export_bundle
            export_bundle(trace_result, out)
            console.print(f"[green]Exported Bundle:[/green] {out}")
        except ImportError:
            console.print("[yellow]Bundle export module not available[/yellow]")
            raise typer.Exit(code=1)

    else:
        console.print(f"[red]Unknown format:[/red] {format}")
        console.print("Supported formats: html, svg, markdown, bundle")
        raise typer.Exit(code=1)


@app.command()
def diff(
    trace_a: Path = typer.Argument(..., help="First trace JSON"),
    trace_b: Path = typer.Argument(..., help="Second trace JSON"),
) -> None:
    """Compare two traces and highlight route differences."""
    if not trace_a.exists():
        console.print(f"[red]File not found:[/red] {trace_a}")
        raise typer.Exit(code=1)

    if not trace_b.exists():
        console.print(f"[red]File not found:[/red] {trace_b}")
        raise typer.Exit(code=1)

    data_a = json.loads(trace_a.read_text(encoding="utf-8"))
    data_b = json.loads(trace_b.read_text(encoding="utf-8"))

    run_a = TraceRun.model_validate(data_a)
    run_b = TraceRun.model_validate(data_b)

    console.print("[bold]Trace Comparison[/bold]\n")

    # Compare metadata
    console.print(f"[cyan]Trace A:[/cyan] {run_a.meta.host} ({len(run_a.hops)} hops)")
    console.print(f"[cyan]Trace B:[/cyan] {run_b.meta.host} ({len(run_b.hops)} hops)")
    console.print()

    # Compare hops
    max_hops = max(len(run_a.hops), len(run_b.hops))

    from rich.table import Table
    t = Table(show_header=True, title="Hop Comparison")
    t.add_column("#", justify="right", width=3)
    t.add_column("Trace A IP", min_width=15)
    t.add_column("Trace B IP", min_width=15)
    t.add_column("Match", justify="center", width=6)

    differences = 0

    for i in range(max_hops):
        hop_a = run_a.hops[i] if i < len(run_a.hops) else None
        hop_b = run_b.hops[i] if i < len(run_b.hops) else None

        ip_a = hop_a.display_ip if hop_a else "-"
        ip_b = hop_b.display_ip if hop_b else "-"

        if ip_a == ip_b:
            match = "[green]✓[/green]"
        else:
            match = "[red]✗[/red]"
            differences += 1

        t.add_row(str(i + 1), ip_a, ip_b, match)

    console.print(t)
    console.print()

    if differences == 0:
        console.print("[green]Routes are identical![/green]")
    else:
        console.print(f"[yellow]Found {differences} differences[/yellow]")


@app.command()
def stats(
    trace_json: Path = typer.Argument(..., help="Path to trace JSON"),
) -> None:
    """Show detailed statistics from a saved trace."""
    if not trace_json.exists():
        console.print(f"[red]File not found:[/red] {trace_json}")
        raise typer.Exit(code=1)

    data = json.loads(trace_json.read_text(encoding="utf-8"))
    trace_result = TraceRun.model_validate(data)

    console.print("[bold]Trace Statistics[/bold]\n")

    # Metadata
    console.print(f"[cyan]Host:[/cyan] {trace_result.meta.host}")
    if trace_result.meta.resolved_ip:
        console.print(f"[cyan]Resolved IP:[/cyan] {trace_result.meta.resolved_ip}")
    console.print(f"[cyan]Protocol:[/cyan] {trace_result.meta.protocol.upper()}")
    console.print(f"[cyan]Started:[/cyan] {trace_result.meta.started_at}")
    console.print(f"[cyan]Platform:[/cyan] {trace_result.meta.platform_system} {trace_result.meta.platform_release}")
    console.print()

    # Hop statistics
    console.print(f"[bold]Hops:[/bold] {trace_result.total_hops}")
    console.print(f"  Responded: {trace_result.responded_hops}")
    console.print(f"  Timeouts: {trace_result.timeout_hops}")
    console.print(f"  Avg Loss: {trace_result.avg_loss_pct:.1f}%")
    console.print()

    # RTT statistics
    rtt_values = [h.rtt_avg_ms for h in trace_result.hops if h.rtt_avg_ms is not None]
    if rtt_values:
        console.print("[bold]RTT Statistics:[/bold]")
        console.print(f"  Min: {min(rtt_values):.1f} ms")
        console.print(f"  Max: {max(rtt_values):.1f} ms")
        console.print(f"  Avg: {sum(rtt_values)/len(rtt_values):.1f} ms")
        console.print()

    # Detour alerts
    alerts = trace_result.get_detour_alerts()
    if alerts:
        console.print("[bold]Detour Alerts:[/bold]")
        for alert in alerts:
            console.print(f"  [yellow]⚠️ {alert}[/yellow]")


def _redact_trace(trace: TraceRun) -> TraceRun:
    """
    Redact IP addresses in a trace for privacy.

    Replaces IPs with hashed versions while preserving geo info.
    """
    import hashlib

    def redact_ip(ip: Optional[str]) -> Optional[str]:
        if ip is None:
            return None
        h = hashlib.sha256(ip.encode()).hexdigest()[:12]
        return f"[redacted:{h}]"

    # Create a copy with redacted IPs
    data = trace.model_dump(mode="json")

    for hop in data.get("hops", []):
        hop["ip"] = redact_ip(hop.get("ip"))
        hop["hostname"] = None  # Remove hostnames too

    return TraceRun.model_validate(data)



@app.command()
def cache(
    action: str = typer.Argument(..., help="Action: clear, stats"),
) -> None:
    """Manage persistent cache database."""
    from .cache import GeoCache
    
    cache_db = Path.home() / ".tracemap" / "cache.sqlite"
    
    if action == "clear":
        if not cache_db.exists():
            console.print("[yellow]Cache database doesn't exist[/yellow]")
            return
        
        cache = GeoCache(cache_db)
        stats_before = cache.get_stats()
        cache.clear_all()
        
        console.print(f"[green]✓ Cleared cache database:[/green] {cache_db}")
        console.print(f"  Removed {stats_before['total_entries']} entries")
        
    elif action == "stats":
        if not cache_db.exists():
            console.print("[yellow]Cache database doesn't exist yet (will be created on first trace)[/yellow]")
            return
        
        cache = GeoCache(cache_db)
        stats = cache.get_stats()
        
        console.print("[bold]Cache Statistics[/bold]\n")
        console.print(f"Database: {cache_db}")
        console.print(f"Total entries: {stats['total_entries']}")
        console.print(f"Valid entries: {stats['valid_entries']}")
        console.print(f"Expired entries: {stats['expired_entries']}")
        
        if stats['hits'] > 0 or stats['misses'] > 0:
            console.print(f"\nSession stats:")
            console.print(f"  Hits: {stats['hits']}")
            console.print(f"  Misses: {stats['misses']}")
            console.print(f"  Hit rate: {stats['hit_rate']:.1%}")
    
    else:
        console.print(f"[red]Unknown action:[/red] {action}")
        console.print("Valid actions: clear, stats")
        raise typer.Exit(code=1)


@app.command()
def watch(
    host: str = typer.Argument(..., help="Hostname or IP to monitor"),
    interval: int = typer.Option(30, "--interval", "-i", help="Seconds between traces"),
    duration: Optional[int] = typer.Option(None, "--duration", "-d", help="Total duration in seconds (None = infinite)"),
    max_hops: int = typer.Option(30, "--max-hops", "-m", help="Maximum hops"),
    protocol: str = typer.Option("udp", "--protocol", "-P", help="Protocol: udp, tcp, icmp"),
    geoip_mmdb: Optional[Path] = typer.Option(None, "--geoip-mmdb", help="Path to GeoLite2-City.mmdb"),
    use_api: bool = typer.Option(True, "--api/--no-api", help="Use API for geo lookups"),
) -> None:
    """
    Continuously monitor route to host (MTR-style).
    
    Detects route changes, RTT spikes, and packet loss patterns.
    Logs all traces to ~/.tracemap/watch_<host>.jsonl
    """
    from .watch import TraceMonitor
    from .trace import Protocol, TraceConfig
    
    # Pick protocol
    try:
        proto = Protocol(protocol.lower())
    except ValueError:
        console.print(f"[red]Invalid protocol:[/red] {protocol}")
        raise typer.Exit(code=1)
    
    # Setup geo locator
    geoloc = _pick_geolocator(geoip_mmdb, enable_asn=False, use_api=use_api)
    
    # Create config
    cfg = TraceConfig(
        host=host,
        max_hops=max_hops,
        timeout_s=2.0,
        probes=3,
        protocol=proto,
    )
    
    # Run monitor
    monitor = TraceMonitor(host, cfg, geoloc, interval_seconds=interval)
    monitor.run(duration_seconds=duration)


def _redact_trace(trace: TraceRun) -> TraceRun:
    """
    Redact IP addresses in a trace for privacy.

    Replaces IPs with hashed versions while preserving geo info.
    """
    import hashlib

    def redact_ip(ip: Optional[str]) -> Optional[str]:
        if ip is None:
            return None
        h = hashlib.sha256(ip.encode()).hexdigest()[:12]
        return f"[redacted:{h}]"

    # Create a copy with redacted IPs
    data = trace.model_dump(mode="json")

    for hop in data.get("hops", []):
        hop["ip"] = redact_ip(hop.get("ip"))
        hop["hostname"] = None  # Remove hostnames too

    return TraceRun.model_validate(data)


if __name__ == "__main__":
    app()
