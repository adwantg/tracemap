"""
Test suite for confidence scoring and analysis.

Tests geo confidence scoring and plausibility checks.

Author: gadwant
"""
import pytest

from tracemap.analysis import ConfidenceScorer
from tracemap.models import Hop, HopGeo, HopProbe


class TestConfidenceScorer:
    """Test confidence scoring."""
    
    def test_high_confidence_public_ip_with_asn(self):
        """Test high confidence for public IP with ASN from API."""
        scorer = ConfidenceScorer()
        
        hop = Hop(
            hop=1,
            ip="8.8.8.8",
            is_private=False,
            hostname="dns.google",
            geo=HopGeo(
                lat=37.4,
                lon=-122.1,
                city="Mountain View",
                asn=15169,
                asn_org="Google LLC"
            )
        )
        
        confidence = scorer.score_hop(hop, metadata={"source": "ip-api"})
        assert confidence == "high"
    
    def test_medium_confidence_private_ip(self):
        """Test medium confidence for private IP."""
        scorer = ConfidenceScorer()
        
        hop = Hop(
            hop=1,
            ip="192.168.1.1",
            is_private=True,
            geo=HopGeo(lat=37.4, lon=-122.1)
        )
        
        confidence = scorer.score_hop(hop, metadata={"source": "mmdb"})
        assert confidence in ("medium", "low")
    
    def test_low_confidence_mock_data(self):
        """Test low confidence for mock data."""
        scorer = ConfidenceScorer()
        
        hop = Hop(
            hop=1,
            ip="8.8.8.8",
            is_private=False,
            geo=HopGeo(lat=37.4, lon=-122.1)
        )
        
        confidence = scorer.score_hop(hop, metadata={"source": "mock"})
        assert confidence == "low"
    
    def test_no_geo_data(self):
        """Test hop without geo data."""
        scorer = ConfidenceScorer()
        
        hop = Hop(hop=1, ip="*", is_timeout=True)
        
        confidence = scorer.score_hop(hop)
        assert confidence == "low"
    
    def test_ocean_crossing_detection(self):
        """Test ocean crossing detection."""
        scorer = ConfidenceScorer()
        
        hop1 = Hop(
            hop=1,
            ip="1.1.1.1",
            geo=HopGeo(lat=37.7749, lon=-122.4194, country_code="US")  # SF
        )
        hop2 = Hop(
            hop=2,
            ip="2.2.2.2",
            geo=HopGeo(lat=35.6762, lon=139.6503, country_code="JP")  # Tokyo
        )
        
        is_ocean = scorer.check_ocean_crossing(hop1, hop2)
        assert is_ocean is True
    
    def test_speed_of_light_bound_valid(self):
        """Test speed of light validation for valid hop."""
        scorer = ConfidenceScorer()
        
        hop1 = Hop(
            hop=1,
            ip="1.1.1.1",
            probes=[HopProbe(rtt_ms=10.0, ok=True)],
            geo=HopGeo(lat=37.7749, lon=-122.4194)  # SF
        )
        hop2 = Hop(
            hop=2,
            ip="2.2.2.2",
            probes=[HopProbe(rtt_ms=15.0, ok=True)],
            geo=HopGeo(lat=37.3382, lon=-121.8863)  # San Jose (~70km)
        )
        
        is_plausible, error = scorer.check_speed_of_light_bound(hop1, hop2)
        assert is_plausible is True
        assert error is None
    
    def test_speed_of_light_bound_violation(self):
        """Test speed of light violation detection (anycast/VPN)."""
        scorer = ConfidenceScorer()
        
        hop1 = Hop(
            hop=1,
            ip="1.1.1.1",
            probes=[HopProbe(rtt_ms=10.0, ok=True)],
            geo=HopGeo(lat=37.7749, lon=-122.4194)  # SF
        )
        hop2 = Hop(
            hop=2,
            ip="2.2.2.2",
            probes=[HopProbe(rtt_ms=10.1, ok=True)],
            geo=HopGeo(lat=35.6762, lon=139.6503)  # Tokyo (9000km away)
        )
        
        is_plausible, error = scorer.check_speed_of_light_bound(hop1, hop2)
        assert is_plausible is False
        assert "Geo data may be incorrect" in error
