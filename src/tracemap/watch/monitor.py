"""
Continuous trace monitoring with anomaly detection.

Runs traceroute at regular intervals, maintains rolling statistics,
and detects route changes, RTT spikes, and loss patterns.

Author: gadwant
"""

import json
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from rich.table import Table

from ..geo import GeoLocator
from ..models import Hop, TraceRun
from ..trace import TraceConfig, run_traceroute


class HopStats:
    """Rolling statistics for a single hop."""

    def __init__(self, max_samples: int = 100):
        self.max_samples = max_samples
        self.rtt_samples: deque[float] = deque(maxlen=max_samples)
        self.loss_count = 0
        self.total_probes = 0
        self.current_ip: Optional[str] = None
        self.ip_history: list[str] = []

    def add_sample(self, hop: Hop):
        """Add a new hop sample to statistics."""
        self.total_probes += 1

        if hop.is_timeout:
            self.loss_count += 1
        elif hop.rtt_avg_ms is not None:
            self.rtt_samples.append(hop.rtt_avg_ms)

        # Track IP changes
        if hop.ip and hop.ip != self.current_ip:
            if self.current_ip:
                self.ip_history.append(self.current_ip)
            self.current_ip = hop.ip

    @property
    def avg_rtt(self) -> Optional[float]:
        """Average RTT across samples."""
        return sum(self.rtt_samples) / len(self.rtt_samples) if self.rtt_samples else None

    @property
    def loss_pct(self) -> float:
        """Packet loss percentage."""
        return (self.loss_count / self.total_probes * 100) if self.total_probes > 0 else 0.0


class TraceMonitor:
    """
    Continuous trace monitor with anomaly detection.

    Similar to MTR but with enhanced features:
    - Route change detection
    - RTT spike alerts
    - Loss pattern detection
    - ASN change tracking
    """

    def __init__(
        self,
        host: str,
        config: TraceConfig,
        geolocator: GeoLocator,
        interval_seconds: int = 30,
        log_path: Optional[Path] = None,
    ):
        """
        Initialize trace monitor.

        Args:
            host: Target host to monitor
            config: Trace configuration
            geolocator: Geo locator
            interval_seconds: Seconds between traces
            log_path: Optional JSONL log file path
        """
        self.host = host
        self.config = config
        self.geolocator = geolocator
        self.interval = interval_seconds
        self.log_path = log_path or Path.home() / ".tracemap" / f"watch_{host}.jsonl"

        # Statistics per hop number
        self.hop_stats: dict[int, HopStats] = defaultdict(HopStats)

        # Trace history
        self.trace_count = 0
        self.last_trace: Optional[TraceRun] = None

        # Create log directory
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def run(self, duration_seconds: Optional[int] = None, alerts: Optional[dict] = None):
        """
        Run continuous monitoring.

        Args:
            duration_seconds: Total duration (None = infinite)
            alerts: Alert thresholds dict
        """
        from rich.console import Console

        from .alerts import AnomalyDetector

        console = Console()
        detector = AnomalyDetector(alerts or {})

        start_time = time.time()

        console.print(f"[bold]Monitoring {self.host}[/bold]")
        console.print(f"Interval: {self.interval}s, Log: {self.log_path}")
        console.print()

        try:
            while True:
                # Check duration limit
                if duration_seconds and (time.time() - start_time) > duration_seconds:
                    break

                # Run trace
                trace = run_traceroute(
                    self.config,
                    self.geolocator,
                    live_render=False,
                    render_map=False,
                )

                self.trace_count += 1

                # Update statistics
                for hop in trace.hops:
                    self.hop_stats[hop.hop].add_sample(hop)

                # Detect anomalies
                if self.last_trace:
                    anomalies = detector.detect(self.last_trace, trace, self.hop_stats)
                    for anomaly in anomalies:
                        console.print(f"[yellow]⚠️  {anomaly}[/yellow]")

                self.last_trace = trace

                # Log to file
                self._log_trace(trace)

                # Display current state
                table = self._build_table()
                console.clear()
                console.print(f"[bold]Monitoring {self.host}[/bold] - Sample #{self.trace_count}")
                console.print(table)
                console.print(f"\n[dim]Next update in {self.interval}s | Ctrl+C to stop[/dim]")

                # Wait for next interval
                time.sleep(self.interval)

        except KeyboardInterrupt:
            console.print("\n[yellow]Monitoring stopped by user[/yellow]")
            console.print(f"Total samples: {self.trace_count}")
            console.print(f"Log saved: {self.log_path}")

    def _build_table(self) -> "Table":
        """Build statistics table."""
        from rich.table import Table

        t = Table(show_header=True, title=f"Statistics ({self.trace_count} samples)")
        t.add_column("#", justify="right", width=3)
        t.add_column("IP", min_width=15)
        t.add_column("Avg RTT", justify="right")
        t.add_column("Loss", justify="right")
        t.add_column("Samples", justify="right")
        t.add_column("Alerts", min_width=15)

        for hop_num in sorted(self.hop_stats.keys()):
            stats = self.hop_stats[hop_num]

            ip_str = stats.current_ip or "*"
            avg_rtt = f"{stats.avg_rtt:.1f}ms" if stats.avg_rtt else "-"
            loss = f"{stats.loss_pct:.0f}%"
            samples = str(len(stats.rtt_samples))

            # Build alerts column
            alerts = []
            if stats.loss_pct > 5.0:
                alerts.append("⚠️ LOSS")
            if len(stats.ip_history) > 0:
                alerts.append("🔴 IP CHANGED")
            alert_str = " ".join(alerts)

            # Color by loss
            if stats.loss_pct > 10:
                loss = f"[red]{loss}[/red]"
            elif stats.loss_pct > 5:
                loss = f"[yellow]{loss}[/yellow]"

            t.add_row(str(hop_num), ip_str, avg_rtt, loss, samples, alert_str)

        return t

    def _log_trace(self, trace: TraceRun):
        """Append trace to JSONL log."""
        with open(self.log_path, "a") as f:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "trace": trace.model_dump(mode="json"),
            }
            f.write(json.dumps(entry, default=str) + "\n")
