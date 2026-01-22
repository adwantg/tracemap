"""
Test rendering functionality.

Author: gadwant
"""
import pytest

from tracemap.models import Hop, HopGeo, HopProbe, TraceRun, TraceMeta
from tracemap.render import (
    MapConfig,
    _project,
    _bresenham,
    render_static,
    get_rtt_level,
    RTTLevel,
)


class TestProjection:
    """Test coordinate projection."""

    def test_project_center(self):
        """Test projecting center of map."""
        cfg = MapConfig(width=120, height=32)
        x, y = _project(0, 0, cfg)

        # Center should be roughly in middle of map
        assert 50 < x < 70
        assert 10 < y < 22

    def test_project_bounds(self):
        """Test projection stays within bounds."""
        cfg = MapConfig(width=120, height=32)

        # Test corners
        x, y = _project(-70, -180, cfg)
        assert 0 <= x < cfg.width
        assert 0 <= y < cfg.height

        x, y = _project(70, 180, cfg)
        assert 0 <= x < cfg.width
        assert 0 <= y < cfg.height


class TestBresenhamLine:
    """Test line drawing algorithm."""

    def test_horizontal_line(self):
        """Test drawing horizontal line."""
        points = _bresenham((0, 0), (5, 0))

        assert len(points) == 6  # 0,1,2,3,4,5
        assert points[0] == (0, 0)
        assert points[-1] == (5, 0)
        # All points should have y=0
        assert all(y == 0 for x, y in points)

    def test_vertical_line(self):
        """Test drawing vertical line."""
        points = _bresenham((0, 0), (0, 5))

        assert len(points) == 6
        # All points should have x=0
        assert all(x == 0 for x, y in points)

    def test_diagonal_line(self):
        """Test drawing diagonal line."""
        points = _bresenham((0, 0), (3, 3))

        assert len(points) == 4
        assert points[0] == (0, 0)
        assert points[-1] == (3, 3)


class TestRTTLevel:
    """Test RTT level classification for coloring."""

    def test_low_rtt(self):
        """Test low RTT classification."""
        assert get_rtt_level(10.0) == RTTLevel.LOW
        assert get_rtt_level(49.9) == RTTLevel.LOW

    def test_med_rtt(self):
        """Test medium RTT classification."""
        assert get_rtt_level(50.0) == RTTLevel.MED
        assert get_rtt_level(100.0) == RTTLevel.MED
        assert get_rtt_level(149.9) == RTTLevel.MED

    def test_high_rtt(self):
        """Test high RTT classification."""
        assert get_rtt_level(150.0) == RTTLevel.HIGH
        assert get_rtt_level(500.0) == RTTLevel.HIGH

    def test_timeout(self):
        """Test timeout classification."""
        assert get_rtt_level(None) == RTTLevel.TIMEOUT


class TestStaticRender:
    """Test static map rendering."""

    def test_render_empty_trace(self):
        """Test rendering trace with no hops."""
        trace = TraceRun(
            meta=TraceMeta(host="example.com", max_hops=5, probes=3, timeout_s=2.0),
            hops=[],
        )

        output = render_static(trace)

        assert "example.com" in output
        assert "hops=0" in output

    def test_render_with_hops(self):
        """Test rendering trace with hops."""
        trace = TraceRun(
            meta=TraceMeta(host="example.com", max_hops=5, probes=3, timeout_s=2.0),
            hops=[
                Hop(
                    hop=1,
                    ip="10.0.0.1",
                    probes=[HopProbe(rtt_ms=10.0, ok=True)],
                    geo=HopGeo(lat=37.7749, lon=-122.4194, city="San Francisco"),
                ),
                Hop(
                    hop=2,
                    ip="10.0.0.2",
                    probes=[HopProbe(rtt_ms=50.0, ok=True)],
                    geo=HopGeo(lat=40.7128, lon=-74.0060, city="New York"),
                ),
            ],
        )

        output = render_static(trace)

        assert "example.com" in output
        assert "hops=2" in output
        assert "responded=2" in output
        # Map should contain hop markers
        assert "1" in output or "2" in output

    def test_render_with_detour_alert(self):
        """Test rendering includes detour alerts."""
        trace = TraceRun(
            meta=TraceMeta(host="example.com", max_hops=5, probes=3, timeout_s=2.0),
            hops=[
                Hop(
                    hop=1,
                    ip="10.0.0.1",
                    geo=HopGeo(lat=40.7128, lon=-74.0060),  # NYC
                ),
                Hop(
                    hop=2,
                    ip="10.0.0.2",
                    geo=HopGeo(lat=51.5074, lon=-0.1278),  # London
                ),
            ],
        )

        output = render_static(trace)

        # Should contain alert about detour
        assert "⚠️" in output or "Detour" in output
