"""
Test data models.

Author: gadwant
"""
import math

import pytest

from tracemap.models import Hop, HopGeo, HopProbe, TraceRun, TraceMeta, _haversine_km


class TestHopGeo:
    """Test HopGeo model."""

    def test_create_basic_geo(self):
        """Test creating basic geo location."""
        geo = HopGeo(lat=37.4, lon=-122.1)

        assert geo.lat == 37.4
        assert geo.lon == -122.1
        assert geo.city is None
        assert geo.asn is None

    def test_create_full_geo(self):
        """Test creating full geo with all fields."""
        geo = HopGeo(
            lat=37.4,
            lon=-122.1,
            city="Mountain View",
            country="United States",
            country_code="US",
            asn=15169,
            asn_org="GOOGLE",
        )

        assert geo.city == "Mountain View"
        assert geo.country_code == "US"
        assert geo.asn == 15169


class TestHaversineDistance:
    """Test great-circle distance calculation."""

    def test_same_location(self):
        """Test distance between same location is zero."""
        dist = _haversine_km(37.4, -122.1, 37.4, -122.1)
        assert dist == pytest.approx(0, abs=0.1)

    def test_known_distance(self):
        """Test distance between known cities."""
        # NYC to LA is approximately 3944 km
        nyc_lat, nyc_lon = 40.7128, -74.0060
        la_lat, la_lon = 34.0522, -118.2437

        dist = _haversine_km(nyc_lat, nyc_lon, la_lat, la_lon)
        assert 3900 < dist < 4000

    def test_antipodes(self):
        """Test distance between opposite sides of Earth."""
        # Approximately half Earth's circumference (~20,000 km)
        dist = _haversine_km(0, 0, 0, 180)
        assert 19000 < dist < 21000


class TestTraceRunDetourAlerts:
    """Test detour alert detection."""

    def test_no_alerts_short_hops(self):
        """Test no alerts for short-distance hops."""
        from tracemap.models import Hop, HopGeo, TraceRun, TraceMeta

        trace = TraceRun(
            meta=TraceMeta(host="example.com", max_hops=5, probes=3, timeout_s=2.0),
            hops=[
                Hop(
                    hop=1,
                    ip="10.0.0.1",
                    geo=HopGeo(lat=37.7749, lon=-122.4194),  # SF
                ),
                Hop(
                    hop=2,
                    ip="10.0.0.2",
                    geo=HopGeo(lat=37.8, lon=-122.3),  # Near SF
                ),
            ],
        )

        alerts = trace.get_detour_alerts(distance_threshold_km=5000)
        assert len(alerts) == 0

    def test_detour_alert_continent_jump(self):
        """Test alert for continent-crossing hop."""
        from tracemap.models import Hop, HopGeo, TraceRun, TraceMeta

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

        alerts = trace.get_detour_alerts(distance_threshold_km=5000)
        assert len(alerts) > 0
        assert "5" in alerts[0]  # Should mention the hop numbers


class TestTraceRunProperties:
    """Test TraceRun computed properties."""

    def test_total_hops(self):
        """Test total hops count."""
        from tracemap.models import Hop, TraceRun, TraceMeta

        trace = TraceRun(
            meta=TraceMeta(host="example.com", max_hops=5, probes=3, timeout_s=2.0),
            hops=[Hop(hop=i, ip=f"10.0.0.{i}") for i in range(1, 6)],
        )

        assert trace.total_hops == 5

    def test_timeout_hops(self):
        """Test counting timeout hops."""
        from tracemap.models import Hop, TraceRun, TraceMeta

        trace = TraceRun(
            meta=TraceMeta(host="example.com", max_hops=5, probes=3, timeout_s=2.0),
            hops=[
                Hop(hop=1, ip="10.0.0.1", is_timeout=False),
                Hop(hop=2, ip=None, is_timeout=True),
                Hop(hop=3, ip="10.0.0.3", is_timeout=False),
                Hop(hop=4, ip=None, is_timeout=True),
            ],
        )

        assert trace.timeout_hops == 2
        assert trace.responded_hops == 2
