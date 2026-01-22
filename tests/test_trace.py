"""
Test traceroute parsing functionality.

Author: gadwant
"""
import pytest

from tracemap.trace import _parse_hop_line, Protocol
from tracemap.models import Hop


class TestHopLineParsing:
    """Test parsing of traceroute output lines."""

    def test_parse_simple_hop_ipv4(self):
        """Test parsing a simple hop with IPv4."""
        line = " 1  8.8.8.8  10.1 ms  11.2 ms  9.9 ms"
        hop = _parse_hop_line(line, probes=3)

        assert hop is not None
        assert hop.hop == 1
        assert hop.ip == "8.8.8.8"
        assert hop.hostname is None
        assert len(hop.probes) == 3
        assert all(p.ok for p in hop.probes)
        assert hop.probes[0].rtt_ms == 10.1
        assert hop.probes[1].rtt_ms == 11.2
        assert hop.probes[2].rtt_ms == 9.9

    def test_parse_hop_with_hostname(self):
        """Test parsing hop with hostname and IP."""
        line = " 5  router.example.com (10.0.0.1)  5.2 ms  5.1 ms  5.0 ms"
        hop = _parse_hop_line(line, probes=3)

        assert hop is not None
        assert hop.hop == 5
        assert hop.ip == "10.0.0.1"
        assert hop.hostname == "router.example.com"
        assert len(hop.probes) == 3

    def test_parse_hop_all_timeouts(self):
        """Test parsing hop with all timeouts."""
        line = " 3  * * *"
        hop = _parse_hop_line(line, probes=3)

        assert hop is not None
        assert hop.hop == 3
        assert hop.ip is None
        assert hop.is_timeout is True
        assert hop.loss_pct == 100.0
        assert all(not p.ok for p in hop.probes)

    def test_parse_hop_mixed_results(self):
        """Test parsing hop with mixed success/timeout."""
        line = " 4  8.8.8.8  20.1 ms  *  19.9 ms"
        hop = _parse_hop_line(line, probes=3)

        assert hop is not None
        assert hop.hop == 4
        assert hop.ip == "8.8.8.8"
        assert hop.probes[0].ok is True
        assert hop.probes[1].ok is False
        assert hop.probes[2].ok is True
        assert 33.0 < hop.loss_pct < 34.0  # One timeout out of three

    def test_parse_hop_ipv6(self):
        """Test parsing hop with IPv6 address."""
        line = " 2  2001:4860:4860::8888  15.3 ms  14.2 ms  15.1 ms"
        hop = _parse_hop_line(line, probes=3)

        assert hop is not None
        assert hop.hop == 2
        assert hop.ip == "2001:4860:4860::8888"
        assert len(hop.probes) == 3

    def test_parse_invalid_line(self):
        """Test parsing invalid line returns None."""
        line = "not a valid hop line"
        hop = _parse_hop_line(line, probes=3)

        assert hop is None

    def test_parse_header_line(self):
        """Test that header lines are skipped."""
        line = "traceroute to example.com (93.184.216.34), 30 hops max"
        hop = _parse_hop_line(line, probes=3)

        assert hop is None


class TestHopProperties:
    """Test computed properties of Hop model."""

    def test_rtt_avg(self):
        """Test RTT average calculation."""
        from tracemap.models import HopProbe

        hop = Hop(
            hop=1,
            ip="8.8.8.8",
            probes=[
                HopProbe(rtt_ms=10.0, ok=True),
                HopProbe(rtt_ms=12.0, ok=True),
                HopProbe(rtt_ms=11.0, ok=True),
            ],
        )

        assert hop.rtt_avg_ms == 11.0

    def test_rtt_min_max(self):
        """Test RTT min/max calculation."""
        from tracemap.models import HopProbe

        hop = Hop(
            hop=1,
            ip="8.8.8.8",
            probes=[
                HopProbe(rtt_ms=10.0, ok=True),
                HopProbe(rtt_ms=15.0, ok=True),
                HopProbe(rtt_ms=12.0, ok=True),
            ],
        )

        assert hop.rtt_min_ms == 10.0
        assert hop.rtt_max_ms == 15.0

    def test_jitter(self):
        """Test jitter (std dev) calculation."""
        from tracemap.models import HopProbe

        hop = Hop(
            hop=1,
            ip="8.8.8.8",
            probes=[
                HopProbe(rtt_ms=10.0, ok=True),
                HopProbe(rtt_ms=12.0, ok=True),
                HopProbe(rtt_ms=14.0, ok=True),
            ],
        )

        # Should have some jitter
        assert hop.jitter_ms is not None
        assert hop.jitter_ms > 0

    def test_loss_percentage(self):
        """Test packet loss percentage calculation."""
        from tracemap.models import HopProbe

        hop = Hop(
            hop=1,
            ip="8.8.8.8",
            probes=[
                HopProbe(rtt_ms=10.0, ok=True),
                HopProbe(rtt_ms=None, ok=False),
                HopProbe(rtt_ms=11.0, ok=True),
            ],
        )

        assert 33.0 < hop.loss_pct < 34.0  # 1 out of 3
