import pytest
import time
from unittest.mock import MagicMock, patch
from tracemap.watch.monitor import HopStats, TraceMonitor
from tracemap.models import Hop, HopProbe, TraceRun, TraceMeta

class TestHopStats:
    def test_stats_calculation(self):
        stats = HopStats(max_samples=100)
        
        # Add some samples
        h1 = Hop(hop=1, probes=[HopProbe(rtt_ms=10, ok=True)], rtt_avg_ms=10.0, ip="1.1.1.1")
        h2 = Hop(hop=1, probes=[HopProbe(rtt_ms=30, ok=True)], rtt_avg_ms=30.0, ip="1.1.1.1")
        h_timeout = Hop(hop=1, probes=[], is_timeout=True)
        
        stats.add_sample(h1)
        stats.add_sample(h2)
        stats.add_sample(h_timeout)
        
        # Verify RTT avg (only successful probes)
        # (10 + 30) / 2 = 20
        assert stats.avg_rtt == 20.0
        
        # Verify Loss pct
        # 1 timeout out of 3 total = 33.3%
        assert abs(stats.loss_pct - 33.33) < 0.1
        
        # Verify IP tracking
        assert stats.current_ip == "1.1.1.1"
        assert len(stats.ip_history) == 0

    def test_ip_change_detection(self):
        stats = HopStats()
        
        h1 = Hop(hop=1, ip="1.1.1.1")
        h2 = Hop(hop=1, ip="2.2.2.2")
        
        stats.add_sample(h1)
        assert stats.current_ip == "1.1.1.1"
        
        stats.add_sample(h2)
        assert stats.current_ip == "2.2.2.2"
        assert stats.ip_history == ["1.1.1.1"]


class TestTraceMonitor:
    @patch("tracemap.watch.monitor.run_traceroute")
    def test_monitor_loop(self, mock_run_trace, tmp_path):
        # Setup
        log_file = tmp_path / "watch.jsonl"
        config = MagicMock()
        geoloc = MagicMock()
        
        monitor = TraceMonitor("example.com", config, geoloc, interval_seconds=0.1, log_path=log_file)
        
        # Mock trace result
        mock_trace = TraceRun(
            meta=TraceMeta(
                host="example.com", 
                max_hops=30,
                probes=3,
                timeout_s=2.0,
                started_at="2023-01-01T00:00:00"
            ),
            hops=[
                Hop(hop=1, ip="1.1.1.1", rtt_avg_ms=10.0),
                Hop(hop=2, ip="2.2.2.2", rtt_avg_ms=20.0)
            ]
        )
        mock_run_trace.return_value = mock_trace
        
        # Run for short duration (enough for 2 iterations hopefully)
        monitor.run(duration_seconds=0.25)
        
        # Verify
        assert monitor.trace_count >= 1
        assert 1 in monitor.hop_stats
        assert 2 in monitor.hop_stats
        
        # Check log file
        assert log_file.exists()
        lines = log_file.read_text().strip().split('\n')
        assert len(lines) >= 1
        assert "example.com" in lines[0]
